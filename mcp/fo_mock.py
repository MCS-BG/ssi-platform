"""Read-only mock of a Dynamics 365 finance and operations (FO) OData v4 endpoint.

FAKE DEMO DATA ONLY. Entity set and field names follow public Microsoft Learn
pages (see fo-mock-notes.md); every record value is invented. There is no
authentication: this service is cluster-internal only. Real FO OData requires
Microsoft Entra ID OAuth 2.0 tokens.

Supported: GET /data, GET /data/$metadata, GET /data/<EntitySet> with
$filter (eq, joined by 'and'), $select, $top, $skip, $count=true and
cross-company=true. Standard library only, so no pip install is needed.
"""
import json
import os
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

PORT = int(os.environ.get("PORT", "8080"))
DEFAULT_COMPANY = os.environ.get("FO_DEFAULT_COMPANY", "usmf")
MAX_TOP = 100
NAMESPACE = "Microsoft.Dynamics.DataEntities"

# Entity set -> (entity type, key fields, {field: Edm type}).
# dataAreaId is the company field that company-specific entities carry.
SCHEMA = {
    "CustomersV3": ("CustomerV3", ["dataAreaId", "CustomerAccount"], {
        "dataAreaId": "Edm.String",
        "CustomerAccount": "Edm.String",
        "OrganizationName": "Edm.String",
        "PartyType": "Edm.String",
        "CustomerGroupId": "Edm.String",
        "SalesCurrencyCode": "Edm.String",
        "InvoiceAccount": "Edm.String",
        "PaymentTerms": "Edm.String",
        "PaymentMethod": "Edm.String",
        "SalesTaxGroup": "Edm.String",
        "CreditLimit": "Edm.Decimal",
        "AddressStreet": "Edm.String",
        "AddressCity": "Edm.String",
        "AddressState": "Edm.String",
        "AddressZipCode": "Edm.String",
        "AddressCountryRegionId": "Edm.String",
        "PrimaryContactEmail": "Edm.String",
    }),
    "VendorsV2": ("VendorV2", ["dataAreaId", "VendorAccountNumber"], {
        "dataAreaId": "Edm.String",
        "VendorAccountNumber": "Edm.String",
        "VendorOrganizationName": "Edm.String",
        "VendorPartyType": "Edm.String",
        "VendorGroupId": "Edm.String",
        "CurrencyCode": "Edm.String",
        "DefaultPaymentTermsName": "Edm.String",
        "SalesTaxGroupCode": "Edm.String",
        "OnHoldStatus": "Edm.String",
        "AddressCity": "Edm.String",
        "AddressStateId": "Edm.String",
        "AddressZipCode": "Edm.String",
        "AddressCountryRegionId": "Edm.String",
        "PrimaryEmailAddress": "Edm.String",
    }),
    "ReleasedProductsV2": ("ReleasedProductV2", ["dataAreaId", "ItemNumber"], {
        "dataAreaId": "Edm.String",
        "ItemNumber": "Edm.String",
        "ProductNumber": "Edm.String",
        "SearchName": "Edm.String",
        "ProductType": "Edm.String",
        "ProductSubType": "Edm.String",
        "ProductGroupId": "Edm.String",
        "ItemModelGroupId": "Edm.String",
        "InventoryUnitSymbol": "Edm.String",
        "SalesUnitSymbol": "Edm.String",
        "PurchaseUnitSymbol": "Edm.String",
        "SalesPrice": "Edm.Decimal",
        "PurchasePrice": "Edm.Decimal",
        "UnitCost": "Edm.Decimal",
        "PrimaryVendorAccountNumber": "Edm.String",
    }),
    "SalesOrderHeadersV2": ("SalesOrderHeaderV2", ["dataAreaId", "SalesOrderNumber"], {
        "dataAreaId": "Edm.String",
        "SalesOrderNumber": "Edm.String",
        "SalesOrderName": "Edm.String",
        "OrderingCustomerAccountNumber": "Edm.String",
        "InvoiceCustomerAccountNumber": "Edm.String",
        "SalesOrderStatus": "Edm.String",
        "CurrencyCode": "Edm.String",
        "CustomerRequisitionNumber": "Edm.String",
        "RequestedShippingDate": "Edm.DateTimeOffset",
        "RequestedReceiptDate": "Edm.DateTimeOffset",
        "PaymentTermsName": "Edm.String",
        "DeliveryTermsCode": "Edm.String",
        "SalesTaxGroupCode": "Edm.String",
        "DefaultShippingSiteId": "Edm.String",
        "DefaultShippingWarehouseId": "Edm.String",
        "OrderTotalAmount": "Edm.Decimal",
    }),
}

# Fake demo records. Names end in "(demo)", emails use example.com.
DATA = {
    "CustomersV3": [
        {"dataAreaId": "usmf", "CustomerAccount": "DEMO-C0001", "OrganizationName": "Lakeside Bike Shop (demo)",
         "PartyType": "Organization", "CustomerGroupId": "30", "SalesCurrencyCode": "USD",
         "InvoiceAccount": "", "PaymentTerms": "Net30", "PaymentMethod": "CHECK", "SalesTaxGroup": "IL",
         "CreditLimit": 25000.0, "AddressStreet": "100 Demo Street", "AddressCity": "Chicago",
         "AddressState": "IL", "AddressZipCode": "60601", "AddressCountryRegionId": "USA",
         "PrimaryContactEmail": "ap@lakeside-bikes.example.com"},
        {"dataAreaId": "usmf", "CustomerAccount": "DEMO-C0002", "OrganizationName": "Prairie Outfitters (demo)",
         "PartyType": "Organization", "CustomerGroupId": "30", "SalesCurrencyCode": "USD",
         "InvoiceAccount": "", "PaymentTerms": "Net45", "PaymentMethod": "ELECTRONIC", "SalesTaxGroup": "WI",
         "CreditLimit": 50000.0, "AddressStreet": "200 Sample Avenue", "AddressCity": "Milwaukee",
         "AddressState": "WI", "AddressZipCode": "53202", "AddressCountryRegionId": "USA",
         "PrimaryContactEmail": "billing@prairie-outfitters.example.com"},
        {"dataAreaId": "usmf", "CustomerAccount": "DEMO-C0003", "OrganizationName": "Northwind Cycles Branch (demo)",
         "PartyType": "Organization", "CustomerGroupId": "10", "SalesCurrencyCode": "USD",
         "InvoiceAccount": "DEMO-C0002", "PaymentTerms": "Net30", "PaymentMethod": "CHECK", "SalesTaxGroup": "MN",
         "CreditLimit": 10000.0, "AddressStreet": "300 Example Road", "AddressCity": "Minneapolis",
         "AddressState": "MN", "AddressZipCode": "55401", "AddressCountryRegionId": "USA",
         "PrimaryContactEmail": "orders@northwind-cycles.example.com"},
        {"dataAreaId": "usrt", "CustomerAccount": "DEMO-C0101", "OrganizationName": "Riverfront Retail (demo)",
         "PartyType": "Organization", "CustomerGroupId": "20", "SalesCurrencyCode": "USD",
         "InvoiceAccount": "", "PaymentTerms": "Net10", "PaymentMethod": "ELECTRONIC", "SalesTaxGroup": "IL",
         "CreditLimit": 5000.0, "AddressStreet": "400 Mock Boulevard", "AddressCity": "Springfield",
         "AddressState": "IL", "AddressZipCode": "62701", "AddressCountryRegionId": "USA",
         "PrimaryContactEmail": "store@riverfront-retail.example.com"},
    ],
    "VendorsV2": [
        {"dataAreaId": "usmf", "VendorAccountNumber": "DEMO-V0001", "VendorOrganizationName": "Great Lakes Components (demo)",
         "VendorPartyType": "Organization", "VendorGroupId": "10", "CurrencyCode": "USD",
         "DefaultPaymentTermsName": "Net30", "SalesTaxGroupCode": "IL", "OnHoldStatus": "No",
         "AddressCity": "Gary", "AddressStateId": "IN", "AddressZipCode": "46402",
         "AddressCountryRegionId": "USA", "PrimaryEmailAddress": "sales@glc.example.com"},
        {"dataAreaId": "usmf", "VendorAccountNumber": "DEMO-V0002", "VendorOrganizationName": "Midwest Freight Partners (demo)",
         "VendorPartyType": "Organization", "VendorGroupId": "20", "CurrencyCode": "USD",
         "DefaultPaymentTermsName": "Net15", "SalesTaxGroupCode": "IL", "OnHoldStatus": "No",
         "AddressCity": "Joliet", "AddressStateId": "IL", "AddressZipCode": "60431",
         "AddressCountryRegionId": "USA", "PrimaryEmailAddress": "dispatch@mfp.example.com"},
        {"dataAreaId": "usmf", "VendorAccountNumber": "DEMO-V0003", "VendorOrganizationName": "Old Mill Packaging (demo)",
         "VendorPartyType": "Organization", "VendorGroupId": "10", "CurrencyCode": "USD",
         "DefaultPaymentTermsName": "Net45", "SalesTaxGroupCode": "WI", "OnHoldStatus": "All",
         "AddressCity": "Madison", "AddressStateId": "WI", "AddressZipCode": "53703",
         "AddressCountryRegionId": "USA", "PrimaryEmailAddress": "ar@oldmill.example.com"},
    ],
    "ReleasedProductsV2": [
        {"dataAreaId": "usmf", "ItemNumber": "DEMO-1000", "ProductNumber": "DEMO-1000", "SearchName": "Demo trail helmet",
         "ProductType": "Item", "ProductSubType": "Product", "ProductGroupId": "Accessory", "ItemModelGroupId": "FIFO",
         "InventoryUnitSymbol": "ea", "SalesUnitSymbol": "ea", "PurchaseUnitSymbol": "ea",
         "SalesPrice": 89.0, "PurchasePrice": 41.5, "UnitCost": 40.25, "PrimaryVendorAccountNumber": "DEMO-V0001"},
        {"dataAreaId": "usmf", "ItemNumber": "DEMO-1001", "ProductNumber": "DEMO-1001", "SearchName": "Demo bike light set",
         "ProductType": "Item", "ProductSubType": "Product", "ProductGroupId": "Accessory", "ItemModelGroupId": "FIFO",
         "InventoryUnitSymbol": "ea", "SalesUnitSymbol": "ea", "PurchaseUnitSymbol": "ea",
         "SalesPrice": 34.0, "PurchasePrice": 12.0, "UnitCost": 11.8, "PrimaryVendorAccountNumber": "DEMO-V0001"},
        {"dataAreaId": "usmf", "ItemNumber": "DEMO-2000", "ProductNumber": "DEMO-2000", "SearchName": "Demo shipping carton",
         "ProductType": "Item", "ProductSubType": "Product", "ProductGroupId": "Packaging", "ItemModelGroupId": "STD",
         "InventoryUnitSymbol": "ea", "SalesUnitSymbol": "box", "PurchaseUnitSymbol": "box",
         "SalesPrice": 2.5, "PurchasePrice": 0.9, "UnitCost": 0.95, "PrimaryVendorAccountNumber": "DEMO-V0003"},
        {"dataAreaId": "usmf", "ItemNumber": "DEMO-9000", "ProductNumber": "DEMO-9000", "SearchName": "Demo assembly service",
         "ProductType": "Service", "ProductSubType": "Product", "ProductGroupId": "Services", "ItemModelGroupId": "SRV",
         "InventoryUnitSymbol": "hr", "SalesUnitSymbol": "hr", "PurchaseUnitSymbol": "hr",
         "SalesPrice": 75.0, "PurchasePrice": 0.0, "UnitCost": 38.0, "PrimaryVendorAccountNumber": ""},
    ],
    "SalesOrderHeadersV2": [
        {"dataAreaId": "usmf", "SalesOrderNumber": "DEMO-SO-0001", "SalesOrderName": "Lakeside Bike Shop (demo)",
         "OrderingCustomerAccountNumber": "DEMO-C0001", "InvoiceCustomerAccountNumber": "DEMO-C0001",
         "SalesOrderStatus": "Backorder", "CurrencyCode": "USD", "CustomerRequisitionNumber": "PO-DEMO-77",
         "RequestedShippingDate": "2026-10-05T12:00:00Z", "RequestedReceiptDate": "2026-10-07T12:00:00Z",
         "PaymentTermsName": "Net30", "DeliveryTermsCode": "FOB", "SalesTaxGroupCode": "IL",
         "DefaultShippingSiteId": "1", "DefaultShippingWarehouseId": "11", "OrderTotalAmount": 1780.0},
        {"dataAreaId": "usmf", "SalesOrderNumber": "DEMO-SO-0002", "SalesOrderName": "Prairie Outfitters (demo)",
         "OrderingCustomerAccountNumber": "DEMO-C0002", "InvoiceCustomerAccountNumber": "DEMO-C0002",
         "SalesOrderStatus": "Delivered", "CurrencyCode": "USD", "CustomerRequisitionNumber": "PO-DEMO-78",
         "RequestedShippingDate": "2026-09-20T12:00:00Z", "RequestedReceiptDate": "2026-09-23T12:00:00Z",
         "PaymentTermsName": "Net45", "DeliveryTermsCode": "FOB", "SalesTaxGroupCode": "WI",
         "DefaultShippingSiteId": "1", "DefaultShippingWarehouseId": "11", "OrderTotalAmount": 612.5},
        {"dataAreaId": "usmf", "SalesOrderNumber": "DEMO-SO-0003", "SalesOrderName": "Northwind Cycles Branch (demo)",
         "OrderingCustomerAccountNumber": "DEMO-C0003", "InvoiceCustomerAccountNumber": "DEMO-C0002",
         "SalesOrderStatus": "Invoiced", "CurrencyCode": "USD", "CustomerRequisitionNumber": "",
         "RequestedShippingDate": "2026-09-01T12:00:00Z", "RequestedReceiptDate": "2026-09-03T12:00:00Z",
         "PaymentTermsName": "Net30", "DeliveryTermsCode": "CIF", "SalesTaxGroupCode": "MN",
         "DefaultShippingSiteId": "2", "DefaultShippingWarehouseId": "21", "OrderTotalAmount": 245.0},
        {"dataAreaId": "usmf", "SalesOrderNumber": "DEMO-SO-0004", "SalesOrderName": "Lakeside Bike Shop (demo)",
         "OrderingCustomerAccountNumber": "DEMO-C0001", "InvoiceCustomerAccountNumber": "DEMO-C0001",
         "SalesOrderStatus": "Backorder", "CurrencyCode": "USD", "CustomerRequisitionNumber": "PO-DEMO-81",
         "RequestedShippingDate": "2026-10-12T12:00:00Z", "RequestedReceiptDate": "2026-10-14T12:00:00Z",
         "PaymentTermsName": "Net30", "DeliveryTermsCode": "FOB", "SalesTaxGroupCode": "IL",
         "DefaultShippingSiteId": "1", "DefaultShippingWarehouseId": "11", "OrderTotalAmount": 3400.0},
    ],
}


class ODataError(Exception):
    def __init__(self, status, message):
        super().__init__(message)
        self.status = status
        self.message = message


# One comparison: <Field> eq <literal>. Literals: 'text' (use '' for a quote),
# numbers, true, false, null, or an FO enum literal such as
# Microsoft.Dynamics.DataEntities.NoYes'Yes'.
CLAUSE = re.compile(
    r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s+eq\s+"
    r"(?:(?:[A-Za-z0-9_.]+)?'((?:[^']|'')*)'|(-?\d+(?:\.\d+)?)|(true|false|null))\s*$"
)


def parse_filter(text, fields):
    """Turn "A eq 'x' and B eq 3" into [(A, 'x'), (B, 3)]. Only eq and 'and' are supported."""
    conditions = []
    for part in re.split(r"\s+and\s+", text.strip()):
        m = CLAUSE.match(part)
        if not m:
            raise ODataError(400, "The mock only supports $filter clauses like Field eq 'value' joined by 'and'. "
                                  "Could not parse: " + part.strip())
        field, text_value, number, keyword = m.groups()
        if field not in fields:
            raise ODataError(400, "Unknown property in $filter: " + field)
        if text_value is not None:
            value = text_value.replace("''", "'")
        elif number is not None:
            value = float(number) if "." in number else int(number)
        else:
            value = {"true": True, "false": False, "null": None}[keyword]
        conditions.append((field, value))
    return conditions


def matches(row, conditions):
    for field, value in conditions:
        actual = row.get(field)
        if isinstance(actual, str) and isinstance(value, str):
            # FO string comparisons are case-insensitive (SQL collation).
            if actual.lower() != value.lower():
                return False
        elif isinstance(actual, (int, float)) and isinstance(value, (int, float)):
            if float(actual) != float(value):
                return False
        elif actual != value:
            return False
    return True


def query_entity_set(name, params, base_url):
    if name not in SCHEMA:
        raise ODataError(404, "Resource not found for the segment '" + name + "'.")
    _, _, fields = SCHEMA[name]
    unsupported = [p for p in params if p.startswith("$") and p not in ("$filter", "$select", "$top", "$skip", "$count", "$format")]
    if unsupported:
        raise ODataError(400, "Query option(s) not supported by the mock: " + ", ".join(sorted(unsupported)))

    rows = DATA[name]
    if params.get("cross-company", "false").lower() != "true":
        rows = [r for r in rows if r["dataAreaId"].lower() == DEFAULT_COMPANY.lower()]
    if params.get("$filter"):
        conditions = parse_filter(params["$filter"], fields)
        rows = [r for r in rows if matches(r, conditions)]
    total = len(rows)

    try:
        skip = int(params.get("$skip", "0"))
        top = int(params.get("$top", str(MAX_TOP)))
    except ValueError:
        raise ODataError(400, "$top and $skip must be integers.")
    rows = rows[max(skip, 0):max(skip, 0) + max(0, min(top, MAX_TOP))]

    select = [s.strip() for s in params.get("$select", "").split(",") if s.strip()]
    for s in select:
        if s not in fields:
            raise ODataError(400, "Unknown property in $select: " + s)
    if select:
        rows = [{k: r[k] for k in select} for r in rows]

    context = base_url + "/data/$metadata#" + name
    if select:
        context += "(" + ",".join(select) + ")"
    body = {"@odata.context": context}
    if params.get("$count", "").lower() == "true":
        body["@odata.count"] = total
    body["value"] = rows
    return body


def metadata_xml():
    out = ['<?xml version="1.0" encoding="utf-8"?>',
           '<edmx:Edmx Version="4.0" xmlns:edmx="http://docs.oasis-open.org/odata/ns/edmx">',
           '<edmx:DataServices>',
           '<Schema Namespace="' + NAMESPACE + '" xmlns="http://docs.oasis-open.org/odata/ns/edm">']
    for set_name, (type_name, keys, fields) in SCHEMA.items():
        out.append('<EntityType Name="' + type_name + '">')
        out.append('<Key>' + "".join('<PropertyRef Name="' + k + '"/>' for k in keys) + '</Key>')
        for field, edm in fields.items():
            nullable = "false" if field in keys else "true"
            out.append('<Property Name="' + field + '" Type="' + edm + '" Nullable="' + nullable + '"/>')
        out.append('</EntityType>')
    out.append('<EntityContainer Name="Resources">')
    for set_name, (type_name, _, _) in SCHEMA.items():
        out.append('<EntitySet Name="' + set_name + '" EntityType="' + NAMESPACE + '.' + type_name + '"/>')
    out.append('</EntityContainer></Schema></edmx:DataServices></edmx:Edmx>')
    return "\n".join(out)


class Handler(BaseHTTPRequestHandler):
    server_version = "fo-mock/0.6"

    def _send(self, status, body, content_type):
        data = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("OData-Version", "4.0")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _json(self, status, obj):
        self._send(status, json.dumps(obj, indent=1), "application/json; odata.metadata=minimal; charset=utf-8")

    def do_GET(self):
        url = urlsplit(self.path)
        path = url.path.rstrip("/") or "/"
        params = {k: v[-1] for k, v in parse_qs(url.query, keep_blank_values=True).items()}
        base_url = "http://" + self.headers.get("Host", "fo-mock")
        try:
            if path == "/healthz":
                self._send(200, "ok\n", "text/plain")
            elif path == "/data":
                self._json(200, {
                    "@odata.context": base_url + "/data/$metadata",
                    "value": [{"name": n, "kind": "EntitySet", "url": n} for n in SCHEMA],
                })
            elif path == "/data/$metadata":
                self._send(200, metadata_xml(), "application/xml; charset=utf-8")
            elif path.startswith("/data/"):
                self._json(200, query_entity_set(path[len("/data/"):], params, base_url))
            else:
                raise ODataError(404, "Not found. Try /data or /data/$metadata.")
        except ODataError as e:
            self._json(e.status, {"error": {"code": "", "message": e.message}})

    def do_POST(self):
        self._json(405, {"error": {"code": "", "message": "The mock is read-only."}})

    do_PUT = do_PATCH = do_DELETE = do_POST

    def log_message(self, fmt, *args):
        print("%s %s" % (self.address_string(), fmt % args), flush=True)


if __name__ == "__main__":
    print("fo-mock (FAKE DEMO DATA, no auth) listening on :%d, default company %s" % (PORT, DEFAULT_COMPANY), flush=True)
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
