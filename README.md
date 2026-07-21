# hw-api-specs

Changelog for v0.8.14 API spec

- Added money movements MIS changes
- Addressed logical issues with some descriptions
- Restrict investorId / advisorId to max length 11

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

 - Added account status updates to PATCH /accounts/{accountId} (HWIT-5629, HWIT-6458)
 - status now accepts ACTIVE, DECEASED, TRADING_SUSPENDED, INTENTION_TO_CLOSE, NON_UK_RESIDENT
 - Documented 400/401/403/404/500 responses on PATCH /accounts/{accountId}, including the HWA-ACCOUNT-038 status error
 - Added investor status updates to PATCH /investors/{investorId} (HWIT-5629, HWIT-6460)
 - InvestorPatch.status now accepts INCEPTED, DECEASED, NON_UK_RESIDENT
 - Documented 400 validation (HWA-EXCEPTION-001) and business-logic (HWA-INVESTOR-023) responses on PATCH /investors/{investorId}

Changelog for v0.8.7 API spec

 - Added descriptions for the GET investor and account endpoints
 - Updated investor email field description to be optional for childrem
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
 - Income options HWIT-8413 and HWIT-8679
 - Declarations are now write only not read only
 - API spec version number to 0.8
 - Removed vulnerability info from GET investor response
 - Removed bank accounts from GET account response
 - Added GET bank accounts endpoint (HWIT-8411)
 - Consolidate API specs so we have only one
 - reordered the endpoints to be in a logical order
 - remove investor vulnerabilities and correspondences deletes
 - resolve money movement PATCH example 2
 - Add PATCH money movements
 - Add PATCH fees
 - Added PATCH account
 - HWIT-7844: add full withdrawals
 - fixed a typo in the decscriptions
 - HWIT-8550: Rename completed to status in fees endpoints
 - added source of funds
 - Added PATCH investor and PUT vulnerability and PUT correspondences
 - read-only decs and reinstated vulnerabilities on investor model