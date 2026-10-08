"""In-cluster smoke test for the day 6 MCP server.

Connects twice (modern protocol auto-negotiation, then the legacy initialize
handshake that older clients use), lists the tools, calls search_notes and the
fo_* tools, and prints the results. Optionally checks that the fo-mock
NetworkPolicy blocks this pod (and reports whether pgvector is reachable). Exits non-zero if an MCP check fails.
"""
import asyncio
import json
import os
import socket
import sys

from mcp import Client

URL = os.environ.get("MCP_URL", "http://mcp-server.si-lab.svc.cluster.local:8000/mcp")
QUESTION = os.environ.get("TEST_QUESTION", "What GPU is in the lab host and how much VRAM does it have?")
FO_HOST = os.environ.get("FO_MOCK_HOST", "fo-mock.si-lab.svc.cluster.local")
FO_PORT = int(os.environ.get("FO_MOCK_PORT", "8080"))
PG_HOST = os.environ.get("PGVECTOR_HOST", "pgvector.si-lab.svc.cluster.local")
WAIT_SECONDS = int(os.environ.get("WAIT_SECONDS", "300"))


def root_cause(e):
    """Unwrap anyio ExceptionGroups so the real error (e.g. ConnectError) is printed."""
    while isinstance(e, BaseExceptionGroup) and e.exceptions:
        e = e.exceptions[0]
    return e


def show(result):
    if result.is_error:
        text = " ".join(getattr(c, "text", "") for c in result.content)
        raise RuntimeError("tool returned an error: " + text)
    return result.structured_content or json.loads(result.content[0].text)


async def run(mode):
    print(f"\n=== connecting to {URL} (mode={mode})")
    async with Client(URL, mode=mode) as client:
        tools = await client.list_tools()
        names = sorted(t.name for t in tools.tools)
        print("tools:", ", ".join(names))
        expected = {"search_notes", "fo_query", "fo_get_entity_metadata", "fo_list_entities"}
        if not expected <= set(names):
            raise RuntimeError(f"missing tools: {expected - set(names)}")
        if mode == "legacy":
            # Older clients (for example Open WebUI's backend) still use this handshake.
            q = show(await client.call_tool("fo_query", {"entity": "VendorsV2", "top": 1}))
            print(f"  fo_query VendorsV2 over the legacy handshake: returned={q['returned']}")
            return

        print(f"\n--- search_notes: {repr(QUESTION)}")
        data = show(await client.call_tool("search_notes", {"query": QUESTION, "k": 3}))
        for r in data["results"]:
            preview = " ".join(r["chunk"].split())[:70]
            print(f"  {r['distance']:.3f}  {r['source']}  {preview}...")
        if not data["results"]:
            raise RuntimeError("search_notes returned no rows (did the day 4 ingest run?)")

        print("\n--- fo_list_entities")
        print("  " + ", ".join(show(await client.call_tool("fo_list_entities", {}))["entity_sets"]))

        print("\n--- fo_get_entity_metadata: CustomersV3")
        meta = show(await client.call_tool("fo_get_entity_metadata", {"entity": "CustomersV3"}))
        print("  keys:", meta["keys"], " fields:", len(meta["fields"]))

        print("\n--- fo_query: CustomersV3 where CustomerGroupId eq '30'")
        q = show(await client.call_tool("fo_query", {
            "entity": "CustomersV3", "filter": "CustomerGroupId eq '30'",
            "select": "CustomerAccount,OrganizationName,AddressCity", "top": 5}))
        print(f"  matched={q['matched']} returned={q['returned']}")
        for rec in q["records"]:
            print("  ", rec)

        print("\n--- fo_query: SalesOrderHeadersV2 backorders for DEMO-C0001")
        q = show(await client.call_tool("fo_query", {
            "entity": "SalesOrderHeadersV2",
            "filter": "OrderingCustomerAccountNumber eq 'DEMO-C0001' and SalesOrderStatus eq 'Backorder'",
            "select": "SalesOrderNumber,RequestedShippingDate,OrderTotalAmount"}))
        for rec in q["records"]:
            print("  ", rec)

        print("\n--- fo_query with an unsupported filter (expect a clean tool error)")
        bad = await client.call_tool("fo_query", {"entity": "CustomersV3", "filter": "CreditLimit gt 1000"})
        print("  is_error =", bad.is_error, "|", " ".join(getattr(c, "text", "") for c in bad.content)[:160])


def tcp_reachable(host, port):
    try:
        socket.create_connection((host, port), timeout=3).close()
        return True, "connected"
    except OSError as e:
        return False, type(e).__name__


def check_network_policies():
    print("\n=== NetworkPolicy checks (direct TCP from this test pod)")
    ok, how = tcp_reachable(FO_HOST, FO_PORT)
    print(f"  fo-mock  {FO_HOST}:{FO_PORT}: " + (
        "REACHABLE - fo-mock is NOT isolated (NetworkPolicy missing or not enforced)" if ok
        else f"blocked as expected ({how})"))
    ok_pg, how_pg = tcp_reachable(PG_HOST, 5432)
    print(f"  pgvector {PG_HOST}:5432: " + (
        "reachable (expected unless the optional pgvector policy is applied)" if ok_pg
        else f"blocked ({how_pg}) - the optional pgvector policy is active"))
    return not ok


async def wait_for_server():
    deadline = asyncio.get_running_loop().time() + WAIT_SECONDS
    while True:
        try:
            async with Client(URL, mode="legacy") as client:
                await client.list_tools()
            return
        except Exception as e:
            e = root_cause(e)
            if asyncio.get_running_loop().time() > deadline:
                raise RuntimeError(f"MCP server not reachable after {WAIT_SECONDS}s: {type(e).__name__}: {e}") from e
            print(f"waiting for {URL} ({type(e).__name__}), retrying in 5s", flush=True)
            await asyncio.sleep(5)


async def main():
    await wait_for_server()
    await run("auto")
    await run("legacy")
    isolated = check_network_policies() if os.environ.get("CHECK_NETPOL", "1") == "1" else True
    print("\nALL MCP CHECKS PASSED" + ("" if isolated else " (but see the NetworkPolicy warning above)"))


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as e:
        e = root_cause(e)
        print(f"\nTEST FAILED: {type(e).__name__}: {e}")
        sys.exit(1)
