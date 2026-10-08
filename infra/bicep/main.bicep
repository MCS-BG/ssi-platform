// Day 12: minimal SSI platform scaffolding on AKS.
// Lab teaching module — readable and small. Does not deploy the full SSI stack by itself.
// Parameters drive naming; modules stay optional where noted.

targetScope = 'subscription'

@description('Azure region for the resource group and child resources.')
param location string = 'eastus'

@description('Short prefix for resource names (letters/numbers only, keep short).')
@minLength(3)
@maxLength(12)
param namePrefix string = 'ssi'

@description('AKS Kubernetes version (patch may float; set explicitly in real runs).')
param kubernetesVersion string = '1.31.2'

@description('System node pool VM size (CPU path for control plane workloads).')
param systemNodeVmSize string = 'Standard_D4s_v5'

@description('System node pool count.')
@minValue(1)
@maxValue(5)
param systemNodeCount int = 1

@description('Create an optional user node pool (CPU). Set true for a second pool.')
param enableUserNodePool bool = false

@description('Optional user node pool VM size.')
param userNodeVmSize string = 'Standard_D4s_v5'

@description('Optional user node pool count.')
@minValue(0)
@maxValue(5)
param userNodeCount int = 1

@description('Placeholder: enable notes/outputs for Private Link + private DNS wiring.')
param enablePrivateLinkNotes bool = true

@description('Tags applied to the resource group and key resources.')
param tags object = {
  project: 'ssi'
  lab: 'day-12'
}

var rgName = '${namePrefix}-aks-rg'
var aksName = '${namePrefix}-aks'
var acrName = 'ssi${uniqueString(subscription().subscriptionId, rgName, namePrefix)}'
var logName = '${namePrefix}-law'
var dnsZoneName = 'privatelink.${location}.azmk8s.io'

resource rg 'Microsoft.Resources/resourceGroups@2024-03-01' = {
  name: rgName
  location: location
  tags: tags
}

module logAnalytics 'modules/logAnalytics.bicep' = {
  name: 'logAnalytics'
  scope: rg
  params: {
    location: location
    name: logName
    tags: tags
  }
}

module acr 'modules/acr.bicep' = {
  name: 'acr'
  scope: rg
  params: {
    location: location
    name: acrName
    tags: tags
  }
}

module aks 'modules/aks.bicep' = {
  name: 'aks'
  scope: rg
  params: {
    location: location
    name: aksName
    kubernetesVersion: kubernetesVersion
    systemNodeVmSize: systemNodeVmSize
    systemNodeCount: systemNodeCount
    enableUserNodePool: enableUserNodePool
    userNodeVmSize: userNodeVmSize
    userNodeCount: userNodeCount
    logAnalyticsWorkspaceId: logAnalytics.outputs.id
    acrName: acr.outputs.name
    tags: tags
  }
}

module privateDns 'modules/privateDns.bicep' = if (enablePrivateLinkNotes) {
  name: 'privateDnsPlaceholder'
  scope: rg
  params: {
    zoneName: dnsZoneName
    tags: tags
  }
}

output resourceGroupName string = rg.name
output aksName string = aks.outputs.name
output aksFqdn string = aks.outputs.fqdn
output acrLoginServer string = acr.outputs.loginServer
output logAnalyticsWorkspaceId string = logAnalytics.outputs.id
output privateDnsZoneName string = enablePrivateLinkNotes ? privateDns!.outputs.zoneName : ''
output privateLinkNotes string = '''
Enterprise reachability for SSI is Private Link / VPN / internal DNS — not Tailscale.
Wire an Internal Load Balancer Service for ssi-gateway, then a Private Link Service +
private endpoint in the consumer VNet. Point SSI Connector at the private hostname.
Home-lab Tailscale Ingress stays on k3s only.
'''
