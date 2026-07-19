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

locals {
  resolved_storage_account_name = var.storage_account_name != "" ? var.storage_account_name : "stlowops${random_string.storage_suffix.result}"
  resolved_function_app_name    = var.function_app_name != "" ? var.function_app_name : "func-lowopscast-${random_string.function_suffix.result}"
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

  tags = local.common_tags
}
