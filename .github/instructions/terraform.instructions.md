---
applyTo: "infra/terraform/**/*.tf"
---

# Terraform Change Standards

- Keep infrastructure changes explicit and minimal.
- Maintain compatibility with versions defined in infra/terraform/versions.tf.
- Prefer additive and idempotent updates over disruptive replacements.

# Validation Sequence

- terraform fmt -recursive
- terraform init
- terraform validate
- terraform plan with required subscription variable

# Azure Context

- CI uses OIDC secrets AZURE_CLIENT_ID, AZURE_TENANT_ID, AZURE_SUBSCRIPTION_ID.
- Treat auth and subscription access errors as separate categories in diagnostics.
