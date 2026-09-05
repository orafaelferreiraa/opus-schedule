resource "random_string" "function_suffix" {
  length  = 6
  special = false
  upper   = false
  numeric = true
}

data "azurerm_client_config" "current" {}

locals {
  resolved_function_app_name = var.function_app_name != "" ? var.function_app_name : "func-lowopscast-${random_string.function_suffix.result}"
  common_tags = {
    project    = "lowopscast"
    managed_by = "terraform"
  }
}

# ---------------------------------------------------------------------------
# Recursos compartilhados reutilizados do rg-jsearch (somente leitura).
# Não são gerenciados por este stack; apenas referenciados.
# ---------------------------------------------------------------------------
data "azurerm_storage_account" "shared" {
  name                = var.shared_storage_account_name
  resource_group_name = var.shared_resource_group_name
}

data "azurerm_application_insights" "shared" {
  name                = var.shared_app_insights_name
  resource_group_name = var.shared_resource_group_name
}

data "azurerm_communication_service" "shared" {
  name                = var.shared_acs_name
  resource_group_name = var.shared_resource_group_name
}

# ---------------------------------------------------------------------------
# Recursos próprios deste stack (isolados em RG dedicado).
# ---------------------------------------------------------------------------
resource "azurerm_resource_group" "core" {
  name     = var.resource_group_name
  location = var.location
  tags     = local.common_tags
}

# Container de deployment do pacote da função, no storage compartilhado.
resource "azurerm_storage_container" "deploy" {
  name                  = "lowopscast-app-package"
  storage_account_id    = data.azurerm_storage_account.shared.id
  container_access_type = "private"
}

resource "azurerm_service_plan" "core" {
  name                = var.app_service_plan_name
  resource_group_name = azurerm_resource_group.core.name
  location            = azurerm_resource_group.core.location
  os_type             = "Linux"
  sku_name            = var.app_service_plan_sku
  tags                = local.common_tags
}

# Function App em Flex Consumption (FC1) — custo por consumo, ~$0 ocioso.
resource "azurerm_function_app_flex_consumption" "lowopscast" {
  name                = local.resolved_function_app_name
  resource_group_name = azurerm_resource_group.core.name
  location            = azurerm_resource_group.core.location
  service_plan_id     = azurerm_service_plan.core.id
  https_only          = true

  storage_container_type      = "blobContainer"
  storage_container_endpoint  = "${data.azurerm_storage_account.shared.primary_blob_endpoint}${azurerm_storage_container.deploy.name}"
  storage_authentication_type = "StorageAccountConnectionString"
  storage_access_key          = data.azurerm_storage_account.shared.primary_access_key

  runtime_name    = "python"
  runtime_version = var.function_python_version

  maximum_instance_count = 40
  instance_memory_in_mb  = 2048

  site_config {
    application_insights_connection_string = data.azurerm_application_insights.shared.connection_string
  }

  app_settings = {
    OTEL_SERVICE_NAME = local.resolved_function_app_name

    # OpusClip
    OPUSCLIP_API_KEY = var.opusclip_api_key
    OPUSCLIP_ORG_ID  = var.opusclip_org_id

    # Notificações por e-mail (ACS compartilhado + domínio verificado)
    ACS_CONNECTION_STRING   = data.azurerm_communication_service.shared.primary_connection_string
    NOTIFICATION_EMAIL_TO   = var.notification_email_to
    NOTIFICATION_EMAIL_FROM = var.notification_email_from

    # Idempotência em Table Storage (storage compartilhado, via connection string)
    STORAGE_ACCOUNT_NAME            = data.azurerm_storage_account.shared.name
    STATE_TABLE_NAME                = var.state_table_name
    STATE_STORAGE_CONNECTION_STRING = data.azurerm_storage_account.shared.primary_connection_string

    # Judge no cloud = só gate mecânico (rules_only). A curadoria de CONTEÚDO
    # (payoff/insight) é feita localmente pelo Claude Code via o harness em
    # tools/curate/ — o Azure AI Foundry foi removido deste stack.
    JUDGE_MODE                      = "rules_only"
    JUDGE_INCLUDE_REVIEW_IN_DRY_RUN = "true"
  }

  identity {
    type = "SystemAssigned"
  }

  tags = local.common_tags
}
