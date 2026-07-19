output "function_app_name" {
  value       = azurerm_linux_function_app.lowopscast.name
  description = "Function app managed by this stack."
}

output "function_app_principal_id" {
  value       = azurerm_linux_function_app.lowopscast.identity[0].principal_id
  description = "Managed identity principal id for RBAC/Key Vault access policies."
}

output "resource_group_name" {
  value       = azurerm_resource_group.core.name
  description = "Dedicated resource group for this stack."
}

output "service_plan_id" {
  value       = azurerm_service_plan.core.id
  description = "Dedicated App Service plan id."
}

output "storage_account_name" {
  value       = azurerm_storage_account.core.name
  description = "Dedicated storage account name."
}

output "application_insights_name" {
  value       = azurerm_application_insights.core.name
  description = "Dedicated Application Insights name."
}
