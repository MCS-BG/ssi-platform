# fo-mock: what it imitates, and where the names come from

`fo-mock` is a read-only imitation of a Dynamics 365 finance and operations (FO) OData v4 endpoint. It lives only inside the `si-lab` namespace. **Every record is fake demo data.** Account numbers start with `DEMO-`, names end in `(demo)`, and email addresses use `example.com`. Only the entity set names and field names come from Microsoft Learn, and each one was checked against the pages below on 2026-09-25 (America/Chicago).

## What's real FO behavior, and what's mocked

| Topic | Real FO (per Microsoft Learn) | fo-mock |
|---|---|---|
| Service root | `[Your organization's root URL]/data`, all public data entities, full CRUD ([OData page][odata]) | `http://fo-mock.si-lab.svc.cluster.local:8080/data`, 4 entity sets, **read-only** (POST/PATCH/DELETE return 405) |
| Metadata | `/data/$metadata` with annotations and enum types ([OData page][odata]) | `/data/$metadata` returns a minimal EDMX: entity types, keys, properties. Enums are typed as `Edm.String`. |
| Query options | `$filter`, `$count`, `$orderby`, `$skip`, `$top`, `$expand` (first level only), `$select` ([OData page][odata]) | `$filter` (only `eq`, joined by `and`), `$select`, `$top` (max 100), `$skip`, `$count=true`. Other options return HTTP 400, so nothing is silently ignored. |
| Company scoping | Returns only the user's default company unless you add `?cross-company=true`. Example: `$filter=dataAreaId eq 'usrt'&cross-company=true` ([OData page][odata]) | Default company is `usmf`. `cross-company=true` also returns the `usrt` rows. |
| Company field | "Company-specific data entities include the `dataAreaId` field" ([CLM master data page][clm]) | Every record has `dataAreaId`. It's part of each key. |
| Enum literals | Namespace `Microsoft.Dynamics.DataEntities`, e.g. `Microsoft.Dynamics.DataEntities.NoYes'Yes'` ([OData page][odata]) | The same literal syntax is accepted in `$filter`. The prefix is ignored. |
| Authentication | "OData services, JSON-based custom services, and the REST metadata service support standard OAuth 2.0 authentication." Clients are registered in Microsoft Entra ID ([Service endpoints overview][svc]) | **None.** It's reachable only inside the cluster, and a NetworkPolicy limits callers to the `mcp-server` pod. |
| Volume guidance | OData is synchronous. For "more than a few hundred thousand records," use the batch data API ([integration overview][intov]) | Not applicable: there are 15 fake rows. |

String comparisons in the mock are case-insensitive, to mimic FO's SQL collation. That's my assumption, not something these Learn pages state.

## Entity sets and fields (verified)

The FastTrack entity pages give each OData collection name, but they list fields as upper-case data management names (for example `CUSTOMERACCOUNT`). The exact PascalCase property names used by the mock come from the Common Data Model (CDM) schema page for the same AOT entity. Those pages are dated 2022-02-22, so treat the CDM lists as reference, not as a guarantee for the current release. A real environment's `/data/$metadata` is the authority.

| OData collection (entity type) | Collection name verified on | Field names verified on | Fields used by the mock |
|---|---|---|---|
| `CustomersV3` (`CustomerV3`, AOT `CustCustomerV3Entity`) | [Customers V3 entity][cust] | [CDM: CustCustomerV3Entity][cdm-cust] | CustomerAccount, OrganizationName, PartyType, CustomerGroupId, SalesCurrencyCode, InvoiceAccount, PaymentTerms, PaymentMethod, SalesTaxGroup, CreditLimit, AddressStreet, AddressCity, AddressState, AddressZipCode, AddressCountryRegionId, PrimaryContactEmail |
| `VendorsV2` (`VendorV2`, AOT `VendVendorV2Entity`) | [Synchronize master data (CLM)][clm]: "Vendors V2, VendVendorV2Entity, VendorsV2, company-specific: Yes" | [CDM: VendVendorV2Entity][cdm-vend] | VendorAccountNumber, VendorOrganizationName, VendorPartyType, VendorGroupId, CurrencyCode, DefaultPaymentTermsName, SalesTaxGroupCode, OnHoldStatus, AddressCity, AddressStateId, AddressZipCode, AddressCountryRegionId, PrimaryEmailAddress |
| `ReleasedProductsV2` (`ReleasedProductV2`, AOT `EcoResReleasedProductV2Entity`) | [Released products V2 entity][rp] | [CDM: EcoResReleasedProductV2Entity][cdm-rp] | ItemNumber, ProductNumber, SearchName, ProductType, ProductSubType, ProductGroupId, ItemModelGroupId, InventoryUnitSymbol, SalesUnitSymbol, PurchaseUnitSymbol, SalesPrice, PurchasePrice, UnitCost, PrimaryVendorAccountNumber |
| `SalesOrderHeadersV2` (`SalesOrderHeaderV2`, AOT `SalesOrderHeaderV2Entity`) | [Sales order headers V2 entity][so] | [CDM: SalesOrderHeaderV2Entity][cdm-so] | SalesOrderNumber, SalesOrderName, OrderingCustomerAccountNumber, InvoiceCustomerAccountNumber, SalesOrderStatus, CurrencyCode, CustomerRequisitionNumber, RequestedShippingDate, RequestedReceiptDate, PaymentTermsName, DeliveryTermsCode, SalesTaxGroupCode, DefaultShippingSiteId, DefaultShippingWarehouseId, OrderTotalAmount |

`dataAreaId` doesn't appear in the CDM attribute lists. It's verified by the OData and CLM pages above.

**Not verified. These are my illustrative choices:**
- Enum values (`PartyType` "Organization" does appear on the Customers V3 page. `SalesOrderStatus` "Backorder/Delivered/Invoiced", `OnHoldStatus` "No/All", and `ProductType` "Item/Service" are plausible, but I didn't check them against Learn.)
- Edm types (`Edm.Decimal` for amounts, `Edm.DateTimeOffset` for dates, with a noon-UTC date convention)
- The group codes, sites, and warehouses in the sample values

Two small typos on Learn, for the record: the Customers V3 page lists `SALECURRENCYCODE` in its field table but `SALESCURRENCYCODE` in its example, and the Sales order headers V2 page lists `SALESDORDERNUMBER`. The CDM pages spell them `SalesCurrencyCode` and `SalesOrderNumber`, which is what the mock uses.

## Positioning: why a mock, and what the real path would be

- Real FO data access for agents goes through supported APIs: OData data entities with Entra ID OAuth, or Microsoft's Dynamics 365 ERP MCP server (`https://<env>.operations.dynamics.com/mcp`, whose data tools include `data_find_entity_type` and `data_get_entity_metadata`). See `../research/fo-data-endpoints-learn.md`. This lab's `fo_get_entity_metadata` then `fo_query` flow mirrors that "metadata first, then query" pattern on purpose.
- Direct database access isn't an option for production FO. Learn says the application "doesn't allow T-SQL connections to the production database". BYOD, Export to Data Lake and LCS are being retired or replaced as part of the move to Power Platform. The analytics successors are Synapse Link and Fabric link, and environment management moves from LCS to the Power Platform admin center. Details and citations are in `../research/fo-data-endpoints-learn.md`, sections 2 and 6. Nothing in this lab suggests AXDB or SQL access.
- The static Dynamics 365 ERP MCP server retires on 2026-10-01 (research notes, section 4). Anything that later points at a real environment should target the dynamic ERP MCP server or OData.

## Sources

[odata]: https://learn.microsoft.com/en-us/dynamics365/fin-ops-core/dev-itpro/data-entities/odata
[svc]: https://learn.microsoft.com/en-us/dynamics365/fin-ops-core/dev-itpro/data-entities/services-home-page
[intov]: https://learn.microsoft.com/en-us/dynamics365/fin-ops-core/dev-itpro/data-entities/integration-overview
[clm]: https://learn.microsoft.com/en-us/dynamics365/supply-chain/procurement/contract-lifecycle-management/developer/clm-sync-master-data
[cust]: https://learn.microsoft.com/en-us/dynamics365/fin-ops-core/dev-itpro/data-entities/entity-customers-v3-customerv3
[rp]: https://learn.microsoft.com/en-us/dynamics365/fin-ops-core/dev-itpro/data-entities/entity-released-products-v2-releasedproductv2
[so]: https://learn.microsoft.com/en-us/dynamics365/fin-ops-core/dev-itpro/data-entities/entity-sales-order-headers-v2-salesorderheaderv2
[cdm-cust]: https://learn.microsoft.com/en-us/common-data-model/schema/core/operationscommon/entities/finance/accountsreceivable/custcustomerv3entity
[cdm-vend]: https://learn.microsoft.com/en-us/common-data-model/schema/core/operationscommon/entities/supplychain/procurementandsourcing/vendvendorv2entity
[cdm-rp]: https://learn.microsoft.com/en-us/common-data-model/schema/core/operationscommon/entities/supplychain/productinformationmanagement/ecoresreleasedproductv2entity
[cdm-so]: https://learn.microsoft.com/en-us/common-data-model/schema/core/operationscommon/entities/supplychain/salesandmarketing/salesorderheaderv2entity

- Open Data Protocol (OData), FO: <https://learn.microsoft.com/en-us/dynamics365/fin-ops-core/dev-itpro/data-entities/odata>
- Service endpoints overview (OAuth 2.0 / Microsoft Entra ID): <https://learn.microsoft.com/en-us/dynamics365/fin-ops-core/dev-itpro/data-entities/services-home-page>
- Integration overview: <https://learn.microsoft.com/en-us/dynamics365/fin-ops-core/dev-itpro/data-entities/integration-overview>
- Synchronize master data (CLM), which names `VendorsV2` / `VendVendorV2Entity` and `dataAreaId`: <https://learn.microsoft.com/en-us/dynamics365/supply-chain/procurement/contract-lifecycle-management/developer/clm-sync-master-data>
- Customers V3 entity: <https://learn.microsoft.com/en-us/dynamics365/fin-ops-core/dev-itpro/data-entities/entity-customers-v3-customerv3>
- Released products V2 entity: <https://learn.microsoft.com/en-us/dynamics365/fin-ops-core/dev-itpro/data-entities/entity-released-products-v2-releasedproductv2>
- Sales order headers V2 entity: <https://learn.microsoft.com/en-us/dynamics365/fin-ops-core/dev-itpro/data-entities/entity-sales-order-headers-v2-salesorderheaderv2>
- CDM CustCustomerV3Entity: <https://learn.microsoft.com/en-us/common-data-model/schema/core/operationscommon/entities/finance/accountsreceivable/custcustomerv3entity>
- CDM VendVendorV2Entity: <https://learn.microsoft.com/en-us/common-data-model/schema/core/operationscommon/entities/supplychain/procurementandsourcing/vendvendorv2entity>
- CDM EcoResReleasedProductV2Entity: <https://learn.microsoft.com/en-us/common-data-model/schema/core/operationscommon/entities/supplychain/productinformationmanagement/ecoresreleasedproductv2entity>
- CDM SalesOrderHeaderV2Entity: <https://learn.microsoft.com/en-us/common-data-model/schema/core/operationscommon/entities/supplychain/salesandmarketing/salesorderheaderv2entity>
