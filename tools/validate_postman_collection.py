#!/usr/bin/env python3
"""Validates the generated Postman collection against the OpenAPI specification.

Checks, for every request in the collection:

  1. The method and path resolve to a real operation in hubwise-v2.yaml.
  2. The JSON request body validates against that operation's request schema.
     Because the schemas set additionalProperties: false, this catches unknown
     fields, misspellings and invalid enum values.
  3. The body sends no readOnly fields.
  4. Every {{variable}} the collection uses is declared somewhere.

Postman placeholders are substituted with representative values first, so that
pattern and length constraints are exercised rather than skipped.

    python tools/validate_postman_collection.py
"""

import json
import os
import re
import sys

import yaml
from jsonschema import Draft202012Validator

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SPEC = os.path.join(ROOT, "hubwise-v2.yaml")
COLLECTION = os.path.join(ROOT, "SSC-Wealth-API-Journeys.postman_collection.json")
ENVIRONMENT = os.path.join(ROOT, "SSC-Wealth-API.postman_environment.json")

# Representative stand-ins for placeholders that are empty at rest, so that
# format and pattern constraints are genuinely tested.
SUBSTITUTES = {
    "adviserId": "E001428",
    "modelId": "HW000000090",
    "modelProviderId": "HUBWISE",
    "modelDate": "2020-04-28",
    "cedingProviderId": "HW009",
    "adviserAnnualFeeCode": "AFGVCD",
    "transferPlanReference": "GIA-4471982",
    "retailInvestorId": "HWI04003371",
    "jointInvestorId": "HWI04003372",
    "childInvestorId": "HWI04003373",
    "corporateInvestorId": "HWI04003374",
    "quickStartInvestorId": "HWI04003375",
    "quickStartAccountId": "HW04003258A",
    "giaAccountId": "HW04003258A",
    "jointGiaAccountId": "HW04003259A",
    "isaAccountId": "HW04003260A",
    "jisaAccountId": "HW04003261A",
    "sippAccountId": "HW04003262A",
    "corporateGiaAccountId": "HW04003263A",
    "employerThirdPartyId": "1",
    "beneficiaryThirdPartyId": "2",
    "today": "2026-08-25",
    "nextMonthFirst": "2026-09-01",
    "oneYearAhead": "2027-08-25",
    "taxYearStart": "2026-04-06",
    "childDateOfBirth": "2016-08-25",
    "$guid": "d8d3a6b1-f1e5-4b0a-8d2c-0a3f5b7e9d1c",
}

PLACEHOLDER = re.compile(r"\{\{([^}]+)\}\}")


def load_spec():
    """Loads the spec, working around literal tabs in its description text.

    Several descriptions contain tab characters inside plain (unquoted) multi-line
    scalars, which strict YAML parsers reject outright. They are replaced with
    spaces here so validation can proceed, and reported so they can be fixed.
    """
    with open(SPEC, encoding="utf-8") as handle:
        text = handle.read()

    tabbed = [n for n, line in enumerate(text.split("\n"), 1) if "\t" in line]
    if tabbed:
        print(f"warning: {os.path.basename(SPEC)} contains literal tab characters on "
              f"{len(tabbed)} line(s): {', '.join(str(n) for n in tabbed)}")
        print("         Strict YAML parsers reject these. Replaced with spaces for validation.")

    return yaml.safe_load(text.replace("\t", " "))


def normalise(schema):
    """Translates OpenAPI 3.0 keyword dialects into JSON Schema 2020-12.

    In OpenAPI 3.0 exclusiveMinimum/exclusiveMaximum are booleans modifying
    minimum/maximum; in 2020-12 they are numeric bounds in their own right.
    """
    for bound, exclusive in (("maximum", "exclusiveMaximum"), ("minimum", "exclusiveMinimum")):
        if isinstance(schema.get(exclusive), bool):
            if schema[exclusive] and bound in schema:
                schema[exclusive] = schema.pop(bound)
            else:
                schema.pop(exclusive)
    return schema


def resolve(spec, node, seen=None):
    """Inlines $ref pointers into components so jsonschema can validate offline."""
    if isinstance(node, dict):
        if "$ref" in node:
            pointer = node["$ref"]
            if not pointer.startswith("#/"):
                raise ValueError(f"external ref not supported: {pointer}")
            seen = seen or set()
            if pointer in seen:          # recursive schema - leave it open
                return {}
            target = spec
            for part in pointer[2:].split("/"):
                target = target[part]
            return resolve(spec, target, seen | {pointer})
        return normalise({k: resolve(spec, v, seen) for k, v in node.items()})
    if isinstance(node, list):
        return [resolve(spec, item, seen) for item in node]
    return node


def substitute(value, variables, used):
    """Replaces {{placeholders}} in every string in a JSON structure."""
    if isinstance(value, str):
        def swap(match):
            name = match.group(1)
            used.add(name)
            if variables.get(name):
                return variables[name]
            if name in SUBSTITUTES:
                return SUBSTITUTES[name]
            return "PLACEHOLDER"
        return PLACEHOLDER.sub(swap, value)
    if isinstance(value, dict):
        return {k: substitute(v, variables, used) for k, v in value.items()}
    if isinstance(value, list):
        return [substitute(v, variables, used) for v in value]
    return value


def read_only_paths(schema, prefix=""):
    """Collects the dotted paths of every readOnly field in a resolved schema."""
    found = []
    if not isinstance(schema, dict):
        return found
    for key in ("allOf", "anyOf", "oneOf"):
        for sub in schema.get(key, []):
            found += read_only_paths(sub, prefix)
    for name, prop in (schema.get("properties") or {}).items():
        path = f"{prefix}.{name}" if prefix else name
        if isinstance(prop, dict):
            if prop.get("readOnly"):
                found.append(path)
            found += read_only_paths(prop, path)
            if isinstance(prop.get("items"), dict):
                found += read_only_paths(prop["items"], f"{path}[]")
    return found


def body_paths(body, prefix=""):
    paths = []
    if isinstance(body, dict):
        for name, value in body.items():
            path = f"{prefix}.{name}" if prefix else name
            paths.append(path)
            paths += body_paths(value, path)
    elif isinstance(body, list):
        for item in body:
            paths += body_paths(item, f"{prefix}[]")
    return paths


def match_operation(spec, method, segments):
    """Finds the spec path whose template matches the request's path segments."""
    for template, operations in spec["paths"].items():
        parts = [p for p in template.strip("/").split("/") if p]
        if len(parts) != len(segments):
            continue
        if all(t.startswith("{") or t == s for t, s in zip(parts, segments)):
            if method.lower() in operations:
                return template, operations[method.lower()]
    return None, None


def walk(items, trail=""):
    for item in items:
        name = f"{trail} › {item['name']}" if trail else item["name"]
        if "item" in item:
            yield from walk(item["item"], name)
        else:
            yield name, item


def main():
    spec = load_spec()
    with open(COLLECTION, encoding="utf-8") as handle:
        collection = json.load(handle)
    with open(ENVIRONMENT, encoding="utf-8") as handle:
        environment = json.load(handle)

    declared = {v["key"] for v in collection.get("variable", [])}
    declared |= {v["key"] for v in environment.get("values", [])}

    # Real values win over the stand-ins: anything the collection or environment
    # ships a value for is validated as the customer would actually send it.
    env_values = {v["key"]: v["value"] for v in collection.get("variable", []) if v["value"]}
    env_values.update({v["key"]: v["value"] for v in environment.get("values", []) if v["value"]})

    failures = []
    used = set()
    checked = 0

    for name, item in walk(collection["item"]):
        request = item["request"]
        raw_url = request["url"]["raw"]

        # The token endpoint is not part of the OpenAPI specification.
        if "{{tokenUrl}}" in raw_url:
            substitute(raw_url, env_values, used)
            for header in request.get("header", []):
                substitute(header.get("value", ""), env_values, used)
            for field in request.get("body", {}).get("urlencoded", []):
                substitute(field.get("value", ""), env_values, used)
            continue

        segments = [s for s in request["url"]["path"] if s]
        template, operation = match_operation(spec, request["method"], segments)
        if operation is None:
            failures.append(f"{name}: no operation matches {request['method']} /{'/'.join(segments)}")
            continue

        for header in request.get("header", []):
            substitute(header.get("value", ""), env_values, used)
        substitute(raw_url, env_values, used)

        body = request.get("body")
        if not body or body.get("mode") != "raw":
            continue

        try:
            payload = json.loads(body["raw"])
        except json.JSONDecodeError as error:
            failures.append(f"{name}: request body is not valid JSON - {error}")
            continue

        schema_node = (operation.get("requestBody", {})
                       .get("content", {})
                       .get("application/json", {})
                       .get("schema"))
        if schema_node is None:
            failures.append(f"{name}: {template} declares no application/json request schema")
            continue

        schema = resolve(spec, schema_node)
        concrete = substitute(payload, env_values, used)

        errors = sorted(Draft202012Validator(schema).iter_errors(concrete),
                        key=lambda e: list(e.absolute_path))
        for error in errors:
            location = "/".join(str(p) for p in error.absolute_path) or "(root)"
            failures.append(f"{name}: {location} - {error.message}")

        sent = set(body_paths(payload))
        for path in read_only_paths(schema):
            if path.replace("[]", "") in {p.replace("[]", "") for p in sent}:
                failures.append(f"{name}: sends readOnly field '{path}'")

        checked += 1

    undeclared = sorted(v for v in used if v not in declared and not v.startswith("$"))
    for variable in undeclared:
        failures.append(f"undeclared variable {{{{{variable}}}}}")

    unused = sorted(declared - used - {"accessToken"})
    print(f"validated {checked} request bodies against {os.path.basename(SPEC)}")
    if unused:
        print(f"note: declared but not yet used by any request: {', '.join(unused)}")

    if failures:
        print(f"\n{len(failures)} problem(s):")
        for failure in failures:
            print(f"  - {failure}")
        return 1
    print("no problems found")
    return 0


if __name__ == "__main__":
    sys.exit(main())
