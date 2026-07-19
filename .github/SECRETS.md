# GitHub Secrets Required

Configure these repository secrets before running the CI/CD workflow:

## Required for GitHub Actions authentication

- `AZURE_CLIENT_ID`
- `AZURE_TENANT_ID`
- `AZURE_SUBSCRIPTION_ID`

## Required for app runtime (not required to run terraform plan/apply itself)

- `JUDGE_AZURE_OPENAI_ENDPOINT`
- `JUDGE_AZURE_OPENAI_API_KEY`
- `OPUSCLIP_API_KEY`
- `OPUSCLIP_ORG_ID` (optional depending on Opus org setup)

Recommended auth mode:

- Use GitHub OIDC with Azure federated credentials for `azure/login@v2`.
- Avoid long-lived service principal secrets when possible.

## Common pipeline failure and fix

If the pipeline fails on `Azure Login (OIDC)` even with the 3 Azure secrets set,
the most common cause is missing federated credential(s) in Microsoft Entra ID.

Create federated credentials for these subjects:

- `repo:ORGANIZATION/REPOSITORY:ref:refs/heads/main`
- `repo:ORGANIZATION/REPOSITORY:pull_request`

And ensure the service principal has at least these roles in the target scope:

- `Reader` (minimum for data lookups)
- `Contributor` (needed for terraform apply that creates/updates resources)

Optional environment variables for app runtime can remain in Key Vault and be referenced by Function App settings managed in Terraform.
