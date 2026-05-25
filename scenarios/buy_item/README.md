# Scenario: Buy Item

Demonstrates the full end-to-end agentic commerce flow:

```
User intent → Catalog discovery → Cart creation → AP2 mandate issuance → UCP checkout → Order confirmed
```

## Steps Covered

1. Agent discovers merchant capabilities via UCP manifest
2. Agent searches catalog for the user's requested item
3. Agent builds a UCP cart
4. User confirms intent → AP2 **Intent Mandate** (VC) is issued
5. Cart snapshot is committed → AP2 **Cart Mandate** (VC) is issued  
6. Merchant verifies both mandates cryptographically
7. UCP checkout succeeds → Order confirmed with non-repudiable audit trail

## Running

```bash
bash scenarios/buy_item/run.sh
```

## What to Watch For

- The `Intent Mandate` and `Cart Mandate` IDs printed in step 4
- The `proof.value` field — this is the HMAC signature binding user → agent → merchant → cart
- The merchant's cross-check: if you tamper with `cart_id` in the mandate, checkout returns HTTP 400
