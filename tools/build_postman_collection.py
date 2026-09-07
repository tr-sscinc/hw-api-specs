#!/usr/bin/env python3
"""Builds the customer-facing Postman collection for the SS&C Wealth API.

The collection is generated rather than hand-edited so that descriptions, tests and
payloads stay consistent across every user journey. Run from the repository root:

    python tools/build_postman_collection.py

Outputs:
    SSC-Wealth-API-Journeys.postman_collection.json
    SSC-Wealth-API.postman_environment.json   (template, no secrets)
"""

import json
import os
import re

COLLECTION_FILE = "SSC-Wealth-API-Journeys.postman_collection.json"
ENVIRONMENT_FILE = "SSC-Wealth-API.postman_environment.json"

SPEC_VERSION = "0.8.20"


# --------------------------------------------------------------------------- #
# Description formatting
# --------------------------------------------------------------------------- #

LIST_ITEM = re.compile(r"^([-*+]|\d+[.)])\s")
HORIZONTAL_RULE = re.compile(r"^(-{3,}|\*{3,}|_{3,})$")


def unwrap(text):
    """Joins each wrapped paragraph in a Markdown description into one line.

    The descriptions in this file are wrapped to a readable width in the source,
    but a paragraph split across several lines is awkward to edit in Postman's
    description pane. Markdown treats a single newline inside a paragraph as a
    space, so joining them changes nothing about how the text renders.

    Structure that depends on line breaks is left exactly as it is: fenced code
    blocks (the orchestration diagrams), table rows, headings, horizontal rules
    and the boundaries between list items and paragraphs.
    """
    out = []
    paragraph = []
    fenced = False

    def flush():
        if paragraph:
            out.append(" ".join(paragraph))
            paragraph.clear()

    for line in text.split("\n"):
        stripped = line.strip()

        if stripped.startswith("```"):
            flush()
            fenced = not fenced
            out.append(line)
            continue
        if fenced:
            out.append(line)
            continue

        # A blank line ends a paragraph and is significant to Markdown.
        if not stripped:
            flush()
            out.append("")
            continue

        # Lines that must stay on their own: headings, table rows, rules.
        if (stripped.startswith("#") or stripped.startswith("|")
                or HORIZONTAL_RULE.match(stripped)):
            flush()
            out.append(line)
            continue

        # A new list item starts a new line; anything that follows it without an
        # intervening blank line is its continuation and folds into it.
        if LIST_ITEM.match(stripped):
            flush()
            paragraph.append(line.rstrip())
            continue

        paragraph.append(stripped)

    flush()
    return "\n".join(out)


def unwrap_descriptions(node):
    """Applies unwrap() to every description in the collection tree."""
    if isinstance(node, dict):
        return {
            key: unwrap(value) if key == "description" and isinstance(value, str)
            else unwrap_descriptions(value)
            for key, value in node.items()
        }
    if isinstance(node, list):
        return [unwrap_descriptions(item) for item in node]
    return node


# --------------------------------------------------------------------------- #
# Diagram helpers
# --------------------------------------------------------------------------- #

def diagram(title, rows):
    """Renders an aligned Unicode orchestration diagram.

    rows is a list of tuples:
        ("section", "Investor set-up")
        ("step", "1", "POST /investors", "201  investorId")
        ("blank",)
    """
    calls = [r[2] for r in rows if r[0] == "step"]
    width = max(len(c) for c in calls) + 1
    steps = [r for r in rows if r[0] == "step"]
    last_step = steps[-1] if steps else None

    out = [f" Client{' ' * (width + 6)}SS&C Wealth API", "   │"]
    for row in rows:
        if row[0] == "section":
            out.append(f"   │   {row[1]}")
        elif row[0] == "blank":
            out.append("   │")
        else:
            _, num, call, result = row
            elbow = "└──" if row is last_step else "├──"
            pad = "─" * (width - len(call))
            out.append(f"   {elbow} {num} ─ {call} {pad}▶ {result}")
    return f"{title}\n\n```\n" + "\n".join(out) + "\n```"


def steps_table(rows):
    """rows: list of (n, request name, method + path, produces)"""
    out = [
        "| # | Request | Endpoint | Produces |",
        "|---|---------|----------|----------|",
    ]
    for n, name, endpoint, produces in rows:
        out.append(f"| {n} | {name} | `{endpoint}` | {produces} |")
    return "\n".join(out)


# --------------------------------------------------------------------------- #
# Request helpers
# --------------------------------------------------------------------------- #

def script(lines):
    return {"type": "text/javascript", "exec": lines}


def guard(requirements, journey, environment=None):
    """Pre-request script that fails fast when a prerequisite is missing.

    requirements are collection variables captured by earlier steps of the journey.
    environment are values only the customer can supply — a ceding provider ID, a
    plan reference — which are blank in the shipped environment template.
    """
    lines = []
    if requirements:
        keys = ", ".join(f'"{k}"' for k in requirements)
        lines += [
            "// Stops the request with a readable message when an earlier step in the",
            "// journey has not been run, instead of sending an obviously invalid request.",
            f"[{keys}].forEach(function (key) {{",
            "    if (!pm.collectionVariables.get(key)) {",
            "        throw new Error(",
            f"            'Missing {{{{' + key + '}}}}. Run the earlier steps of \"{journey}\" first, '",
            "            + 'or set the variable by hand on the Variables tab.'",
            "        );",
            "    }",
            "});",
        ]
    if environment:
        keys = ", ".join(f'"{k}"' for k in environment)
        if lines:
            lines.append("")
        lines += [
            "// These values are specific to your firm and cannot be shipped with the",
            "// collection. Fill them in on the environment before sending.",
            f"[{keys}].forEach(function (key) {{",
            "    if (!pm.variables.get(key)) {",
            "        throw new Error(",
            "            'Missing {{' + key + '}}. This value is specific to your firm - set it '",
            "            + 'on the environment. See the request description for what it should contain.'",
            "        );",
            "    }",
            "});",
        ]
    return script(lines)


def capture(status, var, path, label, extra_tests=None):
    """Test script: assert the status, capture an identifier, log it."""
    lines = [
        f'pm.test("Status code is {status}", function () {{',
        f"    pm.response.to.have.status({status});",
        "});",
        "",
        f"if (pm.response.code === {status}) {{",
        "    var body = pm.response.json();",
        "",
        f'    pm.test("Response returns {label}", function () {{',
        f'        pm.expect({path}).to.be.a("string").and.to.not.be.empty;',
        "    });",
        "",
    ]
    for test in extra_tests or []:
        lines += ["    " + line for line in test] + [""]
    lines += [
        f'    pm.collectionVariables.set("{var}", {path});',
        f'    console.log("{var} =", {path});',
        "} else {",
        "    console.error(pm.response.code + ' ' + pm.response.status, pm.response.text());",
        "}",
    ]
    return script(lines)


def capture_number(status, var, path, label, extra_tests=None):
    """As capture(), for identifiers the API returns as integers."""
    lines = [
        f'pm.test("Status code is {status}", function () {{',
        f"    pm.response.to.have.status({status});",
        "});",
        "",
        f"if (pm.response.code === {status}) {{",
        "    var body = pm.response.json();",
        "",
        f'    pm.test("Response returns {label}", function () {{',
        f'        pm.expect({path}).to.be.a("number");',
        "    });",
        "",
    ]
    for test in extra_tests or []:
        lines += ["    " + line for line in test] + [""]
    lines += [
        f'    pm.collectionVariables.set("{var}", String({path}));',
        f'    console.log("{var} =", {path});',
        "} else {",
        "    console.error(pm.response.code + ' ' + pm.response.status, pm.response.text());",
        "}",
    ]
    return script(lines)


def assert_only(status, extra_tests=None):
    lines = [
        f'pm.test("Status code is {status}", function () {{',
        f"    pm.response.to.have.status({status});",
        "});",
        "",
        f"if (pm.response.code === {status}) {{",
        "    var body = pm.response.json();",
        "",
    ]
    for test in extra_tests or []:
        lines += ["    " + line for line in test] + [""]
    lines += [
        "} else {",
        "    console.error(pm.response.code + ' ' + pm.response.status, pm.response.text());",
        "}",
    ]
    return script(lines)


def request(name, method, path, description, body=None, tests=None,
            prerequest=None, no_auth=False):
    """Builds a Postman request item.

    path is written spec-style, e.g. "accounts/{{giaAccountId}}/fees".
    """
    segments = path.split("/")
    headers = [{
        "key": "Request-Id",
        "value": "{{$guid}}",
        "type": "text",
        "description": "Optional. Uniquely identifies the request for traceability. "
                       "If you omit it the platform generates one and returns it in "
                       "the Request-Id response header.",
    }]
    if body is not None:
        headers.insert(0, {"key": "Content-Type", "value": "application/json", "type": "text"})

    req = {
        "method": method,
        "header": headers,
        "url": {
            "raw": "{{baseUrl}}/" + path,
            "host": ["{{baseUrl}}"],
            "path": segments,
        },
        "description": description,
    }
    if no_auth:
        req["auth"] = {"type": "noauth"}
    if body is not None:
        req["body"] = {
            "mode": "raw",
            "raw": json.dumps(body, indent=2),
            "options": {"raw": {"language": "json"}},
        }

    item = {"name": name, "request": req, "response": []}
    events = []
    if prerequest is not None:
        events.append({"listen": "prerequest", "script": prerequest})
    if tests is not None:
        events.append({"listen": "test", "script": tests})
    if events:
        item["event"] = events
    return item


# --------------------------------------------------------------------------- #
# Collection description
# --------------------------------------------------------------------------- #

COLLECTION_DESCRIPTION = f"""\
# SS&C Wealth API — Quick Start & User Journeys

A working, runnable companion to the SS&C Wealth API OpenAPI specification
(**v{SPEC_VERSION}**). The OpenAPI document tells you what each endpoint does; this
collection shows you how the endpoints fit together to complete real pieces of
business — opening a GIA, an ISA, a JISA, a SIPP, or an account for a corporate
investor.

It is written for developers at advisory firms and at third-party software
providers integrating on an adviser's behalf.

---

## What is inside

| Folder | What it covers |
|--------|----------------|
| **0 · Start Here — Quick Start** | Six calls, end to end: authenticate, create an investor, open an account, add a bank account, activate, read it back. Start here. |
| **1 · Retail GIA** | The full onboarding path for an individual general investment account, including vulnerability and correspondence records, fees, a contribution and a cash transfer in. |
| **2 · Joint GIA** | A second account for a couple: a joint owner, a joint bank account, a fixed-amount fee, a regular contribution and an in-specie transfer in. |
| **3 · Stocks & Shares ISA** | An ISA with current-year subscription details, a fee applied by fee code, and a monthly savings contribution. |
| **4 · JISA** | A child investor, and a JISA with the adult as registered contact. |
| **5 · SIPP** | A pension with an employer third party, employer-funded regular contributions, a beneficiary and a pension transfer in. |
| **6 · Corporate GIA** | A corporate investor, a corporate account, and an instruction to pay all investment income out to the bank. |
| **7 · Verify & Troubleshoot** | Read-only requests for inspecting what the journeys created. |

Journeys **2, 3, 4 and 5** reuse the investor created in journey **1**, so the
first time through, run the folders in order. Journey **6** stands alone and can
be run on its own. Each request checks its prerequisites and tells you plainly if
something is missing.

---

## Before you start

You need three things from SS&C:

1. **Client credentials** — a client ID and client secret for the environment you
   are integrating against.
2. **An adviser ID** — the adviser the records will be created against, for example
   `E001428`.
3. **Reference data for your tenant** — a model portfolio (its ID, owning provider
   and effective date), an authorised ceding provider ID for transfers in, and a
   fee code if you intend to use coded fees.

You also need one thing of your own: the **plan reference** held at the ceding
provider for the plan you are transferring in. It is validated against that
provider's format, so a made-up value will be rejected. Journeys 1, 2 and 5 each
transfer a plan in and all three read the same variable, so set it to the plan
that journey is moving before you send its transfer step.

Product IDs are not environment values — each request sends the code for its own
product (`GIA`, `HIS`, `JIS`, `HWS`). If your tenant uses different codes, change
them in the request body.

Then:

1. Import **SSC-Wealth-API.postman_environment.json** alongside this collection.
2. Select it from the environment selector, top right.
3. Fill in the values marked *supplied by SS&C*. The secrets are empty on purpose —
   nothing confidential ships inside this file.
4. Open **0 · Start Here — Quick Start** and send the requests in order.

### Environment values

| Variable | Meaning |
|----------|---------|
| `baseUrl` | API base URL, including the version path. Defaults to the Pilot/UAT server. |
| `tokenUrl` | Full URL of the OAuth 2.0 token endpoint. |
| `clientId`, `clientSecret` | Your OAuth 2.0 client credentials. *Supplied by SS&C.* |
| `adviserId` | The adviser records are created against. *Supplied by SS&C.* |
| `modelId`, `modelProviderId`, `modelDate` | The investment model applied to new accounts. *Supplied by SS&C.* |
| `cedingProviderId` | An authorised ceding provider, used by the transfer-in steps. *Supplied by SS&C.* |
| `adviserAnnualFeeCode` | A banded fee code, used by journey 3. *Supplied by SS&C.* |
| `transferPlanReference` | The plan number to transfer in, as held at the ceding provider. Shared by the transfer steps in journeys 1, 2 and 5. *Yours.* |

Everything else — investor IDs, account IDs, dates — is filled in for you as you
run the collection.

---

## How the API works

**Authentication.** The API uses OAuth 2.0 client credentials. *Get an access
token* exchanges your client ID and secret for a bearer token and stores it in
`{{{{accessToken}}}}`; every other request inherits bearer authentication from the
collection. Tokens expire, so re-send it if you start seeing `401`.

**Accounts open in PENDING.** `POST /accounts` returns an account with status
`PENDING`. It is not live and cannot trade. Add everything the account needs —
bank details, fees, contributions, transfers, third parties — and then call
`POST /accounts/{{accountId}}/activate` as the final step. Activation returns the
account with status `ACTIVE`.

**Declarations are part of the payload.** Most write operations carry a
`declarations` array recording that the adviser has obtained the relevant client
consent. The template IDs are not interchangeable: an ISA needs
`ISA_ACKNOWLEDGEMENT`, a transfer in needs `TRANSFR_IN`, a change to an existing
account needs `AMENDMENT_CONSENT`. Each request below uses the correct set.

**Identifiers chain together.** An investor ID is required to open an account; an
account ID is required for everything hanging off it. The test script on each
request captures the ID it created into a collection variable, so the next
request can use it.

**Bank accounts are referenced by number and sort code.** A money movement does
not point at a bank account ID — it repeats the account number and sort code of a
bank account already registered against the investment account. The collection
keeps those values in variables so the two always agree.

**Request-Id.** Every request sends a `Request-Id` header containing a fresh GUID.
It is optional, but supplying one makes a request traceable in support
conversations. If you omit it, the platform generates one and returns it.

**Errors follow RFC 9457.** Failures return a `application/problem+json` body with
`type`, `title`, `status`, `detail` and an `errors` array pinpointing the offending
fields. Read `detail` and `errors` first — they usually name the problem exactly.

**Dates are generated at run time.** Contribution dates, fee start dates and the
child investor's date of birth are derived from today's date by a script on the
collection, so this collection does not go stale and you are never posting a date
in the past.

---

## A note on the sample data

The payloads use one fictional family throughout — Alan and Claire Whitfield,
their son Thomas, and Alan's company — so you can follow the relationships between
investors, accounts and third parties. The names, addresses, bank details and
national insurance numbers are invented. Nothing here is real client data, and
none of it should be used beyond a test environment.
"""


COLLECTION_PREREQUEST = script([
    "// ───────────────────────────────────────────────────────────────────────────",
    "// Derives the dates used by the sample payloads from today's date, so the",
    "// collection stays valid however long after publication you run it.",
    "// You do not need to change anything here.",
    "// ───────────────────────────────────────────────────────────────────────────",
    "",
    "function pad(n) { return String(n).padStart(2, '0'); }",
    "function iso(d) { return d.getFullYear() + '-' + pad(d.getMonth() + 1) + '-' + pad(d.getDate()); }",
    "",
    "var today = new Date();",
    "",
    "// Effective date for fees, vulnerabilities and correspondence preferences.",
    "pm.collectionVariables.set('today', iso(today));",
    "",
    "// A safely future date for a first contribution or the start of a regular",
    "// payment: the first of next month.",
    "pm.collectionVariables.set('nextMonthFirst', iso(new Date(today.getFullYear(), today.getMonth() + 1, 1)));",
    "",
    "// One year out, used as an expiry date.",
    "var oneYearAhead = new Date(today);",
    "oneYearAhead.setFullYear(oneYearAhead.getFullYear() + 1);",
    "pm.collectionVariables.set('oneYearAhead', iso(oneYearAhead));",
    "",
    "// Start of the current UK tax year (6 April).",
    "var taxYearStart = new Date(today.getFullYear(), 3, 6);",
    "if (today < taxYearStart) { taxYearStart.setFullYear(taxYearStart.getFullYear() - 1); }",
    "pm.collectionVariables.set('taxYearStart', iso(taxYearStart));",
    "",
    "// Date of birth for the child investor in the JISA journey - always age 10.",
    "var childDob = new Date(today);",
    "childDob.setFullYear(childDob.getFullYear() - 10);",
    "pm.collectionVariables.set('childDateOfBirth', iso(childDob));",
])


# --------------------------------------------------------------------------- #
# Folder 0 — Quick Start
# --------------------------------------------------------------------------- #

QUICK_START_DESCRIPTION = "\n\n".join([
    """\
# Start here

Six requests that take you from a set of client credentials to a live investment
account. Send them in order, top to bottom. Nothing here depends on any other
folder.

If you only read one folder, read this one — every journey that follows is a
longer version of this same shape: **authenticate → create the investor → open
the account → furnish the account → activate**.""",

    diagram("## The shape of every journey", [
        ("step", "1", "POST {tokenUrl}", "200  access token"),
        ("blank",),
        ("step", "2", "POST /investors", "201  investorId"),
        ("blank",),
        ("step", "3", "POST /accounts", "201  accountId · PENDING"),
        ("step", "4", "POST /accounts/{id}/bank-accounts", "201"),
        ("blank",),
        ("step", "5", "POST /accounts/{id}/activate", "200  status ACTIVE"),
        ("step", "6", "GET  /accounts/{id}", "200  the finished account"),
    ]),

    "## Steps\n\n" + steps_table([
        ("1", "Get an access token", "POST {{tokenUrl}}", "`accessToken`"),
        ("2", "Create an investor", "POST /investors", "`quickStartInvestorId`"),
        ("3", "Open a GIA", "POST /accounts", "`quickStartAccountId` (PENDING)"),
        ("4", "Add a bank account", "POST /accounts/{accountId}/bank-accounts", "—"),
        ("5", "Activate the account", "POST /accounts/{accountId}/activate", "status ACTIVE"),
        ("6", "Read the account back", "GET /accounts/{accountId}", "the finished account"),
    ]),

    """\
## If something goes wrong

| Response | Usually means |
|----------|---------------|
| `401 Unauthorized` | The token has expired or was never fetched. Re-send step 1. |
| `403 Forbidden` | The credentials are valid but not entitled to the adviser, product or model you asked for. |
| `400 Bad Request` | Read `detail` and the `errors` array in the response — they name the field at fault. A missing declaration, an unknown `modelId` or a product ID your tenant is not set up for are the common causes. |
| `404 Not Found` | The `accountId` or `investorId` in the path does not exist. Check the variable was captured — the Postman console shows what each step stored. |""",
])


def quick_start_folder():
    token = request(
        "1 · Get an access token",
        "POST", "",
        """\
Exchanges your client credentials for an OAuth 2.0 bearer token.

The token is stored in `{{accessToken}}`, and every other request in this
collection inherits bearer authentication from the collection, so you do not need
to set an `Authorization` header yourself.

Tokens are short-lived. If requests start failing with `401 Unauthorized`, send
this one again.""",
        no_auth=True,
    )
    # The token endpoint is a full URL of its own, not a path under baseUrl.
    token["request"]["url"] = {"raw": "{{tokenUrl}}", "host": ["{{tokenUrl}}"]}
    token["request"]["header"] = [
        {"key": "Content-Type", "value": "application/x-www-form-urlencoded", "type": "text"},
    ]
    token["request"]["body"] = {
        "mode": "urlencoded",
        "urlencoded": [
            {"key": "grant_type", "value": "client_credentials", "type": "text"},
            {"key": "client_id", "value": "{{clientId}}", "type": "text"},
            {"key": "client_secret", "value": "{{clientSecret}}", "type": "text"},
        ],
    }
    token["event"] = [{"listen": "test", "script": script([
        'pm.test("Status code is 200", function () {',
        "    pm.response.to.have.status(200);",
        "});",
        "",
        "if (pm.response.code === 200) {",
        "    var body = pm.response.json();",
        "",
        '    pm.test("Response contains an access token", function () {',
        '        pm.expect(body.access_token).to.be.a("string").and.to.not.be.empty;',
        "    });",
        "",
        '    pm.collectionVariables.set("accessToken", body.access_token);',
        '    console.log("Access token stored. Expires in", body.expires_in, "seconds.");',
        "} else {",
        "    console.error('Could not obtain a token:', pm.response.text());",
        "}",
    ])}]

    investor = request(
        "2 · Create an investor",
        "POST", "investors",
        """\
Creates the individual who will own the account.

This is close to the minimum an adult individual investor requires: identity,
one primary address, one nationality, one tax residency with a taxpayer
identification number, contact details, and the income and investment profile
used for suitability and target-market reporting.

The response returns the investor's SS&C Wealth API ID. Every later call that
concerns this person uses it.

**Journey 1 builds on this** with the vulnerability and correspondence records
that a real onboarding would also capture.""",
        body={
            "adviserId": "{{adviserId}}",
            "type": "INDIVIDUAL",
            "externalReferences": [{"reference": "{{$guid}}", "provider": "CRM"}],
            "individual": {
                "title": "MS",
                "firstName": "Priya",
                "surname": "Raman",
                "dateOfBirth": "1984-09-30",
                "gender": "FEMALE",
                "maritalStatus": "SINGLE",
                "incomeAndInvestment": {
                    "occupation": "MEDICAL_PROFESSIONAL",
                    "industry": "HEALTHCARE",
                    "annualIncome": "FROM_75K_TO_100K",
                    "investmentReason": "GROW_WEALTH",
                    "investmentAgreedInPerson": True,
                },
                "territorialProfile": {
                    "nationalities": [{"countryCode": "GB", "primary": True}],
                    "taxResidencies": [
                        {"countryCode": "GB", "tin": "NR521408B", "primary": True}
                    ],
                },
                "contactDetails": {
                    "contactPhone": "01312294417",
                    "mobilePhone": "07700900412",
                    "email": "priya.raman@example.co.uk",
                },
                "notificationPreferences": {"disableEmails": False, "disableSms": False},
            },
            "addresses": [{
                "premisesIdentifier": "8",
                "line1": "Marchmont Crescent",
                "town": "Edinburgh",
                "county": "Midlothian",
                "countryCode": "GB",
                "postCode": "EH9 1HG",
                "primary": True,
            }],
            "declarations": [
                {"adviserId": "{{adviserId}}", "templateId": "IFA_FCA_AUTH", "acknowledgement": True}
            ],
        },
        tests=capture(201, "quickStartInvestorId", "body.id", "an investor ID",
                      extra_tests=[[
                          'pm.test("Investor is created in PENDING status", function () {',
                          '    pm.expect(body.status).to.eql("PENDING");',
                          "});",
                      ]]),
    )

    account = request(
        "3 · Open a GIA",
        "POST", "accounts",
        """\
Opens a general investment account for the investor created in step 2.

Three things are worth noticing:

- **`investors`** links the account to the person, with a `relationship` of `OWNER`.
- **`model`** is the investment model the account's holdings will be managed
  against. The ID, owning provider and effective date all come from your
  environment; SS&C supplies values valid for your tenant.
- **`declarations`** records the target-market assessment. A GIA needs
  `TARGET_MARKET`; other products need more, as the ISA, JISA and SIPP journeys show.

The account comes back with status **`PENDING`**. It is not live yet.""",
        body={
            "productId": "GIA",
            "type": "ADVISED",
            "adviserId": "{{adviserId}}",
            "baseCurrency": "GBP",
            "marketSettlementCurrency": "GBP",
            "name": "Ms Priya Raman",
            "externalReferences": [{"reference": "{{$guid}}", "provider": "CRM"}],
            "investors": [{"id": "{{quickStartInvestorId}}", "relationship": "OWNER"}],
            "model": {
                "id": "{{modelId}}",
                "providerId": "{{modelProviderId}}",
                "date": "{{modelDate}}",
            },
            "declarations": [
                {"adviserId": "{{adviserId}}", "templateId": "TARGET_MARKET", "acknowledgement": True}
            ],
        },
        prerequest=guard(["quickStartInvestorId"], "0 · Start Here — Quick Start"),
        tests=capture(201, "quickStartAccountId", "body.id", "an account ID",
                      extra_tests=[[
                          'pm.test("Account is created in PENDING status", function () {',
                          '    pm.expect(body.status).to.eql("PENDING");',
                          "});",
                      ]]),
    )

    bank = request(
        "4 · Add a bank account",
        "POST", "accounts/{{quickStartAccountId}}/bank-accounts",
        """\
Registers the investor's bank account against the investment account. Money in
and out — contributions, withdrawals, income payments — needs a registered bank
account to reference.

`holders` carries the investor ID, because the investor owns this bank account.
When the holder is a third party such as an employer, you pass the third party's
sequence number and set `thirdParty` to `true` instead; journey 5 shows that.

`primary` marks this as the default account for the money flows that need one.""",
        body={
            "name": "Ms Priya Raman",
            "number": "{{quickStartBankNumber}}",
            "sortCode": "{{quickStartBankSortCode}}",
            "primary": True,
            "holders": [{"id": "{{quickStartInvestorId}}"}],
            "declarations": [
                {"adviserId": "{{adviserId}}", "templateId": "BANK_ACCT_VALIDATION",
                 "acknowledgement": True}
            ],
        },
        prerequest=guard(["quickStartInvestorId", "quickStartAccountId"],
                         "0 · Start Here — Quick Start"),
        tests=assert_only(201, extra_tests=[[
            'pm.test("Bank account is registered against the investment account", function () {',
            '    pm.expect(body.accountId).to.eql(pm.collectionVariables.get("quickStartAccountId"));',
            "});",
        ]]),
    )

    activate = request(
        "5 · Activate the account",
        "POST", "accounts/{{quickStartAccountId}}/activate",
        """\
Takes the account from `PENDING` to `ACTIVE`. Until this succeeds the account
cannot trade.

Activation is always the **last** step. Anything you want in place from day one —
fees, regular contributions, transfers in, beneficiaries — must be added before
you call it, which is why the journeys that follow have so much between account
creation and this request.

The response is the complete account record, now with `status: "ACTIVE"` and an
`activationDate`.""",
        prerequest=guard(["quickStartAccountId"], "0 · Start Here — Quick Start"),
        tests=assert_only(200, extra_tests=[[
            'pm.test("Account is now ACTIVE", function () {',
            '    pm.expect(body.status).to.eql("ACTIVE");',
            "});",
        ]]),
    )

    read = request(
        "6 · Read the account back",
        "GET", "accounts/{{quickStartAccountId}}",
        """\
Retrieves the finished account.

Use this whenever you need the current state of an account: its status, the model
it is managed against, the linked investors and the income option in force.
Note that bank accounts and fees are not part of this payload — they have their
own retrieval endpoints, collected in folder **7 · Verify & Troubleshoot**.""",
        prerequest=guard(["quickStartAccountId"], "0 · Start Here — Quick Start"),
        tests=assert_only(200, extra_tests=[[
            'pm.test("Account is ACTIVE and linked to the investor", function () {',
            '    pm.expect(body.status).to.eql("ACTIVE");',
            '    pm.expect(body.investors.map(function (i) { return i.id; }))',
            '        .to.include(pm.collectionVariables.get("quickStartInvestorId"));',
            "});",
        ]]),
    )

    return {
        "name": "0 · Start Here — Quick Start",
        "description": QUICK_START_DESCRIPTION,
        "item": [token, investor, account, bank, activate, read],
    }


# --------------------------------------------------------------------------- #
# Folder 1 — Retail GIA
# --------------------------------------------------------------------------- #

RETAIL_GIA_DESCRIPTION = "\n\n".join([
    """\
# 1 · Create a retail general investment account

The complete onboarding path for an individual client opening a general
investment account — the journey most integrations implement first, and the
foundation for the rest of this collection.

A GIA is a straightforward taxable investment account: no subscription limits, no
tax wrapper rules, no pension permissions. That makes it the clearest place to
see the platform's shape without product-specific complications getting in the way.

**Our client.** Alan Whitfield, 50, married, a professional in the technology
sector. He is opening a GIA with a lump sum, a modest monthly commitment and an
existing portfolio he wants to move across from another provider. He has a
hearing impairment and asks for large-print correspondence — so the journey also
records his support needs, which is a regulatory expectation under Consumer Duty,
not an optional extra.

**Later journeys reuse Alan.** The joint GIA, the ISA, the JISA and the SIPP all
build on the investor created here, so run this folder first.""",

    diagram("## Orchestration", [
        ("section", "Investor set-up"),
        ("step", "1", "POST /investors", "201  retailInvestorId"),
        ("step", "2", "POST /investors/{id}/vulnerabilities", "201"),
        ("step", "3", "POST /investors/{id}/correspondences", "201"),
        ("blank",),
        ("section", "Account set-up — the account is PENDING throughout"),
        ("step", "4", "POST /accounts", "201  giaAccountId · PENDING"),
        ("step", "5", "POST /accounts/{id}/bank-accounts", "201"),
        ("step", "6", "POST /accounts/{id}/fees", "201"),
        ("step", "7", "POST /accounts/{id}/money-movements", "201"),
        ("step", "8", "POST /accounts/{id}/transfers", "201"),
        ("blank",),
        ("section", "Go live"),
        ("step", "9", "POST /accounts/{id}/activate", "200  status ACTIVE"),
    ]),

    "## Steps\n\n" + steps_table([
        ("1", "Create the retail investor", "POST /investors", "`retailInvestorId`"),
        ("2", "Record vulnerable characteristics", "POST /investors/{investorId}/vulnerabilities", "—"),
        ("3", "Record correspondence preferences", "POST /investors/{investorId}/correspondences", "—"),
        ("4", "Open the individual GIA", "POST /accounts", "`giaAccountId` (PENDING)"),
        ("5", "Add the investor's bank account", "POST /accounts/{accountId}/bank-accounts", "—"),
        ("6", "Add the adviser annual fee, by percentage", "POST /accounts/{accountId}/fees", "—"),
        ("7", "Add a one-off contribution", "POST /accounts/{accountId}/money-movements", "—"),
        ("8", "Add an inbound cash transfer", "POST /accounts/{accountId}/transfers", "—"),
        ("9", "Activate the GIA", "POST /accounts/{accountId}/activate", "status ACTIVE"),
    ]),

    """\
## Things worth knowing

**Order matters in two places.** Vulnerabilities and correspondences need the
investor to exist; everything from step 5 onwards needs the account to exist. The
steps in between are otherwise independent — you can add fees before bank
details if that suits your workflow better.

**These are create endpoints, not upserts.** `POST` to vulnerabilities or
correspondences fails if records already exist for that investor; use `PUT` to
amend them afterwards. The same applies to beneficiaries and employers in
journey 5. If you re-run this folder against the same investor, expect step 2 and
step 3 to complain.

**The bank account is identified by number and sort code, not by ID.** Step 7's
`bank` object repeats the number and sort code registered in step 5. They must
match a bank account already on the investment account. This collection holds
both in variables so they cannot drift apart.

**`sourceOfFunds` applies to one-off self contributions only.** It is where the
anti-money-laundering narrative goes — where the lump sum came from. Regular
contributions and employer contributions do not carry it.

**A GIA transfer in omits `plan.type`.** That field describes the wrapper being
transferred and is only relevant for ISA, JISA and pension transfers. Journeys 3
and 5 populate it; here it is correctly absent.

**Step 8 needs two values only you have.** The ceding provider ID and the plan
reference at that provider are specific to your firm's arrangements, so they ship
blank in the environment and the request stops with a message until you fill them
in. Every other step runs on the sample data as supplied.

**Percentages are not all on the same scale.** An account fee's `percentage`
(step 6) is capped at `1` by the schema, while the `fee.percentage` inside a money
movement or transfer (steps 7 and 8) is capped at `100`. Check the value you send
against the field you are sending it in.""",
])


def retail_gia_folder():
    journey = "1 · Retail GIA"

    investor = request(
        "1 · Create the retail investor",
        "POST", "investors",
        """\
Creates Alan Whitfield as an individual investor.

An adult individual requires identity and date of birth, at least one address
flagged `primary`, at least one nationality, at least one tax residency carrying
a `tin`, contact details including an email address, and the
`incomeAndInvestment` profile — occupation, industry, income band, reason for
investing, and whether the investment was agreed face to face. Those last fields
support suitability and target-market obligations, so the API treats them as
mandatory for adults rather than optional colour.

Where an enumeration does not fit, several fields have an `...OtherValue`
companion: pick `OTHER` for `occupation` and supply `occupationOtherValue`. This
example uses standard values throughout.

`externalReferences` is your own identifier — a CRM record ID, typically. Storing
it here means you can reconcile the platform's records against your own without
keeping a separate mapping table. It is generated fresh on each run so repeat
runs do not collide.

The investor is created in `PENDING` status and moves on once SS&C's onboarding
checks complete. You do not have to wait for that before opening an account.""",
        body={
            "adviserId": "{{adviserId}}",
            "type": "INDIVIDUAL",
            "externalReferences": [{"reference": "{{$guid}}", "provider": "CRM"}],
            "individual": {
                "title": "MR",
                "firstName": "Alan",
                "middleName": "James",
                "surname": "Whitfield",
                "dateOfBirth": "1975-06-14",
                "gender": "MALE",
                "maritalStatus": "MARRIED",
                "incomeAndInvestment": {
                    "occupation": "CORPORATE_PROFESSIONAL",
                    "industry": "TECHNOLOGY_IT_TELECOMS",
                    "annualIncome": "FROM_100K_TO_125K",
                    "investmentReason": "GROW_WEALTH",
                    "investmentAgreedInPerson": True,
                },
                "territorialProfile": {
                    "nationalities": [{"countryCode": "GB", "primary": True}],
                    "taxResidencies": [
                        {"countryCode": "GB", "tin": "AB472913C", "primary": True}
                    ],
                },
                "contactDetails": {
                    "contactPhone": "01619465521",
                    "homePhone": "01619465520",
                    "mobilePhone": "07700900183",
                    "email": "alan.whitfield@example.co.uk",
                },
                "notificationPreferences": {"disableEmails": False, "disableSms": False},
            },
            "addresses": [{
                "premisesIdentifier": "24",
                "line1": "Beechwood Avenue",
                "town": "Altrincham",
                "county": "Cheshire",
                "countryCode": "GB",
                "postCode": "WA14 2QP",
                "primary": True,
            }],
            "declarations": [
                {"adviserId": "{{adviserId}}", "templateId": "IFA_FCA_AUTH", "acknowledgement": True}
            ],
        },
        tests=capture(201, "retailInvestorId", "body.id", "an investor ID",
                      extra_tests=[[
                          'pm.test("Investor is created in PENDING status", function () {',
                          '    pm.expect(body.status).to.eql("PENDING");',
                          "});",
                      ]]),
    )

    vulnerabilities = request(
        "2 · Record vulnerable characteristics",
        "POST", "investors/{{retailInvestorId}}/vulnerabilities",
        """\
Records Alan's vulnerable characteristics and the service adjustments the firm
should make.

Each entry pairs a **characteristic** — `HEALTH`, `LIFE_EVENTS`, `RESILIENCE` or
`CAPABILITY`, the four drivers of vulnerability in the FCA's framework — with the
**service level** describing the practical accommodation. One characteristic can
carry several service levels; send one array entry for each pairing.

Alan's hearing impairment sits under `HEALTH`, with two adjustments: speak loudly
and clearly, and confirm discussions in writing. The second entry, needing extra
time to complete tasks, is recorded under `CAPABILITY` with a review date a year
out — vulnerability records can be time-limited where the underlying circumstance
is expected to change, and an `expiryDate` must be later than the `startDate`.
Omit `startDate` and it defaults to today.

Two constraints to design around: this endpoint applies only to `INDIVIDUAL` and
`COURT_APPOINTED_DEPUTY` investors, and it creates rather than replaces. If the
investor already has vulnerability records, `PUT` to the same path instead.""",
        body={
            "vulnerabilities": [
                {"type": "HEALTH", "serviceLevel": "SPEAK_LOUDLY_AND_CLEARLY",
                 "startDate": "{{today}}"},
                {"type": "HEALTH", "serviceLevel": "ARRANGE_WRITTEN_CONFIRMATION_OF_ANY_DISCUSSIONS",
                 "startDate": "{{today}}"},
                {"type": "CAPABILITY", "serviceLevel": "EXTRA_TIME_REQUIRED_TO_RESPOND_OR_COMPLETE_TASKS",
                 "startDate": "{{today}}", "expiryDate": "{{oneYearAhead}}"},
            ],
            "declarations": [
                {"adviserId": "{{adviserId}}", "templateId": "CONFIRM_VULNERABILITY_CONSENT",
                 "acknowledgement": True}
            ],
        },
        prerequest=guard(["retailInvestorId"], journey),
        tests=assert_only(201, extra_tests=[[
            'pm.test("All three characteristics are recorded", function () {',
            "    pm.expect(body.vulnerabilities).to.have.lengthOf(3);",
            "});",
        ]]),
    )

    correspondences = request(
        "3 · Record correspondence preferences",
        "POST", "investors/{{retailInvestorId}}/correspondences",
        """\
Records the format Alan needs his documents in.

Correspondence preferences are the delivery side of the vulnerability record in
step 2: `AUDIO`, `BRAILLE` or `LARGE_PRINT`. Alan asks for large print, with no
expiry date because the need is permanent.

Like vulnerabilities, this endpoint applies only to `INDIVIDUAL` and
`COURT_APPOINTED_DEPUTY` investors, creates rather than replaces, and defaults
`startDate` to today when you omit it. Use `PUT` to change preferences later.""",
        body={
            "correspondences": [
                {"type": "LARGE_PRINT", "startDate": "{{today}}"}
            ],
            "declarations": [
                {"adviserId": "{{adviserId}}", "templateId": "CONFIRM_CORRESPONDENCES_CONSENT",
                 "acknowledgement": True}
            ],
        },
        prerequest=guard(["retailInvestorId"], journey),
        tests=assert_only(201, extra_tests=[[
            'pm.test("Large print preference is recorded", function () {',
            '    pm.expect(body.correspondences[0].type).to.eql("LARGE_PRINT");',
            "});",
        ]]),
    )

    account = request(
        "4 · Open the individual GIA",
        "POST", "accounts",
        """\
Opens the general investment account in Alan's sole name.

**`investors`** holds a single entry with `relationship: "OWNER"`. Journey 2 adds
a second owner to make an account joint; journey 4 uses the other permitted
relationship, `REGISTERED_CONTACT`, for a JISA.

**`type`** is the service level: `ADVISED` where the adviser makes the
recommendation, `DISCRETIONARY` where a manager acts under mandate, or
`EXECUTION_ONLY` where the client decides alone. It cannot be changed later, and
neither can `productId` or the currencies.

**`name`** is what appears on documents and in the Adviser Portal. For an
individual it is title, first name, middle name and surname; the limit is 50
characters, so drop the middle name or title on longer names. Joint and corporate
accounts follow different conventions — see journeys 2 and 6.

**`model`** identifies the investment model. Supplying `date` pins the account to
a specific version of the model; omit it and the latest is used. Omit
`providerId` and the tenant on your token is assumed.

**`declarations`** for a GIA needs only `TARGET_MARKET`, confirming the product
suits this client. Wrappers need more: the ISA journey sends three.

The response returns the account ID and `status: "PENDING"`. Steps 5 to 8 furnish
the account; step 9 makes it live.""",
        body={
            "productId": "GIA",
            "type": "ADVISED",
            "adviserId": "{{adviserId}}",
            "baseCurrency": "GBP",
            "marketSettlementCurrency": "GBP",
            "name": "Mr Alan James Whitfield",
            "externalReferences": [{"reference": "{{$guid}}", "provider": "CRM"}],
            "investors": [{"id": "{{retailInvestorId}}", "relationship": "OWNER"}],
            "model": {
                "id": "{{modelId}}",
                "providerId": "{{modelProviderId}}",
                "date": "{{modelDate}}",
            },
            "declarations": [
                {"adviserId": "{{adviserId}}", "templateId": "TARGET_MARKET", "acknowledgement": True}
            ],
        },
        prerequest=guard(["retailInvestorId"], journey),
        tests=capture(201, "giaAccountId", "body.id", "an account ID",
                      extra_tests=[[
                          'pm.test("Account is created in PENDING status", function () {',
                          '    pm.expect(body.status).to.eql("PENDING");',
                          "});",
                      ], [
                          'pm.test("Investor is linked as OWNER", function () {',
                          '    pm.expect(body.investors[0].relationship).to.eql("OWNER");',
                          "});",
                      ]]),
    )

    bank = request(
        "5 · Add the investor's bank account",
        "POST", "accounts/{{giaAccountId}}/bank-accounts",
        """\
Registers Alan's current account against the GIA.

`holders` carries his investor ID: he owns this bank account. A joint account
lists both investor IDs (journey 2), and a third party's account — an employer,
say — uses the third party's sequence number with `thirdParty: true` (journey 5).

`primary` marks it as the default for money flows that need one. Only one bank
account per investment account should be primary.

For a GBP account, `number` and `sortCode` are required. Other currencies take
different combinations: EUR needs `iban` and `bicSwift`, USD needs `number` and
`bicSwift`.

**Remember the number and sort code.** Money movements reference a bank account
by repeating them, not by any ID the response returns. This collection keeps both
in `{{retailBankNumber}}` and `{{retailBankSortCode}}`, which is why step 7 can
stay in step with this one.

The bank account is created `UNCHECKED` and moves to `ACTIVE` once validation
completes. That does not block account activation.""",
        body={
            "name": "Mr Alan James Whitfield",
            "number": "{{retailBankNumber}}",
            "sortCode": "{{retailBankSortCode}}",
            "primary": True,
            "holders": [{"id": "{{retailInvestorId}}"}],
            "declarations": [
                {"adviserId": "{{adviserId}}", "templateId": "BANK_ACCT_VALIDATION",
                 "acknowledgement": True}
            ],
        },
        prerequest=guard(["retailInvestorId", "giaAccountId"], journey),
        tests=assert_only(201, extra_tests=[[
            'pm.test("Bank account is registered against the GIA", function () {',
            '    pm.expect(body.accountId).to.eql(pm.collectionVariables.get("giaAccountId"));',
            "});",
        ]]),
    )

    fee = request(
        "6 · Add the adviser annual fee, by percentage",
        "POST", "accounts/{{giaAccountId}}/fees",
        """\
Applies the ongoing adviser charge as a flat percentage of the account's value.

There are three ways to express an adviser fee, and this collection shows each in
turn:

| Approach | Fields | Where |
|----------|--------|-------|
| Flat percentage | `percentage` | here |
| Fixed amount | `amount` | journey 2 |
| Banded, by fee code | `code` | journey 3 |

`percentage` is expressed as a decimal and the schema caps it at `1`. Note this
is a different scale from the `fee.percentage` inside a money movement or
transfer, which is capped at `100`.

`vatIncluded` states whether the figure is VAT-inclusive. `startDate` is when the
charge begins accruing; today is the usual choice at onboarding.

Some fee types are system-managed and rejected here — product annual, platform
annual, platform initial and discretionary model management. Fees attached to a
contribution or a transfer are not set here either: they travel in the `fee`
object on the money movement or transfer itself, as steps 7 and 8 show.

The response echoes the fee with its ID, status, invoicing frequency and — for a
coded fee — the full band structure.""",
        body={
            "fees": [
                {"type": "ADVISER_ANNUAL", "percentage": 0.5, "vatIncluded": True,
                 "startDate": "{{today}}"}
            ],
            "declarations": [
                {"adviserId": "{{adviserId}}", "templateId": "AMENDMENT_CONSENT",
                 "acknowledgement": True}
            ],
        },
        prerequest=guard(["giaAccountId"], journey),
        tests=assert_only(201, extra_tests=[[
            'pm.test("Adviser annual fee is active on the account", function () {',
            '    pm.expect(body.fees[0].type).to.eql("ADVISER_ANNUAL");',
            '    pm.expect(body.fees[0].status).to.eql("ACTIVE");',
            "});",
        ]]),
    )

    contribution = request(
        "7 · Add a one-off contribution",
        "POST", "accounts/{{giaAccountId}}/money-movements",
        """\
Sets up Alan's opening lump sum of £25,000.

One endpoint covers all money in and out of an account — contributions,
withdrawals and pension decumulation — and a single request can carry several
movements at once. This one sends a single `ONE_OFF` contribution.

**`contributionMethod`** is how the money arrives: `ELECTRONIC` for a bank
transfer the client pushes, `DIRECT_DEBIT` for a payment the platform collects,
or `CHEQUE`. One-off direct debits are not supported, so a lump sum is
`ELECTRONIC` or `CHEQUE`.

**`payer`** is `SELF` here. `EMPLOYER` is valid only on pension products, and
journey 5 uses it.

**`investmentInstruction`** decides what happens on receipt: `INVEST_IN_MODEL`
buys into the account's model straight away, `LEAVE_IN_CASH` holds it.

**`bank`** repeats the number and sort code registered in step 5 — this is the
account the money comes from, and it must already exist on the investment
account.

**`fee`** is the initial adviser charge on this contribution, separate from the
ongoing fee in step 6. Here it is 0.5% of the £25,000. A fixed amount can be
spread over monthly instalments with `instalmentPlan` — journey 2 shows that.

**`sourceOfFunds`** is the anti-money-laundering narrative and applies to one-off
self contributions on retail accounts only. `EARNINGS` optionally takes salary,
job description and nature of business.

**`nextDate`** is when the movement is expected. For a regular payment it is the
first collection date; for a lump sum, when it should arrive.""",
        body={
            "moneyMovements": [{
                "type": "CONTRIBUTIONS",
                "contributionMethod": "ELECTRONIC",
                "payer": "SELF",
                "frequency": "ONE_OFF",
                "value": {"amount": 25000, "currency": "GBP"},
                "nextDate": "{{nextMonthFirst}}",
                "includeNonDailyAssets": False,
                "investmentInstruction": "INVEST_IN_MODEL",
                "bank": {
                    "number": "{{retailBankNumber}}",
                    "sortCode": "{{retailBankSortCode}}",
                },
                "fee": {"percentage": 0.5},
                "sourceOfFunds": {
                    "type": "EARNINGS",
                    "fields": {
                        "annualSalary": 115000,
                        "jobDescription": "Technology programme director",
                        "natureOfBusiness": "Software and IT services",
                    },
                },
            }],
            "declarations": [
                {"adviserId": "{{adviserId}}", "templateId": "AMENDMENT_CONSENT",
                 "acknowledgement": True}
            ],
        },
        prerequest=guard(["giaAccountId"], journey),
        tests=capture_number(201, "giaContributionId", "body.moneyMovements[0].id",
                      "a money movement ID",
                      extra_tests=[[
                          'pm.test("One-off contribution is recorded", function () {',
                          '    pm.expect(body.moneyMovements[0].type).to.eql("CONTRIBUTIONS");',
                          '    pm.expect(body.moneyMovements[0].frequency).to.eql("ONE_OFF");',
                          "});",
                      ]]),
    )

    transfer = request(
        "8 · Add an inbound cash transfer",
        "POST", "accounts/{{giaAccountId}}/transfers",
        """\
Brings across £45,000 held with another provider, as cash.

**`type`** is `CASH` — the ceding provider sells the holdings and sends the
proceeds. `INSPECIE` moves the assets themselves without selling, keeping the
client invested throughout; journey 2 shows one.

**`isPartial`** is `false`, so the whole plan comes across and it closes at the
ceding provider. `true` moves part of it and leaves the rest behind.

**`investmentInstruction`** works as it does for contributions: invest on arrival,
or hold as cash. It applies to cash transfers only.

**`plan`** describes what is being transferred. `reference` is the ceding
provider's plan number, and it is validated against that provider's format — so
it has to be a real one, which means it can only come from you. It is held in
`{{transferPlanReference}}` on the environment, blank until you fill it in. That
one variable is shared by the transfer steps in journeys 2 and 5 as well, so set it
to the plan the journey you are running is actually moving.
The limit is 20 characters. `holderName` is the name the plan is registered in.

**`plan.type`** is deliberately absent. It describes the wrapper being
transferred and is only relevant for ISA, JISA and pension transfers — journey 5
sends `SIPP` for a pension, and an ISA transfer would send `STOCKS_AND_SHARES` or
`CASH`. A GIA has no wrapper, so the field is omitted here.

**`provider.id`** identifies the ceding provider from SS&C's list of authorised
counterparties, and is likewise specific to your firm's arrangements — set
`{{cedingProviderId}}` on the environment. The provider's name and address come
back in the response, so you do not send them. If the plans in journeys 2, 3 and 5
sit with different providers, override the value on those requests rather than
here.

**`fee`** is the adviser's initial charge on the transferred value — a fixed £250
here, where step 7 used a percentage. Note the different scale: this
`percentage` would be capped at 100, not 1.

The transfer is created with status `CREATED` and progresses as the two providers
exchange instructions. Nothing else in this journey waits on it.""",
        body={
            "transfers": [{
                "type": "CASH",
                "isPartial": False,
                "investmentInstruction": "INVEST_IN_MODEL",
                "value": {"amount": 45000, "currency": "GBP"},
                "fee": {"amount": 250},
                "plan": {
                    "reference": "{{transferPlanReference}}",
                    "holderName": "Mr Alan James Whitfield",
                },
                "provider": {"id": "{{cedingProviderId}}"},
            }],
            "declarations": [
                {"adviserId": "{{adviserId}}", "templateId": "TRANSFR_IN", "acknowledgement": True}
            ],
        },
        prerequest=guard(["giaAccountId"], journey,
                         environment=["cedingProviderId", "transferPlanReference"]),
        tests=capture_number(201, "giaTransferId", "body.transfers[0].id", "a transfer ID",
                      extra_tests=[[
                          'pm.test("Inbound cash transfer is created", function () {',
                          '    pm.expect(body.transfers[0].type).to.eql("CASH");',
                          '    pm.expect(body.transfers[0].direction).to.eql("IN");',
                          "});",
                      ]]),
    )

    activate = request(
        "9 · Activate the GIA",
        "POST", "accounts/{{giaAccountId}}/activate",
        """\
Takes the account live.

Everything Alan's account needs is now in place: his bank details, the ongoing
adviser charge, the opening lump sum and the transfer in from his previous
provider. Activation moves the account from `PENDING` to `ACTIVE`, and from here
it can trade.

Activation is the last step of every onboarding journey. Anything that should be
in force from day one belongs before it.

Later changes go through the individual maintenance endpoints — `PATCH
/accounts/{accountId}` for the account itself, `POST` to money-movements for a new
regular withdrawal, and so on. Folder **7 · Verify & Troubleshoot** has the
read-only requests for checking the result.""",
        prerequest=guard(["giaAccountId"], journey),
        tests=assert_only(200, extra_tests=[[
            'pm.test("GIA is now ACTIVE", function () {',
            '    pm.expect(body.status).to.eql("ACTIVE");',
            "});",
        ], [
            'pm.test("Activation date is returned", function () {',
            '    pm.expect(body.activationDate).to.be.a("string").and.to.not.be.empty;',
            "});",
        ]]),
    )

    return {
        "name": journey,
        "description": RETAIL_GIA_DESCRIPTION,
        "item": [investor, vulnerabilities, correspondences, account, bank, fee,
                 contribution, transfer, activate],
    }


# --------------------------------------------------------------------------- #
# Folder 2 — Joint GIA
# --------------------------------------------------------------------------- #

JOINT_GIA_DESCRIPTION = "\n\n".join([
    """\
# 2 · Create a joint GIA

A second general investment account, this time held jointly by a couple. It shows
the three things that change when an account has more than one owner, and
introduces a fee expressed as a fixed amount, a regular monthly contribution and
an in-specie transfer.

**Our clients.** Alan Whitfield, from journey 1, and his wife Claire, a secondary
school teacher. They are investing jointly and moving an existing joint portfolio
across from another provider without selling it.

**There is no `JOINT` relationship.** A joint account is expressed as two entries
in `investors`, both with `relationship: "OWNER"`. The permitted relationships are
`OWNER` and `REGISTERED_CONTACT`, and the latter exists for JISAs, not for
couples.

**Prerequisite.** Run journey **1** first — this account is opened for the
investor created there plus the new one created here.""",

    diagram("## Orchestration", [
        ("section", "The second owner"),
        ("step", "1", "POST /investors", "201  jointInvestorId"),
        ("blank",),
        ("section", "Account set-up — two owners throughout"),
        ("step", "2", "POST /accounts", "201  jointGiaAccountId · PENDING"),
        ("step", "3", "POST /accounts/{id}/bank-accounts", "201  two holders"),
        ("step", "4", "POST /accounts/{id}/fees", "201  fixed amount"),
        ("step", "5", "POST /accounts/{id}/money-movements", "201  monthly"),
        ("step", "6", "POST /accounts/{id}/transfers", "201  in-specie"),
        ("blank",),
        ("section", "Go live"),
        ("step", "7", "POST /accounts/{id}/activate", "200  status ACTIVE"),
    ]),

    "## Steps\n\n" + steps_table([
        ("1", "Create the second investor", "POST /investors", "`jointInvestorId`"),
        ("2", "Open the joint GIA", "POST /accounts", "`jointGiaAccountId` (PENDING)"),
        ("3", "Add the joint bank account", "POST /accounts/{accountId}/bank-accounts", "—"),
        ("4", "Add the adviser annual fee, by amount", "POST /accounts/{accountId}/fees", "—"),
        ("5", "Add a regular contribution", "POST /accounts/{accountId}/money-movements", "—"),
        ("6", "Add an inbound in-specie transfer", "POST /accounts/{accountId}/transfers", "—"),
        ("7", "Activate the joint GIA", "POST /accounts/{accountId}/activate", "status ACTIVE"),
    ]),

    """\
## Things worth knowing

**Joint accounts are for GIAs, not wrappers.** ISAs, JISAs and pensions are
individual by law, so only an unwrapped account like a GIA can be held jointly.
That is why this journey opens a second GIA rather than a joint version of a
later product.

**The account name uses an ampersand.** The platform's convention for a joint
account is the owners' names separated by ` & `. The 50-character limit still
applies, so long names lose middle names and titles first.

**Both owners hold the bank account.** `holders` carries two entries, one per
investor ID. A regular contribution collected by direct debit needs a bank
account whose holders match the account's owners.

**In-specie means the assets move, not the money.** The ceding provider
re-registers the holdings into the new account instead of selling them, so the
client stays invested and avoids being out of the market. It takes longer than a
cash transfer and only works where both providers can hold the same instruments —
anything unsupported is usually sold and sent as residual cash.

**`investmentInstruction` is omitted on an in-specie transfer.** There is nothing
to invest: the assets arrive as assets. The field applies to cash transfers only.

**`isPartial` is `true` here.** The Whitfields are moving part of their portfolio
and leaving the rest with the existing provider. A partial in-specie transfer
requires the ceding provider to agree which holdings come across.""",
])


def joint_gia_folder():
    journey = "2 · Joint GIA"
    both = "1 · Retail GIA and 2 · Joint GIA"

    investor = request(
        "1 · Create the second investor",
        "POST", "investors",
        """\
Creates Claire Whitfield, who will be the joint owner.

The payload is the same shape as journey 1 step 1: every adult individual needs
identity, an address, a nationality, a tax residency with a `tin`, contact
details and the `incomeAndInvestment` profile, whether they are the first owner
or the second.

Two things to note for a couple:

- **Each investor is a separate record.** There is no notion of a household or a
  couple in the API. Claire gets her own investor ID, her own address list and her
  own suitability profile, and the two are only connected by the accounts they
  jointly own.
- **A shared address is still entered per investor.** Claire's address is the same
  as Alan's, but it is recorded again here. There is no linking of address records
  between investors.

Claire has no vulnerability or correspondence records, so this journey goes
straight from the investor to the account.""",
        body={
            "adviserId": "{{adviserId}}",
            "type": "INDIVIDUAL",
            "externalReferences": [{"reference": "{{$guid}}", "provider": "CRM"}],
            "individual": {
                "title": "MRS",
                "firstName": "Claire",
                "surname": "Whitfield",
                "dateOfBirth": "1978-02-11",
                "gender": "FEMALE",
                "maritalStatus": "MARRIED",
                "incomeAndInvestment": {
                    "occupation": "EDUCATION_PROFESSIONAL",
                    "industry": "EDUCATION",
                    "annualIncome": "FROM_50K_TO_75K",
                    "investmentReason": "GROW_WEALTH",
                    "investmentAgreedInPerson": True,
                },
                "territorialProfile": {
                    "nationalities": [{"countryCode": "GB", "primary": True}],
                    "taxResidencies": [
                        {"countryCode": "GB", "tin": "AB558274D", "primary": True}
                    ],
                },
                "contactDetails": {
                    "contactPhone": "01619465521",
                    "mobilePhone": "07700900274",
                    "email": "claire.whitfield@example.co.uk",
                },
                "notificationPreferences": {"disableEmails": False, "disableSms": False},
            },
            "addresses": [{
                "premisesIdentifier": "24",
                "line1": "Beechwood Avenue",
                "town": "Altrincham",
                "county": "Cheshire",
                "countryCode": "GB",
                "postCode": "WA14 2QP",
                "primary": True,
            }],
            "declarations": [
                {"adviserId": "{{adviserId}}", "templateId": "IFA_FCA_AUTH", "acknowledgement": True}
            ],
        },
        tests=capture(201, "jointInvestorId", "body.id", "an investor ID",
                      extra_tests=[[
                          'pm.test("Investor is created in PENDING status", function () {',
                          '    pm.expect(body.status).to.eql("PENDING");',
                          "});",
                      ]]),
    )

    account = request(
        "2 · Open the joint GIA",
        "POST", "accounts",
        """\
Opens a general investment account owned jointly by Alan and Claire.

**Two owners, both `OWNER`.** This is the whole of what makes an account joint.
The `relationship` enumeration offers only `OWNER` and `REGISTERED_CONTACT`, so
there is no separate joint indicator to set and no limit implied by the schema on
the number of owners — in practice a GIA is held by two.

**The name convention differs.** A joint account is named by concatenating the
owners' names with an ampersand: `Mr Alan James Whitfield & Mrs Claire Whitfield`.
That is 46 characters, inside the 50-character limit; if it were not, the middle
name and then the titles would be dropped.

**Everything else matches journey 1.** Same product, same service level, same
model, and a single `TARGET_MARKET` declaration — a GIA carries no wrapper rules
whether it has one owner or two.

The account opens `PENDING`, as always.""",
        body={
            "productId": "GIA",
            "type": "ADVISED",
            "adviserId": "{{adviserId}}",
            "baseCurrency": "GBP",
            "marketSettlementCurrency": "GBP",
            "name": "Mr Alan James Whitfield & Mrs Claire Whitfield",
            "externalReferences": [{"reference": "{{$guid}}", "provider": "CRM"}],
            "investors": [
                {"id": "{{retailInvestorId}}", "relationship": "OWNER"},
                {"id": "{{jointInvestorId}}", "relationship": "OWNER"},
            ],
            "model": {
                "id": "{{modelId}}",
                "providerId": "{{modelProviderId}}",
                "date": "{{modelDate}}",
            },
            "declarations": [
                {"adviserId": "{{adviserId}}", "templateId": "TARGET_MARKET", "acknowledgement": True}
            ],
        },
        prerequest=guard(["retailInvestorId", "jointInvestorId"], both),
        tests=capture(201, "jointGiaAccountId", "body.id", "an account ID",
                      extra_tests=[[
                          'pm.test("Account is created in PENDING status", function () {',
                          '    pm.expect(body.status).to.eql("PENDING");',
                          "});",
                      ], [
                          'pm.test("Both investors are linked as owners", function () {',
                          "    pm.expect(body.investors).to.have.lengthOf(2);",
                          '    pm.expect(body.investors.map(function (i) { return i.relationship; }))',
                          '        .to.eql(["OWNER", "OWNER"]);',
                          "});",
                      ]]),
    )

    bank = request(
        "3 · Add the joint bank account",
        "POST", "accounts/{{jointGiaAccountId}}/bank-accounts",
        """\
Registers the couple's joint current account.

**`holders` carries both investor IDs.** That is the only difference from journey
1 step 5. `holders` accepts up to 20 entries, and each is either an investor ID or
— with `thirdParty: true` — the sequence number of a third party on the account,
as journey 5 shows for an employer.

The account is `primary`, so it is the default for the direct debit set up in
step 5. A direct debit needs the mandate to be in the names of the account's
owners, which is why a joint account contributes from a joint bank account rather
than from either owner's sole account.

As in journey 1, remember that money movements identify this bank account by
repeating `number` and `sortCode` — they are held in `{{jointBankNumber}}` and
`{{jointBankSortCode}}` so step 5 cannot drift out of step.""",
        body={
            "name": "Mr A J Whitfield & Mrs C Whitfield",
            "number": "{{jointBankNumber}}",
            "sortCode": "{{jointBankSortCode}}",
            "primary": True,
            "holders": [
                {"id": "{{retailInvestorId}}"},
                {"id": "{{jointInvestorId}}"},
            ],
            "declarations": [
                {"adviserId": "{{adviserId}}", "templateId": "BANK_ACCT_VALIDATION",
                 "acknowledgement": True}
            ],
        },
        prerequest=guard(["retailInvestorId", "jointInvestorId", "jointGiaAccountId"], both),
        tests=assert_only(201, extra_tests=[[
            'pm.test("Bank account has two holders", function () {',
            "    pm.expect(body.holders).to.have.lengthOf(2);",
            "});",
        ]]),
    )

    fee = request(
        "4 · Add the adviser annual fee, by amount",
        "POST", "accounts/{{jointGiaAccountId}}/fees",
        """\
Applies the ongoing adviser charge as a fixed monetary amount rather than a
percentage of the account.

This is the second of the three ways to express an adviser fee — journey 1 used
`percentage`, journey 3 uses `code`. Send exactly one of the three: a fee that is
both a percentage and an amount has no meaning.

**`amount` has no schema maximum**, unlike `percentage`, and `currency` must match
the account's `baseCurrency`. £1,200 a year on a joint portfolio is a typical
fixed-fee arrangement, and fixed fees are increasingly common where a firm charges
for advice by service tier rather than by portfolio size.

**One caveat.** The OpenAPI examples only ever pair `amount` with
`ADVISER_ONE_OFF`, and `percentage` with `ADVISER_ANNUAL`. The schema permits
`ADVISER_ANNUAL` with `amount`, which is what an annual fee by amount means and
what this request sends — but if your tenant is configured to reject it, switch to
`percentage` or raise it with SS&C.

The response returns the fee with its ID, status and the `invoiceFrequency` the
platform will charge it on.""",
        body={
            "fees": [
                {"type": "ADVISER_ANNUAL", "amount": 1200, "currency": "GBP",
                 "vatIncluded": True, "startDate": "{{today}}"}
            ],
            "declarations": [
                {"adviserId": "{{adviserId}}", "templateId": "AMENDMENT_CONSENT",
                 "acknowledgement": True}
            ],
        },
        prerequest=guard(["jointGiaAccountId"], journey),
        tests=assert_only(201, extra_tests=[[
            'pm.test("Fixed-amount adviser annual fee is active", function () {',
            '    pm.expect(body.fees[0].type).to.eql("ADVISER_ANNUAL");',
            "    pm.expect(body.fees[0].amount).to.eql(1200);",
            "});",
        ]]),
    )

    contribution = request(
        "5 · Add a regular contribution",
        "POST", "accounts/{{jointGiaAccountId}}/money-movements",
        """\
Sets up a monthly direct debit of £750.

The endpoint is the same as journey 1 step 7; the difference is the shape of a
recurring payment:

- **`frequency`** is `MONTHLY` rather than `ONE_OFF`. `ANNUALLY`, `QUARTERLY` and
  `HALF_YEARLY` are also available.
- **`contributionMethod`** is `DIRECT_DEBIT`, so the platform collects the money.
  One-off direct debits are not supported — a recurring collection is the point of
  the mandate.
- **`nextDate`** is the first collection date, and every subsequent collection
  follows the frequency from there.
- **`sourceOfFunds` is absent.** It applies to one-off self contributions only. A
  regular commitment out of income does not carry an anti-money-laundering
  narrative per payment.

**`fee.instalmentPlan`** is the interesting part. The £120 initial adviser charge
is spread across 12 monthly instalments rather than taken in one bite, which is
how initial advice is usually paid for out of a regular savings plan. The response
returns `completedMonths` so you can see how far through the plan an account is.

**`reference`** comes back in the response for regular direct debit contributions,
and is the reference the collection will appear under. You cannot set it.""",
        body={
            "moneyMovements": [{
                "type": "CONTRIBUTIONS",
                "contributionMethod": "DIRECT_DEBIT",
                "payer": "SELF",
                "frequency": "MONTHLY",
                "value": {"amount": 750, "currency": "GBP"},
                "nextDate": "{{nextMonthFirst}}",
                "investmentInstruction": "INVEST_IN_MODEL",
                "bank": {
                    "number": "{{jointBankNumber}}",
                    "sortCode": "{{jointBankSortCode}}",
                },
                "fee": {
                    "amount": 120,
                    "instalmentPlan": {"totalMonths": 12},
                },
            }],
            "declarations": [
                {"adviserId": "{{adviserId}}", "templateId": "AMENDMENT_CONSENT",
                 "acknowledgement": True}
            ],
        },
        prerequest=guard(["jointGiaAccountId"], journey),
        tests=capture_number(201, "jointGiaContributionId", "body.moneyMovements[0].id",
                            "a money movement ID",
                            extra_tests=[[
                                'pm.test("Monthly direct debit is recorded", function () {',
                                '    pm.expect(body.moneyMovements[0].frequency).to.eql("MONTHLY");',
                                '    pm.expect(body.moneyMovements[0].contributionMethod)',
                                '        .to.eql("DIRECT_DEBIT");',
                                "});",
                            ]]),
    )

    transfer = request(
        "6 · Add an inbound in-specie transfer",
        "POST", "accounts/{{jointGiaAccountId}}/transfers",
        """\
Moves £90,000 of the couple's existing holdings across as assets rather than cash.

**`type` is `INSPECIE`.** The ceding provider re-registers the holdings into the
new account instead of selling them. The client is never out of the market, and no
disposal is triggered — which matters on a GIA, where a sale would realise a
capital gain. The trade-off is time: in-specie transfers depend on both providers
being able to hold the same instruments, and anything unsupported is usually sold
and sent on as residual cash.

**`isPartial` is `true`.** They are moving part of the portfolio and leaving the
rest where it is. The ceding provider needs to know which holdings are in scope,
which is agreed outside the API.

**`investmentInstruction` is omitted.** It decides whether arriving *cash* is
invested or held, and an in-specie transfer brings no cash. Journey 1 sends it
because that transfer is a cash one.

**`plan.type` is omitted too**, exactly as in journey 1 — a GIA has no wrapper to
describe. Journey 5 populates it for a pension.

**`fee.amount`** is a flat £250 initial charge on the transfer. Note again the
scale difference flagged in journey 1: a `percentage` here is capped at 100, while
an account fee's `percentage` is capped at 1.

`{{transferPlanReference}}` and `{{cedingProviderId}}` are yours to supply — the
plan number is validated against the ceding provider's format. The same
`{{transferPlanReference}}` serves journeys 1 and 5 too, so point it at the joint
portfolio being moved here before you send this request.""",
        body={
            "transfers": [{
                "type": "INSPECIE",
                "isPartial": True,
                "value": {"amount": 90000, "currency": "GBP"},
                "fee": {"amount": 250},
                "plan": {
                    "reference": "{{transferPlanReference}}",
                    "holderName": "Mr Alan James Whitfield & Mrs Claire Whitfield",
                },
                "provider": {"id": "{{cedingProviderId}}"},
            }],
            "declarations": [
                {"adviserId": "{{adviserId}}", "templateId": "TRANSFR_IN", "acknowledgement": True}
            ],
        },
        prerequest=guard(["jointGiaAccountId"], journey,
                         environment=["cedingProviderId", "transferPlanReference"]),
        tests=capture_number(201, "jointGiaTransferId", "body.transfers[0].id", "a transfer ID",
                            extra_tests=[[
                                'pm.test("Partial in-specie transfer in is created", function () {',
                                '    pm.expect(body.transfers[0].type).to.eql("INSPECIE");',
                                "    pm.expect(body.transfers[0].isPartial).to.eql(true);",
                                '    pm.expect(body.transfers[0].direction).to.eql("IN");',
                                "});",
                            ]]),
    )

    activate = request(
        "7 · Activate the joint GIA",
        "POST", "accounts/{{jointGiaAccountId}}/activate",
        """\
Takes the joint account live.

Both owners, the joint bank account, the fixed annual charge, the monthly direct
debit and the in-specie transfer are all in place, so the account can be
activated. As ever, activation is the final step.

The Whitfields now hold two accounts between them: Alan's sole GIA from journey 1
and this joint one. Journey 3 adds an ISA in Alan's sole name.""",
        prerequest=guard(["jointGiaAccountId"], journey),
        tests=assert_only(200, extra_tests=[[
            'pm.test("Joint GIA is now ACTIVE", function () {',
            '    pm.expect(body.status).to.eql("ACTIVE");',
            "});",
        ]]),
    )

    return {
        "name": journey,
        "description": JOINT_GIA_DESCRIPTION,
        "item": [investor, account, bank, fee, contribution, transfer, activate],
    }


# --------------------------------------------------------------------------- #
# Folder 3 — Stocks & Shares ISA
# --------------------------------------------------------------------------- #

ISA_DESCRIPTION = "\n\n".join([
    """\
# 3 · Create a stocks and shares ISA

An ISA for the investor created in journey 1. This is the first *wrapped* product
in the collection, and wrappers bring three things a GIA does not: extra
declarations, subscription tracking, and rules about who can hold one.

**Our client.** Alan Whitfield again, now using his annual ISA allowance with a
monthly savings plan alongside the GIA he already holds.

**Prerequisite.** Run journey **1** first — the ISA is opened for the investor
created there.""",

    diagram("## Orchestration", [
        ("section", "Account set-up — no new investor needed"),
        ("step", "1", "POST /accounts", "201  isaAccountId · PENDING"),
        ("step", "2", "POST /accounts/{id}/bank-accounts", "201"),
        ("step", "3", "POST /accounts/{id}/fees", "201  by fee code"),
        ("step", "4", "POST /accounts/{id}/money-movements", "201  monthly"),
        ("blank",),
        ("section", "Go live"),
        ("step", "5", "POST /accounts/{id}/activate", "200  status ACTIVE"),
    ]),

    "## Steps\n\n" + steps_table([
        ("1", "Open the ISA", "POST /accounts", "`isaAccountId` (PENDING)"),
        ("2", "Add a bank account", "POST /accounts/{accountId}/bank-accounts", "—"),
        ("3", "Add the adviser annual fee, by fee code", "POST /accounts/{accountId}/fees", "—"),
        ("4", "Add a monthly savings contribution", "POST /accounts/{accountId}/money-movements", "—"),
        ("5", "Activate the ISA", "POST /accounts/{accountId}/activate", "status ACTIVE"),
    ]),

    """\
## Things worth knowing

**An ISA is always individual.** There is no such thing as a joint ISA, so
`investors` holds exactly one `OWNER`. Contrast journey 2.

**Three declarations, not one.** A GIA needs only `TARGET_MARKET`. An ISA adds
`ISA_ACKNOWLEDGEMENT` — the investor has made the statutory ISA declaration — and
`ISA_NOT_IN_WRITING`, which records that the declaration was given other than in
writing, as it is when an adviser takes it over the phone or in a meeting. Send
all three.

**Subscriptions and transfers are counted differently.** New money paid in counts
against the annual subscription allowance; money transferred in from another ISA
manager does not. That distinction is why `currentYearSubscription` appears in two
places with two different fields: `amountNotTransfered` on the account records
current-year subscriptions made elsewhere and *not* being transferred, and
`amount` on a transfer records the current-year subscriptions that *are* coming
across. Getting these right is what keeps the client inside their allowance across
two managers in one tax year.

**The contribution is a savings plan, not a lump sum.** A monthly direct debit is
how most ISAs are funded, and it carries no `sourceOfFunds` — that field is for
one-off self contributions.

**No fee travels with this contribution.** Journey 1 charged an initial fee on the
lump sum and journey 2 spread one over instalments. Here the ongoing coded fee from
step 3 is the only adviser charge, which is the common arrangement for a regular
savings ISA.

**This journey has no transfer in.** For an ISA transfer, the transfer body would
carry `plan.type: "STOCKS_AND_SHARES"` (or `"CASH"` from a cash ISA) and, where
the client has subscribed with the ceding manager this tax year,
`currentYearSubscription` with the `amount` coming across and a `startDate` — for
which the collection derives `{{taxYearStart}}`, 6 April of the current tax year.
Journey 5 shows the transfer endpoint with a `plan.type` populated.""",
])


def isa_folder():
    journey = "3 · Stocks & Shares ISA"
    both = "1 · Retail GIA and 3 · Stocks & Shares ISA"

    account = request(
        "1 · Open the ISA",
        "POST", "accounts",
        """\
Opens a stocks and shares ISA for Alan.

**No new investor.** The account is opened against `{{retailInvestorId}}` from
journey 1. One investor can hold any number of accounts across products, and this
is the normal shape of a real book: one investor record, several accounts.

**`productId` is the ISA product**, `HIS`. Product IDs are exactly three
characters; confirm the code your tenant is entitled to, and change it here if it
differs.

**`investors` holds exactly one `OWNER`.** ISAs cannot be jointly held.

**`declarations` carries three entries** where a GIA carried one:

| Declaration | Records |
|-------------|---------|
| `TARGET_MARKET` | The product suits this client |
| `ISA_ACKNOWLEDGEMENT` | The investor has made the statutory ISA declaration |
| `ISA_NOT_IN_WRITING` | That declaration was given other than in writing |

**`currentYearSubscription.amountNotTransfered`** records how much the client has
already subscribed to an ISA elsewhere this tax year and is *not* transferring in.
The platform needs it to police the annual allowance: without it, it cannot know
about subscriptions made with another manager before the client moved. Omit it for
a client who has not subscribed anywhere else this year. Note the spelling of the
field, with one `r`.

The account opens `PENDING`.""",
        body={
            "productId": "HIS",
            "type": "ADVISED",
            "adviserId": "{{adviserId}}",
            "baseCurrency": "GBP",
            "marketSettlementCurrency": "GBP",
            "name": "Mr Alan James Whitfield",
            "externalReferences": [{"reference": "{{$guid}}", "provider": "CRM"}],
            "investors": [{"id": "{{retailInvestorId}}", "relationship": "OWNER"}],
            "model": {
                "id": "{{modelId}}",
                "providerId": "{{modelProviderId}}",
                "date": "{{modelDate}}",
            },
            "currentYearSubscription": {"amountNotTransfered": 4000},
            "declarations": [
                {"adviserId": "{{adviserId}}", "templateId": "TARGET_MARKET",
                 "acknowledgement": True},
                {"adviserId": "{{adviserId}}", "templateId": "ISA_ACKNOWLEDGEMENT",
                 "acknowledgement": True},
                {"adviserId": "{{adviserId}}", "templateId": "ISA_NOT_IN_WRITING",
                 "acknowledgement": True},
            ],
        },
        prerequest=guard(["retailInvestorId"], both),
        tests=capture(201, "isaAccountId", "body.id", "an account ID",
                      extra_tests=[[
                          'pm.test("Account is created in PENDING status", function () {',
                          '    pm.expect(body.status).to.eql("PENDING");',
                          "});",
                      ], [
                          'pm.test("ISA has a single owner", function () {',
                          "    pm.expect(body.investors).to.have.lengthOf(1);",
                          '    pm.expect(body.investors[0].relationship).to.eql("OWNER");',
                          "});",
                      ]]),
    )

    bank = request(
        "2 · Add a bank account",
        "POST", "accounts/{{isaAccountId}}/bank-accounts",
        """\
Registers a bank account against the ISA.

**Bank accounts belong to the investment account, not to the investor.** Alan
already has a bank account registered against his GIA in journey 1, but that
registration does not carry across — each investment account keeps its own list.
This step registers the account Alan wants his ISA direct debit collected from,
which he has chosen to be a different account from the one funding his GIA.

Everything else follows journey 1 step 5: `holders` names the investor, `primary`
marks it as the default, and for a GBP account `number` and `sortCode` are the
required pair.

The values are held in `{{isaBankNumber}}` and `{{isaBankSortCode}}`, which step 4
repeats.""",
        body={
            "name": "Mr Alan James Whitfield",
            "number": "{{isaBankNumber}}",
            "sortCode": "{{isaBankSortCode}}",
            "primary": True,
            "holders": [{"id": "{{retailInvestorId}}"}],
            "declarations": [
                {"adviserId": "{{adviserId}}", "templateId": "BANK_ACCT_VALIDATION",
                 "acknowledgement": True}
            ],
        },
        prerequest=guard(["retailInvestorId", "isaAccountId"], both),
        tests=assert_only(201, extra_tests=[[
            'pm.test("Bank account is registered against the ISA", function () {',
            '    pm.expect(body.accountId).to.eql(pm.collectionVariables.get("isaAccountId"));',
            "});",
        ]]),
    )

    fee = request(
        "3 · Add the adviser annual fee, by fee code",
        "POST", "accounts/{{isaAccountId}}/fees",
        """\
Applies the ongoing adviser charge from a pre-agreed banded fee scale.

This is the third and last way to express an adviser fee, after `percentage`
(journey 1) and `amount` (journey 2). A **fee code** points at a banded structure
held on the platform and agreed with SS&C in advance: a tiered scale that charges,
say, 1% on the first £250,000 and less above it. Codes are up to six characters.

Coded fees are how most firms charge in practice. The scale lives in one place, so
changing it does not mean patching every account, and the same code can be applied
across a client's whole portfolio.

**The response tells you what the code actually means.** A coded fee comes back
with a `bandDetails` object setting out the full band structure — the rate bands,
the invoice minimum and maximum, and the charging period. If you are surfacing
charges to an adviser or a client, read it from there rather than hard-coding your
own copy of the scale. `bandDetails` is read-only.

Set `{{adviserAnnualFeeCode}}` on the environment before sending this; SS&C
supplies the codes configured for your tenant.""",
        body={
            "fees": [
                {"type": "ADVISER_ANNUAL", "code": "{{adviserAnnualFeeCode}}",
                 "vatIncluded": True, "startDate": "{{today}}"}
            ],
            "declarations": [
                {"adviserId": "{{adviserId}}", "templateId": "AMENDMENT_CONSENT",
                 "acknowledgement": True}
            ],
        },
        prerequest=guard(["isaAccountId"], journey, environment=["adviserAnnualFeeCode"]),
        tests=assert_only(201, extra_tests=[[
            'pm.test("Coded adviser annual fee is active", function () {',
            '    pm.expect(body.fees[0].type).to.eql("ADVISER_ANNUAL");',
            '    pm.expect(body.fees[0].status).to.eql("ACTIVE");',
            "});",
        ], [
            'pm.test("Response explains the fee bands", function () {',
            "    pm.expect(body.fees[0].bandDetails).to.be.an(\"object\");",
            "});",
        ]]),
    )

    contribution = request(
        "4 · Add a monthly savings contribution",
        "POST", "accounts/{{isaAccountId}}/money-movements",
        """\
Sets up a £500 monthly savings plan into the ISA.

A regular savings plan is the typical way an ISA is funded, and the payload is
deliberately plainer than the earlier contributions:

- **`frequency: "MONTHLY"`** with **`contributionMethod: "DIRECT_DEBIT"`** — the
  platform collects on the mandate registered in step 2.
- **`payer: "SELF"`**. `EMPLOYER` is only valid on pension products.
- **No `fee` object.** The coded ongoing fee from step 3 is the only adviser
  charge; there is no initial charge on each monthly collection. Contrast journey 2,
  which spread an initial fee over twelve instalments.
- **No `sourceOfFunds`.** It applies to one-off self contributions only.
- **No `includeNonDailyAssets`.** It concerns one-off contributions and
  withdrawals, and defaults sensibly.

**Subscriptions count against the annual ISA allowance** — £20,000 in the current
rules, £500 a month using £6,000 of it. The platform tracks subscriptions against
the allowance, using `currentYearSubscription` on the account (step 1) to account
for anything the client subscribed elsewhere this tax year. Exceeding the
allowance is rejected at collection time, not here.

**`nextDate`** is the first collection date. This collection sets it to the first
of next month.""",
        body={
            "moneyMovements": [{
                "type": "CONTRIBUTIONS",
                "contributionMethod": "DIRECT_DEBIT",
                "payer": "SELF",
                "frequency": "MONTHLY",
                "value": {"amount": 500, "currency": "GBP"},
                "nextDate": "{{nextMonthFirst}}",
                "investmentInstruction": "INVEST_IN_MODEL",
                "bank": {
                    "number": "{{isaBankNumber}}",
                    "sortCode": "{{isaBankSortCode}}",
                },
            }],
            "declarations": [
                {"adviserId": "{{adviserId}}", "templateId": "AMENDMENT_CONSENT",
                 "acknowledgement": True}
            ],
        },
        prerequest=guard(["isaAccountId"], journey),
        tests=capture_number(201, "isaContributionId", "body.moneyMovements[0].id",
                            "a money movement ID",
                            extra_tests=[[
                                'pm.test("Monthly ISA savings plan is recorded", function () {',
                                '    pm.expect(body.moneyMovements[0].frequency).to.eql("MONTHLY");',
                                "    pm.expect(body.moneyMovements[0].value.amount).to.eql(500);",
                                "});",
                            ]]),
    )

    activate = request(
        "5 · Activate the ISA",
        "POST", "accounts/{{isaAccountId}}/activate",
        """\
Takes the ISA live.

The wrapper, the bank mandate, the coded ongoing charge and the savings plan are
all in place. Activation is the final step, as in every journey.

Alan now holds a GIA, a joint GIA and an ISA. Journey 4 opens a JISA for his son
with Alan as the registered contact, and journey 5 a SIPP.""",
        prerequest=guard(["isaAccountId"], journey),
        tests=assert_only(200, extra_tests=[[
            'pm.test("ISA is now ACTIVE", function () {',
            '    pm.expect(body.status).to.eql("ACTIVE");',
            "});",
        ]]),
    )

    return {
        "name": journey,
        "description": ISA_DESCRIPTION,
        "item": [account, bank, fee, contribution, activate],
    }


# --------------------------------------------------------------------------- #
# Folder 4 — JISA
# --------------------------------------------------------------------------- #

JISA_DESCRIPTION = "\n\n".join([
    """\
# 4 · Create a JISA

The shortest journey in the collection, and the one that shows what a child
investor looks like and what `REGISTERED_CONTACT` is for.

**Our client.** Thomas Whitfield, aged 10, Alan's son. The account is Thomas's —
he owns it and gets control of it at 18 — but he cannot operate it, so Alan is
recorded as the registered contact who instructs on his behalf.

**Prerequisite.** Run journey **1** first: Alan is the registered contact on this
account.""",

    diagram("## Orchestration", [
        ("step", "1", "POST /investors", "201  childInvestorId"),
        ("step", "2", "POST /accounts", "201  jisaAccountId · PENDING"),
        ("step", "3", "POST /accounts/{id}/activate", "200  status ACTIVE"),
    ]),

    "## Steps\n\n" + steps_table([
        ("1", "Create the child investor", "POST /investors", "`childInvestorId`"),
        ("2", "Open the JISA", "POST /accounts", "`jisaAccountId` (PENDING)"),
        ("3", "Activate the JISA", "POST /accounts/{accountId}/activate", "status ACTIVE"),
    ]),

    """\
## Things worth knowing

**A child investor is a much smaller record.** No marital status, no
`incomeAndInvestment`, no tax residency and no contact details — all of those are
mandatory for an adult and meaningless for a ten-year-old. What remains is
identity, one nationality and an address.

**Two investors, two different relationships.** Thomas is the `OWNER`; Alan is the
`REGISTERED_CONTACT`. This is the only journey that uses the second relationship,
and the only one where the account owner is not the person the firm deals with.
The registered contact must be someone with parental responsibility, and remains
the contact until the child turns 18.

**The money stays the child's.** A JISA cannot be withdrawn from before the child
is 18 except in narrow circumstances, and at 18 it converts to an adult ISA with
the child in full control. That is a materially different proposition from money
held in a parent's own ISA, and it is worth being explicit about it in whatever
you build on top of this.

**The allowance is separate.** A JISA has its own annual subscription allowance —
£9,000 in the current rules — which does not touch the registered contact's own
£20,000 ISA allowance.

**No bank account, fee or contribution here.** This journey is deliberately the
bare minimum needed to open and activate an account: three calls. In practice you
would add funding and fees exactly as journeys 1 to 3 do, with the same endpoints
and the same shapes — a JISA behaves like an ISA once it is open.

**`JISA_ACKNOWLEDGEMENT` and `JISA_NOT_IN_WRITING`** are the JISA equivalents of
the ISA declarations. Do not send the ISA ones on a JISA.""",
])


def jisa_folder():
    journey = "4 · JISA"
    both = "1 · Retail GIA and 4 · JISA"

    investor = request(
        "1 · Create the child investor",
        "POST", "investors",
        """\
Creates Thomas Whitfield, aged 10, as an investor in his own right.

Compare this payload with journey 1 step 1. A child's record omits a great deal:

| Field | Adult | Child |
|-------|-------|-------|
| `maritalStatus` | Required | Omit |
| `incomeAndInvestment` | Required | Omit |
| `territorialProfile.taxResidencies` | Required, with a `tin` | Omit |
| `contactDetails` | Required, including `email` | Optional |
| `territorialProfile.nationalities` | Required | Required |
| `addresses` | Required | Required |

**`title` is `MASTER`.** The enumeration also offers `MISS` for a girl.

**`dateOfBirth`** comes from `{{childDateOfBirth}}`, which the collection's
pre-request script sets to exactly ten years ago. That keeps this request valid
however long after publication you run it — a hard-coded date of birth would
eventually make Thomas an adult and the payload invalid.

The investor is created `PENDING`, as adults are. Note that the child is an
investor, not a dependant of another investor: the API has no concept of a family
group, and the relationship between Thomas and Alan exists only on the account
created in step 2.""",
        body={
            "adviserId": "{{adviserId}}",
            "type": "INDIVIDUAL",
            "externalReferences": [{"reference": "{{$guid}}", "provider": "CRM"}],
            "individual": {
                "title": "MASTER",
                "firstName": "Thomas",
                "middleName": "Alan",
                "surname": "Whitfield",
                "dateOfBirth": "{{childDateOfBirth}}",
                "gender": "MALE",
                "territorialProfile": {
                    "nationalities": [{"countryCode": "GB", "primary": True}],
                },
                "notificationPreferences": {"disableEmails": False, "disableSms": False},
            },
            "addresses": [{
                "premisesIdentifier": "24",
                "line1": "Beechwood Avenue",
                "town": "Altrincham",
                "county": "Cheshire",
                "countryCode": "GB",
                "postCode": "WA14 2QP",
                "primary": True,
            }],
            "declarations": [
                {"adviserId": "{{adviserId}}", "templateId": "IFA_FCA_AUTH", "acknowledgement": True}
            ],
        },
        tests=capture(201, "childInvestorId", "body.id", "an investor ID",
                      extra_tests=[[
                          'pm.test("Child investor is created in PENDING status", function () {',
                          '    pm.expect(body.status).to.eql("PENDING");',
                          "});",
                      ]]),
    )

    account = request(
        "2 · Open the JISA",
        "POST", "accounts",
        """\
Opens a junior ISA owned by Thomas, with Alan as the registered contact.

**This is the one place `REGISTERED_CONTACT` is used.** `investors` holds two
entries with different relationships:

- Thomas, `OWNER` — the account is his, and the money in it is his
- Alan, `REGISTERED_CONTACT` — the adult with parental responsibility who
  operates the account until Thomas turns 18

Getting these the wrong way round creates an account owned by the parent, which is
a different product with different tax treatment. The `relationship` enumeration
has only these two values, so there is no third option to reach for.

**`name` follows the individual convention** — title, first name, middle name,
surname — and names the *owner*, not the registered contact.

**Three declarations, the JISA set.** `TARGET_MARKET`, plus
`JISA_ACKNOWLEDGEMENT` and `JISA_NOT_IN_WRITING`. These mirror the ISA
declarations in journey 3 and are not interchangeable with them: a JISA sent with
`ISA_ACKNOWLEDGEMENT` is rejected. For a JISA the statutory declaration is made by
the registered contact on the child's behalf.

**`currentYearSubscription` is omitted.** Thomas has not subscribed to a JISA
elsewhere this tax year. Populate `amountNotTransfered` where the child has, so
the platform can police the £9,000 allowance.""",
        body={
            "productId": "JIS",
            "type": "ADVISED",
            "adviserId": "{{adviserId}}",
            "baseCurrency": "GBP",
            "marketSettlementCurrency": "GBP",
            "name": "Master Thomas Alan Whitfield",
            "externalReferences": [{"reference": "{{$guid}}", "provider": "CRM"}],
            "investors": [
                {"id": "{{childInvestorId}}", "relationship": "OWNER"},
                {"id": "{{retailInvestorId}}", "relationship": "REGISTERED_CONTACT"},
            ],
            "model": {
                "id": "{{modelId}}",
                "providerId": "{{modelProviderId}}",
                "date": "{{modelDate}}",
            },
            "declarations": [
                {"adviserId": "{{adviserId}}", "templateId": "TARGET_MARKET",
                 "acknowledgement": True},
                {"adviserId": "{{adviserId}}", "templateId": "JISA_ACKNOWLEDGEMENT",
                 "acknowledgement": True},
                {"adviserId": "{{adviserId}}", "templateId": "JISA_NOT_IN_WRITING",
                 "acknowledgement": True},
            ],
        },
        prerequest=guard(["retailInvestorId", "childInvestorId"], both),
        tests=capture(201, "jisaAccountId", "body.id", "an account ID",
                      extra_tests=[[
                          'pm.test("Child owns the account and the adult is the contact",',
                          "         function () {",
                          '    var byRelationship = {};',
                          "    body.investors.forEach(function (i) {",
                          "        byRelationship[i.relationship] = i.id;",
                          "    });",
                          '    pm.expect(byRelationship.OWNER)',
                          '        .to.eql(pm.collectionVariables.get("childInvestorId"));',
                          '    pm.expect(byRelationship.REGISTERED_CONTACT)',
                          '        .to.eql(pm.collectionVariables.get("retailInvestorId"));',
                          "});",
                      ]]),
    )

    activate = request(
        "3 · Activate the JISA",
        "POST", "accounts/{{jisaAccountId}}/activate",
        """\
Takes the JISA live.

Three calls from nothing to an active account — this is the floor for any product:
an investor, an account, an activation. Everything else in this collection is
detail layered on top of that spine.

To fund the JISA, add a bank account and a contribution before activating, exactly
as journey 3 does for the ISA. A JISA can also receive transfers in from another
JISA or from a Child Trust Fund, using the transfers endpoint with
`plan.type: "STOCKS_AND_SHARES"` or `"CASH"`.""",
        prerequest=guard(["jisaAccountId"], journey),
        tests=assert_only(200, extra_tests=[[
            'pm.test("JISA is now ACTIVE", function () {',
            '    pm.expect(body.status).to.eql("ACTIVE");',
            "});",
        ]]),
    )

    return {
        "name": journey,
        "description": JISA_DESCRIPTION,
        "item": [investor, account, activate],
    }


# --------------------------------------------------------------------------- #
# Folder 5 — SIPP
# --------------------------------------------------------------------------- #

SIPP_DESCRIPTION = "\n\n".join([
    """\
# 5 · Create a SIPP

The longest journey, and the one that introduces **third parties** — people and
organisations connected to an account who are not investors in it.

**Our client.** Alan Whitfield again, consolidating an old pension into a SIPP,
arranging for his employer to contribute monthly, and nominating his son Thomas as
the beneficiary of the pension on his death.

**Three parties, three roles.** Alan owns the account. His employer pays into it
and is a third party of type `EMPLOYER`. Thomas is nominated to receive the fund
and is a third party of type `BENEFICIARY`. Only Alan appears in `investors`.

**Prerequisites.** Run journey **1** for Alan. Journey **4** is not required — the
beneficiary is recorded by name and date of birth rather than by investor ID — but
running it first makes the family consistent.""",

    diagram("## Orchestration", [
        ("section", "The pension"),
        ("step", "1", "POST /accounts", "201  sippAccountId · PENDING"),
        ("blank",),
        ("section", "The employer — order matters here"),
        ("step", "2", "POST /accounts/{id}/third-parties", "201  employerThirdPartyId"),
        ("step", "3", "POST /accounts/{id}/bank-accounts", "201  held by the employer"),
        ("step", "4", "POST /accounts/{id}/money-movements", "201  payer EMPLOYER"),
        ("blank",),
        ("section", "The beneficiary and the transfer in"),
        ("step", "5", "POST /accounts/{id}/third-parties", "201  beneficiary"),
        ("step", "6", "POST /accounts/{id}/transfers", "201  plan.type SIPP"),
        ("blank",),
        ("section", "Go live"),
        ("step", "7", "POST /accounts/{id}/activate", "200  status ACTIVE"),
    ]),

    "## Steps\n\n" + steps_table([
        ("1", "Open the SIPP", "POST /accounts", "`sippAccountId` (PENDING)"),
        ("2", "Add the employer as a third party", "POST /accounts/{accountId}/third-parties",
         "`employerThirdPartyId`"),
        ("3", "Add the employer's bank account", "POST /accounts/{accountId}/bank-accounts", "—"),
        ("4", "Add a regular employer contribution", "POST /accounts/{accountId}/money-movements", "—"),
        ("5", "Add the child as a beneficiary", "POST /accounts/{accountId}/third-parties",
         "`beneficiaryThirdPartyId`"),
        ("6", "Add an inbound SIPP transfer", "POST /accounts/{accountId}/transfers", "—"),
        ("7", "Activate the SIPP", "POST /accounts/{accountId}/activate", "status ACTIVE"),
    ]),

    """\
## Things worth knowing

**Steps 2, 3 and 4 must run in that order.** The employer's bank account is held
*by the employer*, so it needs the third party's sequence number, which only
exists once step 2 has run. The contribution then references both the third party
and the bank account. This is the only hard ordering constraint in the collection
beyond investor-before-account.

**Third parties are numbered, not identified by a long ID.** `POST
/third-parties` returns each entry with a small integer `id` — 1, 2, 3 — that is
its sequence number within the account. That is the value a bank account holder or
a money movement refers to, and it is an integer in the response but a string in
`Movement.thirdPartyId` and `BankAccountHolder.id`. The test scripts here handle
the conversion.

**Third parties carry no declarations.** Every other write endpoint in this
collection accepts a `declarations` array; `POST /third-parties` does not, and the
schema rejects one if you send it.

**`POST` creates, it does not add.** Use `POST` for the *first* beneficiary or
employer on an account. Only one employer is permitted per account, and once any
beneficiary exists, further beneficiaries go through `PUT` (replace all) or `PATCH`
(amend). Power of attorney is the exception: `POST` may be used repeatedly.

**Beneficiary percentages must total 100.** One beneficiary at 100%, or several
splitting it. Nominating a beneficiary is an expression of wish — it guides the
scheme administrator's discretion on death rather than binding it, which is what
keeps the fund outside the estate for inheritance tax.

**`pensionDetails` is mandatory for a pension and rejected for anything else.**
Employment status, tax relief entitlement and intended retirement age drive tax
relief and illustrations.

**Employer contributions work differently from the client's own.** `payer:
"EMPLOYER"` is only valid on a pension product, carries no `sourceOfFunds`, and
gets no relief at source — the employer pays gross and claims corporation tax
relief itself, whereas a member contribution is paid net and the platform reclaims
basic-rate relief from HMRC.

**Pension transfers describe the ceding wrapper.** `plan.type` is mandatory for a
pension transfer — `SIPP` here, but the enumeration covers everything from a
`PERSONAL_PENSION_SCHEME` to a `SECTION_32_BUY_OUT`. Send the type the ceding
scheme actually is. `value.crystallised` records any already-crystallised element;
the uncrystallised part is calculated for you.

**Transferring a defined benefit pension is advice-heavy.** Where the ceding
scheme is a `DEFINED_BENEFITS_RETIREMENT_BENEFITS_SCHEME`, transferring out of
safeguarded benefits requires specialist permissions and an appropriate advice
process. The API will take the instruction; your firm's own controls decide
whether it should.""",
])


def sipp_folder():
    journey = "5 · SIPP"
    both = "1 · Retail GIA and 5 · SIPP"

    account = request(
        "1 · Open the SIPP",
        "POST", "accounts",
        """\
Opens a self-invested personal pension for Alan.

**`pensionDetails` is what makes this a pension.** The object is mandatory for a
pension product and rejected on anything else. Three fields are required:

| Field | Meaning |
|-------|---------|
| `employmentStatus` | Alan is `EMPLOYED`. `OTHER` requires `employmentStatusOther`. |
| `taxReliefEntitlement` | `UK_RELEVANT_EARNINGS` — he has earnings to relieve against, so contributions attract relief up to the lower of his earnings and the annual allowance. |
| `retirementAge` | The age he plans to retire, here 67. Drives projections and illustrations. |

`mpaaTriggeredDate` is also available and should be sent where the client has
already flexibly accessed a pension, because it cuts the annual allowance for
money purchase contributions sharply. Alan has not, so it is omitted.

**Declarations are `TARGET_MARKET` and `SIPP_ACKNOWLEDGEMENT`** — two, where a GIA
needs one and an ISA needs three.

**`investors` holds one `OWNER`.** Pensions are individual. The employer and the
beneficiary added later are third parties, not investors, and they never appear
here.

The account opens `PENDING`, and stays that way through the next five steps.""",
        body={
            "productId": "HWS",
            "type": "ADVISED",
            "adviserId": "{{adviserId}}",
            "baseCurrency": "GBP",
            "marketSettlementCurrency": "GBP",
            "name": "Mr Alan James Whitfield",
            "externalReferences": [{"reference": "{{$guid}}", "provider": "CRM"}],
            "investors": [{"id": "{{retailInvestorId}}", "relationship": "OWNER"}],
            "pensionDetails": {
                "employmentStatus": "EMPLOYED",
                "taxReliefEntitlement": "UK_RELEVANT_EARNINGS",
                "retirementAge": 67,
            },
            "model": {
                "id": "{{modelId}}",
                "providerId": "{{modelProviderId}}",
                "date": "{{modelDate}}",
            },
            "declarations": [
                {"adviserId": "{{adviserId}}", "templateId": "TARGET_MARKET",
                 "acknowledgement": True},
                {"adviserId": "{{adviserId}}", "templateId": "SIPP_ACKNOWLEDGEMENT",
                 "acknowledgement": True},
            ],
        },
        prerequest=guard(["retailInvestorId"], both),
        tests=capture(201, "sippAccountId", "body.id", "an account ID",
                      extra_tests=[[
                          'pm.test("Account is created in PENDING status", function () {',
                          '    pm.expect(body.status).to.eql("PENDING");',
                          "});",
                      ], [
                          'pm.test("Pension details are recorded", function () {',
                          "    pm.expect(body.pensionDetails.retirementAge).to.eql(67);",
                          "});",
                      ]]),
    )

    employer = request(
        "2 · Add the employer as a third party",
        "POST", "accounts/{{sippAccountId}}/third-parties",
        """\
Records Alan's employer on the pension, so it can contribute to it.

**A third party is anyone connected to the account who is not an investor in it.**
Three types are supported — `EMPLOYER`, `BENEFICIARY` and `POWER_OF_ATTORNEY` —
and one request can create several of any mix, up to ten.

**An employer is an organisation, so the payload looks different.** It carries
`companyName` and `companyRegistration` where a beneficiary carries `title`,
`firstName` and `surname`. `contactDetails` requires *both* `phone` and `email`
when present.

**Only one employer per account.** Use `POST` for the first one, and `PATCH` or
`PUT` to amend it afterwards. Sending a second employer by `POST` is rejected.

**No `declarations`.** Unlike almost every other write operation in this
collection, `ThirdPartiesHeader` has no `declarations` property and the schema
rejects unknown fields, so sending one produces a `400`.

**The response gives you a sequence number, not a long identifier.** `id` comes
back as a small integer — `1` for the first third party on the account. Steps 3
and 4 both need it: the bank account because the employer holds it, the
contribution because the employer pays it. The test script stores it in
`{{employerThirdPartyId}}`.""",
        body={
            "thirdParties": [{
                "type": "EMPLOYER",
                "companyName": "Marchford Systems Ltd",
                "companyRegistration": "09442671",
                "contactDetails": {
                    "phone": "01619334410",
                    "email": "payroll@marchfordsystems.example.co.uk",
                },
                "address": {
                    "premisesIdentifier": "7",
                    "line1": "Marchford House",
                    "line2": "Talbot Road",
                    "town": "Stretford",
                    "county": "Greater Manchester",
                    "countryCode": "GB",
                    "postCode": "M32 0FP",
                },
            }],
        },
        prerequest=guard(["sippAccountId"], journey),
        tests=capture_number(201, "employerThirdPartyId", "body.thirdParties[0].id",
                            "a third party sequence number",
                            extra_tests=[[
                                'pm.test("Employer is recorded on the account", function () {',
                                '    pm.expect(body.thirdParties[0].type).to.eql("EMPLOYER");',
                                "});",
                            ]]),
    )

    employer_bank = request(
        "3 · Add the employer's bank account",
        "POST", "accounts/{{sippAccountId}}/bank-accounts",
        """\
Registers the employer's bank account against the pension, so the monthly
contribution can be collected from it.

**`thirdParty: true` is the whole point of this request.** Where journeys 1 to 3
put an investor ID in `holders[].id`, this puts the employer's *sequence number*
from step 2 and flags the holder as a third party. The field is the same; what it
contains depends on the flag.

**`primary` is `false`.** The employer's account is not the account's default for
money flows — Alan's own would be, if this journey registered one. Only one bank
account per investment account should be primary.

**`name` is the company's name**, because the company is the holder. A direct
debit mandate has to be in the name of whoever holds the account it draws on,
which is why an employer contribution needs the employer's own bank details rather
than the member's.

The number and sort code are held in `{{employerBankNumber}}` and
`{{employerBankSortCode}}`, which step 4 repeats — money movements match a bank
account on those two values, not on any ID.""",
        body={
            "name": "Marchford Systems Ltd",
            "number": "{{employerBankNumber}}",
            "sortCode": "{{employerBankSortCode}}",
            "primary": False,
            "holders": [{"id": "{{employerThirdPartyId}}", "thirdParty": True}],
            "declarations": [
                {"adviserId": "{{adviserId}}", "templateId": "BANK_ACCT_VALIDATION",
                 "acknowledgement": True}
            ],
        },
        prerequest=guard(["sippAccountId", "employerThirdPartyId"], journey),
        tests=assert_only(201, extra_tests=[[
            'pm.test("Bank account is held by a third party", function () {',
            "    pm.expect(body.holders[0].thirdParty).to.eql(true);",
            "});",
        ]]),
    )

    contribution = request(
        "4 · Add a regular employer contribution",
        "POST", "accounts/{{sippAccountId}}/money-movements",
        """\
Sets up the employer's £1,000 monthly contribution to Alan's pension.

Two fields make this an employer contribution rather than a member one:

- **`payer: "EMPLOYER"`** — only valid on a pension product. Everything else in
  this collection uses `SELF`.
- **`thirdPartyId`** — the employer's sequence number from step 2, telling the
  platform *which* employer is paying. Note it is a string here, while the
  third-parties response returns `id` as an integer.

**`bank`** repeats the employer's account number and sort code from step 3. The
money comes from the employer's account, so the direct debit must draw on it.

**No `sourceOfFunds`.** It applies to one-off self contributions on retail
accounts. An employer contribution needs no such narrative.

**Tax treatment differs, and it matters for what you display.** An employer pays
gross and claims corporation tax relief itself, so £1,000 in is £1,000 invested. A
member contribution is paid net of basic-rate relief, which the platform reclaims
from HMRC and adds later — so £1,000 from Alan becomes £1,250 in the pension, but
not on day one. Do not present the two the same way.

**Both count against the annual allowance.** Employer and member contributions
together are tested against the client's annual allowance — £60,000 under current
rules, tapered for high earners and cut sharply once the money purchase annual
allowance is triggered. The platform does not police the client's total across
providers; that is the adviser's job.""",
        body={
            "moneyMovements": [{
                "type": "CONTRIBUTIONS",
                "contributionMethod": "DIRECT_DEBIT",
                "payer": "EMPLOYER",
                "frequency": "MONTHLY",
                "value": {"amount": 1000, "currency": "GBP"},
                "nextDate": "{{nextMonthFirst}}",
                "investmentInstruction": "INVEST_IN_MODEL",
                "thirdPartyId": "{{employerThirdPartyId}}",
                "bank": {
                    "number": "{{employerBankNumber}}",
                    "sortCode": "{{employerBankSortCode}}",
                },
                "fee": {"percentage": 0.5},
            }],
            "declarations": [
                {"adviserId": "{{adviserId}}", "templateId": "AMENDMENT_CONSENT",
                 "acknowledgement": True}
            ],
        },
        prerequest=guard(["sippAccountId", "employerThirdPartyId"], journey),
        tests=capture_number(201, "sippContributionId", "body.moneyMovements[0].id",
                            "a money movement ID",
                            extra_tests=[[
                                'pm.test("Contribution is paid by the employer", function () {',
                                '    pm.expect(body.moneyMovements[0].payer).to.eql("EMPLOYER");',
                                '    pm.expect(body.moneyMovements[0].frequency).to.eql("MONTHLY");',
                                "});",
                            ]]),
    )

    beneficiary = request(
        "5 · Add the child as a beneficiary",
        "POST", "accounts/{{sippAccountId}}/third-parties",
        """\
Nominates Thomas to receive the pension fund on Alan's death.

Same endpoint as step 2, different type — and a different shape of payload. A
`BENEFICIARY` is a person, so it carries `title`, `firstName` and `surname` where
the employer carried `companyName`, plus a `beneficiaryDetails` object:

| Field | Meaning |
|-------|---------|
| `relationship` | Free text, up to 30 characters — `"Son"` here |
| `percentage` | The share of the fund. All beneficiaries on an account must total 100. |
| `dateOfBirth` | Optional, but worth sending — it distinguishes people with the same name and shows the beneficiary is a minor |

**`contactDetails` are the registered contact's.** Thomas is ten and has no phone
or email of his own, so Alan's are recorded — which is who the scheme would
actually contact. Both `phone` and `email` are required when the object is present;
omit the whole object if you have neither.

**A nomination is an expression of wish, not an instruction.** It guides the scheme
administrator's discretion rather than binding it, and that discretion is what
keeps the fund outside the estate for inheritance tax. Beneficiaries should be
reviewed after any significant life event.

**`POST` is for the first beneficiaries only.** Once any exist on the account, use
`PUT` to replace the whole set — which is how you keep percentages totalling 100 —
or `PATCH` to amend one. A second `POST` is rejected.

As in step 2, no `declarations`: the schema does not accept them.""",
        body={
            "thirdParties": [{
                "type": "BENEFICIARY",
                "title": "MASTER",
                "firstName": "Thomas",
                "surname": "Whitfield",
                "contactDetails": {
                    "phone": "07700900183",
                    "email": "alan.whitfield@example.co.uk",
                },
                "beneficiaryDetails": {
                    "relationship": "Son",
                    "percentage": 100,
                    "dateOfBirth": "{{childDateOfBirth}}",
                },
                "address": {
                    "premisesIdentifier": "24",
                    "line1": "Beechwood Avenue",
                    "town": "Altrincham",
                    "county": "Cheshire",
                    "countryCode": "GB",
                    "postCode": "WA14 2QP",
                },
            }],
        },
        prerequest=guard(["sippAccountId"], journey),
        tests=capture_number(201, "beneficiaryThirdPartyId", "body.thirdParties[0].id",
                            "a third party sequence number",
                            extra_tests=[[
                                'pm.test("Beneficiary is nominated for the whole fund", function () {',
                                '    pm.expect(body.thirdParties[0].type).to.eql("BENEFICIARY");',
                                "    pm.expect(body.thirdParties[0].beneficiaryDetails.percentage)",
                                "        .to.eql(100);",
                                "});",
                            ]]),
    )

    transfer = request(
        "6 · Add an inbound SIPP transfer",
        "POST", "accounts/{{sippAccountId}}/transfers",
        """\
Brings £185,000 across from Alan's existing pension.

The endpoint is the same as journeys 1 and 2; what changes is that a pension
transfer must describe the wrapper it is leaving.

**`plan.type` is mandatory here.** It is `SIPP` in this example, but the
enumeration covers the whole range of UK arrangements — `PERSONAL_PENSION_SCHEME`,
`RETIREMENT_ANNUITY_CONTRACT`, `SECTION_32_BUY_OUT`, `AVC`, `QROPS` and more. Send
what the ceding scheme actually is, not the product it is arriving into; the
receiving scheme's obligations depend on it. Journeys 1 and 2 omit the field
because a GIA has no wrapper.

**`value.crystallised`** records how much of the transferring fund has already been
crystallised — put into drawdown, with the tax-free cash taken. It cannot exceed
the transfer amount, and the uncrystallised balance is calculated for you rather
than sent. Alan's pension is wholly uncrystallised, so the field is omitted.

**`type` is `CASH` and `isPartial` is `false`.** The ceding scheme sells the
holdings and sends the proceeds, and the old plan closes. An in-specie pension
transfer is possible — journey 2 shows the shape — and avoids being out of the
market, but needs both schemes to hold the same assets.

**`fee.percentage` is 0.25**, an initial adviser charge of a quarter of a percent
on the transferred value. Remember the scale: a transfer fee's `percentage` is
capped at 100, an account fee's at 1.

Set `{{transferPlanReference}}` and `{{cedingProviderId}}` on the environment
first — the plan number is validated against the ceding scheme's format. That
variable is shared with the transfers in journeys 1 and 2, so set it to the pension
plan being moved before you send this request.""",
        body={
            "transfers": [{
                "type": "CASH",
                "isPartial": False,
                "investmentInstruction": "INVEST_IN_MODEL",
                "value": {"amount": 185000, "currency": "GBP"},
                "fee": {"percentage": 0.25},
                "plan": {
                    "reference": "{{transferPlanReference}}",
                    "holderName": "Mr Alan James Whitfield",
                    "type": "SIPP",
                },
                "provider": {"id": "{{cedingProviderId}}"},
            }],
            "declarations": [
                {"adviserId": "{{adviserId}}", "templateId": "TRANSFR_IN", "acknowledgement": True}
            ],
        },
        prerequest=guard(["sippAccountId"], journey,
                         environment=["cedingProviderId", "transferPlanReference"]),
        tests=capture_number(201, "sippTransferId", "body.transfers[0].id", "a transfer ID",
                            extra_tests=[[
                                'pm.test("Full pension cash transfer in is created", function () {',
                                '    pm.expect(body.transfers[0].type).to.eql("CASH");',
                                "    pm.expect(body.transfers[0].isPartial).to.eql(false);",
                                '    pm.expect(body.transfers[0].plan.type).to.eql("SIPP");',
                                "});",
                            ]]),
    )

    activate = request(
        "7 · Activate the SIPP",
        "POST", "accounts/{{sippAccountId}}/activate",
        """\
Takes the pension live.

Six calls of set-up behind this one: the pension itself, the employer, the
employer's bank account, the employer's contribution, the beneficiary nomination
and the transfer in. All of it had to be in place first, which is why pensions are
the longest onboarding path of any product here.

**What comes after activation.** A pension's interesting life is decumulation, and
it runs through the same money-movements endpoint with different `type` values:
`FLEXI_ACCESS_PCLS` for tax-free cash, `FLEXI_ACCESS_INCOME` for drawdown income,
and `UFPLS` for uncrystallised funds pension lump sums. Those carry their own
requirements — a `DRAWDOWN_INCOME` declaration, and a copy of the client's P45 via
`copyP45Provided` so the right tax code is applied. They are out of scope for an
onboarding collection, but the endpoint you already know is where they happen.""",
        prerequest=guard(["sippAccountId"], journey),
        tests=assert_only(200, extra_tests=[[
            'pm.test("SIPP is now ACTIVE", function () {',
            '    pm.expect(body.status).to.eql("ACTIVE");',
            "});",
        ]]),
    )

    return {
        "name": journey,
        "description": SIPP_DESCRIPTION,
        "item": [account, employer, employer_bank, contribution, beneficiary,
                 transfer, activate],
    }


# --------------------------------------------------------------------------- #
# Folder 6 — Corporate GIA
# --------------------------------------------------------------------------- #

CORPORATE_GIA_DESCRIPTION = "\n\n".join([
    """\
# 6 · Create a GIA for a corporate investor

An account for a company rather than a person, and the one journey that needs no
individual investor at all.

**Our client.** Whitfield Technology Consulting Ltd, Alan's consultancy, investing
surplus cash from the business. The company wants the investment income paid out
to its bank account each month rather than reinvested, which is typical corporate
cash management: the portfolio is a place to hold reserves, and the income
supports the company's own cash flow.

**Independent of the other journeys.** No prerequisites — this journey creates its
own investor. It is the second folder you can run on a fresh environment, after
the quick start.""",

    diagram("## Orchestration", [
        ("step", "1", "POST /investors", "201  corporateInvestorId"),
        ("step", "2", "POST /accounts", "201  corporateGiaAccountId · PENDING"),
        ("step", "3", "POST /accounts/{id}/bank-accounts", "201"),
        ("step", "4", "PUT  /accounts/{id}/income-options", "200  income WITHDRAW"),
        ("blank",),
        ("section", "Go live"),
        ("step", "5", "POST /accounts/{id}/activate", "200  status ACTIVE"),
    ]),

    "## Steps\n\n" + steps_table([
        ("1", "Create the corporate investor", "POST /investors", "`corporateInvestorId`"),
        ("2", "Open the corporate GIA", "POST /accounts", "`corporateGiaAccountId` (PENDING)"),
        ("3", "Add the company bank account", "POST /accounts/{accountId}/bank-accounts", "—"),
        ("4", "Withdraw all investment income", "PUT /accounts/{accountId}/income-options",
         "income option in force"),
        ("5", "Activate the corporate GIA", "POST /accounts/{accountId}/activate", "status ACTIVE"),
    ]),

    """\
## Things worth knowing

**A corporate investor uses `corporate`, not `individual`.** The payload is much
smaller: a legal name, contact details and an address. No date of birth, no
gender, no occupation, no vulnerability records — those endpoints reject anything
that is not an `INDIVIDUAL` or a `COURT_APPOINTED_DEPUTY`.

**The same `corporate` object serves trusts.** `type` distinguishes them —
`CORPORATE` here, or one of nine trust types such as `BARE_TRUST` or
`DISCRETIONARY_TRUST` — but a trust's details go in either `trust` or `corporate`.
A bare trust is the usual wrapper for holding investments for a child outside a
JISA.

**An LEI is required, and it is declared.** A Legal Entity Identifier is a
20-character code identifying the company for transaction reporting; without one
a firm cannot report trades for it, and in practice cannot trade for it. It goes in
`territorialProfile.taxResidencies[].lei` — where an individual would put a `tin` —
and is backed by the `LEI_VALID` declaration. Where an entity genuinely does not
need one, send `LEI_NOT_REQ` instead and omit the LEI. Send one or the other.

**Corporates can only hold unwrapped accounts.** ISAs, JISAs and SIPPs are
individual by statute, so a GIA is the product. That also means no subscription
limits and no wrapper declarations — `TARGET_MARKET` alone.

**The account name is the organisation's name**, not a person's. This is the first
of the three naming conventions in the account `name` description, and the reason
the 50-character limit is worth checking against real company names, which run long.

**Income options are set through their own endpoint, with `PUT`.** `incomeOption`
appears on the account you read back, but it is read-only there — you cannot set
it on `POST /accounts`. `PUT /accounts/{accountId}/income-options` creates or
replaces it, which is why the same call works for a change of instruction later.

**Watch the bank account number format.** An income option's `accountNumber` must
be exactly 8 digits, while a registered bank account's `number` allows 5 to 15. If
you support unusual account numbers, an account that registers happily may still
be refused as an income destination.""",
])


def corporate_gia_folder():
    journey = "6 · Corporate GIA"

    investor = request(
        "1 · Create the corporate investor",
        "POST", "investors",
        """\
Creates Whitfield Technology Consulting Ltd as an investor.

**`corporate` replaces `individual`.** The object needs only `legalName` and
`contactDetails`, and the record as a whole is far smaller than a person's: there
is no date of birth, gender, marital status or income profile, because none of them
mean anything for a company. The suitability and target-market information an
adult individual must supply has no corporate equivalent in this API.

**The LEI goes where a person's `tin` goes.** `territorialProfile.taxResidencies`
takes one entry per tax residency; for a company that entry carries `lei` — a
20-character Legal Entity Identifier — instead of a taxpayer identification
number. Trades cannot be reported for a legal entity without one, so it is
effectively mandatory for a company that intends to invest.

**Two declarations.** `IFA_FCA_AUTH` as for any investor, plus `LEI_VALID`
confirming the adviser has verified the identifier. Where an entity genuinely does
not require an LEI, send `LEI_NOT_REQ` and omit the `lei` field — one or the other,
not both, not neither.

**`type` also covers trusts.** `CORPORATE` here; the enumeration includes nine
trust types, and a trust's details go in the `trust` object of the same shape. A
`BARE_TRUST` is how investments are commonly held for a child outside a JISA.

**No vulnerability or correspondence records.** Those endpoints accept only
`INDIVIDUAL` and `COURT_APPOINTED_DEPUTY` investors.

The LEI, company registration and bank details here are invented. A real corporate
onboarding needs the entity's actual LEI, which is validated.""",
        body={
            "adviserId": "{{adviserId}}",
            "type": "CORPORATE",
            "externalReferences": [{"reference": "{{$guid}}", "provider": "CRM"}],
            "corporate": {
                "legalName": "Whitfield Technology Consulting Ltd",
                "territorialProfile": {
                    "taxResidencies": [
                        {"countryCode": "GB", "lei": "213800QK5PJ8FQ9RTN31", "primary": True}
                    ],
                },
                "contactDetails": {
                    "contactPhone": "01619334488",
                    "email": "finance@whitfieldtech.example.co.uk",
                },
                "notificationPreferences": {"disableEmails": False, "disableSms": False},
            },
            "addresses": [{
                "premisesIdentifier": "Unit 12",
                "line1": "Brookfield Business Park",
                "line2": "Ashley Road",
                "town": "Altrincham",
                "county": "Cheshire",
                "countryCode": "GB",
                "postCode": "WA14 2LR",
                "primary": True,
            }],
            "declarations": [
                {"adviserId": "{{adviserId}}", "templateId": "IFA_FCA_AUTH",
                 "acknowledgement": True},
                {"adviserId": "{{adviserId}}", "templateId": "LEI_VALID",
                 "acknowledgement": True},
            ],
        },
        tests=capture(201, "corporateInvestorId", "body.id", "an investor ID",
                      extra_tests=[[
                          'pm.test("Corporate investor is created in PENDING status", function () {',
                          '    pm.expect(body.type).to.eql("CORPORATE");',
                          '    pm.expect(body.status).to.eql("PENDING");',
                          "});",
                      ]]),
    )

    account = request(
        "2 · Open the corporate GIA",
        "POST", "accounts",
        """\
Opens a general investment account for the company.

**`name` is the organisation's name.** The account `name` description sets out
three conventions — organisation name for a corporate or trust, title and names for
an individual, names joined by ` & ` for a joint account. This is the first of
them. Real company names run long, so check them against the 50-character limit.

**`investors` holds the company as `OWNER`.** A corporate investor links to its
account exactly as a person does; the `relationship` enumeration does not change.

**A GIA is the only option.** ISAs, JISAs and pensions are individual by statute,
so `TARGET_MARKET` is the only declaration needed — no wrapper rules apply. There
are no subscription limits either, which is part of why a GIA suits corporate
reserves.

**The company is taxed differently from a person**, and the API does not model
this: gains and income fall within corporation tax rather than capital gains tax
and dividend tax, and there is no annual exempt amount. It changes the advice, not
the payload.

The account opens `PENDING`.""",
        body={
            "productId": "GIA",
            "type": "ADVISED",
            "adviserId": "{{adviserId}}",
            "baseCurrency": "GBP",
            "marketSettlementCurrency": "GBP",
            "name": "Whitfield Technology Consulting Ltd",
            "externalReferences": [{"reference": "{{$guid}}", "provider": "CRM"}],
            "investors": [{"id": "{{corporateInvestorId}}", "relationship": "OWNER"}],
            "model": {
                "id": "{{modelId}}",
                "providerId": "{{modelProviderId}}",
                "date": "{{modelDate}}",
            },
            "declarations": [
                {"adviserId": "{{adviserId}}", "templateId": "TARGET_MARKET",
                 "acknowledgement": True}
            ],
        },
        prerequest=guard(["corporateInvestorId"], journey),
        tests=capture(201, "corporateGiaAccountId", "body.id", "an account ID",
                      extra_tests=[[
                          'pm.test("Account is created in PENDING status", function () {',
                          '    pm.expect(body.status).to.eql("PENDING");',
                          "});",
                      ]]),
    )

    bank = request(
        "3 · Add the company bank account",
        "POST", "accounts/{{corporateGiaAccountId}}/bank-accounts",
        """\
Registers the company's business bank account against the investment account.

**`holders` names the corporate investor.** A company holds its own bank account,
so the holder is the corporate investor's ID with no `thirdParty` flag — the flag
is for parties who are not investors in the account, like the employer in
journey 5.

**`primary` is `true`**, making this the default destination for money out. Step 4
names the account explicitly anyway, but a primary account should always be set.

**The number is 8 digits for a reason.** Step 4 pays investment income to this
account, and an income option's `accountNumber` must match `^[0-9]{8}$` exactly,
where a bank account's `number` accepts 5 to 15 digits. Registering a number that
cannot then be used as an income destination is an easy trap.

The values live in `{{corporateBankNumber}}` and `{{corporateBankSortCode}}`, which
step 4 repeats.""",
        body={
            "name": "Whitfield Technology Consulting Ltd",
            "number": "{{corporateBankNumber}}",
            "sortCode": "{{corporateBankSortCode}}",
            "primary": True,
            "holders": [{"id": "{{corporateInvestorId}}"}],
            "declarations": [
                {"adviserId": "{{adviserId}}", "templateId": "BANK_ACCT_VALIDATION",
                 "acknowledgement": True}
            ],
        },
        prerequest=guard(["corporateInvestorId", "corporateGiaAccountId"], journey),
        tests=assert_only(201, extra_tests=[[
            'pm.test("Bank account is registered against the corporate GIA", function () {',
            '    pm.expect(body.accountId)',
            '        .to.eql(pm.collectionVariables.get("corporateGiaAccountId"));',
            "});",
        ]]),
    )

    income = request(
        "4 · Withdraw all investment income",
        "PUT", "accounts/{{corporateGiaAccountId}}/income-options",
        """\
Instructs the platform to pay all investment income out to the company's bank
account instead of holding or reinvesting it.

**There are three things an account can do with income**, and `type` chooses:

| `type` | Effect | Also send |
|--------|--------|-----------|
| `CASH` | Income accumulates as cash in the account | — |
| `REINVEST` | Income is reinvested into the portfolio | `reinvestmentDate` |
| `WITHDRAW` | Income is paid out to a bank account | `withdrawalDate`, `withdrawalFrequency`, and the bank details |

**`WITHDRAW` needs the bank account spelled out.** `sortCode`, `accountNumber` and
`accountName` are given here rather than referencing the bank account registered in
step 3 — the same pattern as money movements, which match on number and sort code
rather than on an ID. They must correspond to a bank account already on the
investment account.

**`accountNumber` must be exactly 8 digits.** Stricter than the bank-account
endpoint, which allows 5 to 15.

**`withdrawalFrequency`** is `MONTHLY`, `QUARTERLY`, `HALF_YEARLY` or `YEARLY` —
note `YEARLY` here, where fees and money movements use `ANNUALLY` for the same
idea. Monthly income payments suit a company using its portfolio to support
operating cash flow.

**This is a `PUT`, and the only one in the collection.** It creates the income
option if there is none and replaces it if there is, so the same request serves a
later change of instruction. It returns `200`, not `201`, for the same reason.

**You cannot set this on `POST /accounts`.** The account's `incomeOption` is
read-only when you read the account back; this endpoint is the only way to set it.""",
        body={
            "incomeOption": {
                "type": "WITHDRAW",
                "withdrawalDate": "{{nextMonthFirst}}",
                "withdrawalFrequency": "MONTHLY",
                "sortCode": "{{corporateBankSortCode}}",
                "accountNumber": "{{corporateBankNumber}}",
                "accountName": "Whitfield Technology Consulting Ltd",
            },
        },
        prerequest=guard(["corporateGiaAccountId"], journey),
        tests=assert_only(200, extra_tests=[[
            'pm.test("All investment income is paid out monthly", function () {',
            '    pm.expect(body.incomeOption.type).to.eql("WITHDRAW");',
            '    pm.expect(body.incomeOption.withdrawalFrequency).to.eql("MONTHLY");',
            "});",
        ]]),
    )

    activate = request(
        "5 · Activate the corporate GIA",
        "POST", "accounts/{{corporateGiaAccountId}}/activate",
        """\
Takes the company's account live.

The investor, the account, the bank account and the income instruction are all in
place, so the account can be activated — the same final step as every other
journey, whoever owns the account.

That completes the collection: six journeys covering an individual, a couple, a
child, a pension with third parties, and a company. Folder **7 · Verify &
Troubleshoot** has read-only requests for inspecting anything they created.""",
        prerequest=guard(["corporateGiaAccountId"], journey),
        tests=assert_only(200, extra_tests=[[
            'pm.test("Corporate GIA is now ACTIVE", function () {',
            '    pm.expect(body.status).to.eql("ACTIVE");',
            "});",
        ]]),
    )

    return {
        "name": journey,
        "description": CORPORATE_GIA_DESCRIPTION,
        "item": [investor, account, bank, income, activate],
    }


# --------------------------------------------------------------------------- #
# Folder 7 — Verify & Troubleshoot
# --------------------------------------------------------------------------- #

VERIFY_DESCRIPTION = "\n\n".join([
    """\
# 7 · Verify & troubleshoot

Read-only requests for inspecting what the journeys created. Nothing here changes
anything, so they are safe to send at any point and in any order.

**They are pointed at journey 1 by default.** Each request reads
`{{giaAccountId}}` or `{{retailInvestorId}}`. To inspect a different account,
change the variable in the URL — `{{isaAccountId}}`, `{{sippAccountId}}`,
`{{corporateGiaAccountId}}` and the rest are all populated as you run the folders,
and the Variables tab on the collection lists them with their current values.""",

    """\
## What lives where

Reading an account back does **not** return everything attached to it. The
sub-resources have their own endpoints, and knowing which is which saves a lot of
guessing:

| To see | Send |
|--------|------|
| Status, model, linked investors, income option | `GET /accounts/{accountId}` |
| Registered bank accounts | `GET /accounts/{accountId}/bank-accounts` |
| Fees, including the bands behind a coded fee | `GET /accounts/{accountId}/fees` |
| Contributions and withdrawals | `GET /accounts/{accountId}/money-movements` |
| Transfers in and out, and their progress | `GET /accounts/{accountId}/transfers` |
| Employers, beneficiaries, attorneys | `GET /accounts/{accountId}/third-parties` |
| The investor's own record | `GET /investors/{investorId}` |
| Recorded vulnerabilities | `GET /investors/{investorId}/vulnerabilities` |

Declarations are write-only throughout: you send them, and they never come back in
a response.""",

    """\
## Reading an error

Failures return `application/problem+json` — RFC 9457 Problem Details — rather
than a bare message:

```json
{
  "type": "https://developer.hubwise.co.uk/errors/validation",
  "title": "Bad Request",
  "status": 400,
  "detail": "One or more validation errors occurred.",
  "errors": [
    { "code": "HWA-ACCOUNT-012", "message": "...", "field": "investors[0].id" }
  ]
}
```

Read `detail` first, then `errors` — each entry names the offending `field` and
carries a stable `code` worth logging and quoting to support.

| Response | Usually means |
|----------|---------------|
| `400` | A validation problem. The `errors` array names the field. Common causes: a missing or wrong declaration for the product, an unknown `modelId`, a bank account referenced by number and sort code that is not registered on the account, or a `POST` to an endpoint that only creates where records already exist. |
| `401` | The token has expired. Re-send *0 · Start Here › 1 · Get an access token*. |
| `403` | Valid credentials, but no entitlement to that adviser, product or model. |
| `404` | The ID in the path does not exist. Check what the variable actually holds. |
| `500` | Quote the `Request-Id` to SS&C — every request in this collection sends one. |""",
])


def verify_folder():
    def reader(name, path, description, requires, journey="the journeys", tests=None):
        return request(name, "GET", path, description,
                       prerequest=guard(requires, journey),
                       tests=tests or assert_only(200))

    return {
        "name": "7 · Verify & Troubleshoot",
        "description": VERIFY_DESCRIPTION,
        "item": [
            reader(
                "Get an investor",
                "investors/{{retailInvestorId}}",
                """\
Returns the investor record: identity, addresses, nationalities, tax residencies,
contact details and status.

Vulnerabilities and correspondence preferences are **not** included — they have
their own endpoints. Declarations are never returned, being write-only.

Watch `status`. An investor is created `PENDING` and moves to `ACTIVE` once SS&C's
onboarding checks pass. You do not have to wait for that to open an account, but a
`REFERRED` or `BLOCKED` investor needs attention before the relationship can
proceed.""",
                ["retailInvestorId"], "1 · Retail GIA",
            ),
            reader(
                "Get an investor's vulnerabilities",
                "investors/{{retailInvestorId}}/vulnerabilities",
                """\
Returns the vulnerable characteristics and service levels recorded for the
investor — the records created in journey 1 step 2.

Each entry pairs a characteristic with a service adjustment and carries its own
`startDate` and optional `expiryDate`. Expired records still appear, so filter on
the dates when deciding what applies today.

Consumer Duty expects a firm to act on what it knows about a client's
circumstances, so this endpoint is the one to call before any client
communication. `GET /investors/{investorId}/correspondences` does the same for
document format preferences.""",
                ["retailInvestorId"], "1 · Retail GIA",
            ),
            reader(
                "Get an account",
                "accounts/{{giaAccountId}}",
                """\
Returns the account: status, product, service level, currencies, name, the model
it is managed against, the linked investors and their relationships, the income
option in force, and — for an ISA or JISA — current-year subscription details.

Bank accounts, fees, money movements, transfers and third parties are all absent.
They are separate resources with their own endpoints, listed in this folder.

`status` is the field to check after activation: `PENDING` before,
`ACTIVE` after, along with an `activationDate`.""",
                ["giaAccountId"], "1 · Retail GIA",
            ),
            reader(
                "Get the bank accounts on an account",
                "accounts/{{giaAccountId}}/bank-accounts",
                """\
Lists the bank accounts registered against the investment account, with their
holders, currency, primary flag and validation status.

**Use this to debug a rejected money movement.** A movement's `bank` object has to
match the number and sort code of an account in this list. If a contribution comes
back `400`, compare what you sent against what is actually registered here.

`status` starts at `UNCHECKED` and becomes `ACTIVE` once validation completes.
`REFERRED` or `WAITING_FOR_CUSTOMER` means the details could not be verified
automatically. Validation does not block account activation, but it does block the
money moving.""",
                ["giaAccountId"], "1 · Retail GIA",
            ),
            reader(
                "Get the fees on an account",
                "accounts/{{giaAccountId}}/fees",
                """\
Lists the fees on the account, with their type, basis, status, charging period and
invoicing frequency.

**For a coded fee this is where the bands are.** `bandDetails` sets out the tiered
rates, the invoice minimum and maximum and the charging period behind the fee code
applied in journey 3 — the authoritative statement of what the client will actually
be charged. Read it from here rather than keeping your own copy of the scale.

System-managed fees appear alongside the adviser's own: product annual, platform
annual, platform initial and discretionary model management are all configured by
SS&C and cannot be created or changed through the API.

Change the account variable in the URL to `{{isaAccountId}}` to see the coded fee
from journey 3.""",
                ["giaAccountId"], "1 · Retail GIA",
            ),
            reader(
                "Get the money movements on an account",
                "accounts/{{giaAccountId}}/money-movements",
                """\
Lists the contributions and withdrawals set up on the account, one entry per
movement, with the amount, frequency, next date, bank details, fee and status.

`status` tells you where each one is: `NEW`, `ACTIVE`, `PENDING`, `COMPLETED` or
`ARCHIVED`. A one-off contribution completes; a regular one stays active with
`nextDate` rolling forward.

**`reference` appears here for regular direct debits** — the reference the
collection will show under. It is generated by the platform and cannot be set.

To change a regular movement, `PATCH
/accounts/{accountId}/money-movements/{moneyMovementId}` with the ID from this
list; to stop one, `DELETE` the same path.""",
                ["giaAccountId"], "1 · Retail GIA",
            ),
            reader(
                "Get the transfers on an account",
                "accounts/{{giaAccountId}}/transfers",
                """\
Lists transfers in and out, with type, direction, value, ceding provider, fee and
status.

**This is how you follow a transfer's progress.** Transfers are created `CREATED`
and move through `OPEN` as the two providers exchange instructions, to `COMPLETED`,
or to `REJECTED`, `CANCELLED`, `CLOSED` or `EXPIRED`. Nothing in the onboarding
journeys waits on a transfer — the account activates regardless — so this endpoint
is where you check whether the assets actually arrived, sometimes weeks later.

The response also carries the ceding provider's name and address, which you never
send; you send only `provider.id`.

`isElectronic` tells you whether the transfer is running through an electronic
service or being handled manually, which is the main driver of how long it takes.""",
                ["giaAccountId"], "1 · Retail GIA",
            ),
            reader(
                "Get the third parties on an account",
                "accounts/{{sippAccountId}}/third-parties",
                """\
Lists the employers, beneficiaries and attorneys on the account — for the SIPP
from journey 5, the employer and the beneficiary nomination.

**The `id` values here are the sequence numbers** that money movements and bank
account holders refer to. If an employer contribution or a third-party bank
account is being rejected, this is where to confirm the number you are quoting.

Check that beneficiary percentages still total 100 after any change. To amend the
set, `PUT` replaces all of them and `PATCH` updates individual entries by `id`.""",
                ["sippAccountId"], "5 · SIPP",
            ),
        ],
    }


# --------------------------------------------------------------------------- #
# Collection variables
# --------------------------------------------------------------------------- #

def collection_variables():
    def var(key, value, description, vtype="string"):
        return {"key": key, "value": value, "type": vtype, "description": description}

    return [
        # Captured at run time.
        var("accessToken", "", "Set by '0 · Start Here — Quick Start › 1 · Get an access token'."),
        var("quickStartInvestorId", "", "Set by the quick start."),
        var("quickStartAccountId", "", "Set by the quick start."),
        var("retailInvestorId", "", "Set by '1 · Retail GIA › 1'. Reused by journeys 2 to 5."),
        var("giaAccountId", "", "Set by '1 · Retail GIA › 4'."),
        var("giaContributionId", "", "Set by '1 · Retail GIA › 7'."),
        var("giaTransferId", "", "Set by '1 · Retail GIA › 8'."),
        var("jointInvestorId", "", "Set by '2 · Joint GIA › 1'."),
        var("jointGiaAccountId", "", "Set by '2 · Joint GIA › 2'."),
        var("jointGiaContributionId", "", "Set by '2 · Joint GIA › 5'."),
        var("jointGiaTransferId", "", "Set by '2 · Joint GIA › 6'."),
        var("isaAccountId", "", "Set by '3 · Stocks & Shares ISA › 1'."),
        var("isaContributionId", "", "Set by '3 · Stocks & Shares ISA › 4'."),
        var("childInvestorId", "", "Set by '4 · JISA › 1'."),
        var("jisaAccountId", "", "Set by '4 · JISA › 2'."),
        var("sippAccountId", "", "Set by '5 · SIPP › 1'."),
        var("employerThirdPartyId", "",
            "Set by '5 · SIPP › 2'. The employer's sequence number within the account, "
            "used by the bank account holder in step 3 and the contribution in step 4."),
        var("sippContributionId", "", "Set by '5 · SIPP › 4'."),
        var("beneficiaryThirdPartyId", "", "Set by '5 · SIPP › 5'."),
        var("sippTransferId", "", "Set by '5 · SIPP › 6'."),
        var("corporateInvestorId", "", "Set by '6 · Corporate GIA › 1'."),
        var("corporateGiaAccountId", "", "Set by '6 · Corporate GIA › 2'."),

        # Derived from today's date by the collection pre-request script.
        var("today", "", "Derived at run time. Today, as YYYY-MM-DD."),
        var("nextMonthFirst", "", "Derived at run time. The first of next month."),
        var("oneYearAhead", "", "Derived at run time. One year from today."),
        var("taxYearStart", "", "Derived at run time. 6 April of the current UK tax year."),
        var("childDateOfBirth", "", "Derived at run time. A date of birth ten years ago."),

        # Sample data shared between steps that must agree.
        var("quickStartBankNumber", "87654321", "Sample bank account number used by the quick start."),
        var("quickStartBankSortCode", "309894", "Sample sort code used by the quick start."),
        var("retailBankNumber", "50220369",
            "Alan Whitfield's sample bank account number. Registered in journey 1 step 5 and "
            "referenced by the money movement in step 7 - the two must match."),
        var("retailBankSortCode", "700125", "Sort code for the account above."),
        var("jointBankNumber", "60418822",
            "The Whitfields' sample joint bank account number. Registered in journey 2 step 3 "
            "and referenced by the contribution in step 5 - the two must match."),
        var("jointBankSortCode", "404784", "Sort code for the account above."),
        var("isaBankNumber", "31905544",
            "The sample bank account funding the ISA. Registered in journey 3 step 2 and "
            "referenced by the contribution in step 4 - the two must match."),
        var("isaBankSortCode", "182131", "Sort code for the account above."),
        var("employerBankNumber", "78113029",
            "The employer's sample bank account number. Registered in journey 5 step 3 and "
            "referenced by the contribution in step 4 - the two must match."),
        var("employerBankSortCode", "601613", "Sort code for the account above."),
        var("corporateBankNumber", "41028836",
            "The company's sample bank account number. Registered in journey 6 step 3 and "
            "referenced by the income option in step 4. Exactly 8 digits, because an "
            "income option's accountNumber allows no other length."),
        var("corporateBankSortCode", "231470", "Sort code for the account above."),
    ]


ENVIRONMENT = {
    "name": "SS&C Wealth API — Pilot/UAT",
    "values": [
        # ---- Connection ----
        {"key": "baseUrl", "value": "https://rest-qd.hubwise.co.uk/adviser/v2",
         "type": "default", "enabled": True},
        {"key": "tokenUrl", "value": "", "type": "default", "enabled": True},

        # ---- Credentials: supplied by SS&C, keep out of source control ----
        {"key": "clientId", "value": "", "type": "secret", "enabled": True},
        {"key": "clientSecret", "value": "", "type": "secret", "enabled": True},

        # ---- Reference data: supplied by SS&C for your tenant ----
        {"key": "adviserId", "value": "", "type": "default", "enabled": True},
        {"key": "modelId", "value": "", "type": "default", "enabled": True},
        {"key": "modelProviderId", "value": "", "type": "default", "enabled": True},
        {"key": "modelDate", "value": "", "type": "default", "enabled": True},
        {"key": "cedingProviderId", "value": "", "type": "default", "enabled": True},
        {"key": "adviserAnnualFeeCode", "value": "", "type": "default", "enabled": True},

        # ---- Transfers in: the plan number held at the ceding provider ----
        # Validated against the ceding provider's own format, so only a real one
        # will be accepted. Shared by every transfer step in the collection: set
        # it to the plan you are transferring before you send that step.
        {"key": "transferPlanReference", "value": "", "type": "default", "enabled": True},
    ],
    "_postman_variable_scope": "environment",
}


# --------------------------------------------------------------------------- #
# Build
# --------------------------------------------------------------------------- #

def build():
    collection = {
        "info": {
            "name": "SS&C Wealth API — Quick Start & User Journeys",
            "description": COLLECTION_DESCRIPTION,
            "schema": "https://schema.getpostman.com/json/collection/v2.1.0/collection.json",
        },
        "auth": {
            "type": "bearer",
            "bearer": [{"key": "token", "value": "{{accessToken}}", "type": "string"}],
        },
        "event": [{"listen": "prerequest", "script": COLLECTION_PREREQUEST}],
        "variable": collection_variables(),
        "item": [
            quick_start_folder(),
            retail_gia_folder(),
            joint_gia_folder(),
            isa_folder(),
            jisa_folder(),
            sipp_folder(),
            corporate_gia_folder(),
            verify_folder(),
        ],
    }

    # The source wraps its prose for readability; the shipped descriptions carry
    # one line per paragraph so they can be edited comfortably in Postman.
    collection = unwrap_descriptions(collection)

    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    for filename, payload in ((COLLECTION_FILE, collection), (ENVIRONMENT_FILE, ENVIRONMENT)):
        path = os.path.join(root, filename)
        with open(path, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(payload, handle, indent=2, ensure_ascii=False)
            handle.write("\n")
        print(f"wrote {filename}")

    requests = sum(len(f["item"]) for f in collection["item"])
    print(f"{len(collection['item'])} folders, {requests} requests")


if __name__ == "__main__":
    build()
