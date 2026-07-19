output "function_app_name" {
  value       = azurerm_linux_function_app.lowopscast.name
  description = "Function app managed by this stack."
}

output "function_app_principal_id" {
  value       = azurerm_linux_function_app.lowopscast.identity[0].principal_id
  description = "Managed identity principal id for RBAC/Key Vault access policies."
}

output "existing_key_vault_id" {
  value       = data.azurerm_key_vault.existing.id
  description = "Existing Key Vault used by the workload."
}
