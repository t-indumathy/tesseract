# KYA Layer-0: Agent Pre-Registration
## Detailed Design & Technical Implementation

> **Version:** 1.0 | **Audience:** Platform Architects, Security Engineers, Compliance Tech  
> **Scope:** Full design of the Layer-0 KYA pre-registration system for a bank or fintech, covering
> data models, APIs, credential issuance, mandate enforcement, runtime verification, revocation,
> and audit. Designed to be KYC/KYB-native and TAP/AP2-compatible.

---

## Table of Contents

1. [System Architecture](#1-system-architecture)
2. [Core Data Models](#2-core-data-models)
3. [Registration Lifecycle](#3-registration-lifecycle)
4. [API Specification](#4-api-specification)
5. [Credential Format & Key Management](#5-credential-format--key-management)
6. [Mandate Engine](#6-mandate-engine)
7. [Runtime Verification Gateway](#7-runtime-verification-gateway)
8. [Revocation & Lifecycle Management](#8-revocation--lifecycle-management)
9. [Audit & Observability](#9-audit--observability)
10. [Risk Tiering Model](#10-risk-tiering-model)
11. [KYC/KYB Integration](#11-kyckyb-integration)
12. [Security Threat Model](#12-security-threat-model)

---

## 1. System Architecture

### 1.1 Component Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        CUSTOMER ENVIRONMENT                                  │
│                                                                               │
│   ┌────────────────┐     ┌────────────────┐     ┌──────────────────────┐    │
│   │  Retail User   │     │ Commercial User │     │   Agent Runtime      │    │
│   │  (KYC'd)       │     │  (KYB'd)        │     │ (LangChain/Operator/ │    │
│   └───────┬────────┘     └───────┬─────────┘     │  Claude/Copilot etc) │    │
│           │                      │                └──────────┬───────────┘    │
│           │                      │                           │                │
└───────────┼──────────────────────┼───────────────────────────┼────────────────┘
            │   Registration        │                           │  Signed Request
            ▼                      ▼                           ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                        BANK / FINTECH PLATFORM                               │
│                                                                               │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │                     LAYER-0: KYA PRE-REGISTRATION                    │   │
│  │                                                                        │   │
│  │  ┌─────────────┐  ┌──────────────┐  ┌───────────┐  ┌─────────────┐  │   │
│  │  │   KYA       │  │  Credential  │  │  Mandate  │  │  Principal  │  │   │
│  │  │  Registry   │  │   Service    │  │  Engine   │  │  Binder     │  │   │
│  │  │  (Postgres) │  │  (JWK/JWT)   │  │  (Rules)  │  │  (KYC/KYB) │  │   │
│  │  └──────┬──────┘  └──────┬───────┘  └─────┬─────┘  └──────┬──────┘  │   │
│  │         │                │                 │               │          │   │
│  │  ┌──────┴──────┐  ┌──────┴───────┐  ┌─────┴──────────────┴──────┐  │   │
│  │  │  Revocation │  │  JWKS Public │  │     Risk Tiering Engine    │  │   │
│  │  │  Service    │  │  Endpoint    │  │  (Auto-approve / Review)   │  │   │
│  │  └─────────────┘  └──────────────┘  └────────────────────────────┘  │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
│                                                                               │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │                  RUNTIME VERIFICATION GATEWAY                         │   │
│  │   (Sits in front of all payment APIs / banking APIs)                  │   │
│  │                                                                        │   │
│  │  Verify Sig → Check Revocation → Evaluate Mandate → Track Spend      │   │
│  │                         │                                             │   │
│  │              ┌──────────┴──────────┐                                 │   │
│  │              │   Spend Tracker     │                                  │   │
│  │              │   (Redis)           │                                  │   │
│  │              └─────────────────────┘                                 │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
│                                                                               │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │              PAYMENT / BANKING EXECUTION LAYER                        │   │
│  │   (ACH, Wire, Card Rail, Stablecoin — Deterministic APIs only)        │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
│                                                                               │
│  ┌─────────────────────┐  ┌────────────────────────────────────────────┐   │
│  │   Audit Service     │  │   KYC/KYB Identity Platform               │   │
│  │   (Kafka + S3)      │  │   (Existing: Jumio/Onfido/Alloy/Persona)  │   │
│  └─────────────────────┘  └────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 1.2 Technology Stack

| Layer | Technology | Rationale |
|---|---|---|
| Agent Registry | PostgreSQL 16 (JSONB) | Flexible mandate schemas, ACID for registration state |
| Credential Service | Node.js / jose library | Ed25519 JWT signing, JWKS management |
| Mandate Engine | Go service | High-throughput rule evaluation per request |
| Spend Tracker | Redis 7 (atomic INCRBY/DECRBY) | Sub-millisecond limit checks, TTL-based reset |
| Revocation Store | Redis + PostgreSQL | Fast hot-path check (Redis), durable record (PG) |
| Audit Events | Apache Kafka + S3 (Parquet) | Tamper-evident, retention-compliant, queryable |
| API Gateway | Kong / AWS API Gateway | Rate limiting, mTLS termination |
| Key Management | AWS KMS / HashiCorp Vault | HSM-backed private key storage |

---

## 2. Core Data Models

### 2.1 PostgreSQL Schema

```sql
-- ============================================================
-- PRINCIPAL TABLE
-- Link to existing KYC or KYB record. One principal can own
-- multiple agents. This is the root of the trust chain.
-- ============================================================
CREATE TABLE kya_principals (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    principal_type      TEXT NOT NULL CHECK (principal_type IN ('RETAIL', 'COMMERCIAL')),

    -- KYC / KYB foreign key (points into existing identity platform)
    kyc_record_id       TEXT,           -- for RETAIL principals
    kyb_record_id       TEXT,           -- for COMMERCIAL principals
    kyc_status          TEXT NOT NULL CHECK (kyc_status IN ('VERIFIED', 'PENDING', 'SUSPENDED')),

    -- Legal identity snapshot at time of principal binding
    legal_name          TEXT NOT NULL,
    tax_id_hash         TEXT NOT NULL,  -- hashed TIN/SSN - never store plaintext
    country_of_domicile CHAR(2) NOT NULL,

    -- Attestation: the principal accepted legal liability for all child agents
    liability_attested_at   TIMESTAMPTZ,
    liability_attestation_ip INET,
    liability_doc_version    TEXT,       -- version of T&Cs they signed

    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ============================================================
-- AGENT REGISTRATION TABLE
-- The core entity. One row per registered agent.
-- ============================================================
CREATE TABLE kya_agents (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_uid           TEXT NOT NULL UNIQUE, -- human-readable: "agt_prod_a1b2c3d4"
    principal_id        UUID NOT NULL REFERENCES kya_principals(id),

    -- Agent identity envelope
    display_name        TEXT NOT NULL,        -- "My Procurement Bot"
    agent_type          TEXT NOT NULL CHECK (agent_type IN (
                            'PAYMENT_INITIATOR',
                            'ACCOUNT_INQUIRY',
                            'TRADE_EXECUTOR',
                            'MULTI_PURPOSE',
                            'SUB_AGENT'       -- delegated by another KYA agent
                        )),
    declared_purpose    TEXT NOT NULL,        -- free-text: "Automate vendor invoice payments"

    -- Runtime provenance (what is actually running in the customer's env)
    runtime_vendor      TEXT NOT NULL,        -- "Anthropic", "OpenAI", "LangChain", "Custom"
    runtime_product     TEXT NOT NULL,        -- "Claude Computer Use", "GPT-4o Operator"
    runtime_version     TEXT,                 -- semver if available
    deployment_env      TEXT NOT NULL CHECK (deployment_env IN (
                            'CUSTOMER_PRIVATE_CLOUD',
                            'CUSTOMER_SAAS',
                            'CUSTOMER_ON_PREMISE',
                            'THIRD_PARTY_MANAGED'
                        )),
    deployment_region   TEXT,                 -- ISO 3166-2 or "EU", "US-EAST-1"

    -- Agent developer / vendor identity
    -- If the agent was built by a third-party ISV, we capture that separately
    developer_entity_name TEXT,
    developer_kyb_id      TEXT,               -- if ISV is also KYB'd with us

    -- Sub-agent relationship
    parent_agent_id     UUID REFERENCES kya_agents(id),

    -- Registration state machine
    status              TEXT NOT NULL DEFAULT 'DRAFT'
                            CHECK (status IN (
                                'DRAFT',           -- customer filling form
                                'PENDING_REVIEW',  -- submitted, awaiting risk team
                                'APPROVED',        -- credential can be issued
                                'ACTIVE',          -- credential issued and live
                                'SUSPENDED',       -- temporarily blocked
                                'REVOKED',         -- permanently terminated
                                'EXPIRED'          -- past credential expiry, needs renewal
                            )),

    risk_tier           INT CHECK (risk_tier BETWEEN 1 AND 4),
    review_notes        TEXT,
    reviewed_by         TEXT,
    reviewed_at         TIMESTAMPTZ,

    -- Lifecycle
    activated_at        TIMESTAMPTZ,
    credential_expires_at TIMESTAMPTZ,
    last_activity_at    TIMESTAMPTZ,

    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_kya_agents_principal ON kya_agents(principal_id);
CREATE INDEX idx_kya_agents_status ON kya_agents(status);
CREATE INDEX idx_kya_agents_uid ON kya_agents(agent_uid);

-- ============================================================
-- AGENT MANDATE TABLE
-- The permission scope. Strictly what the agent may do.
-- ============================================================
CREATE TABLE kya_mandates (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_id        UUID NOT NULL REFERENCES kya_agents(id) ON DELETE CASCADE,
    version         INT NOT NULL DEFAULT 1,     -- increments on each re-attestation
    is_current      BOOLEAN NOT NULL DEFAULT TRUE,

    -- Transaction type permissions (explicit whitelist)
    permitted_tx_types      TEXT[] NOT NULL,    -- e.g. ['ACH_CREDIT', 'RTP', 'CARD_PURCHASE']
    prohibited_tx_types     TEXT[],             -- explicit blocklist (belt-and-suspenders)

    -- Spend controls
    per_tx_limit_amount     NUMERIC(18,2),      -- max single transaction
    per_tx_limit_currency   CHAR(3) DEFAULT 'USD',
    daily_limit_amount      NUMERIC(18,2),
    weekly_limit_amount     NUMERIC(18,2),
    monthly_limit_amount    NUMERIC(18,2),
    cumulative_limit_amount NUMERIC(18,2),      -- lifetime cap before re-attestation required

    -- Counterparty restrictions
    permitted_counterparty_types TEXT[],        -- ['VERIFIED_VENDOR', 'WHITELISTED_PAYEE']
    counterparty_whitelist  JSONB,              -- [{name, account_hash, routing_hash}]
    domestic_only           BOOLEAN DEFAULT TRUE,
    permitted_countries     CHAR(2)[],

    -- Rail restrictions
    permitted_rails         TEXT[] NOT NULL,    -- ['ACH', 'RTP', 'CARD', 'WIRE', 'STABLECOIN']
    max_wire_amount         NUMERIC(18,2),      -- wire-specific override

    -- Sensitive action prohibitions (hard-coded for all agents unless explicitly granted)
    can_add_beneficiary         BOOLEAN DEFAULT FALSE,
    can_change_account_settings BOOLEAN DEFAULT FALSE,
    can_initiate_outbound_wire  BOOLEAN DEFAULT FALSE,
    can_access_statements       BOOLEAN DEFAULT FALSE,
    can_delegate_to_sub_agents  BOOLEAN DEFAULT FALSE,

    -- Human-in-the-loop configuration
    hitl_mode           TEXT NOT NULL CHECK (hitl_mode IN (
                            'FULL_AUTO',        -- no human confirmation needed (Tier 1/2 only)
                            'THRESHOLD_HITL',   -- HITL above a spend threshold
                            'ALWAYS_HITL'       -- every action requires human confirmation
                        )),
    hitl_threshold_amount NUMERIC(18,2),        -- applicable when mode = THRESHOLD_HITL

    -- Mandate validity
    effective_from      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    effective_until     TIMESTAMPTZ,            -- NULL = follows credential expiry

    -- Re-attestation
    reattested_by_principal BOOLEAN DEFAULT FALSE,
    reattested_at       TIMESTAMPTZ,
    reattested_ip       INET,

    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_kya_mandates_agent ON kya_mandates(agent_id, is_current);

-- ============================================================
-- AGENT CREDENTIAL TABLE
-- Record of issued JWT credentials. The JWT itself is NOT
-- stored here — only its claims and verification metadata.
-- ============================================================
CREATE TABLE kya_credentials (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_id        UUID NOT NULL REFERENCES kya_agents(id),
    jti             TEXT NOT NULL UNIQUE,       -- JWT ID - used for revocation lookup
    key_id          TEXT NOT NULL,              -- kid in JWKS
    algorithm       TEXT NOT NULL DEFAULT 'EdDSA',

    issued_at       TIMESTAMPTZ NOT NULL,
    expires_at      TIMESTAMPTZ NOT NULL,
    revoked_at      TIMESTAMPTZ,
    revocation_reason TEXT,

    -- Snapshot of mandate version bound to this credential
    mandate_id      UUID NOT NULL REFERENCES kya_mandates(id),
    mandate_version INT NOT NULL,

    -- TAP compatibility fields
    tap_agent_id    TEXT,                       -- Visa TAP agent directory entry
    tap_public_key_url TEXT,                    -- URL of agent's public key in TAP directory

    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ============================================================
-- MCP SERVER WHITELIST
-- Which MCP tool servers this agent is authorized to call
-- ============================================================
CREATE TABLE kya_agent_mcp_servers (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_id        UUID NOT NULL REFERENCES kya_agents(id),
    server_url      TEXT NOT NULL,
    server_name     TEXT NOT NULL,
    permitted_tools TEXT[],                     -- NULL = all tools on that server
    added_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (agent_id, server_url)
);

-- ============================================================
-- AUDIT EVENT TABLE (hot partition — rotate to S3 after 90d)
-- ============================================================
CREATE TABLE kya_audit_events (
    id              UUID DEFAULT gen_random_uuid(),
    event_time      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    event_type      TEXT NOT NULL,
    agent_id        UUID,
    principal_id    UUID,
    jti             TEXT,                       -- credential used
    action          TEXT,
    outcome         TEXT CHECK (outcome IN ('ALLOWED', 'DENIED', 'ESCALATED')),
    tx_amount       NUMERIC(18,2),
    tx_currency     CHAR(3),
    tx_rail         TEXT,
    counterparty_hash TEXT,
    request_ip      INET,
    request_id      TEXT,
    metadata        JSONB,
    -- Tamper-evidence: hash of (previous_hash || this_row_fields)
    chain_hash      TEXT NOT NULL
) PARTITION BY RANGE (event_time);

CREATE INDEX idx_audit_agent_time ON kya_audit_events(agent_id, event_time);
CREATE INDEX idx_audit_jti ON kya_audit_events(jti);
```

### 2.2 Agent Registration JSON Schema (API Input)

```json
{
  "$schema": "http://json-schema.org/draft-07/schema",
  "title": "AgentRegistrationRequest",
  "type": "object",
  "required": ["display_name", "agent_type", "declared_purpose", "runtime", "mandate"],
  "properties": {
    "display_name": { "type": "string", "maxLength": 100 },
    "agent_type": {
      "type": "string",
      "enum": ["PAYMENT_INITIATOR", "ACCOUNT_INQUIRY", "TRADE_EXECUTOR", "MULTI_PURPOSE", "SUB_AGENT"]
    },
    "declared_purpose": { "type": "string", "maxLength": 500 },

    "runtime": {
      "type": "object",
      "required": ["vendor", "product", "deployment_env"],
      "properties": {
        "vendor":          { "type": "string" },
        "product":         { "type": "string" },
        "version":         { "type": "string" },
        "deployment_env":  { "type": "string", "enum": ["CUSTOMER_PRIVATE_CLOUD", "CUSTOMER_SAAS", "CUSTOMER_ON_PREMISE", "THIRD_PARTY_MANAGED"] },
        "deployment_region": { "type": "string" },
        "mcp_servers": {
          "type": "array",
          "items": {
            "type": "object",
            "required": ["server_url", "server_name"],
            "properties": {
              "server_url":     { "type": "string", "format": "uri" },
              "server_name":    { "type": "string" },
              "permitted_tools": { "type": "array", "items": { "type": "string" } }
            }
          }
        }
      }
    },

    "developer": {
      "type": "object",
      "properties": {
        "entity_name": { "type": "string" },
        "kyb_id":      { "type": "string" }
      }
    },

    "mandate": {
      "type": "object",
      "required": ["permitted_tx_types", "permitted_rails", "hitl_mode"],
      "properties": {
        "permitted_tx_types": {
          "type": "array",
          "items": { "type": "string", "enum": ["ACH_CREDIT", "ACH_DEBIT", "RTP", "WIRE", "CARD_PURCHASE", "CARD_REFUND", "STABLECOIN_TRANSFER", "FX_CONVERSION"] }
        },
        "prohibited_tx_types": { "type": "array", "items": { "type": "string" } },
        "spend_limits": {
          "type": "object",
          "properties": {
            "per_transaction": { "type": "number", "minimum": 0 },
            "daily":           { "type": "number", "minimum": 0 },
            "weekly":          { "type": "number", "minimum": 0 },
            "monthly":         { "type": "number", "minimum": 0 },
            "cumulative":      { "type": "number", "minimum": 0 },
            "currency":        { "type": "string", "pattern": "^[A-Z]{3}$" }
          }
        },
        "counterparty": {
          "type": "object",
          "properties": {
            "domestic_only": { "type": "boolean" },
            "permitted_countries": { "type": "array", "items": { "type": "string", "pattern": "^[A-Z]{2}$" } },
            "whitelist": {
              "type": "array",
              "items": {
                "type": "object",
                "required": ["alias", "account_hash", "routing_hash"],
                "properties": {
                  "alias":        { "type": "string" },
                  "account_hash": { "type": "string" },
                  "routing_hash": { "type": "string" }
                }
              }
            }
          }
        },
        "permitted_rails": {
          "type": "array",
          "items": { "type": "string", "enum": ["ACH", "RTP", "WIRE", "CARD", "STABLECOIN"] }
        },
        "sensitive_permissions": {
          "type": "object",
          "properties": {
            "can_add_beneficiary":          { "type": "boolean", "default": false },
            "can_change_account_settings":  { "type": "boolean", "default": false },
            "can_initiate_outbound_wire":   { "type": "boolean", "default": false },
            "can_access_statements":        { "type": "boolean", "default": false },
            "can_delegate_to_sub_agents":   { "type": "boolean", "default": false }
          }
        },
        "hitl_mode":             { "type": "string", "enum": ["FULL_AUTO", "THRESHOLD_HITL", "ALWAYS_HITL"] },
        "hitl_threshold_amount": { "type": "number", "minimum": 0 }
      }
    },

    "public_key_jwk": {
      "type": "object",
      "description": "Agent's Ed25519 public key in JWK format. The private key stays in the customer's environment."
    }
  }
}
```

---

## 3. Registration Lifecycle

### 3.1 Full Flow Sequence

```
CUSTOMER                   KYA PORTAL              KYA REGISTRY         KYC/KYB PLATFORM
   │                           │                        │                      │
   │── POST /agents/register ──▶                        │                      │
   │   (with agent metadata,   │                        │                      │
   │    mandate, public_key)   │                        │                      │
   │                           │── Lookup principal ───▶│                      │
   │                           │◀── principal_id ───────│                      │
   │                           │                        │                      │
   │                           │── Verify KYC/KYB ──────────────────────────▶ │
   │                           │◀── status: VERIFIED ────────────────────────  │
   │                           │                        │                      │
   │                           │── Validate liability attestation exists        │
   │                           │── Validate mandate schema                     │
   │                           │── Run Risk Tiering Engine ───────────────────▶│
   │                           │◀── risk_tier: 1-4 ─────────────────────────  │
   │                           │                        │                      │
   │                           │  [IF Tier 1-2: auto-approve]                  │
   │                           │  [IF Tier 3-4: queue for manual review]       │
   │                           │                        │                      │
   │                           │── INSERT kya_agents (status=APPROVED) ───────▶│
   │                           │── INSERT kya_mandates ────────────────────────▶│
   │                           │── Store public_key_jwk ────────────────────────▶│
   │                           │                        │                      │
   │◀── 201 agent_uid, status ─│                        │                      │
   │                           │                        │                      │
   │── POST /agents/{id}/credential/issue ─────────────▶│                      │
   │                           │── Verify status=APPROVED                      │
   │                           │── Sign JWT (EdDSA, Ed25519)                   │
   │                           │── Register in JWKS directory                  │
   │                           │── UPDATE agent status=ACTIVE                  │
   │                           │── Emit audit event: CREDENTIAL_ISSUED         │
   │                           │                        │                      │
   │◀── 200 { signed_jwt, ─────│                        │                      │
   │         kid, expires_at } │                        │                      │
   │                           │                        │                      │

--- RUNTIME (every payment API call) ---

AGENT RUNTIME              KYA GATEWAY              PAYMENT API
   │                           │                        │
   │── POST /payments ─────────▶ (with KYA headers)     │
   │   KYA-Agent-Id: agt_xxx   │                        │
   │   KYA-Signature: <sig>    │                        │
   │   KYA-Signature-Input:... │                        │
   │                           │── Verify Ed25519 sig   │
   │                           │── Check revocation     │
   │                           │── Evaluate mandate     │
   │                           │── Atomic spend check (Redis)
   │                           │── Log audit event      │
   │                           │── Forward if ALLOWED ─▶│
   │◀── 200 / 4xx / 403 ───────│◀── payment response ───│
```

### 3.2 Registration State Machine

```
                    ┌─────────┐
                    │  DRAFT  │  ← Customer starts filling form
                    └────┬────┘
                         │ POST /agents/register (submitted)
                         ▼
               ┌──────────────────┐
               │  PENDING_REVIEW  │  ← Tier 3/4: awaits compliance team
               └────────┬─────────┘
                        │          └──── Tier 1/2: auto-transitions
                        │ Compliance approves
                        ▼
                  ┌──────────┐
                  │ APPROVED │  ← Credential can now be issued
                  └────┬─────┘
                       │ POST /credential/issue
                       ▼
                  ┌──────────┐
                  │  ACTIVE  │ ←─────────────────────────────────┐
                  └────┬─────┘                                    │
            ┌──────────┼──────────────┐                           │
            │          │              │                           │
            ▼          ▼              ▼                           │
      ┌──────────┐ ┌─────────┐ ┌──────────┐                      │
      │SUSPENDED │ │ EXPIRED │ │ REVOKED  │                      │
      └────┬─────┘ └────┬────┘ └──────────┘                      │
           │             │  (terminal)                            │
           │ Unsuspend   │ Re-attest & re-register                │
           └─────────────┴────────────────────────────────────────┘
```

### 3.3 Risk Tiering Engine Logic

```python
# risk_tiering_engine.py
from decimal import Decimal
from dataclasses import dataclass
from typing import List

@dataclass
class MandateRequest:
    permitted_tx_types: List[str]
    permitted_rails: List[str]
    per_tx_limit: Decimal
    daily_limit: Decimal
    can_initiate_outbound_wire: bool
    can_add_beneficiary: bool
    can_delegate_to_sub_agents: bool
    hitl_mode: str
    domestic_only: bool
    runtime_vendor: str
    has_developer_kyb: bool

def compute_risk_tier(mandate: MandateRequest) -> tuple[int, list[str]]:
    """
    Returns (tier: int 1-4, reasons: list[str])
    
    Tier 1: Read-only / micro-spend. Auto-approved.
    Tier 2: Standard payment initiation under limits. Auto-approved.
    Tier 3: High-value, sensitive permissions, or wire-capable. Manual review.
    Tier 4: Trade execution, treasury ops, sub-agent delegation. Enhanced review.
    """
    score = 0
    flags = []

    # --- Rail risk ---
    if 'WIRE' in mandate.permitted_rails:
        score += 30
        flags.append("Wire rail requested")
    if 'STABLECOIN' in mandate.permitted_rails:
        score += 20
        flags.append("Stablecoin rail requested")
    if 'RTP' in mandate.permitted_rails:
        score += 10
        flags.append("Real-time payment rail requested")

    # --- Transaction type risk ---
    if 'WIRE' in mandate.permitted_tx_types:
        score += 20
        flags.append("Outbound wire transaction type")
    if 'FX_CONVERSION' in mandate.permitted_tx_types:
        score += 15
        flags.append("FX conversion requested")

    # --- Spend limit risk ---
    if mandate.per_tx_limit > Decimal('10000'):
        score += 25
        flags.append(f"High per-tx limit: {mandate.per_tx_limit}")
    elif mandate.per_tx_limit > Decimal('1000'):
        score += 10

    if mandate.daily_limit > Decimal('50000'):
        score += 20
        flags.append(f"High daily limit: {mandate.daily_limit}")
    elif mandate.daily_limit > Decimal('10000'):
        score += 10

    # --- Sensitive permission risk ---
    if mandate.can_initiate_outbound_wire:
        score += 30
        flags.append("Outbound wire permission requested")
    if mandate.can_add_beneficiary:
        score += 25
        flags.append("Add beneficiary permission requested")
    if mandate.can_delegate_to_sub_agents:
        score += 20
        flags.append("Sub-agent delegation requested")
    if mandate.can_change_account_settings:
        score += 15

    # --- HITL mode risk ---
    if mandate.hitl_mode == 'FULL_AUTO':
        score += 15
        flags.append("Full autonomous mode (no HITL)")

    # --- Geography risk ---
    if not mandate.domestic_only:
        score += 15
        flags.append("Cross-border transactions enabled")

    # --- Runtime provenance risk ---
    if mandate.runtime_vendor == 'Custom':
        score += 10
        flags.append("Custom/unverified runtime vendor")
    if not mandate.has_developer_kyb and mandate.runtime_vendor not in ['Anthropic', 'OpenAI', 'Microsoft', 'Google']:
        score += 10
        flags.append("Third-party developer without KYB")

    # --- Tier assignment ---
    if score <= 15:
        tier = 1
    elif score <= 35:
        tier = 2
    elif score <= 65:
        tier = 3
    else:
        tier = 4

    return tier, flags
```

---

## 4. API Specification

Base URL: `https://api.{bank}.com/kya/v1`

All endpoints require:
- `Authorization: Bearer {customer_access_token}` (customer's OAuth2 token)
- `Content-Type: application/json`
- `X-Request-ID: {uuid}` (for idempotency and audit correlation)

### 4.1 Register an Agent

```
POST /agents

Request:
{
  "display_name": "Vendor Payment Bot",
  "agent_type": "PAYMENT_INITIATOR",
  "declared_purpose": "Automates payment of approved vendor invoices from AP system",
  "runtime": {
    "vendor": "Anthropic",
    "product": "Claude Computer Use",
    "version": "3.7",
    "deployment_env": "CUSTOMER_PRIVATE_CLOUD",
    "deployment_region": "US-EAST-1",
    "mcp_servers": [
      {
        "server_url": "https://mcp.ourbank.com/payments",
        "server_name": "Bank Payments MCP",
        "permitted_tools": ["initiate_payment", "get_balance", "list_transactions"]
      }
    ]
  },
  "developer": {
    "entity_name": "Anthropic PBC",
    "kyb_id": "kyb_anthropic_001"
  },
  "mandate": {
    "permitted_tx_types": ["ACH_CREDIT"],
    "permitted_rails": ["ACH"],
    "spend_limits": {
      "per_transaction": 5000.00,
      "daily": 25000.00,
      "monthly": 100000.00,
      "currency": "USD"
    },
    "counterparty": {
      "domestic_only": true,
      "whitelist": [
        {
          "alias": "Acme Supplies",
          "account_hash": "sha256:a1b2c3...",
          "routing_hash": "sha256:d4e5f6..."
        }
      ]
    },
    "sensitive_permissions": {
      "can_add_beneficiary": false,
      "can_change_account_settings": false,
      "can_initiate_outbound_wire": false
    },
    "hitl_mode": "THRESHOLD_HITL",
    "hitl_threshold_amount": 2000.00
  },
  "public_key_jwk": {
    "kty": "OKP",
    "crv": "Ed25519",
    "x": "11qYAYKxCrfVS_7TyWQHOg7hcvPapiMlrwIaaPcHURo",
    "use": "sig",
    "kid": "agent-key-2026-001"
  }
}

Response 201:
{
  "agent_uid": "agt_prod_a1b2c3d4",
  "agent_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "APPROVED",    // or "PENDING_REVIEW" for Tier 3/4
  "risk_tier": 2,
  "risk_flags": [],
  "mandate_id": "m_8f4a2b9c",
  "credential_issuance_url": "/agents/agt_prod_a1b2c3d4/credential/issue",
  "created_at": "2026-06-24T10:00:00Z"
}
```

### 4.2 Issue Credential

```
POST /agents/{agent_uid}/credential/issue

Request: {}  // no body — uses registered public key

Response 200:
{
  "signed_jwt": "eyJhbGciOiJFZERTQSIsInR5cCI6IkpXVCIsImtpZCI6ImtheS1iYW5rLTAxIn0...",
  "kid": "kya-bank-signing-key-2026-q2",
  "algorithm": "EdDSA",
  "jti": "jti_9x8y7z6w",
  "issued_at": "2026-06-24T10:00:00Z",
  "expires_at": "2026-12-24T10:00:00Z",
  "tap_headers": {
    // Pre-computed TAP-compatible header values for this agent's requests
    "Signature-Agent": "https://api.bank.com/.well-known/agent-keys/agt_prod_a1b2c3d4",
    "note": "Agent must attach KYA-Signature and KYA-Signature-Input on each request"
  }
}
```

### 4.3 Verify a Credential (Runtime — called by Gateway internally)

```
POST /credentials/verify

Request:
{
  "signed_jwt": "eyJhbGciOiJFZERTQSIsInR5cCI6IkpXVCJ9...",
  "requested_action": {
    "tx_type": "ACH_CREDIT",
    "rail": "ACH",
    "amount": 1500.00,
    "currency": "USD",
    "counterparty_account_hash": "sha256:a1b2c3..."
  }
}

Response 200:
{
  "decision": "ALLOWED",         // or "DENIED" or "HITL_REQUIRED"
  "agent_uid": "agt_prod_a1b2c3d4",
  "principal_id": "550e8400...",
  "mandate_snapshot": { ... },
  "spend_remaining": {
    "daily": 23500.00,
    "monthly": 98500.00
  },
  "hitl_required": false,
  "verification_id": "ver_xyz"   // reference for audit
}
```

### 4.4 Revoke an Agent

```
POST /agents/{agent_uid}/revoke

Request:
{
  "reason": "CUSTOMER_REQUEST",   // or: SUSPICIOUS_ACTIVITY, MANDATE_EXPIRED, PRINCIPAL_KYC_FAILED
  "notes": "Customer requested immediate shutdown"
}

Response 200:
{
  "revoked_at": "2026-06-24T11:00:00Z",
  "revocation_id": "rev_abc123",
  "credential_jti_invalidated": "jti_9x8y7z6w"
}
```

### 4.5 Re-Attest Mandate (annual / triggered by drift)

```
POST /agents/{agent_uid}/mandate/reatttest

Request:
{
  "mandate_changes": {
    "spend_limits": { "daily": 30000.00 }   // only fields being updated
  },
  "attestation": {
    "principal_confirms_accuracy": true,
    "principal_accepts_liability": true,
    "attestation_timestamp": "2026-06-24T12:00:00Z"
  }
}

Response 200:
{
  "new_mandate_id": "m_new_001",
  "mandate_version": 2,
  "new_risk_tier": 2,            // re-evaluated on new mandate
  "credential_renewal_required": false
}
```

### 4.6 Public Key Directory (JWKS — unauthenticated, for TAP compatibility)

```
GET /.well-known/agent-jwks.json

Response 200:
{
  "keys": [
    {
      "kty": "OKP",
      "crv": "Ed25519",
      "x": "11qYAYKxCrfVS_7TyWQHOg7hcvPapiMlrwIaaPcHURo",
      "use": "sig",
      "kid": "agent-key-2026-001",
      "agent_uid": "agt_prod_a1b2c3d4",
      "status": "active",
      "registered_at": "2026-06-24T10:00:00Z"
    }
  ]
}

GET /.well-known/agent-keys/{agent_uid}   // per-agent public key (TAP directory format)
```

---

## 5. Credential Format & Key Management

### 5.1 JWT Structure

The bank acts as the **issuer** of the credential. The agent's private key signs *requests*; the bank's private key signs *the credential itself*.

#### 5.1.1 Credential JWT (Bank-issued, Ed25519 / EdDSA)

```json
// HEADER
{
  "alg": "EdDSA",
  "typ": "JWT",
  "kid": "kya-bank-signing-key-2026-q2"
}

// PAYLOAD
{
  // Standard JWT claims
  "iss": "https://api.bank.com/kya",           // Bank is issuer
  "sub": "agt_prod_a1b2c3d4",                  // Agent UID
  "aud": ["https://payments.bank.com", "https://api.bank.com"],
  "iat": 1750760400,
  "exp": 1766485200,                            // 6-month TTL (adjustable by risk tier)
  "jti": "jti_9x8y7z6w",                       // Unique — used for revocation

  // KYA-specific claims
  "kya_version": "1.0",
  "agent_type": "PAYMENT_INITIATOR",
  "principal_id": "550e8400-e29b-41d4-a716-446655440000",
  "principal_type": "COMMERCIAL",
  "risk_tier": 2,
  "mandate_id": "m_8f4a2b9c",
  "mandate_version": 1,

  // Mandate snapshot (embedded for offline verification)
  "mandate": {
    "permitted_tx_types": ["ACH_CREDIT"],
    "permitted_rails": ["ACH"],
    "spend_limits": {
      "per_transaction": 5000.00,
      "daily": 25000.00,
      "monthly": 100000.00,
      "currency": "USD"
    },
    "domestic_only": true,
    "counterparty_whitelist_hash": "sha256:abc123...",  // hash of whitelist — not inline
    "sensitive_permissions": {
      "can_add_beneficiary": false,
      "can_initiate_outbound_wire": false
    },
    "hitl_mode": "THRESHOLD_HITL",
    "hitl_threshold_amount": 2000.00
  },

  // Agent's own public key (for request signing — separate from credential signing)
  "agent_public_key": {
    "kty": "OKP",
    "crv": "Ed25519",
    "x": "11qYAYKxCrfVS_7TyWQHOg7hcvPapiMlrwIaaPcHURo",
    "kid": "agent-key-2026-001"
  },

  // TAP-compatibility fields
  "tap_agent_type": "agent-payer-auth",
  "tap_operator_key_url": "https://api.bank.com/.well-known/agent-keys/agt_prod_a1b2c3d4"
}
```

#### 5.1.2 Request Signing (Agent → Bank, TAP-compatible)

The agent's runtime uses its *private* key (stored in customer env, never leaves) to sign each outbound API call:

```
HTTP Headers on every payment request:

KYA-Agent-Id: agt_prod_a1b2c3d4
KYA-Credential: eyJhbGciOiJFZERTQS...   // the bank-issued JWT above
KYA-Signature-Input: sig1=("@method" "@path" "@authority" "content-type" "content-digest");
                          created=1750760400; keyid="agent-key-2026-001"; tag="kya-payer-auth"
KYA-Signature: sig1=:base64urlEncodedSignature:
Content-Digest: sha-256=:47DEQpj8HBSa+/TImW+5JCeuQeRkm5NMpJWZG3hSuFU=:
```

#### 5.1.3 Key Management

```
┌─────────────────────────────────────────────────────────┐
│ BANK KEY (credential signing)                           │
│ Stored in: AWS KMS (HSM-backed)                         │
│ Access: kya-credential-service only                     │
│ Rotation: Quarterly (new kid each quarter)              │
│ Old keys: Retained for verification until all JWTs exp  │
└─────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────┐
│ AGENT KEYPAIR (request signing)                         │
│ Private key: Customer's environment (never leaves)      │
│ Public key: Registered in kya_agents at registration    │
│             Exposed in /.well-known/agent-jwks.json     │
│ Rotation: Customer-initiated via /agents/{id}/keys/rotate│
└─────────────────────────────────────────────────────────┘
```

---

## 6. Mandate Engine

### 6.1 Evaluation Logic

```go
// mandate_engine.go
package mandate

import (
    "context"
    "errors"
    "github.com/redis/go-redis/v9"
    "time"
    "fmt"
)

type TransactionRequest struct {
    AgentUID        string
    TxType          string
    Rail            string
    Amount          float64
    Currency        string
    CounterpartyHash string
    IsInternational bool
}

type Decision struct {
    Allowed        bool
    HITLRequired   bool
    DenialReason   string
    SpendRemaining SpendRemaining
    VerificationID string
}

type SpendRemaining struct {
    Daily   float64
    Weekly  float64
    Monthly float64
}

type MandateEngine struct {
    rdb    *redis.Client
    db     AgentRepository
}

func (e *MandateEngine) Evaluate(ctx context.Context, req TransactionRequest, credential *AgentCredential) (*Decision, error) {
    mandate := credential.Mandate

    // Step 1: Transaction type check
    if !contains(mandate.PermittedTxTypes, req.TxType) {
        return deny("TX_TYPE_NOT_PERMITTED", fmt.Sprintf("tx_type %s not in mandate", req.TxType)), nil
    }
    if contains(mandate.ProhibitedTxTypes, req.TxType) {
        return deny("TX_TYPE_EXPLICITLY_PROHIBITED", ""), nil
    }

    // Step 2: Rail check
    if !contains(mandate.PermittedRails, req.Rail) {
        return deny("RAIL_NOT_PERMITTED", ""), nil
    }

    // Step 3: Geography check
    if mandate.DomesticOnly && req.IsInternational {
        return deny("CROSS_BORDER_NOT_PERMITTED", ""), nil
    }

    // Step 4: Counterparty whitelist check (if whitelist is set)
    if len(mandate.CounterpartyWhitelist) > 0 {
        if !isWhitelisted(req.CounterpartyHash, mandate.CounterpartyWhitelist) {
            return deny("COUNTERPARTY_NOT_WHITELISTED", ""), nil
        }
    }

    // Step 5: Sensitive permission checks
    if req.TxType == "WIRE" && !mandate.SensitivePermissions.CanInitiateOutboundWire {
        return deny("WIRE_NOT_PERMITTED", ""), nil
    }

    // Step 6: Per-transaction limit (synchronous, no Redis needed)
    if req.Amount > mandate.SpendLimits.PerTransaction {
        return deny("PER_TX_LIMIT_EXCEEDED", fmt.Sprintf("%.2f > %.2f", req.Amount, mandate.SpendLimits.PerTransaction)), nil
    }

    // Step 7: Velocity checks via Redis (atomic)
    spendResult, err := e.checkAndReserveSpend(ctx, credential.AgentUID, req.Amount, mandate.SpendLimits)
    if err != nil {
        return nil, err
    }
    if !spendResult.Allowed {
        return deny(spendResult.DenialCode, ""), nil
    }

    // Step 8: HITL check
    hitlRequired := false
    if mandate.HITLMode == "ALWAYS_HITL" {
        hitlRequired = true
    } else if mandate.HITLMode == "THRESHOLD_HITL" && req.Amount >= mandate.HITLThreshold {
        hitlRequired = true
    }

    return &Decision{
        Allowed:      true,
        HITLRequired: hitlRequired,
        SpendRemaining: SpendRemaining{
            Daily:   spendResult.DailyRemaining,
            Monthly: spendResult.MonthlyRemaining,
        },
    }, nil
}

// Step 7 detail: Atomic Redis spend check + reservation
func (e *MandateEngine) checkAndReserveSpend(
    ctx context.Context,
    agentUID string,
    amount float64,
    limits SpendLimits,
) (*SpendCheckResult, error) {

    // Redis keys with appropriate TTLs
    dailyKey   := fmt.Sprintf("kya:spend:daily:%s:%s",   agentUID, today())
    weeklyKey  := fmt.Sprintf("kya:spend:weekly:%s:%s",  agentUID, thisWeek())
    monthlyKey := fmt.Sprintf("kya:spend:monthly:%s:%s", agentUID, thisMonth())

    amountCents := int64(amount * 100)

    // Lua script ensures atomicity — all checks and increments happen together
    luaScript := redis.NewScript(`
        local daily_key   = KEYS[1]
        local weekly_key  = KEYS[2]
        local monthly_key = KEYS[3]
        local amount      = tonumber(ARGV[1])
        local daily_limit = tonumber(ARGV[2])
        local weekly_limit = tonumber(ARGV[3])
        local monthly_limit = tonumber(ARGV[4])
        local daily_ttl   = tonumber(ARGV[5])
        local weekly_ttl  = tonumber(ARGV[6])
        local monthly_ttl = tonumber(ARGV[7])

        local daily_used   = tonumber(redis.call('GET', daily_key) or '0')
        local weekly_used  = tonumber(redis.call('GET', weekly_key) or '0')
        local monthly_used = tonumber(redis.call('GET', monthly_key) or '0')

        if daily_limit > 0 and (daily_used + amount) > daily_limit then
            return {'DENIED', 'DAILY_LIMIT_EXCEEDED', daily_used, weekly_used, monthly_used}
        end
        if weekly_limit > 0 and (weekly_used + amount) > weekly_limit then
            return {'DENIED', 'WEEKLY_LIMIT_EXCEEDED', daily_used, weekly_used, monthly_used}
        end
        if monthly_limit > 0 and (monthly_used + amount) > monthly_limit then
            return {'DENIED', 'MONTHLY_LIMIT_EXCEEDED', daily_used, weekly_used, monthly_used}
        end

        -- Reserve spend
        redis.call('INCRBY', daily_key,   amount)
        redis.call('EXPIRE', daily_key,   daily_ttl)
        redis.call('INCRBY', weekly_key,  amount)
        redis.call('EXPIRE', weekly_key,  weekly_ttl)
        redis.call('INCRBY', monthly_key, amount)
        redis.call('EXPIRE', monthly_key, monthly_ttl)

        return {'ALLOWED', '', 
                daily_used + amount, weekly_used + amount, monthly_used + amount}
    `)

    result, err := luaScript.Run(ctx, e.rdb,
        []string{dailyKey, weeklyKey, monthlyKey},
        amountCents,
        int64(limits.Daily * 100),
        int64(limits.Weekly * 100),
        int64(limits.Monthly * 100),
        secondsUntilEndOfDay(),
        secondsUntilEndOfWeek(),
        secondsUntilEndOfMonth(),
    ).StringSlice()

    if err != nil {
        return nil, err
    }

    if result[0] == "DENIED" {
        return &SpendCheckResult{Allowed: false, DenialCode: result[1]}, nil
    }

    return &SpendCheckResult{
        Allowed:          true,
        DailyRemaining:   (limits.Daily*100 - float64(parseIntResult(result[2]))) / 100,
        MonthlyRemaining: (limits.Monthly*100 - float64(parseIntResult(result[4]))) / 100,
    }, nil
}

// Rollback spend reservation on downstream payment failure
func (e *MandateEngine) RollbackSpend(ctx context.Context, agentUID string, amount float64) error {
    amountCents := int64(amount * 100)
    keys := []string{
        fmt.Sprintf("kya:spend:daily:%s:%s",   agentUID, today()),
        fmt.Sprintf("kya:spend:weekly:%s:%s",  agentUID, thisWeek()),
        fmt.Sprintf("kya:spend:monthly:%s:%s", agentUID, thisMonth()),
    }
    for _, key := range keys {
        if err := e.rdb.DecrBy(ctx, key, amountCents).Err(); err != nil {
            return err  // log and alert; don't fail silently
        }
    }
    return nil
}
```

---

## 7. Runtime Verification Gateway

### 7.1 Middleware Implementation (Node.js / Express)

```typescript
// kya-gateway-middleware.ts
import { Request, Response, NextFunction } from 'express';
import * as jose from 'jose';
import Redis from 'ioredis';
import { MandateEngine } from './mandate-engine';
import { AuditService } from './audit-service';
import { RevocationService } from './revocation-service';

interface KYARequest extends Request {
  kya?: {
    agentUID: string;
    principalId: string;
    riskTier: number;
    mandate: AgentMandate;
    verificationId: string;
  };
}

export class KYAGatewayMiddleware {
  constructor(
    private mandateEngine: MandateEngine,
    private revocationService: RevocationService,
    private auditService: AuditService,
    private bankPublicKeySet: jose.KeyLike,
  ) {}

  middleware() {
    return async (req: KYARequest, res: Response, next: NextFunction) => {
      const requestId = req.headers['x-request-id'] as string;
      const agentId   = req.headers['kya-agent-id'] as string;
      const credentialJwt = req.headers['kya-credential'] as string;

      // === STEP 1: Presence check ===
      if (!agentId || !credentialJwt) {
        return res.status(401).json({
          error: 'KYA_CREDENTIAL_MISSING',
          message: 'This endpoint requires a KYA-Agent-Id and KYA-Credential header.'
        });
      }

      // === STEP 2: Verify bank-issued credential signature ===
      let payload: AgentCredentialPayload;
      try {
        const { payload: p } = await jose.jwtVerify(credentialJwt, this.bankPublicKeySet, {
          issuer: 'https://api.bank.com/kya',
          audience: req.hostname,
        });
        payload = p as AgentCredentialPayload;
      } catch (err) {
        await this.auditService.emit({
          event_type: 'CREDENTIAL_VERIFICATION_FAILED',
          agent_id: agentId,
          outcome: 'DENIED',
          metadata: { error: (err as Error).message, request_id: requestId },
        });
        return res.status(401).json({ error: 'KYA_CREDENTIAL_INVALID' });
      }

      // === STEP 3: Verify agent_uid matches credential subject ===
      if (payload.sub !== agentId) {
        return res.status(401).json({ error: 'KYA_AGENT_ID_MISMATCH' });
      }

      // === STEP 4: Revocation check (Redis fast-path, PG fallback) ===
      const isRevoked = await this.revocationService.isRevoked(payload.jti);
      if (isRevoked) {
        await this.auditService.emit({
          event_type: 'REVOKED_CREDENTIAL_USED',
          agent_id: agentId,
          jti: payload.jti,
          outcome: 'DENIED',
        });
        return res.status(401).json({ error: 'KYA_CREDENTIAL_REVOKED' });
      }

      // === STEP 5: Verify agent request signature (Ed25519) ===
      const agentPublicKey = await jose.importJWK(payload.agent_public_key);
      const signatureHeader = req.headers['kya-signature'] as string;
      const signatureInput  = req.headers['kya-signature-input'] as string;

      const signatureValid = await this.verifyRequestSignature(
        req, agentPublicKey, signatureHeader, signatureInput
      );
      if (!signatureValid) {
        return res.status(401).json({ error: 'KYA_REQUEST_SIGNATURE_INVALID' });
      }

      // === STEP 6: Extract transaction intent from request body ===
      const txRequest = this.extractTransactionIntent(req);

      // === STEP 7: Mandate evaluation + spend check ===
      const decision = await this.mandateEngine.evaluate(agentId, txRequest, payload.mandate);

      if (!decision.allowed) {
        await this.auditService.emit({
          event_type: 'MANDATE_DENIED',
          agent_id: agentId,
          jti: payload.jti,
          action: txRequest.txType,
          outcome: 'DENIED',
          tx_amount: txRequest.amount,
          metadata: { denial_reason: decision.denialReason },
        });
        return res.status(403).json({
          error: 'KYA_MANDATE_VIOLATION',
          reason: decision.denialReason,
          spend_remaining: decision.spendRemaining,
        });
      }

      // === STEP 8: HITL gate ===
      if (decision.hitlRequired) {
        const approval = await this.requestHITLApproval(payload, txRequest, requestId);
        if (!approval.approved) {
          return res.status(202).json({
            error: 'KYA_HITL_PENDING',
            approval_id: approval.approvalId,
            message: 'Human confirmation required. Poll /approvals/{id} for status.',
          });
        }
      }

      // === STEP 9: Attach KYA context to request — available to downstream handlers ===
      req.kya = {
        agentUID:       agentId,
        principalId:    payload.principal_id,
        riskTier:       payload.risk_tier,
        mandate:        payload.mandate,
        verificationId: decision.verificationId,
      };

      // Emit pre-execution audit event
      await this.auditService.emit({
        event_type: 'TX_PRE_AUTHORIZED',
        agent_id:   agentId,
        jti:        payload.jti,
        action:     txRequest.txType,
        outcome:    'ALLOWED',
        tx_amount:  txRequest.amount,
        tx_rail:    txRequest.rail,
        counterparty_hash: txRequest.counterpartyHash,
        metadata: {
          request_id:       requestId,
          verification_id:  decision.verificationId,
          hitl_approved:    decision.hitlRequired,
          spend_remaining:  decision.spendRemaining,
        },
      });

      next();
    };
  }

  // On downstream payment failure, roll back spend reservation
  async onPaymentFailure(agentUID: string, amount: number): Promise<void> {
    await this.mandateEngine.rollbackSpend(agentUID, amount);
  }
}
```

### 7.2 Verification Flow Summary

```
Agent Request arrives at Gateway
          │
          ├─ [1] KYA headers present?          → NO  → 401 KYA_CREDENTIAL_MISSING
          │
          ├─ [2] Bank signature on JWT valid?  → NO  → 401 KYA_CREDENTIAL_INVALID
          │
          ├─ [3] agent_uid == JWT.sub?         → NO  → 401 KYA_AGENT_ID_MISMATCH
          │
          ├─ [4] JTI in revocation list?       → YES → 401 KYA_CREDENTIAL_REVOKED
          │
          ├─ [5] Agent request signature valid? → NO  → 401 KYA_REQUEST_SIGNATURE_INVALID
          │
          ├─ [6] TX type in mandate?           → NO  → 403 MANDATE_VIOLATION
          │
          ├─ [7] Rail in mandate?              → NO  → 403 MANDATE_VIOLATION
          │
          ├─ [8] Counterparty whitelisted?     → NO  → 403 MANDATE_VIOLATION
          │
          ├─ [9] Spend limits OK? (Redis)      → NO  → 403 LIMIT_EXCEEDED
          │
          ├─ [10] HITL required?               → YES → 202 HITL_PENDING
          │
          └─ [11] ALLOWED → attach req.kya context → forward to Payment API
```

---

## 8. Revocation & Lifecycle Management

### 8.1 Revocation Service

```typescript
// revocation-service.ts
import Redis from 'ioredis';
import { Pool } from 'pg';
import { KafkaProducer } from './kafka';

export class RevocationService {
  private REVOCATION_KEY_PREFIX = 'kya:revoked:jti:';
  private REVOCATION_TTL = 60 * 60 * 24 * 400; // 400 days (longer than max JWT TTL)

  constructor(
    private redis: Redis,
    private pg: Pool,
    private kafka: KafkaProducer,
  ) {}

  /**
   * Immediately revoke an agent credential.
   * Writes to Redis first (instant effect) then to PG (durable record).
   */
  async revoke(agentUID: string, jti: string, reason: string, revokedBy: string): Promise<void> {
    const revokedAt = new Date().toISOString();

    // 1. Hot-path: Redis cache (sub-millisecond check on every request)
    await this.redis.setex(
      `${this.REVOCATION_KEY_PREFIX}${jti}`,
      this.REVOCATION_TTL,
      JSON.stringify({ reason, revokedAt })
    );

    // 2. Durable record: PostgreSQL
    await this.pg.query(`
      UPDATE kya_credentials
      SET revoked_at = $1, revocation_reason = $2
      WHERE jti = $3
    `, [revokedAt, reason, jti]);

    // 3. Update agent status
    await this.pg.query(`
      UPDATE kya_agents SET status = 'REVOKED', updated_at = NOW()
      WHERE agent_uid = $1
    `, [agentUID]);

    // 4. Publish revocation event (downstream systems can subscribe)
    await this.kafka.send('kya.revocations', {
      agent_uid: agentUID,
      jti,
      reason,
      revoked_at: revokedAt,
      revoked_by: revokedBy,
    });

    // Note: In-flight transactions that passed gateway but not yet settled
    // are handled by the payment layer's idempotency + late revocation check.
  }

  /**
   * Fast revocation check — Redis only.
   * Falls back to PG if Redis misses (after cache warm-up period).
   */
  async isRevoked(jti: string): Promise<boolean> {
    const cached = await this.redis.get(`${this.REVOCATION_KEY_PREFIX}${jti}`);
    if (cached !== null) return true;

    // Cache miss — check PG (only during warm-up window)
    const result = await this.pg.query(
      `SELECT revoked_at FROM kya_credentials WHERE jti = $1 AND revoked_at IS NOT NULL`,
      [jti]
    );
    if (result.rows.length > 0) {
      // Re-populate Redis cache
      await this.redis.setex(
        `${this.REVOCATION_KEY_PREFIX}${jti}`,
        this.REVOCATION_TTL,
        JSON.stringify({ reason: 'RECOVERED_FROM_DB' })
      );
      return true;
    }

    return false;
  }

  /**
   * Suspend (reversible) — stops accepting requests but preserves registration.
   */
  async suspend(agentUID: string, jti: string, reason: string): Promise<void> {
    await this.redis.setex(
      `${this.REVOCATION_KEY_PREFIX}${jti}`,
      this.REVOCATION_TTL,
      JSON.stringify({ reason: `SUSPENDED:${reason}` })
    );
    await this.pg.query(
      `UPDATE kya_agents SET status = 'SUSPENDED' WHERE agent_uid = $1`, [agentUID]
    );
  }

  async unsuspend(agentUID: string, jti: string): Promise<void> {
    await this.redis.del(`${this.REVOCATION_KEY_PREFIX}${jti}`);
    await this.pg.query(
      `UPDATE kya_agents SET status = 'ACTIVE' WHERE agent_uid = $1`, [agentUID]
    );
  }
}
```

### 8.2 Credential TTL by Risk Tier

| Tier | Credential TTL | Re-Attestation Trigger | Auto-Renewal |
|---|---|---|---|
| 1 (Read-only / micro) | 12 months | Annual | Yes |
| 2 (Standard payment) | 6 months | 6-monthly or on mandate change | Yes (if no changes) |
| 3 (High-value / wire) | 3 months | Quarterly + on any anomaly | No — manual |
| 4 (Trade / treasury) | 1 month | Monthly + on every suspicious event | No — compliance sign-off |

### 8.3 Mandate Drift Detection

```sql
-- Detect agents whose mandate may no longer reflect principal intent
-- Run as a nightly job

SELECT
    a.agent_uid,
    a.display_name,
    p.legal_name AS principal,
    a.last_activity_at,
    m.effective_from AS mandate_set_at,
    m.reattested_at,
    EXTRACT(DAYS FROM NOW() - COALESCE(m.reattested_at, m.effective_from)) AS days_since_attestation,
    a.risk_tier

FROM kya_agents a
JOIN kya_mandates m ON m.agent_id = a.id AND m.is_current = TRUE
JOIN kya_principals p ON p.id = a.principal_id

WHERE
    a.status = 'ACTIVE'
    AND (
        -- Tier 3/4: flag if not re-attested in 90 days
        (a.risk_tier >= 3 AND COALESCE(m.reattested_at, m.effective_from) < NOW() - INTERVAL '90 days')
        OR
        -- Tier 1/2: flag if not re-attested in 180 days
        (a.risk_tier <= 2 AND COALESCE(m.reattested_at, m.effective_from) < NOW() - INTERVAL '180 days')
        OR
        -- All tiers: flag if principal KYC has been updated since mandate was set
        (p.updated_at > m.effective_from AND m.reattested_at IS NULL)
    )

ORDER BY days_since_attestation DESC;
```

---

## 9. Audit & Observability

### 9.1 Tamper-Evident Audit Chain

```python
# audit_service.py
import hashlib
import json
from datetime import datetime, timezone
from typing import Optional

class AuditService:
    """
    Produces a hash-chained audit log.
    Each event includes a hash of (previous_event_hash + this_event_content).
    Makes insertion/deletion of events cryptographically detectable.
    """

    def __init__(self, kafka_producer, pg_pool):
        self.kafka = kafka_producer
        self.pg = pg_pool

    async def emit(
        self,
        event_type: str,
        agent_id: Optional[str] = None,
        principal_id: Optional[str] = None,
        jti: Optional[str] = None,
        action: Optional[str] = None,
        outcome: Optional[str] = None,
        tx_amount: Optional[float] = None,
        tx_currency: Optional[str] = None,
        tx_rail: Optional[str] = None,
        counterparty_hash: Optional[str] = None,
        request_ip: Optional[str] = None,
        request_id: Optional[str] = None,
        metadata: Optional[dict] = None,
    ) -> str:
        event_id = generate_uuid()
        event_time = datetime.now(timezone.utc).isoformat()

        # Fetch previous chain hash for this agent (or global if agent_id is None)
        previous_hash = await self._get_last_hash(agent_id)

        # Canonical content for hashing (deterministic serialization)
        content = json.dumps({
            "id": event_id,
            "event_time": event_time,
            "event_type": event_type,
            "agent_id": agent_id,
            "principal_id": principal_id,
            "jti": jti,
            "action": action,
            "outcome": outcome,
            "tx_amount": str(tx_amount) if tx_amount else None,
            "tx_currency": tx_currency,
            "counterparty_hash": counterparty_hash,
        }, sort_keys=True, separators=(',', ':'))

        chain_hash = hashlib.sha256(
            f"{previous_hash}|{content}".encode()
        ).hexdigest()

        event = {
            "id": event_id,
            "event_time": event_time,
            "event_type": event_type,
            "agent_id": agent_id,
            "principal_id": principal_id,
            "jti": jti,
            "action": action,
            "outcome": outcome,
            "tx_amount": tx_amount,
            "tx_currency": tx_currency,
            "tx_rail": tx_rail,
            "counterparty_hash": counterparty_hash,
            "request_ip": request_ip,
            "request_id": request_id,
            "metadata": metadata,
            "chain_hash": chain_hash,
        }

        # Write to Kafka (fast, for real-time monitoring)
        await self.kafka.send('kya.audit', event)

        # Write to PG (for queries and regulatory access)
        await self.pg.execute(
            """INSERT INTO kya_audit_events
               (id, event_time, event_type, agent_id, principal_id, jti, action,
                outcome, tx_amount, tx_currency, tx_rail, counterparty_hash,
                request_ip, request_id, metadata, chain_hash)
               VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16)""",
            list(event.values())
        )

        return event_id
```

### 9.2 Key Audit Event Types

| Event Type | Trigger | Regulatory Relevance |
|---|---|---|
| `AGENT_REGISTERED` | Registration submitted | AML record creation |
| `AGENT_APPROVED` | Risk team or auto-approval | KYA onboarding complete |
| `CREDENTIAL_ISSUED` | JWT generated and returned | Identity credential lifecycle |
| `CREDENTIAL_REVOKED` | Any revocation | Immediate compliance record |
| `TX_PRE_AUTHORIZED` | Gateway allows request | Pre-execution evidence |
| `TX_COMPLETED` | Payment settled | Full audit trail |
| `TX_FAILED_ROLLBACK` | Payment failed after auth | Spend rollback record |
| `MANDATE_DENIED` | Request blocked by mandate | AML / fraud signal |
| `HITL_REQUIRED` | Threshold triggered | Human control evidence |
| `HITL_APPROVED` | Human confirmed | Authorization chain |
| `SPEND_LIMIT_HIT` | Redis limit exhausted | Risk alert |
| `REVOKED_CREDENTIAL_USED` | Revoked JTI presented | Fraud signal — escalate |
| `MANDATE_DRIFT_ALERT` | Re-attestation overdue | Compliance hygiene |
| `SUB_AGENT_DELEGATION` | Agent delegated to child | Multi-agent chain record |

### 9.3 Regulatory Reporting Query (SAR / BSA context)

```sql
-- Retrieve full audit trail for an agent — for regulatory examination or SAR filing
SELECT
    ae.event_time,
    ae.event_type,
    a.agent_uid,
    a.display_name,
    a.risk_tier,
    p.legal_name AS principal,
    ae.action,
    ae.outcome,
    ae.tx_amount,
    ae.tx_currency,
    ae.tx_rail,
    ae.counterparty_hash,
    ae.request_ip,
    ae.chain_hash,
    -- Verify chain integrity inline
    CASE
        WHEN ae.chain_hash = encode(
            sha256(
                (LAG(ae.chain_hash) OVER (PARTITION BY ae.agent_id ORDER BY ae.event_time) || '|' ||
                ae.id::text)::bytea
            ), 'hex')
        THEN 'INTACT'
        ELSE '⚠ CHAIN_BREAK — INVESTIGATE'
    END AS chain_integrity
FROM kya_audit_events ae
JOIN kya_agents a ON a.id = ae.agent_id
JOIN kya_principals p ON p.id = ae.principal_id
WHERE a.agent_uid = 'agt_prod_a1b2c3d4'
  AND ae.event_time BETWEEN '2026-01-01' AND '2026-06-30'
ORDER BY ae.event_time ASC;
```

---

## 10. Risk Tiering Model

```
TIER 1 — Inquiry / Micro-spend
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Permitted: ACH credits only, domestic, < $500/tx, < $2,000/day
Prohibited: Wires, stablecoins, RTP, cross-border
Sensitive perms: All FALSE
HITL: Optional (FULL_AUTO allowed)
Approval: Automatic
Credential TTL: 12 months
Example: Balance-check bot, invoice inquiry agent

TIER 2 — Standard Payment Automation
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Permitted: ACH, RTP, card — domestic, < $5,000/tx, < $25,000/day
Prohibited: Wires, cross-border, stablecoin
Sensitive perms: All FALSE (can_access_statements may be TRUE)
HITL: THRESHOLD recommended (above $2,000)
Approval: Automatic
Credential TTL: 6 months
Example: Vendor payment bot (whitelisted payees), subscription manager

TIER 3 — High-Value / Wire-Capable
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Permitted: ACH, wire, RTP, limited FX — may include cross-border
Limits: Up to $50,000/tx, $250,000/day (institution discretion)
Sensitive perms: can_initiate_outbound_wire may be TRUE
HITL: THRESHOLD mandatory (above $10,000)
Approval: Manual review by compliance officer
Credential TTL: 3 months
Example: Treasury operations bot, payroll agent, FX execution agent

TIER 4 — Trade / Treasury / Sub-agent Orchestration
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Permitted: All rails including stablecoin, cross-border
Limits: Negotiated (board-level approval equivalent)
Sensitive perms: All may be TRUE with enhanced controls
HITL: ALWAYS_HITL for wires; THRESHOLD_HITL for ACH
Approval: Enhanced due diligence — compliance + legal sign-off
Credential TTL: 1 month
Example: Algo trading agent, treasury sweep orchestrator, multi-agent mesh
```

---

## 11. KYC/KYB Integration

### 11.1 Principal Binding at Registration

```python
# principal_binder.py

async def bind_principal(customer_auth_token: str, agent_registration: dict) -> Principal:
    """
    Called at the start of agent registration.
    Resolves the authenticated customer to their KYC/KYB record
    and verifies they are in VERIFIED status before allowing agent creation.
    """

    # Decode customer OAuth2 token
    customer_id = decode_token(customer_auth_token)['sub']
    customer_type = decode_token(customer_auth_token)['account_type']  # RETAIL or COMMERCIAL

    if customer_type == 'RETAIL':
        # Fetch KYC status from identity platform (Jumio/Onfido/Alloy/Persona)
        kyc_record = await identity_platform.get_kyc_record(customer_id)

        if kyc_record['status'] != 'VERIFIED':
            raise KYAError('PRINCIPAL_KYC_NOT_VERIFIED',
                f"Customer KYC status is {kyc_record['status']}. Must be VERIFIED.")

        # Retail agents inherit the customer's KYC risk rating
        # A PEP-flagged or high-risk customer cannot register Tier 3+ agents
        if kyc_record['risk_rating'] == 'HIGH' and agent_registration.get('risk_tier', 1) >= 3:
            raise KYAError('HIGH_RISK_PRINCIPAL_TIER_RESTRICTION',
                'High-risk KYC profile is not eligible for Tier 3+ agent registration.')

        return Principal(
            principal_type='RETAIL',
            kyc_record_id=kyc_record['id'],
            kyb_record_id=None,
            kyc_status='VERIFIED',
            legal_name=kyc_record['legal_name'],
            tax_id_hash=hash_pii(kyc_record['ssn']),
            country_of_domicile=kyc_record['country'],
        )

    elif customer_type == 'COMMERCIAL':
        # Fetch KYB status
        kyb_record = await kyb_platform.get_kyb_record(customer_id)

        if kyb_record['status'] != 'VERIFIED':
            raise KYAError('PRINCIPAL_KYB_NOT_VERIFIED')

        # For commercial: also verify the authorized signatory
        # The person registering the agent must be a verified authorized signer
        signatory = await kyb_platform.get_authorized_signatory(
            kyb_record['id'],
            decode_token(customer_auth_token)['user_id']
        )
        if not signatory or signatory['role'] not in ['OWNER', 'DIRECTOR', 'AUTHORIZED_SIGNER']:
            raise KYAError('SIGNATORY_NOT_AUTHORIZED',
                'Only an authorized signatory can register agents for this business.')

        return Principal(
            principal_type='COMMERCIAL',
            kyc_record_id=None,
            kyb_record_id=kyb_record['id'],
            kyc_status='VERIFIED',
            legal_name=kyb_record['business_name'],
            tax_id_hash=hash_pii(kyb_record['ein']),
            country_of_domicile=kyb_record['country_of_incorporation'],
        )
```

### 11.2 Ongoing KYC/KYB Sync

```sql
-- Trigger: when a principal's KYC/KYB status changes, auto-suspend their agents
-- Implemented as a webhook from the identity platform into this function:

CREATE OR REPLACE FUNCTION handle_principal_status_change(
    p_kyc_record_id TEXT,
    p_new_status TEXT
)
RETURNS VOID AS $$
BEGIN
    -- If KYC is suspended or failed, suspend all active agents for this principal
    IF p_new_status IN ('SUSPENDED', 'FAILED', 'EXPIRED') THEN
        UPDATE kya_agents
        SET status = 'SUSPENDED',
            updated_at = NOW(),
            review_notes = CONCAT('Auto-suspended: principal KYC status changed to ', p_new_status)
        WHERE principal_id = (
            SELECT id FROM kya_principals WHERE kyc_record_id = p_kyc_record_id
        )
        AND status = 'ACTIVE';

        -- Emit revocation events for all active credentials
        INSERT INTO kya_audit_events (event_type, agent_id, outcome, metadata)
        SELECT
            'AGENT_AUTO_SUSPENDED',
            a.id,
            'DENIED',
            jsonb_build_object('trigger', 'PRINCIPAL_KYC_STATUS_CHANGE', 'new_status', p_new_status)
        FROM kya_agents a
        JOIN kya_principals p ON p.id = a.principal_id
        WHERE p.kyc_record_id = p_kyc_record_id;
    END IF;
END;
$$ LANGUAGE plpgsql;
```

---

## 12. Security Threat Model

### 12.1 Threat Matrix

| Threat | Attack Vector | Mitigation |
|---|---|---|
| **Credential theft** | Agent JWT stolen from customer env | Short TTL + JTI revocation + request signature (stolen JWT alone is insufficient — attacker also needs agent's private key) |
| **Mandate escalation** | Attacker modifies JWT payload claims | EdDSA signature — JWT is tamper-evident; any modification invalidates signature |
| **Prompt injection** | Malicious content tricks agent into initiating unauthorized payment | Mandate engine enforces hard limits regardless of what the LLM decided; execution API is deterministic |
| **Replay attack** | Attacker replays a valid signed request | Signature-Input includes timestamp; gateway rejects requests where `created` > 5 minutes ago |
| **Private key exfiltration** | Agent's signing key stolen from customer env | Request signatures use agent's key (compromise of key means compromised agent — revoke immediately); bank's credential signing key is HSM-backed |
| **Rogue agent registration** | Bad actor registers agent under stolen customer credentials | Requires valid OAuth2 session + liability attestation + KYC VERIFIED status + (for commercial) authorized signatory check |
| **Spend laundering** | Agent makes many small transactions to stay under limits | Cumulative limit + transaction velocity monitoring in audit layer |
| **Sub-agent chain abuse** | Legitimate Tier-2 agent spawns unauthorized sub-agents | Sub-agent delegation requires `can_delegate_to_sub_agents=true` (default false) + sub-agents inherit parent tier ceiling |
| **HITL bypass** | Agent routes around HITL gateway | HITL check is in the gateway, not in the agent — agent cannot bypass it; execution API will not process without gateway KYA context |
| **Revocation lag** | Revoked agent continues transacting during propagation window | Redis revocation is synchronous with the gateway check — zero lag for the issuing institution; TAP directory updated within 60 seconds |
| **Principal spoofing** | Agent claims to act for a different principal | `principal_id` is embedded in bank-signed JWT — cannot be forged without bank's HSM private key |
| **KYC status drift** | Principal's KYC lapses after agent activation | Nightly KYC sync + webhook-triggered auto-suspend (see §11.2) |

### 12.2 Defence-in-Depth Summary

```
Layer 0: Principal verification (KYC/KYB must be VERIFIED before any agent is registered)
Layer 1: Registration controls (risk tiering, manual review for Tier 3/4)
Layer 2: Credential integrity (bank-signed JWT, Ed25519 — forgery requires HSM key)
Layer 3: Request authentication (agent's private key signs each call)
Layer 4: Revocation (Redis fast-path — millisecond propagation)
Layer 5: Mandate enforcement (hard limits in gateway — LLM cannot override)
Layer 6: Spend tracking (Redis atomic — no race condition exploits)
Layer 7: HITL gate (structural, not advisory — payment won't process without approval)
Layer 8: Audit chain (tamper-evident — deletions and modifications are detectable)
Layer 9: KYC sync (principal status changes cascade to agents automatically)
```

---

## Appendix A: Environment Variables Reference

```bash
# Credential Service
KYA_BANK_SIGNING_KEY_ARN=arn:aws:kms:us-east-1:123456789:key/...
KYA_JWT_ISSUER=https://api.bank.com/kya
KYA_JWT_DEFAULT_TTL_SECONDS=15552000      # 6 months
KYA_JWKS_CACHE_TTL_SECONDS=300           # 5 minutes

# Revocation
KYA_REVOCATION_REDIS_URL=redis://...
KYA_REVOCATION_CACHE_TTL_SECONDS=34560000 # 400 days

# Spend Tracking
KYA_SPEND_REDIS_URL=redis://...

# Database
KYA_POSTGRES_URL=postgresql://...

# Audit
KYA_KAFKA_BROKERS=kafka://...
KYA_AUDIT_TOPIC=kya.audit
KYA_REVOCATION_TOPIC=kya.revocations
KYA_S3_AUDIT_BUCKET=bank-kya-audit-archive

# Gateway
KYA_REQUEST_SIGNATURE_MAX_AGE_SECONDS=300  # 5-minute replay window
KYA_HITL_WEBHOOK_URL=https://internal.bank.com/hitl/approvals
```

## Appendix B: DID Readiness (Future-Proofing)

The registration data model above maps cleanly to a W3C DID Document.
When cross-platform portability is required, the following export is available:

```json
{
  "@context": ["https://www.w3.org/ns/did/v1"],
  "id": "did:web:api.bank.com:kya:agents:agt_prod_a1b2c3d4",
  "controller": "did:web:api.bank.com",
  "verificationMethod": [{
    "id": "did:web:api.bank.com:kya:agents:agt_prod_a1b2c3d4#key-1",
    "type": "JsonWebKey2020",
    "controller": "did:web:api.bank.com:kya:agents:agt_prod_a1b2c3d4",
    "publicKeyJwk": {
      "kty": "OKP", "crv": "Ed25519",
      "x": "11qYAYKxCrfVS_7TyWQHOg7hcvPapiMlrwIaaPcHURo"
    }
  }],
  "service": [{
    "id": "did:web:api.bank.com:kya:agents:agt_prod_a1b2c3d4#kya-registry",
    "type": "KYARegistry",
    "serviceEndpoint": "https://api.bank.com/kya/v1/agents/agt_prod_a1b2c3d4"
  }],
  "kyaExtension": {
    "principal_did": "did:web:api.bank.com:principals:550e8400",
    "risk_tier": 2,
    "mandate_hash": "sha256:mandate_content_hash",
    "erc8004_token_id": "0x1234..."   // if on-chain registry also used
  }
}
```

**Recommendation:** Issue `did:web` DIDs by default (no blockchain dependency,
resolves over HTTPS from your own domain). Reserve `did:ethr` / ERC-8004
for agents that transact on stablecoin rails or need cross-institution portability.
