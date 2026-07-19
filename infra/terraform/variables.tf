variable "resource_group_name" {
  description = "Resource group dedicado deste stack (recursos próprios)."
  type        = string
  default     = "rg-lowopscast-schedule"
}

variable "location" {
  description = "Região Azure. Co-localizada com os recursos compartilhados (East US 2)."
  type        = string
  default     = "eastus2"
}

variable "app_service_plan_name" {
  description = "Nome do App Service Plan dedicado."
  type        = string
  default     = "plan-lowopscast-schedule"
}

variable "app_service_plan_sku" {
  description = "SKU do plano. FC1 = Flex Consumption (~$0 ocioso). B1 = dedicado (fallback confiável se faltar quota FC1)."
  type        = string
  default     = "FC1"

  validation {
    condition     = length(trimspace(var.app_service_plan_sku)) > 0
    error_message = "app_service_plan_sku não pode ser vazio (ex.: FC1, B1, EP1)."
  }
}

variable "function_app_name" {
  description = "Nome opcional do Function App. Vazio gera um nome único isolado."
  type        = string
  default     = ""
}

variable "function_python_version" {
  description = "Versão do runtime Python do Function App."
  type        = string
  default     = "3.13"
}

# ---------------------------------------------------------------------------
# Recursos compartilhados reutilizados (rg-jsearch)
# ---------------------------------------------------------------------------
variable "shared_resource_group_name" {
  description = "Resource group que hospeda os recursos compartilhados reutilizados."
  type        = string
  default     = "rg-jsearch"
}

variable "shared_storage_account_name" {
  description = "Storage account compartilhado (runtime da função + tabela de idempotência)."
  type        = string
  default     = "stjobfinderprodrandonix"
}

variable "shared_app_insights_name" {
  description = "Application Insights compartilhado para telemetria."
  type        = string
  default     = "appi-jobfinder-prod"
}

variable "shared_acs_name" {
  description = "Azure Communication Services compartilhado (e-mail) com domínio verificado."
  type        = string
  default     = "acs-jobfinder-prod"
}

variable "shared_foundry_name" {
  description = "Conta Azure OpenAI/Foundry compartilhada usada pelo Judge (modo hybrid)."
  type        = string
  default     = "aif-jobfinder-prod-randonix"
}

# ---------------------------------------------------------------------------
# Judge (dormente por padrão: JUDGE_MODE=rules_only)
# ---------------------------------------------------------------------------
variable "judge_auth_mode" {
  description = "Modo de auth do Judge no modo hybrid: managed_identity ou api_key."
  type        = string
  default     = "managed_identity"

  validation {
    condition     = contains(["managed_identity", "api_key"], var.judge_auth_mode)
    error_message = "judge_auth_mode deve ser: managed_identity ou api_key."
  }
}

variable "judge_primary_model" {
  description = "Deployment primário no Foundry compartilhado (reutiliza o existente)."
  type        = string
  default     = "gpt-5-mini"
}

variable "judge_fallback_model" {
  description = "Deployment de fallback no Foundry compartilhado."
  type        = string
  default     = "gpt-5-mini"
}

# ---------------------------------------------------------------------------
# Segredos / configuração de runtime
# ---------------------------------------------------------------------------
variable "opusclip_api_key" {
  description = "API key da OpusClip (via GitHub secret / TF_VAR)."
  type        = string
  default     = ""
  sensitive   = true
}

variable "opusclip_org_id" {
  description = "Org id opcional da OpusClip."
  type        = string
  default     = ""
}

variable "state_table_name" {
  description = "Nome da tabela de idempotência no storage compartilhado."
  type        = string
  default     = "lowopscaststate"
}

variable "notification_email_to" {
  description = "E-mail de destino do resumo de agendamentos."
  type        = string
  default     = ""
}

variable "notification_email_from" {
  description = "E-mail remetente (domínio verificado no ACS compartilhado)."
  type        = string
  default     = "noreply@orafaelferreira.com"
}
