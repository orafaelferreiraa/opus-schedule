terraform {
  backend "azurerm" {
    resource_group_name  = "rg-state-opus"
    storage_account_name = "stoopusstate"
    container_name       = "statetf"
    key                  = "infra.terraform.tfstate"
    use_azuread_auth     = true
  }
}
