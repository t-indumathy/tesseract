# Option-B Build Plan — AP2 Official SDK Base

This branch rebuilds the PoC on top of Google's official AP2 Python samples
instead of hand-rolling protocol primitives.

## Why

The `main` branch invented its own UCP manifest shape and AP2 VC types.
This branch imports them directly from:
- **AP2 SDK**: `google-agentic-commerce/AP2` → `code/sdk/`
- **AP2 Python samples**: `code/samples/python/src/roles/`

## AP2 Role Mapping

The official repo defines six Python roles we cherry-pick from:

| AP2 Role (upstream) | Our Usage |
|---|---|
| `shopping_agent_v2` | Our buying agent — uses `UcpClient` + AP2 mandate flow |
| `merchant_agent` | Our seller — exposes real `/.well-known/ucp` manifest |
| `credentials_provider_agent` | Issues AP2 credentials (Intent/Cart mandates as real VCs) |
| `merchant_payment_processor_agent` | Validates mandates + processes mock payment |

We skip the MCP variants (`*_mcp`) for now — ADK tool-based approach is simpler for a PoC.

## Incremental Commit Plan

| Commit | What |
|---|---|
| **1/4** (this) | Branch plan + `pyproject.toml` with real AP2 dep |
| **2/4** | `src/merchant/` rewritten using `merchant_agent` pattern (real UCP manifest) |
| **3/4** | `src/ap2/` rewritten using `credentials_provider_agent` pattern (real VC types) |
| **4/4** | `src/agent/` updated to `shopping_agent_v2` pattern + updated scenario + tests |

## Key Differences from `main`

| Aspect | `main` branch | This branch |
|---|---|---|
| UCP manifest path | `/.well-known/ucp-manifest` (invented) | `/.well-known/ucp` (spec) |
| UCP capability names | `"checkout"` (invented) | `"dev.ucp.shopping.checkout"` (spec) |
| `UCP-Agent` header | Not sent | Sent on every request |
| AP2 VC types | Hand-rolled Pydantic | Imported from official AP2 SDK |
| AP2 mandate signing | HMAC-SHA256 (PoC shortcut) | ECDSA P-256 via AP2 SDK |
| Agent framework | Google ADK (manual tools) | Google ADK + `shopping_agent_v2` pattern |
