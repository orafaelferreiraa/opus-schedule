# GitHub Secrets Required

Configure these repository secrets before running the CI/CD workflow:

## Required for GitHub Actions authentication

- `AZURE_CLIENT_ID`
- `AZURE_TENANT_ID`
- `AZURE_SUBSCRIPTION_ID`

## Required for app runtime (injected into the Function App by `terraform apply`)

Secrets (repository **secrets**):

- `OPUSCLIP_API_KEY` — OpusClip REST API key.
- `OPUSCLIP_ORG_ID` — optional, depending on the Opus org setup.

Non-secret config (repository **variables**):

- `NOTIFICATION_EMAIL_TO` — recipient of the schedule summary e-mail.
- `NOTIFICATION_EMAIL_FROM` — sender on the verified ACS domain (default `noreply@orafaelferreira.com`).

The Function App reuses shared resources from `rg-jsearch` via Terraform data
sources, so their connection strings are resolved at apply time and do **not**
need to be stored as secrets: Storage (`stjobfinderprodrandonix`), Application
Insights (`appi-jobfinder-prod`), ACS Email (`acs-jobfinder-prod` +
`orafaelferreira.com`) and the Foundry account (`aif-jobfinder-prod-randonix`).

The Judge runs in `rules_only` by default (LLM dormant), so no Azure OpenAI key
is required. To enable `hybrid` later, grant the Function App identity the
`Cognitive Services OpenAI User` role on the Foundry account (managed identity)
or set `JUDGE_AZURE_OPENAI_API_KEY` and `JUDGE_AUTH_MODE=api_key`.

## Terraform remote state backend

State lives in the `azurerm` backend defined in `infra/terraform/backend.tf`
(resource group `rg-state-opus`, storage `stoopusstate`, container `statetf`).
The CI service principal must have **Storage Blob Data Contributor** on
`stoopusstate` (the backend uses Azure AD auth, not storage keys).

Recommended auth mode:

- Use GitHub OIDC with Azure federated credentials for `azure/login@v3`.
- Avoid long-lived service principal secrets when possible.

## Common pipeline failure and fix

If the pipeline fails on `Azure Login (OIDC)` even with the 3 Azure secrets set,
the most common cause is missing federated credential(s) in Microsoft Entra ID.

Create federated credentials for these subjects (replace with your repo if forked):

- `repo:orafaelferreiraa/opus-schedule:ref:refs/heads/main`
- `repo:orafaelferreiraa/opus-schedule:pull_request`

And ensure the service principal has at least these roles in the target scope:

- `Reader` (minimum for data lookups)
- `Contributor` (needed for terraform apply that creates/updates resources)

Optional environment variables for app runtime can remain in Key Vault and be referenced by Function App settings managed in Terraform.
