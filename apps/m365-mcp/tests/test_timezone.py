"""Day 18 offline tests for the m365-mcp timezone fix (no network, no Graph, no sign-in).

Run:  python3 -m pytest -q apps/m365-mcp/tests
"""
from __future__ import annotations

import os
import pathlib
import sys

import pytest

APP = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP))
os.environ.setdefault("OTEL_SDK_DISABLED", "true")

import server  # noqa: E402


@pytest.mark.parametrize("value", ["auto", "AUTO", "", None, "local", "  "])
def test_auto_empty_or_missing_becomes_central(value):
    assert server.normalize_timezone(value) == ("Central Standard Time", "America/Chicago")


@pytest.mark.parametrize("value", ["Mars/Olympus_Mons", "not a zone", "Central;DROP", "x" * 200, "Etc/GMT+99"])
def test_invalid_becomes_central(value):
    assert server.normalize_timezone(value)[1] == "America/Chicago"


@pytest.mark.parametrize("value,expected", [
    ("America/New_York", ("Eastern Standard Time", "America/New_York")),
    ("America/Chicago", ("Central Standard Time", "America/Chicago")),
    ("UTC", ("UTC", "UTC")),
    ("Pacific Standard Time", ("Pacific Standard Time", "America/Los_Angeles")),
])
def test_valid_timezone_passes_through(value, expected):
    assert server.normalize_timezone(value) == expected


def test_default_is_configurable(monkeypatch):
    monkeypatch.setattr(server, "DEFAULT_TIMEZONE", "America/Denver")
    assert server.normalize_timezone("auto") == ("Mountain Standard Time", "America/Denver")
    monkeypatch.setattr(server, "DEFAULT_TIMEZONE", "garbage")
    assert server.normalize_timezone("auto")[1] == "America/Chicago"


def _call_events(monkeypatch, **kwargs):
    sent = {}

    def fake_graph_get(path, params=None, headers=None):
        sent.update(path=path, params=params, headers=headers)
        return {"value": []}

    monkeypatch.setattr(server, "graph_get", fake_graph_get)
    monkeypatch.setattr(server, "guard_input", lambda *a, **k: None)
    fn = getattr(server.m365_list_events, "fn", server.m365_list_events)
    return fn(**kwargs), sent


def test_live_case_auto_sends_windows_name_to_graph(monkeypatch):
    """The exact live call: {top: 50, days: 7, timezone: 'auto'}."""
    out, sent = _call_events(monkeypatch, top=50, days=7, timezone="auto")
    assert sent["headers"] == {"Prefer": 'outlook.timezone="Central Standard Time"'}
    assert sent["params"]["$top"] == "50"
    assert out["time_zone"] == "America/Chicago" and out["returned"] == 0 and out["events"] == []


def test_events_iana_zone_sent_as_windows_name(monkeypatch):
    _, sent = _call_events(monkeypatch, timezone="America/New_York")
    assert sent["headers"]["Prefer"] == 'outlook.timezone="Eastern Standard Time"'


def test_schema_description_tells_the_model_the_default():
    doc = server.m365_list_events.__doc__ or getattr(getattr(server.m365_list_events, "fn", None), "__doc__", "")
    assert "America/Chicago" in doc and "leave it out" in doc
