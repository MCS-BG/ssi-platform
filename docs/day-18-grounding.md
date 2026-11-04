# Day 18: grounded answers (no made-up facts from errors or empty results)

**Status:** built and tested on branch `day-18-grounding`. Not applied yet.

## The bug (seen live, Day 17)
`/ask "Do I have meetings this week?"` made llama3.2:3b call `m365_list_events` with
`{"top": 50, "days": 7, "timezone": "auto"}`. Microsoft Graph returned
`400 TimeZoneNotSupportedException`, and the model still answered
"No, you do not have meetings this week."

## Fix 1: m365-mcp timezone
`normalize_timezone()` turns `auto`, empty, missing, or invalid (checked with `zoneinfo`) into
`DEFAULT_TIMEZONE` (env, default `America/Chicago`). Graph gets the Windows name in
`Prefer: outlook.timezone="Central Standard Time"`. IANA names with a known mapping pass through
(converted); Windows names are accepted too. The tool description now tells the model to leave
`timezone` out.

## Fix 2: deterministic grounding (control layer + ssi-langgraph)
`grounded_answer()` replaces `synthesize()` at every answer step:

| Tool results in the turn | `grounding.rule` | Answer written by |
|---|---|---|
| every call errored | `all_errors` | code: "I couldn't read your calendar: Microsoft Graph returned an error (timezone not supported)." |
| every call empty (or empty + errors) | `empty` | code: "No meetings found in the next 7 days." / "No open pull requests found." |
| some failed or empty, some data | `none` + `mixed`, `failed`, `empty` | model, with a note: name the failed/empty tools, do not invent data, counts must match |
| all data | `none` | model, unchanged |

Reasons are short and fixed (timezone not supported, not signed in, access denied, not found,
rate limited, service unreachable, request rejected); raw server text and tokens are never echoed.
The response JSON keeps its shape and adds `grounding`; `/v1/chat/completions` carries it in `ssi.grounding`.

## Apply
See the PR description (deployment plan): ConfigMaps only, from
`k8s/day-14-m365-mcp.yaml`, `k8s/day-16-control-layer.yaml`, `k8s/day-17-ssi-langgraph.yaml`.
