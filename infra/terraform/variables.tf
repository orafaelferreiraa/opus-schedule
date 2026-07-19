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
  description = "Optional Key Vault name. Leave empty to generate a unique name."
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

variable "foundry_account_name" {
  description = "Optional Azure OpenAI/Foundry account name. Leave empty to generate a unique name."
  type        = string
  default     = ""
}

variable "judge_auth_mode" {
  description = "Judge auth mode: managed_identity or api_key."
  type        = string
  default     = "managed_identity"

  validation {
    condition     = contains(["managed_identity", "api_key"], var.judge_auth_mode)
    error_message = "judge_auth_mode must be one of: managed_identity, api_key."
  }
}

variable "judge_primary_model_name" {
  description = "Primary model name from Azure OpenAI catalog."
  type        = string
  default     = "gpt-5"
}

variable "judge_primary_model_version" {
  description = "Primary model version from Azure OpenAI catalog."
  type        = string
  default     = "2025-08-07"
}

variable "judge_primary_sku_name" {
  description = "Primary deployment SKU name."
  type        = string
  default     = "GlobalStandard"
}

variable "judge_primary_sku_capacity" {
  description = "Primary deployment SKU capacity."
  type        = number
  default     = 50
}

variable "judge_fallback_model_name" {
  description = "Fallback model name from Azure OpenAI catalog."
  type        = string
  default     = "gpt-4.1-mini"
}

variable "judge_fallback_model_version" {
  description = "Fallback model version from Azure OpenAI catalog."
  type        = string
  default     = "2025-04-14"
}

variable "judge_fallback_sku_name" {
  description = "Fallback deployment SKU name."
  type        = string
  default     = "GlobalStandard"
}

variable "judge_fallback_sku_capacity" {
  description = "Fallback deployment SKU capacity."
  type        = number
  default     = 20
}

variable "opusclip_api_key" {
  description = "OpusClip API key stored in Key Vault and referenced by Function App."
  type        = string
  default     = ""
  sensitive   = true
}

variable "acs_connection_string" {
  description = "ACS Email connection string stored in Key Vault."
  type        = string
  default     = ""
  sensitive   = true
}

variable "notification_email_to" {
  description = "Target e-mail for schedule summary notifications."
  type        = string
  default     = ""
}

variable "notification_email_from" {
  description = "Source e-mail for schedule summary notifications."
  type        = string
  default     = "noreply@orafaelferreira.com"
}
