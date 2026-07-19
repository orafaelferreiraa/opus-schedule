# GitHub Secrets Required

Configure these repository secrets before running the CI/CD workflow:

- `AZURE_CLIENT_ID`
- `AZURE_TENANT_ID`
- `AZURE_SUBSCRIPTION_ID`
- `JUDGE_AZURE_OPENAI_ENDPOINT`
- `JUDGE_AZURE_OPENAI_API_KEY`
- `OPUSCLIP_API_KEY`
- `OPUSCLIP_ORG_ID`

Recommended auth mode:

- Use GitHub OIDC with Azure federated credentials for `azure/login@v2`.
- Avoid long-lived service principal secrets when possible.

Optional environment variables for app runtime can remain in Key Vault and be referenced by Function App settings managed in Terraform.
