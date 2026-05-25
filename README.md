# Tesseract — UCP + AP2 Agentic Commerce PoC

> **Branch:** `poc/ucp-ap2-spec-compliant`  
> Built on the official [AP2 samples](https://github.com/google-agentic-commerce/AP2) structure.

## Architecture

```
Shopping Agent (ADK + Gemini 2.5 Flash)
      │
      │ 1. GET /.well-known/ucp          ← Real UCP profile (spec 2026-04-08)
      │ 2. POST /checkout-sessions       ← dev.ucp.shopping.checkout capability
      │    └── UCP-Agent header          ← Platform profile advertisement (RFC 8941)
      │    └── ucp.capabilities in resp  ← Capability echo-back (mandatory per spec)
      │
      ├── AP2 Intent Mandate (VC)        ← User → Agent authorization
      └── AP2 Cart Mandate (VC)          ← Cart snapshot lock
            │
            └── dev.ucp.shopping.ap2_mandate extension
                 (merchant verifies both VCs before completing checkout)
```

## What Makes This Spec-Compliant

| Concern | Old (main branch) | This branch |
|---|---|---|
| UCP profile shape | Invented fields | Real `2026-04-08` spec shape at `/.well-known/ucp` |
| Capability names | `"checkout"` | `dev.ucp.shopping.checkout` (reverse-domain per spec) |
| `spec` + `schema` URLs | Absent | Real `ucp.dev` URLs included |
| Platform header | Absent | `UCP-Agent: profile="..."` on every request (RFC 8941) |
| Capability negotiation | Absent | Intersection algorithm + echo-back in every response |
| `ucp` block in responses | Absent | Every response carries `ucp.version` + `ucp.capabilities` |
| AP2 types | Hand-rolled models | `ap2` package from `google-agentic-commerce/AP2` |
| AP2 mandate extension | Bolted on separately | `dev.ucp.shopping.ap2_mandate` capability declared in profile |

## Project Structure

```
tesseract/
├── README.md
├── .env.example
├── pyproject.toml
└── src/
    ├── merchant/
    │   ├── server.py          # UCP-compliant FastAPI merchant
    │   ├── profile.py         # /.well-known/ucp profile builder
    │   ├── negotiation.py     # Capability intersection algorithm
    │   ├── catalog.py         # Mock product catalog
    │   └── models.py          # Pydantic models (UCP spec-shaped)
    ├── agent/
    │   ├── shopping_agent.py  # ADK agent entrypoint
    │   └── tools.py           # UCP + AP2 tool callables
    └── ap2/
        ├── mandates.py        # Intent + Cart Mandate issuance
        └── verifier.py        # Mandate verification
```

## Quickstart

```bash
# 1. Install AP2 types from official repo
uv pip install git+https://github.com/google-agentic-commerce/AP2.git@main

# 2. Install project deps
uv sync

# 3. Set env vars
cp .env.example .env
# add GOOGLE_API_KEY

# 4. Start merchant server
uv run uvicorn src.merchant.server:app --reload --port 8080

# 5. Run agent (new terminal)
uv run python src/agent/shopping_agent.py
```

## References
- [UCP Specification (2026-04-08)](https://ucp.dev/2026-04-08/specification/overview/)
- [AP2 GitHub](https://github.com/google-agentic-commerce/AP2)
- [Google UCP Developer Guide](https://developers.google.com/merchant/ucp)
