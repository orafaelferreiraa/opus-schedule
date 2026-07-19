variable "subscription_id" {
  description = "Azure subscription id for deployment context."
  type        = string
}

variable "resource_group_name" {
  description = "Existing resource group name."
  type        = string
  default     = "rg-jsearch"
}

variable "location" {
  description = "Azure region."
  type        = string
  default     = "eastus"
}

variable "app_service_plan_name" {
  description = "Existing App Service plan used by Function App."
  type        = string
  default     = "plan-jobfinder-prod"
}

variable "application_insights_name" {
  description = "Existing Application Insights instance."
  type        = string
  default     = "appi-jobfinder-prod"
}

variable "storage_account_name" {
  description = "Existing storage account for function runtime and state."
  type        = string
  default     = "stjobfinderprodrandonix"
}

variable "key_vault_name" {
  description = "Existing Key Vault used for runtime secrets."
  type        = string
  default     = "kv-jf-prod-randonix"
}

variable "function_app_name" {
  description = "Function app name (new or existing managed in this stack)."
  type        = string
  default     = "func-lowopscast-prod"
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
