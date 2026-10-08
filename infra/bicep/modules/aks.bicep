@description('Azure region.')
param location string

@description('AKS cluster name.')
param name string

@description('Kubernetes version.')
param kubernetesVersion string

@description('System node pool VM size.')
param systemNodeVmSize string

@description('System node pool count.')
param systemNodeCount int

@description('Create optional user node pool.')
param enableUserNodePool bool = false

@description('User node pool VM size.')
param userNodeVmSize string = 'Standard_D4s_v5'

@description('User node pool count.')
param userNodeCount int = 1

@description('Log Analytics workspace resource ID for Container Insights.')
param logAnalyticsWorkspaceId string

@description('ACR name (same resource group) for AcrPull.')
param acrName string

@description('Resource tags.')
param tags object = {}

var systemPool = {
  name: 'system'
  mode: 'System'
  count: systemNodeCount
  vmSize: systemNodeVmSize
  osType: 'Linux'
  type: 'VirtualMachineScaleSets'
  enableAutoScaling: false
}

var userPool = {
  name: 'userpool'
  mode: 'User'
  count: userNodeCount
  vmSize: userNodeVmSize
  osType: 'Linux'
  type: 'VirtualMachineScaleSets'
  enableAutoScaling: false
}

resource aks 'Microsoft.ContainerService/managedClusters@2024-09-01' = {
  name: name
  location: location
  tags: tags
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    dnsPrefix: take(replace(name, '-', ''), 10)
    kubernetesVersion: kubernetesVersion
    agentPoolProfiles: enableUserNodePool ? [ systemPool, userPool ] : [ systemPool ]
    networkProfile: {
      networkPlugin: 'azure'
      loadBalancerSku: 'standard'
      outboundType: 'loadBalancer'
    }
    addonProfiles: {
      omsagent: {
        enabled: true
        config: {
          logAnalyticsWorkspaceResourceID: logAnalyticsWorkspaceId
        }
      }
    }
  }
}

// Optional GPU user pool is intentionally NOT created here.
// Day 12 treats GPU vs Azure OpenAI as a swappable model slot in the steps doc —
// add a dedicated GPU pool later (NC/ND family) or point the model base URL at Azure OpenAI.

resource acr 'Microsoft.ContainerRegistry/registries@2023-07-01' existing = {
  name: acrName
}

resource aksAcrPull 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(acr.id, aks.id, 'AcrPull')
  scope: acr
  properties: {
    roleDefinitionId: subscriptionResourceId(
      'Microsoft.Authorization/roleDefinitions',
      '7f951dda-4ed3-4680-a7ca-43fe172d538d'
    )
    principalId: aks.properties.identityProfile.kubeletidentity.objectId
    principalType: 'ServicePrincipal'
  }
}

output name string = aks.name
output id string = aks.id
output fqdn string = aks.properties.fqdn
output kubeletObjectId string = aks.properties.identityProfile.kubeletidentity.objectId
