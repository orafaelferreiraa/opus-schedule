resource "random_string" "storage_suffix" {
  length  = 6
  special = false
  upper   = false
  numeric = true
}

resource "random_string" "function_suffix" {
  length  = 6
  special = false
  upper   = false
  numeric = true
}

resource "random_string" "key_vault_suffix" {
  length  = 6
  special = false
  upper   = false
  numeric = true
}

resource "random_string" "foundry_suffix" {
  length  = 6
  special = false
  upper   = false
  numeric = true
}

data "azurerm_client_config" "current" {}

locals {
  resolved_storage_account_name = var.storage_account_name != "" ? var.storage_account_name : "stlowops${random_string.storage_suffix.result}"
  resolved_function_app_name    = var.function_app_name != "" ? var.function_app_name : "func-lowopscast-${random_string.function_suffix.result}"
  resolved_key_vault_name       = var.key_vault_name != "" ? var.key_vault_name : "kvlowops${random_string.key_vault_suffix.result}"
  resolved_foundry_account_name = var.foundry_account_name != "" ? var.foundry_account_name : "aoailowops${random_string.foundry_suffix.result}"
  using_managed_identity_judge  = var.judge_auth_mode == "managed_identity"
  using_api_key_judge           = var.judge_auth_mode == "api_key"
  common_tags = {
    project    = "lowopscast"
    managed_by = "terraform"
  }
}

resource "azurerm_resource_group" "core" {
  name     = var.resource_group_name
  location = var.location
  tags     = local.common_tags
}

resource "azurerm_service_plan" "core" {
  name                = var.app_service_plan_name
  resource_group_name = azurerm_resource_group.core.name
  location            = azurerm_resource_group.core.location
  os_type             = "Linux"
  sku_name            = var.app_service_plan_sku
  tags                = local.common_tags
}

resource "azurerm_application_insights" "core" {
  name                = var.application_insights_name
  location            = azurerm_resource_group.core.location
  resource_group_name = azurerm_resource_group.core.name
  application_type    = "web"
  tags                = local.common_tags
}

resource "azurerm_storage_account" "core" {
  name                            = local.resolved_storage_account_name
  resource_group_name             = azurerm_resource_group.core.name
  location                        = azurerm_resource_group.core.location
  account_tier                    = "Standard"
  account_replication_type        = var.storage_replication_type
  allow_nested_items_to_be_public = false
  min_tls_version                 = "TLS1_2"
  tags                            = local.common_tags
}

resource "azurerm_cognitive_account" "foundry" {
  name                = local.resolved_foundry_account_name
  location            = azurerm_resource_group.core.location
  resource_group_name = azurerm_resource_group.core.name
  kind                = "OpenAI"
  sku_name            = "S0"

  custom_subdomain_name         = local.resolved_foundry_account_name
  public_network_access_enabled = true

  tags = local.common_tags
}

resource "azurerm_cognitive_deployment" "judge_primary" {
  name                 = var.judge_primary_model
  cognitive_account_id = azurerm_cognitive_account.foundry.id

  model {
    format  = "OpenAI"
    name    = var.judge_primary_model_name
    version = var.judge_primary_model_version
  }

  sku {
    name     = var.judge_primary_sku_name
    capacity = var.judge_primary_sku_capacity
  }
}

resource "azurerm_cognitive_deployment" "judge_fallback" {
  name                 = var.judge_fallback_model
  cognitive_account_id = azurerm_cognitive_account.foundry.id

  model {
    format  = "OpenAI"
    name    = var.judge_fallback_model_name
    version = var.judge_fallback_model_version
  }

  sku {
    name     = var.judge_fallback_sku_name
    capacity = var.judge_fallback_sku_capacity
  }
}

resource "azurerm_key_vault" "core" {
  name                = local.resolved_key_vault_name
  location            = azurerm_resource_group.core.location
  resource_group_name = azurerm_resource_group.core.name
  tenant_id           = data.azurerm_client_config.current.tenant_id
  sku_name            = "standard"

  soft_delete_retention_days = 7
  purge_protection_enabled   = false

  tags = local.common_tags
}

resource "azurerm_key_vault_access_policy" "deployer" {
  key_vault_id = azurerm_key_vault.core.id
  tenant_id    = data.azurerm_client_config.current.tenant_id
  object_id    = data.azurerm_client_config.current.object_id

  secret_permissions = [
    "Get",
    "List",
    "Set",
    "Delete",
    "Purge",
    "Recover",
  ]
}

resource "azurerm_key_vault_secret" "opusclip_api_key" {
  key_vault_id = azurerm_key_vault.core.id
  name         = "opusclip-api-key"
  value        = var.opusclip_api_key

  depends_on = [azurerm_key_vault_access_policy.deployer]
}

resource "azurerm_key_vault_secret" "acs_connection_string" {
  key_vault_id = azurerm_key_vault.core.id
  name         = "acs-connection-string"
  value        = var.acs_connection_string

  depends_on = [azurerm_key_vault_access_policy.deployer]
}

resource "azurerm_key_vault_secret" "notification_email_to" {
  key_vault_id = azurerm_key_vault.core.id
  name         = "notification-email-to"
  value        = var.notification_email_to

  depends_on = [azurerm_key_vault_access_policy.deployer]
}

resource "azurerm_key_vault_secret" "notification_email_from" {
  key_vault_id = azurerm_key_vault.core.id
  name         = "notification-email-from"
  value        = var.notification_email_from

  depends_on = [azurerm_key_vault_access_policy.deployer]
}

# This stack is intentionally isolated and provisions its own shared resources.
resource "azurerm_linux_function_app" "lowopscast" {
  name                                           = local.resolved_function_app_name
  resource_group_name                            = azurerm_resource_group.core.name
  location                                       = var.location
  service_plan_id                                = azurerm_service_plan.core.id
  storage_account_name                           = azurerm_storage_account.core.name
  storage_account_access_key                     = azurerm_storage_account.core.primary_access_key
  https_only                                     = true
  ftp_publish_basic_authentication_enabled       = false
  webdeploy_publish_basic_authentication_enabled = false

  site_config {
    ftps_state          = "Disabled"
    minimum_tls_version = "1.2"

    application_stack {
      python_version = var.function_python_version
    }
  }

  app_settings = {
    FUNCTIONS_WORKER_RUNTIME              = "python"
    APPLICATIONINSIGHTS_CONNECTION_STRING = azurerm_application_insights.core.connection_string
    OTEL_SERVICE_NAME                     = local.resolved_function_app_name
    OPUSCLIP_API_KEY                      = "@Microsoft.KeyVault(SecretUri=${azurerm_key_vault_secret.opusclip_api_key.versionless_id})"
    ACS_CONNECTION_STRING                 = "@Microsoft.KeyVault(SecretUri=${azurerm_key_vault_secret.acs_connection_string.versionless_id})"
    NOTIFICATION_EMAIL_TO                 = "@Microsoft.KeyVault(SecretUri=${azurerm_key_vault_secret.notification_email_to.versionless_id})"
    NOTIFICATION_EMAIL_FROM               = "@Microsoft.KeyVault(SecretUri=${azurerm_key_vault_secret.notification_email_from.versionless_id})"
    JUDGE_MODE                            = "rules_only"
    JUDGE_AUTH_MODE                       = var.judge_auth_mode
    JUDGE_PROVIDER                        = "foundry"
    JUDGE_AZURE_OPENAI_ENDPOINT           = azurerm_cognitive_account.foundry.endpoint
    JUDGE_MODEL_DEPLOYMENT_PRIMARY        = var.judge_primary_model
    JUDGE_MODEL_DEPLOYMENT_FALLBACK       = var.judge_fallback_model
    JUDGE_API_VERSION                     = "2025-01-01-preview"
    JUDGE_THRESHOLD                       = "70"
    JUDGE_INCLUDE_REVIEW_IN_DRY_RUN       = "true"
    JUDGE_TIMEOUT_MS                      = "12000"
    JUDGE_MAX_RETRIES                     = "2"
  }

  identity {
    type = "SystemAssigned"
  }

  tags = local.common_tags
}

resource "azurerm_key_vault_access_policy" "function_app" {
  key_vault_id = azurerm_key_vault.core.id
  tenant_id    = data.azurerm_client_config.current.tenant_id
  object_id    = azurerm_linux_function_app.lowopscast.identity[0].principal_id

  secret_permissions = [
    "Get",
    "List",
  ]
}

resource "azurerm_role_assignment" "judge_foundry_inference" {
  scope                = azurerm_cognitive_account.foundry.id
  role_definition_name = "Cognitive Services OpenAI User"
  principal_id         = azurerm_linux_function_app.lowopscast.identity[0].principal_id
}
