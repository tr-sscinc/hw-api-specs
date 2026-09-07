The goal is to generate a postman collection describing how our API works which we can give to our customers.   

This folder contains a yaml OpenAPI spec describing our wealth management API. Our customers are financial advisor/wealth management firms who use our platform for investor onboardingm, portfolio mamnagement and to execute investment instructions. We also intent the API to be used by third party software providers whose clients are advisors.

Alongside the OpenAPI spec, we want to be able to provide our customers with a postman collection containing a "quick start guide" and several end to end business user journeys. 

This postman collection will be an artefact that we will allow customers to download from our API developer portal and will be accessed and downloaded by developers working for the advisor firms and third party software providers. 

As such, the postman collection must be very well presented, with proper descriptions for the collection as a whole, and each user journey supported. It would be amazing to be able to have a diagram (mermaid?) included in the description for each user journey to help users understand the orchestration of the multiple calls necessary to transact these user journeys.

The following bullet list contains the user journeys that I would like you to produce and the associated steps. It would be lovely if you could consult your knowledge of the wealth management industry as well as this spec. 

**Create a retail general investment account (GIA)**
  - Create a retail investor
  - Create vulnerabilities for the retail investor
  - Create correspondences for the retail investor
  - Create Individual GIA
  - Add a bank account
  - Add an advisor annual fee by percentage
  - Add a one-off contribution
  - Add an inbound cash transfer
  - Activate the individual GIA

**Create a joint GIA**
  - Create a new investor to be the joint investor
  - Create a joint GIA with the retail investor created above
  - Add a joint bank account
  - Add an advisor annual fee by amount
  - Add a regular contribution
  - Add an inbound in-specie transfer
  - Active the joint GIA

**Create an ISA**
  - Create an ISA for the retail investor
  - Add a new bank account
  - Add an advisor annual fee by fee code
  - Add a monthly savings contribution
  - Activate the ISA account

**Create a JISA**
  - Create a child investor
  - Create a JISA account for the child investor and with the retail investor as the REGISTERED_CONTACT
  - Activate the JISA account

**Create a SIPP**
  - Create a SIPP account for the retail investor
  - Add a third party employer onto the SIPP account
  - Add the employer's bank account to the SIPP account
  - Create a regular contribution to the SIPP account from the employer's bank account
  - Add the child investor as a third party beneficiary to the SIPP account 
  - Add an inbound SIPP transfer
  - Activate the SIPP account

**Create a GIA for a corporate investor**
  - Create a corporate investor
  - Create a GIA for the corporate investor
  - Add a bank account
  - Set the account to withdraw all investment income into the bank account.
  - Activate the corporate GIA

As well as the OpenAPI spec, there is also a manually created postman collection that contains some of these user journeys. This is the file OpenAPI-examples-testing.postman_collection.json, and a postman environment file called DS.postman_environment.json. You can use the examples in the OpenAPI spec but you'll find many alternative values for many of the request properties in the postman collection.

