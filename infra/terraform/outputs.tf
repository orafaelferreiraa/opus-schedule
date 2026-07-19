output "function_app_name" {
  value       = azurerm_function_app_flex_consumption.lowopscast.name
  description = "Function app gerenciado por este stack."
}

output "function_app_principal_id" {
  value       = azurerm_function_app_flex_consumption.lowopscast.identity[0].principal_id
  description = "Managed identity principal id (para RBAC futuro: KV, Foundry, Table)."
}

output "function_app_default_hostname" {
  value       = azurerm_function_app_flex_consumption.lowopscast.default_hostname
  description = "Hostname padrão do Function App."
}

output "resource_group_name" {
  value       = azurerm_resource_group.core.name
  description = "Resource group dedicado deste stack."
}

output "service_plan_id" {
  value       = azurerm_service_plan.core.id
  description = "App Service plan dedicado."
}

output "shared_storage_account_name" {
  value       = data.azurerm_storage_account.shared.name
  description = "Storage account compartilhado reutilizado."
}

output "judge_endpoint" {
  value       = data.azurerm_cognitive_account.shared_foundry.endpoint
  description = "Endpoint do Foundry compartilhado (Judge em modo hybrid)."
}
