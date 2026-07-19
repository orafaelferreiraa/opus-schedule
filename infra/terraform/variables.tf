variable "resource_group_name" {
  description = "Resource group name for the isolated stack."
  type        = string
  default     = "rg-lowopscast-schedule"
}

variable "location" {
  description = "Azure region."
  type        = string
  default     = "eastus"
}

variable "app_service_plan_name" {
  description = "App Service plan name for the isolated stack."
  type        = string
  default     = "plan-lowopscast-schedule"
}

variable "app_service_plan_sku" {
  description = "SKU for the dedicated Linux App Service plan."
  type        = string
  default     = "B1"

  validation {
    condition     = length(trimspace(var.app_service_plan_sku)) > 0
    error_message = "app_service_plan_sku cannot be empty. Set a valid SKU (for example: B1, Y1, EP1, FC1)."
  }
}

variable "application_insights_name" {
  description = "Application Insights name for the isolated stack."
  type        = string
  default     = "appi-lowopscast-schedule"
}

variable "storage_account_name" {
  description = "Optional storage account name. Leave empty to generate a unique name."
  type        = string
  default     = ""
}

variable "storage_replication_type" {
  description = "Storage replication type for the dedicated storage account."
  type        = string
  default     = "LRS"
}

variable "key_vault_name" {
  description = "Optional Key Vault name reserved for future use."
  type        = string
  default     = ""
}

variable "function_app_name" {
  description = "Optional Function App name. Leave empty to generate an isolated unique name."
  type        = string
  default     = ""
}

variable "function_python_version" {
  description = "Python runtime version for Azure Functions application stack."
  type        = string
  default     = "3.12"
}

variable "judge_primary_model" {
  description = "Primary judge deployment name in Foundry/Azure OpenAI."
  type        = string
  default     = "gpt-5.6-sol"
}

variable "judge_fallback_model" {
  description = "Fallback judge deployment name in Foundry/Azure OpenAI."
  type        = string
  default     = "gpt-5.4-mini"
}
