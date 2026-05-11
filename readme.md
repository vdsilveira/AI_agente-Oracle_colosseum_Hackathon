# Oracle Agent - SolCuts Colosseum

## Overview

The Oracle Agent is an off-chain Python service that validates YouTube video clip submissions and updates metrics on the Solana blockchain. It acts as an automated judge that verifies if submitted clips are authentic and belong to the editors' channels.

## Responsibilities

### 1. Submission Validation
- **Channel Check**: Verifies if the video is on the editor's registered channel
- **Transcript Check**: >=70% similarity with the original video
- **Frame Check**: 3/5 frames with SSIM >=0.70

### 2. Metrics Update
- Fetches metrics (views, likes, comments) via external Metrics API
- Calculates weighted score based on pool scoring rules
- Executes CPI `update_metrics` on the blockchain

### 3. Fraud Detection
- Executes `slash_user()` for detected fraud
- Bans fraudulent users and slashes 50% of stake to treasury

### 4. Pool Closure
- Executes `close_and_payout()` when pools expire
- Enables participants to claim their prizes

## Thresholds

| Parameter | Value |
|-----------|-------|
| Transcript | >=70% |
| Frames | 3/5 (SSIM >=0.70) |
| Poll Interval | 3 hours (10800s) |

## Docker

### Build
```bash
docker build -t oracle-agent .
```

### Run
```bash
docker run -d --name oracle-agent oracle-agent sleep infinity
docker exec oracle-agent bash -c 'cat > .env << EOF
APP_API_KEY=your_api_key_here
ORACLE_PUBLIC_KEY=your_oracle_public_key
ORACLE_PRIVATE_KEY=your_oracle_private_key
SOLANA_RPC_URL=https://api.devnet.solana.com
METRICS_API_URL=https://backend-views-solana.onrender.com
POLL_INTERVAL_SECONDS=10800
PROGRAM_ID=J45dp2TMQXx5v5RDygsF3im7URJqu7QQ996V1kqXeNxN
CORE_API_URL=http://core-api:8001/api/v1
EOF'
docker exec -d oracle-agent python -m src.main
docker logs -f oracle-agent
```

## Environment Variables

| Variable | Description |
|----------|-------------|
| `APP_API_KEY` | Shared key for Metrics API authentication |
| `ORACLE_PUBLIC_KEY` | Oracle public key |
| `ORACLE_PRIVATE_KEY` | Oracle private key |
| `SOLANA_RPC_URL` | Solana RPC (devnet/mainnet) |
| `METRICS_API_URL` | Metrics API URL (views, likes, comments) |
| `POLL_INTERVAL_SECONDS` | Polling interval (default: 10800) |
| `PROGRAM_ID` | Solana program ID |
| `CORE_API_URL` | Core API URL for syncing pool/entry data |

## Oracle Keys

To generate new oracle keys:
```bash
python scripts/generate_oracle_keypair.py
```

**IMPORTANT**: Never commit private keys to version control!

## Database Population Scripts

### Backfill existing pools from chain
```bash
python -m scripts.backfill_db
```
Reads all pools and entries from the Solana blockchain and syncs them to the Core API database.

### Enrich video titles
```bash
python -m scripts.enrich_titles
```
Fetches YouTube video titles via oEmbed for pools missing titles.

## Project Structure

```
AI_agente-Oracle_colosseum_Hackathon/
├── src/
│   ├── main.py                 # Entry point (polling loop)
│   ├── config.py               # Configuration
│   ├── services/
│   │   ├── transcript_service.py   # YouTube transcript comparison
│   │   ├── channel_service.py      # Channel verification
│   │   ├── similarity_service.py   # SSIM frame comparison
│   │   └── metrics_api_client.py   # Metrics API client
│   ├── oracle/
│   │   ├── types.py            # Data models & enums
│   │   └── validator.py        # Validation pipeline
│   ├── solana/
│   │   ├── connection.py       # Solana connection + CPI
│   │   └── mcp_client.py       # RPC client (account parsing)
│   └── db/
│       └── database.py         # SQLite storage
├── scripts/
│   ├── backfill_db.py          # Chain → Core API sync
│   ├── enrich_titles.py        # YouTube title enrichment
│   └── generate_oracle_keypair.py
├── tests/
├── docs/
│   ├── ORACLE_CHANGES.md       # Refactoring history
│   └── API_TEST_RESULTS.md     # Metrics API test results
├── Dockerfile
├── requirements.txt
├── AGENT_RULES.md              # Full agent documentation
└── PLAN.md                     # Development plan & roadmap
```

## Commands

```bash
# Install dependencies
pip install -r requirements.txt

# Run locally
python -m src.main

# Run single iteration (testing)
python -m src.main --once

# Run tests
pytest tests/

# Backfill database from chain
python -m scripts.backfill_db

# Enrich video titles
python -m scripts.enrich_titles
```
