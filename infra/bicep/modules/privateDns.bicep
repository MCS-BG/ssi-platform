// Placeholder private DNS zone for Private Link hostname teaching.
// Enterprise path: Private Link / VPN / internal DNS — not Tailscale.
// Wire the zone to the consumer VNet link in a follow-on change; this module only creates the zone shell.

@description('Private DNS zone name (example placeholder for AKS / Private Link docs).')
param zoneName string

@description('Resource tags.')
param tags object = {}

resource zone 'Microsoft.Network/privateDnsZones@2024-06-01' = {
  name: zoneName
  location: 'global'
  tags: tags
}

output zoneName string = zone.name
output zoneId string = zone.id
output notes string = '''
Next (not automated in Day 12):
1. Expose ssi-gateway via an Internal Load Balancer Service annotation.
2. Create a Private Link Service in front of that ILB.
3. Create a private endpoint in the consumer VNet.
4. Add an A record in this (or a customer) private DNS zone for the SSI Connector base URL.
Quiet observability (Grafana / Langfuse) can stay on-cluster or feed Azure Monitor; update endpoints only when the step changes them.
'''
