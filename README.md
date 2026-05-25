# Tesseract — UCP + AP2 Agentic Commerce PoC

A minimal working proof-of-concept demonstrating **Universal Commerce Protocol (UCP)** + **Agent Payments Protocol (AP2)** flowing end-to-end through a simulated AI shopping agent.

## What This PoC Demonstrates

```
User → Shopping Agent (ADK / Gemini) → UCP Merchant Server → AP2 Payment Flow
                                               ↕
                                    Cart Mandate (VC)
                                    Intent Mandate (VC)
```

1. **Discovery** — Agent queries the UCP merchant's capability manifest
2. **Cart Building** — Agent selects a product and builds a cart
3. **AP2 Intent Mandate** — User confirms intent; a Verifiable Credential is issued
4. **AP2 Cart Mandate** — Cart details are cryptographically signed
5. **Checkout** — UCP merchant processes the order referencing the AP2 mandates
6. **Order Confirmation** — Non-repudiable, auditable transaction record

## Project Structure

```
tesseract/
├── README.md
├── .env.example               # Required env vars
├── pyproject.toml             # uv-compatible project manifest
├── src/
│   ├── merchant/              # UCP Merchant Server (FastAPI)
│   │   ├── __init__.py
│   │   ├── server.py          # UCP REST endpoints
│   │   ├── catalog.py         # Mock product catalog
│   │   └── models.py          # UCP Pydantic models
│   ├── agent/                 # Shopping Agent (Google ADK)
│   │   ├── __init__.py
│   │   ├── shopping_agent.py  # Main agent entrypoint
│   │   └── tools.py           # UCP + AP2 tool bindings
│   └── ap2/                   # AP2 mandate handling
│       ├── __init__.py
│       ├── mandates.py        # Intent & Cart Mandate issuance
│       └── verifier.py        # VC verification logic
├── scenarios/
│   └── buy_item/
│       ├── README.md
│       └── run.sh
└── tests/
    ├── test_ucp_merchant.py
    └── test_ap2_mandates.py
```

## Quickstart

### Prerequisites
- Python 3.10+
- [`uv`](https://github.com/astral-sh/uv) package manager
- Google API key (from [AI Studio](https://aistudio.google.com/))

### Setup

```bash
# 1. Clone and enter the repo
git clone https://github.com/t-indumathy/tesseract.git
cd tesseract

# 2. Copy and fill in env vars
cp .env.example .env
# edit .env with your GOOGLE_API_KEY

# 3. Install dependencies
uv sync

# 4. Run the merchant server (terminal 1)
uv run uvicorn src.merchant.server:app --reload --port 8080

# 5. Run the shopping agent (terminal 2)
uv run python src/agent/shopping_agent.py
```

### Run the full buy_item scenario

```bash
bash scenarios/buy_item/run.sh
```

## Protocol Flow (Detailed)

### UCP Side

| Endpoint | Method | Description |
|---|---|---|
| `/.well-known/ucp-manifest` | GET | Capability discovery |
| `/ucp/catalog/search` | POST | Product search |
| `/ucp/cart` | POST | Create cart |
| `/ucp/checkout` | POST | Initiate checkout |
| `/ucp/order/{id}` | GET | Order status |

### AP2 Side

| Object | Role |
|---|---|
| **Intent Mandate (VC)** | Cryptographically-signed user intent — proves the user authorised the agent to act |
| **Cart Mandate (VC)** | Signed cart snapshot — non-repudiable record of what was purchased and at what price |

AP2 mandates are issued as [W3C Verifiable Credentials](https://www.w3.org/TR/vc-data-model/) and verified by the merchant before processing checkout.

## Key Design Decisions

- **Mock Verifiable Credentials** — real VC signing uses `cryptography` lib with ECDSA P-256; this PoC uses a simplified HMAC-based substitute so you don't need a DID/wallet setup
- **Stateless merchant server** — in-memory order store; swap with any DB for production
- **Agent framework** — uses Google ADK with Gemini 2.5 Flash; swap the LLM or framework freely since AP2/UCP are protocol-agnostic

## References

- [UCP Specification](https://ucp.dev)
- [UCP GitHub](https://github.com/universal-commerce-protocol/ucp)
- [AP2 GitHub](https://github.com/google-agentic-commerce/AP2)
- [Google UCP Developer Guide](https://developers.google.com/merchant/ucp)
- [AP2 Cloud Blog](https://cloud.google.com/blog/products/ai-machine-learning/announcing-agents-to-payments-ap2-protocol)
