data "azurerm_resource_group" "core" {
  name = var.resource_group_name
}

data "azurerm_service_plan" "existing" {
  name                = var.app_service_plan_name
  resource_group_name = data.azurerm_resource_group.core.name
}

data "azurerm_application_insights" "existing" {
  name                = var.application_insights_name
  resource_group_name = data.azurerm_resource_group.core.name
}

data "azurerm_storage_account" "existing" {
  name                = var.storage_account_name
  resource_group_name = data.azurerm_resource_group.core.name
}

data "azurerm_key_vault" "existing" {
  name                = var.key_vault_name
  resource_group_name = data.azurerm_resource_group.core.name
}

# Existing shared resources are read via data sources.
# The Function App below is created by Terraform.
# Only run terraform import if this Function App was already created outside Terraform.
resource "azurerm_linux_function_app" "lowopscast" {
  name                       = var.function_app_name
  resource_group_name        = data.azurerm_resource_group.core.name
  location                   = var.location
  service_plan_id            = data.azurerm_service_plan.existing.id
  storage_account_name       = data.azurerm_storage_account.existing.name
  storage_account_access_key = data.azurerm_storage_account.existing.primary_access_key

  site_config {
    application_stack {
      python_version = "3.13"
    }
  }

  app_settings = {
    FUNCTIONS_WORKER_RUNTIME              = "python"
    APPLICATIONINSIGHTS_CONNECTION_STRING = data.azurerm_application_insights.existing.connection_string
    OTEL_SERVICE_NAME                     = "func-lowopscast-prod"
    JUDGE_MODE                            = "off"
    JUDGE_PROVIDER                        = "foundry"
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

  tags = {
    project    = "lowopscast"
    managed_by = "terraform"
  }
}
