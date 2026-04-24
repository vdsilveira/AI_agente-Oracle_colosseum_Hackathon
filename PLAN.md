# 📋 Plano de Desenvolvimento: AI Oracle Agent para Colosseum Hackathon

## 1. Visão Geral do Sistema

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           SOLANA BLOCKCHAIN                                 │
│  ┌─────────────┐  ┌──────────────────┐  ┌─────────────────────────────┐      │
│  │ VideoPool   │  │ ParticipantEntry │  │ UserProfile / StakeAccount │      │
│  │ (original)  │  │ (submitted B)   │  │ (creator channels)         │      │
│  └─────────────┘  └──────────────────┘  └─────────────────────────────┘      │
└─────────────────────────────────────────────────────────────────────────────┘
                                   ▲
                                   │ update_metrics / slash_user (oracle signer)
                                   │
┌─────────────────────────────────────────────────────────────────────────────┐
│                        AI ORACLE AGENT (Off-chain)                          │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                      Validation Pipeline                             │   │
│  │                                                                      │   │
│  │  1. CHANNEL CHECK ─► Video B posted on creator's channel?            │   │
│  │  2. TRANSCRIPT CHECK ─► ≥70% similarity with Video A               │   │
│  │  3. FRAME CHECK ─► 3/5 frames SSIM ≥0.70                          │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                            │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                      Metrics Pipeline (Loop)                         │   │
│  │                                                                      │   │
│  │  1. Fetch active pools from Solana                                   │   │
│  │  2. Batch call metrics API (user_handle = wallet address)            │   │
│  │  3. Update scores via CPI                                           │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Fluxo Completo do Oracle

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         ORACLE FULL WORKFLOW                                │
└─────────────────────────────────────────────────────────────────────────────┘

USER SUBMITS VIDEO B ──► join_pool (on-chain)
         │
         ▼
┌────────────────────────┐
│ ORACLE DETECTS NEW ENTRY │
└────────────────────────┘
         │
         ▼
┌────────────────────────────────────────────────────────┐
│              INITIAL VALIDATION (Automatic)                │
│                                                        │
│  ┌─────────────────┐    ┌─────────────────────────┐     │
│  │ 1. CHANNEL CHECK │    │ Video B channel belongs  │     │
│  │                 │───►│ to creator's channels? │     │
│  └─────────────────┘    └─────────────────────────┘     │
│              │                      │                    │
│         ┌────┼────┐                 │                    │
│        YES   │   NO                 │                    │
│         │    │    │                 │                    │
│         ▼    ▼    ▼                 │                    │
│   ┌──────────┐  WRONG CHANNEL      │                    │
│   │CONTINUE  │    (skip)           │                    │
│   │VALIDATION│    + log reason     │                    │
│   └──────────┘    + frontend alert│                    │
│         │                       │                    │
│         ▼                       │                    │
│ ┌──────────────────┐          │                    │
│ │2.TRANSCRIPT CHECK │          │                    │
│ │   ≥70% match     │          │                    │
│ └──────────────────┘          │                    │
│         │                       │                    │
│    ┌────┼────┐                 │                    │
│   PASS  │   FAIL               │                    │
│    │     │    │                 │                    │
│    ▼     ▼    ▼                 │                    │
│ ┌──────────┐  WRONG             │                    │
│ │CONTINUE  │  TRANSCRIPT         │                    │
│ │VALIDATION │  + log reason      │                    │
│ └──────────┘                    │                    │
│         │                       │                    │
│         ▼                       │                    │
│ ┌──────────────────┐          │                    │
│ │ 3. FRAME CHECK    │          │                    │
│ │    3/5 SSIM ≥0.70│          │                    │
│ └──────────────────┘          │                    │
│         │                       │                    │
│    ┌────┼────┐                  │                    │
│   PASS  │   FAIL                │                    │
│    │     │    │                 │                    │
│    ▼     ▼    ▼                 │                    │
│ ┌──────────┐ FRAME              │                    │
│ │ VALID    │ MISMATCH           │                    │
│ └──────────┘ + log reason       │                    │
└────────────────────────────────────────────────────────┘
         │
   ┌─────┴─────┐
   │           │
   ▼           ▼
┌────────┐  ┌────────────┐
│ VALID  │  │ WRONG/     │
│        │  │ FRAUD      │
└────────┘  └────────────┘
   │           │
   ▼           ▼
┌────────────────┐  ┌─────────────────────────────┐
│ ONGOING LOOP    │  │ FRAUD DETECTED              │
│ (metrics only) │  │                             │
│                │  │ • Log reason (off-chain DB) │
│ • Poll pools   │  │ • Execute slash_user() CPI  │
│ • Batch API   │  │ • Ban user on Solana       │
│ • Update      │  │ • Flag for frontend        │
│   metrics     │  │                             │
└────────────────┘  └─────────────────────────────┘
```

---

## 3. Decisões de Validação

| Resultado | Condição | Ação |
|-----------|----------|------|
| **VALID** | Channel ✓ + Transcript ≥70% + Frames 3/5 | Contar pontos |
| **WRONG CHANNEL** | Video B em canal diferente do criador | Ignorar entry, avisar frontend |
| **FRAUD (GOLPE)** | Video B pertencer a OUTRO criador | `slash_user()` + ban |

### Detalhes do WRONG CHANNEL
- Vídeo está em um canal que o criador **tem na lista**, mas **não é esse vídeo específico**
- Entry é marcada como inválida
- Motivo salvo no banco off-chain
- Frontend exibe alerta para o usuário

### Detalhes do FRAUD
- Vídeo B pertence a **OUTRO criador** (não está na lista)
- Oracle executa `slash_user()` via CPI
- 50% do stake é transferido para treasury
- `is_banned = true` no UserProfile
- Flag para banir também os canais

---

## 4. Estado Atual do Projeto

### ✅ Implementado

```
AI_agente-Oracle_colosseum_Hackathon/
├── .opencode/skills/
│   ├── transcript-validator/     ✅ SKILL.md pronto
│   ├── frame-validator/         ✅ SKILL.md pronto
│   └── channel-validator/      ✅ SKILL.md pronto
├── .env                         ✅ JWT_TOKEN configurado
├── .gitignore                   ✅ Protege .env
├── AGENTS.md                    ✅ Instruções básicas
├── PLAN.md                     ✅ Este arquivo
├── api.md                      ✅ Docs API métricas
└── readme.md                   ⚠️ Template vazio
```

### ❌ Falta Implementar

| Componente | Arquivo | Prioridade |
|-----------|---------|-----------|
| **Setup** | | |
| Dependências Python | `requirements.txt` | 🔴 Crítica |
| Configuração | `src/config.py` | 🔴 Crítica |
| **Services** | | |
| Transcript Fetch | `src/services/transcript_service.py` | 🔴 Crítica |
| Frame Extraction | `src/services/frame_extractor.py` | 🔴 Crítica |
| SSIM Comparison | `src/services/similarity_service.py` | 🔴 Crítica |
| Channel Verification | `src/services/channel_service.py` | 🔴 Crítica |
| Metrics API Client | `src/services/metrics_api_client.py` | 🔴 Crítica |
| **Solana** | | |
| Connection | `src/solana/connection.py` | 🔴 Crítica |
| Oracle Signer | `src/solana/oracle_signer.py` | 🔴 Crítica |
| CPI Instructions | `src/solana/instructions.py` | 🔴 Crítica |
| **Oracle Core** | | |
| Types/Models | `src/oracle/types.py` | 🔴 Crítica |
| Validator | `src/oracle/validator.py` | 🔴 Crítica |
| Metrics Updater | `src/oracle/metrics_updater.py` | 🔴 Crítica |
| **Database** | | |
| SQLite Models | `src/db/models.py` | 🟡 Alta |
| Database Operations | `src/db/database.py` | 🟡 Alta |
| **Entry Point** | | |
| Main CLI/API | `src/main.py` | 🔴 Crítica |
| Scheduler | `src/oracle/scheduler.py` | 🔴 Crítica |
| **Scripts** | | |
| Generate Keypair | `scripts/generate_oracle_keypair.py` | 🔴 Crítica |
| **Tests** | | |
| Unit Tests | `tests/` | 🟡 Alta |

---

## 5. Estrutura de Diretórios

```
AI_agente-Oracle_colosseum_Hackathon/
├── src/
│   ├── __init__.py
│   ├── main.py                      # Entry point (CLI/API)
│   ├── config.py                    # Environment variables
│   │
│   ├── services/
│   │   ├── __init__.py
│   │   ├── transcript_service.py    # youtube-transcript-api
│   │   ├── frame_extractor.py       # FFmpeg + opencv
│   │   ├── similarity_service.py   # SSIM comparison
│   │   ├── channel_service.py      # pytube channel verification
│   │   └── metrics_api_client.py   # Batch metrics API calls
│   │
│   ├── solana/
│   │   ├── __init__.py
│   │   ├── connection.py           # Solana RPC connection
│   │   ├── oracle_signer.py        # Oracle wallet (keypair)
│   │   └── instructions.py        # CPI: update_metrics, slash_user
│   │
│   ├── oracle/
│   │   ├── __init__.py
│   │   ├── types.py               # Pydantic models
│   │   ├── validator.py          # Initial validation pipeline
│   │   ├── metrics_updater.py    # Ongoing metrics updates
│   │   └── scheduler.py          # Polling loop
│   │
│   └── db/
│       ├── __init__.py
│       ├── models.py              # SQLAlchemy models
│       └── database.py           # DB operations
│
├── scripts/
│   └── generate_oracle_keypair.py  # Generate oracle keypair
│
├── tests/                        # Unit tests
│
├── requirements.txt
├── pyproject.toml
└── README.md
```

---

## 6. APIs e Serviços Externos

| Serviço | Fonte | Auth | Retorna |
|---------|-------|------|---------|
| Métricas | `backend-views-solana.onrender.com` | JWT_TOKEN | views, likes, comments, channel_name |
| Transcrição | `youtube-transcript-api` | Nenhuma | Transcript com timestamps |
| Frames | `yt-dlp` + `ffmpeg` | Nenhuma | Frames em timestamps |
| SSIM | `scikit-image` | Nenhuma | Score de similaridade |
| Channel | `pytube` | Nenhuma | channel_id, channel_name |

---

## 7. Thresholds de Validação

| Parâmetro | Valor | Descrição |
|-----------|-------|----------|
| `TRANSCRIPT_MIN_SCORE` | 0.70 | 70% mínimo de similaridade |
| `FRAME_SIMILARITY_THRESHOLD` | 0.70 | SSIM mínimo por frame |
| `FRAME_MIN_MATCHES` | 3 | Frames que precisam passar (de 5) |
| `POLL_INTERVAL_SECONDS` | 300 | Intervalo de polling (5 min) |

---

## 8. Integração Solana (Devnet)

### Accounts Lidos pelo Oracle
- `GlobalConfig` - Verificar oracle address
- `VideoPool` - Buscar pools com status = Open
- `ParticipantEntry` - Lista de participantes por pool

### Instruções Executadas pelo Oracle
- `update_metrics` - Atualizar views/likes/comments/score
- `slash_user` - Banir fraudulentos (50% slashed)

### Setup do Oracle
1. Gerar keypair: `scripts/generate_oracle_keypair.py`
2. Salvar path em `.env`: `ORACLE_KEYPAIR_PATH=./keys/oracle.json`
3. Atualizar `GlobalConfig.oracle` via programa

---

## 9. Cronograma de Implementação

| Fase | Task | Estimativa |
|------|------|------------|
| **1** | Setup: requirements.txt, config.py, estrutura | 1 dia |
| **2** | TranscriptService: fetch + compare | 2 dias |
| **3** | FrameExtractor + SimilarityService | 2 dias |
| **4** | ChannelService: pytube verification | 1 dia |
| **5** | MetricsApiClient: batch calls | 1 dia |
| **6** | OracleValidator: pipeline completo | 2 dias |
| **7** | Solana Integration: connection, signer, CPI | 2 dias |
| **8** | OracleMetricsUpdater: loop de updates | 1 dia |
| **9** | Database: SQLite storage | 1 dia |
| **10** | Scheduler: polling loop | 1 dia |
| **11** | Main + CLI | 1 dia |
| **12** | Tests + ajustes | 2 dias |
| **TOTAL** | | **17 dias** |

---

## 10. Configuração (.env)

```env
# JWT Token para API de métricas
JWT_TOKEN=f0a84c40027bfa649d3a41c261c227bf24221a2161be704305a9156c56554fb3

# Solana Devnet
SOLANA_RPC_URL=https://api.devnet.solana.com

# Oracle Keypair
ORACLE_KEYPAIR_PATH=./keys/oracle.json

# Thresholds
TRANSCRIPT_MIN_SCORE=0.70
FRAME_SIMILARITY_THRESHOLD=0.70
FRAME_MIN_MATCHES=3
FRAME_TOTAL_SAMPLES=5

# Polling
POLL_INTERVAL_SECONDS=300

# Database
DATABASE_URL=sqlite:///oracle.db
```

---

## 11. Fluxo Detalhado de Validação

```python
async def validate_submission(
    video_a_id: str,           # Original video do pool
    video_b_url: str,          # Clip submetido
    creator_channels: list[str]  # Canais do criador
) -> ValidationResult:
    """
    Returns:
    - ValidationStatus.VALID
    - ValidationStatus.WRONG_CHANNEL
    - ValidationStatus.INVALID_TRANSCRIPT
    - ValidationStatus.INVALID_FRAMES
    - ValidationStatus.FRAUD
    """
    # 1. Get Video B channel
    channel_b = get_video_channel(video_b_url)

    # 2. Check channel ownership
    if channel_b not in creator_channels:
        # Check if belongs to another creator
        is_known_channel = check_if_known_creator(channel_b)
        if is_known_channel:
            return ValidationResult.WRONG_CHANNEL
        else:
            return ValidationResult.FRAUD  # Oracle will slash

    # 3. Transcript check
    transcript_a = fetch_transcript(video_a_id)
    transcript_b = fetch_transcript(extract_video_id(video_b_url))
    transcript_score = compare_transcripts(transcript_a, transcript_b)

    if transcript_score < TRANSCRIPT_MIN_SCORE:
        return ValidationResult.INVALID_TRANSCRIPT

    # 4. Frame check
    timestamps = find_matching_timestamps(transcript_a, transcript_b)
    frame_score = compare_frames(video_a_id, video_b_url, timestamps)

    if frame_score < FRAME_MIN_MATCHES:
        return ValidationResult.INVALID_FRAMES

    return ValidationResult.VALID
```

---

## 12. Fluxo de Métricas (Loop)

```python
async def update_all_metrics():
    """Called every POLL_INTERVAL_SECONDS"""

    # 1. Fetch active pools
    active_pools = get_active_pools()

    for pool in active_pools:
        # 2. Get participants
        participants = get_participants(pool)

        # 3. Filter VALID entries only
        valid_entries = [p for p in participants if p.validation_status == VALID]

        if not valid_entries:
            continue

        # 4. Build batch request
        tasks = [
            {"url": entry.clip_link, "platform": "youtube", "user_handle": entry.user}
            for entry in valid_entries
        ]

        # 5. Call metrics API
        metrics = await call_metrics_api(tasks)

        # 6. Update each on Solana
        for entry, metric in zip(valid_entries, metrics):
            calculate_score(metric)
            await update_metrics_on_solana(entry, metric)
```

---

## 13. Regras Anti-Fraude

### Validação de Transcrição (≥70%)
- Comparar transcrição normalizada (lowercase, sem pontuação)
- Usar similaridade de texto (TF-IDF ou similar)
- Tolerância para erros de transcrição automática do YouTube

### Validação de Frames (3/5)
- Extrair frames em pontos onde transcrições coincidem
- Comparar usando SSIM (Structural Similarity Index)
- Threshold: 0.7 por frame
- Mínimo: 3 de 5 frames similares

### Verificação de Canal
1. Verificar se vídeo B foi publicado no canal declarado (`channel_id`)
2. Se NÃO: verificar se pertence a outro canal do criador
   - Se SIM: rejeitar por "Wrong Channel", não contar pontos
   - Se NÃO: flag para SLASH + ban

### Slash & Ban
- Oracle executa `slash_user()` automaticamente
- 50% do stake transferido para treasury
- `is_banned = true` no UserProfile
- Canais do usuário banidos