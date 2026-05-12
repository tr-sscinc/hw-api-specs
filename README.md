# Wesleyan API specification v0.3

## Changelog 0.3.1

 - Renamed SS&C Hubwise -> SS&C Wealth Platform
 - Added a set of new vulnerability service levels
 - Added new declaration template LEI_VALID and examples
 - Added 400 status response definition to POST /investors
 - Added 404 status response definition to GET /investors/{investorId}
 - Updated the examples for PATCH /investors/{investorId}
 - Added 400 status response definition to GET /investors/{investorId}/vulnerabilities
 - Added 400 status response definition to GET /investors/{investorId}/correspondences
 - Added endpoint DELETE /investors/{investorId}/taxations/{taxationId}
 - Added endpoint DELETE /investors/{investorId}/nationalities/{nationalityId}
 - Added endpoint DELETE /investors/{investorId}/addresses/{addressId}
 - Changed primary flag in the Address model to non-required / default to false
 - Changed templateId in the Declaration model to be an enumeration
 - Removed vulnerabilities and correspondences fields from the Investor model
 - Removed id, tenantid, adviserid, type, and status from the InvestorPatch model

## Changelog 0.3.0

 - Added operation GET /investors/{investorId} 
 - Added operation PATCH /investors/{investorId} 
 - Added operation GET /investors/{investorId}/vulnerabilities
 - Added operation PUT /investors/{investorId}/vulnerabilities
 - Added operation GET /investors/{investorId}/correspondences
 - Added operation PUT /investors/{investorId}/correspondences
 - Added a maxLength constraint to the investorId path parameter on operation POST /investors/{investorId}/vulnerabilities
 - Changed operationId for operation POST /investors/{investorId}/vulnerabilities from createVulnerabilities to createInvestorVulnerabilities
 - Added a maxLength constraint to the investorId path parameter on operation POST /investors/{investorId}/correspondences
 - Changed operationId for operation POST /investors/{investorId}/correspondences from createCorrespondences to createInvestorCorrespondences
 - Change to ErrorDetail schema - removal of property "jsonPath"
 - Addition of description and maxLength constraints to properties in the Error and ErrorDetail schemas 
 - Addition of new schema definitions to support PATCH operations
