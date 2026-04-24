# AGENTS.md - AI Oracle Agent

## Overview

Off-chain oracle that validates video submissions and updates scores on Solana Devnet.

## ⚠️ Read First

Before implementing anything, read the planning document:

```bash
cat AI_agente-Oracle_colosseum_Hackathon/PLAN.md
```

Contains: full oracle workflow, thresholds, slash decision flow, tech stack.

## Oracle Full Workflow

```
USER SUBMITS VIDEO B → ORACLE AUTOMATICALLY:
         │
         ▼
    CHANNEL CHECK
         │
    ┌────┼────┐
   YES   │   NO
    │    │    │
    ▼    ▼    ▼
  NEXT  WRONG FOREIGN
        │    │
        │    ▼
        │  SLASH + BAN
        │  (CPI)
        ▼
   TRANSCRIPT CHECK (≥70%)
         │
    ┌────┼────┐
   PASS  │   FAIL
    │    │    │
    ▼    ▼    ▼
  NEXT  LOG  LOG
        REASON REASON
        ▼
   FRAME CHECK (3/5 SSIM)
         │
    ┌────┼────┐
   PASS  │   FAIL
    │    │    │
    ▼    ▼    ▼
  VALID LOG  LOG
        │    │
        ▼    ▼
   ONGOING METRICS UPDATE LOOP
```

## Validation Results

| Result | Action |
|--------|--------|
| **VALID** | Update metrics via API (loop every 5 min) |
| **WRONG CHANNEL** | Ignore entry, log reason, frontend alert |
| **FRAUD** | Execute `slash_user()` CPI, ban user |

## Project Structure

```
AI_agente-Oracle_colosseum_Hackathon/
├── src/
│   ├── main.py                 # Entry point
│   ├── config.py              # Configuration
│   ├── services/
│   │   ├── transcript_service.py   # youtube-transcript-api
│   │   ├── channel_service.py     # pytube verification
│   │   ├── similarity_service.py   # SSIM comparison
│   │   └── metrics_api_client.py   # Metrics API calls
│   ├── oracle/
│   │   ├── types.py           # Data models
│   │   └── validator.py       # Validation pipeline
│   ├── solana/
│   │   └── connection.py     # Solana connection + CPI
│   └── db/
│       └── database.py        # SQLite storage
├── scripts/
│   └── generate_oracle_keypair.py
├── keys/                     # Oracle keypair (gitignored)
│   └── oracle.json
└── requirements.txt
```

## Commands

```bash
# Install dependencies
pip install -r requirements.txt

# Generate oracle keypair
python scripts/generate_oracle_keypair.py

# Run agent
python -m src.main

# Run tests
pytest tests/
```

## Environment Variables

Required in `.env`:
- `JWT_TOKEN` - Metrics API authentication
- `SOLANA_RPC_URL` - Solana RPC (Devnet)
- `ORACLE_KEYPAIR_PATH` - Path to oracle keypair

## Thresholds

| Parameter | Value |
|-----------|-------|
| Transcript | ≥70% match |
| Frames | 3/5 must pass (SSIM ≥0.70) |
| Poll interval | 300 seconds |

## Solana Instructions (via CPI)

| Instruction | When |
|-------------|------|
| `update_metrics` | Every poll for VALID entries |
| `slash_user` | Fraud detected (oracle signer) |