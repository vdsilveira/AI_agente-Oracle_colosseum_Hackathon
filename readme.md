# Oracle Agent - SolCuts Colosseum

## Overview

The Oracle Agent is an off-chain service that validates YouTube video clip submissions and updates metrics on the Solana blockchain. It acts as an automated judge that verifies if submitted clips are authentic and belong to the editors' channels.

## Responsibilities

### 1. Submission Validation
- **Channel Check**: Verifies if the video is on the editor's registered channel
- **Transcript Check**: ≥70% similarity with the original video
- **Frame Check**: 3/5 frames with SSIM ≥0.70

### 2. Metrics Update
- Fetches metrics (views, likes, comments) via external API
- Calculates weighted score
- Executes CPI `update_metrics` on the blockchain

### 3. Fraud Detection
- Executes `slash_user()` for detected fraud
- Bans fraudulent users

### 4. Pool Closure
- Executes `close_and_payout()` when pools expire
- Enables participants to claim their prizes

## Thresholds

| Parameter | Value |
|-----------|-------|
| Transcript | ≥70% |
| Frames | 3/5 (SSIM ≥0.70) |
| Poll Interval | 3 hours (10800s) |

## Docker

### Build
```bash
docker build -t oracle-agent .
```

### Run
```bash
# Create container
docker run -d --name oracle-agent oracle-agent sleep infinity

# Configure .env
docker exec oracle-agent bash -c 'cat > .env << EOF
JWT_TOKEN=your_jwt_token_here
ORACLE_PUBLIC_KEY=your_oracle_public_key
ORACLE_PRIVATE_KEY=your_oracle_private_key
SOLANA_RPC_URL=https://api.devnet.solana.com
METRICS_API_URL=https://backend-views-solana.onrender.com
POLL_INTERVAL_SECONDS=10800
PROGRAM_ID=4RAbxbEVCsYaaK3WR8r7eYwrofTJ7yqdZ3hqSYRLPfT4
EOF'

# Start agent
docker exec -d oracle-agent python -m src.main

# View logs
docker logs -f oracle-agent
```

## Environment Variables

| Variable | Description |
|----------|-------------|
| JWT_TOKEN | Token for metrics API |
| ORACLE_PUBLIC_KEY | Oracle public key (generate with scripts/generate_oracle_keypair.py) |
| ORACLE_PRIVATE_KEY | Oracle private key (generate with scripts/generate_oracle_keypair.py) |
| SOLANA_RPC_URL | Solana RPC (devnet/mainnet) |
| METRICS_API_URL | Metrics API URL |
| POLL_INTERVAL_SECONDS | Polling interval (default: 10800) |
| PROGRAM_ID | Solana program ID |

## Oracle Keys

To generate new oracle keys:
```bash
python scripts/generate_oracle_keypair.py
```

The generated keys must be:
1. Added to `.env` in the container
2. Registered in the Solana program via `update_config` instruction

**IMPORTANT**: Never commit private keys to version control!

## Technical Details

See [AGENT_RULES.md](./AGENT_RULES.md) for complete documentation.

## Project Structure

```
AI_agente-Oracle_colosseum_Hackathon/
├── src/
│   ├── main.py                 # Entry point
│   ├── config.py              # Configuration
│   ├── services/
│   │   ├── transcript_service.py   # YouTube transcript
│   │   ├── channel_service.py     # Channel verification
│   │   ├── similarity_service.py   # SSIM comparison
│   │   └── metrics_api_client.py   # Metrics API
│   ├── oracle/
│   │   ├── types.py           # Data models
│   │   └── validator.py       # Validation pipeline
│   ├── solana/
│   │   ├── connection.py     # Solana connection + CPI
│   │   └── mcp_client.py     # RPC client
│   └── db/
│       └── database.py        # SQLite storage
├── scripts/
│   └── generate_oracle_keypair.py
├── Dockerfile
├── requirements.txt
├── .env.example
├── AGENT_RULES.md
└── PLAN.md
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
```