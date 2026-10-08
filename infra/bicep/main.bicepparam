using 'main.bicep'

param location = 'eastus'
param namePrefix = 'ssi'
param kubernetesVersion = '1.31.2'
param systemNodeVmSize = 'Standard_D4s_v5'
param systemNodeCount = 1
param enableUserNodePool = false
param enablePrivateLinkNotes = true
param tags = {
  project: 'ssi'
  lab: 'day-12'
}
