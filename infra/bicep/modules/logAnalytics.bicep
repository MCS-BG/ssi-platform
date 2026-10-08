@description('Azure region.')
param location string

@description('Log Analytics workspace name.')
param name string

@description('Resource tags.')
param tags object = {}

resource law 'Microsoft.OperationalInsights/workspaces@2023-09-01' = {
  name: name
  location: location
  tags: tags
  properties: {
    sku: {
      name: 'PerGB2018'
    }
    retentionInDays: 30
  }
}

output id string = law.id
output name string = law.name
output customerId string = law.properties.customerId
