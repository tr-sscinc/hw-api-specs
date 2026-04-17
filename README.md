# Wesleyan API specification v0.3

## Changelog

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
