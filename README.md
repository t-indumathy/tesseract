# Tesseract — UCP + AP2 PoC

A working end-to-end proof-of-concept for the
[Universal Checkout Protocol (UCP)](https://ucp.dev/2026-04-08/specification/overview/)
and
[Agent Payments Protocol v2 (AP2)](https://github.com/google-agentic-commerce/AP2).

Built on the official AP2 sample role pattern
([`merchant_agent`](https://github.com/google-agentic-commerce/AP2/tree/main/code/samples/python/src/roles/merchant_agent) +
[`credentials_provider_agent`](https://github.com/google-agentic-commerce/AP2/tree/main/code/samples/python/src/roles/credentials_provider_agent)).

---

## Architecture

```
 Shopping Agent (buyer)
        │
        │  1. GET /.well-known/ucp          ← capability discovery
        │  2. POST /ucp/catalog/search       ← product search
        │  3. POST /ucp/cart                 ← cart creation
        │  4. POST /ucp/checkout             ← AP2 mandate verification
        │  5. GET  /ucp/order/{id}           ← order status
        ▼
  ┌────────────────────────────────┐
  │  Tesseract Merchant Server           │
  │  src/merchant/server.py (FastAPI)    │
  │  └ UCP-Version header on all routes  │
  │  └ Reverse-domain capability names   │
  └────────────────────────────────┘
        │
        ▼
  ┌────────────────────────────────┐
  │  AP2 Mandate Layer                   │
  │  src/ap2/mandate_verifier.py         │
  │  └ MandateClient().verify()          │
  │  └ HNP (single-token SD-JWT)         │
  │  └ DPC chain ("~~" split, X5c/kid)   │
  │  └ Stub mode when ap2-sdk absent     │
  └────────────────────────────────┘
```

## Project Structure

```
tesseract/
├── src/
│   ├── merchant/
│   │   ├── server.py          # FastAPI app — UCP-compliant routes
│   │   ├── catalog.py         # Mock product catalog (5 SKUs)
│   │   ├── storage.py         # In-memory cart + order store
│   │   └── ucp_manifest.py    # UCP capability manifest builder
│   └── ap2/
│       ├── mandate_verifier.py # MandateClient wrapper (HNP + DPC)
│       └── credentials.py      # Stub account/token store
├── tests/
│   └── test_e2e_ucp_ap2.py    # End-to-end pytest suite
├── pyproject.toml
└── README.md
```

## Quick Start

```bash
# 1. Install
pip install -e ".[dev]"

# 2. Run the server
python -m src.merchant.server
# → http://localhost:8080

# 3. Run the test suite
pytest tests/ -v
```

## Key Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/.well-known/ucp` | UCP capability manifest |
| `POST` | `/ucp/catalog/search` | Keyword product search |
| `POST` | `/ucp/cart` | Create cart + compute tax |
| `POST` | `/ucp/checkout` | AP2 mandate verification + order confirm |
| `GET` | `/ucp/order/{id}` | Order status |

## AP2 Mandate Flows

The checkout endpoint supports both AP2 flows from the official sample:

### HNP (Hosted Network Payment — standard)
```json
{
  "cart_id": "<cart_id>",
  "checkout_mandate_sdjwt": "<CheckoutMandate SD-JWT>",
  "payment_mandate_sdjwt":  "<PaymentMandate SD-JWT>"
}
```

### DPC (Digital Payment Credential — wallet-bound)
Same shape. The `~~` separator in the SD-JWT string triggers the
three-level delegation path: `DPC cnf → wallet key → KB-SD-JWT cnf → agent key → agent KB-JWT`.

### PoC Fallback (no ap2-sdk)
```json
{
  "cart_id": "<cart_id>",
  "intent_mandate": { "action": "purchase" },
  "cart_mandate":   { "authorized_total_usd": 200.0 }
}
```

## Spec Compliance Notes

| Requirement | Implementation |
|-------------|----------------|
| Manifest at `/.well-known/ucp` | ✅ `server.py` |
| `UCP-Version` header on all responses | ✅ `_ucp_headers()` |
| Reverse-domain capability names | ✅ `ucp_manifest.py` |
| `UCP-Agent` header echoed in manifest | ✅ `ucp_manifest.build_manifest()` |
| AP2 HNP single-token verification | ✅ `mandate_verifier.verify_*()` |
| AP2 DPC chain verification (`~~`) | ✅ `mandate_verifier.verify_*()` |
| Graceful stub when ap2-sdk absent | ✅ `_AP2_AVAILABLE` guard |

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `AGENT_PROVIDER_PUBLIC_KEY_PATH` | `` | Path to agent-provider public key PEM |
| `MERCHANT_SIGNING_KEY_PATH` | `` | Path to merchant EC private key PEM |
| `AP2_CERTS_DIR` | `certs/` | Directory containing `issuer_cert_sdjwt.pem` |
| `MERCHANT_AUD` | `https://merchant.com` | Expected audience in CheckoutMandate |
| `MERCHANT_NONCE` | `merchant-nonce-xyz` | Expected nonce in CheckoutMandate |
| `MERCHANT_BASE_URL` | `http://localhost:8080` | Base URL for capability endpoints |

## References

- [UCP Specification 2026-04-08](https://ucp.dev/2026-04-08/specification/overview/)
- [AP2 GitHub (Apache-2.0)](https://github.com/google-agentic-commerce/AP2)
- [AP2 merchant_agent sample](https://github.com/google-agentic-commerce/AP2/tree/main/code/samples/python/src/roles/merchant_agent)
- [AP2 credentials_provider_agent sample](https://github.com/google-agentic-commerce/AP2/tree/main/code/samples/python/src/roles/credentials_provider_agent)
