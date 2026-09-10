# hw-api-specs

Changelog for v0.8.23 API spec

- Removed testMode query param throughout
- Added 202 response for create bank account
- Removed nullable fields throughout
- Changed account status XX3 to TRADING_SUSPENDED_DATA
- Remove 204 responses in get fees, money movements, third parties and transfers endpoints 
- Added MIS examples to pension and non-pension illutrations endpoints

Changelog for v0.8.22 API spec

- Added pension illustrations

Changelog for v0.8.21 API spec

- Added retrieve raise cash instructions endpoint, returning the instructions as an array
- Consolidated the raise cash instruction schemas into a single `RaiseCashInstruction`, and added a `reason` field returned for failed and rejected instructions

Changelog for v0.8.20 API spec

- Added intra-account transfers endpoints
- Added get Investment Instruction
- Restructured tags to clarity
- Fixed marital statuses OTHER_DEPENDANT and UNDISCLOSED

Changelog for v0.8.19 API spec

- Remove reference field from money movement
- Added illustration investor properties

Changelog for v0.8.18 API spec

- Added create raise cash instruction endpoint
- Added RaiseCashInstruction and RaiseCashInstructionResponse schemas

Changelog for v0.8.17 API spec

- Added ring-fence cash endpoints for accounts

Changelog for v0.8.16 API spec

- Added MIS transfers support for creating transfers
- Added read-only id field to MovementAllocation schema
- Added MIS cash transfer examples 
- Added description for INSPECIE single sub-account constraint
- Added error example for allocation validation failures
- Changed POST /accounts/{accountId}/transfers response status from 200 to 201

Changelog for v0.8.15 API spec

- Update API response for retire the old error format
- Updated get fees allocation for MIS accounts, only info for the specified primary or sub-account is shown
- Updated patch fees for MIS accounts so only the specified primary or sub-account is archived
- Create fees are only on sub-accounts and are of valid types

Changelog for v0.8.14 API spec

- Added money movements MIS changes
- Addressed logical issues with some descriptions
- Restrict investorId / advisorId to max length 11
- Added Executed Trades endpoint
- Removed old error format

Changelog for v0.8.13 API spec

- Corrected the Investor status enumerations

Changelog for v0.8.12 API spec

 - Made income option in account read-only
 - Added delete money movements endpoint
 - Removed x-api-key security scheme 

Changelog for v0.8.11 API spec

 - create account updated for MIS
 - removed is maximum for UFPLS and 
 - allow is maximum value for PCLS and Income 

Changelog for v0.8.10 API spec

 - Updated portfolio adjustments endpoint parameter validation and response description

Changelog for v0.8.9 API spec

 - Added inter-account transfers endpoints

Changelog for v0.8.8 API spec

 - Added account status updates to PATCH /accounts/{accountId} 
 - Added non-success responses on PATCH /accounts/{accountId}
 - Added investor status updates to PATCH /investors/{investorId} 
 - Added non-success responses on PATCH /investors/{investorId}

Changelog for v0.8.7 API spec

 - Added descriptions for the GET investor and account endpoints
 - Updated investor email field description to be optional for children
 - Updated investor POST, PATCH and GET examples
 - Added descriptions for the PUT vulnerability and correspondence endpoints
 - Added server information for QI environment
 - Added RFC9457 Problem Details example responses

Changelog for v0.8.6 API spec

 - Added Illustrations endpoints 

Changelog for v0.8.5 API spec

 - Added Fee Groups endpoints 

Changelog for v0.8.4 API spec

 - Added investment instructions endpoint
  
Changelog for v0.8.3 API spec 

 - Added third party relationships
 - Added primary bank account flag
 - Added JISA example
 - Added amountNotTransfered field for ISA accounts
 - Renamed startDate -> nextDate for movements
 - Added XX3 account status
 - Removed declarations from responses
 - Removed provider name and address in create transfer request example
 - Renamed SS&C Hubwise -> SS&C Wealth Platform
 - Fixed JISA examples
 - Added investor subresource delete endpoints
 - Updated the investor patch examples
 - Added new investor vulnerability service levels 
 - Added portfolio adjustments endpoint
 - Added LEI_VALID declaration for corporate and trust investors
 - Added enum for declarations

Changelog for v0.8.1 API spec

 - Added missing responses and fixed advisorId -> adviserId
 - Income options changes
 - Declarations are now write only not read only
 - API spec version number to 0.8
 - Removed vulnerability info from GET investor response
 - Removed bank accounts from GET account response
 - Added GET bank accounts endpoint
 - Consolidate API specs so we have only one
 - reordered the endpoints to be in a logical order
 - remove investor vulnerabilities and correspondences deletes
 - resolve money movement PATCH example 2
 - Add PATCH money movements
 - Add PATCH fees
 - Added PATCH account
 - Add full withdrawals
 - fixed a typo in the decscriptions
 - Rename completed to status in fees endpoints
 - added source of funds
 - Added PATCH investor and PUT vulnerability and PUT correspondences
 - read-only decs and reinstated vulnerabilities on investor model