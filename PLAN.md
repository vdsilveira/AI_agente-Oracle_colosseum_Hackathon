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
JWT_TOKEN=your_jwt_token_here

# Solana Devnet
SOLANA_RPC_URL=https://api.devnet.solana.com

# Oracle Keys
ORACLE_PUBLIC_KEY=your_oracle_public_key_here
ORACLE_PRIVATE_KEY=your_oracle_private_key_here

# Thresholds
TRANSCRIPT_MIN_SCORE=0.70
FRAME_SIMILARITY_THRESHOLD=0.70
FRAME_MIN_MATCHES=3
FRAME_TOTAL_SAMPLES=5

# Polling (3 horas)
POLL_INTERVAL_SECONDS=10800

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

---

## 14. CPI Real Implementation

### 14.1 Arquivo: src/solana/connection.py

O arquivo precisa implementar as seguintes funções usando anchorpy:

```python
class OracleCPI:
    async def update_metrics(
        self,
        entry_pda: str,
        pool_pda: str,
        views: int,
        likes: int,
        comments: int,
        link_hash: list[int],  # 32 bytes
    ) -> str:
        """
        Chama instruction update_metrics(program, entry, pool, config, oracleSigner)
        
        Accounts necessários:
        - entry: ParticipantEntry (mut)
        - pool: VideoPool (mut)
        - config: GlobalConfig
        - oracle: Signer (oracle keypair)
        
        Args (instruction data):
        - views: u64
        - likes: u64
        - comments: u64
        - link_hash: [u8; 32]
        """

    async def slash_user(
        self,
        user_authority: str,  # usuário a ser banido
    ) -> str:
        """
        Chama instruction slash_user(program, config, userProfile, stakeAccount, treasury, caller)
        
        Accounts necessários:
        - config: GlobalConfig
        - user_profile: UserProfile (mut)
        - stake_account: StakeAccount (mut)
        - treasury: UncheckedAccount (mut)
        - caller: Signer (oracle)
        
        O programa calcula os PDAs automaticamente:
        - user_profile = find_program_address([user_profile, authority], program_id)
        - stake_account = find_program_address([stake, authority], program_id)
        """

    async def close_and_payout(
        self,
        pool_pda: str,
        original_video_id: str,
        creator: str,
    ) -> str:
        """
        Chama instruction close_and_payout(program, pool, prizeVault, creator, oracle, config, treasury)
        
        Accounts necessários:
        - pool: VideoPool (mut)
        - prize_vault: PrizeVault (mut)
        - creator: UncheckedAccount (mut)
        - caller: Signer (oracle)
        - config: GlobalConfig
        - treasury: UncheckedAccount (mut)
        """
```

### 14.2 PDAs a Calcular

**Baseado em llms-full.txt** - O bump seed canonical é incluído automaticamente:

```python
from solders.pubkey import Pubkey

def find_pda(seeds: list[bytes], program_id: Pubkey) -> tuple[str, int]:
    """
    Derive PDA com bump seed (canonical).
    
    Based on llms-full.txt: PublicKey.findProgramAddressSync()
    """
    pda, bump = Pubkey.find_program_address(seeds, program_id)
    return str(pda), bump


# Exemplo de uso
PROGRAM_ID = Pubkey.from_string("J45dp2TMQXx5v5RDygsF3im7URJqu7QQ996V1kqXeNxN")

# GlobalConfig: [b"global_config_v1"]
global_config, global_bump = find_pda([b"global_config_v1"], PROGRAM_ID)

# UserProfile: [b"user_profile", authority]
user_profile, user_bump = find_pda([b"user_profile", authority_bytes], PROGRAM_ID)

# StakeAccount: [b"stake", authority]
stake_account, stake_bump = find_pda([b"stake", authority_bytes], PROGRAM_ID)

# VideoPool: [b"pool", video_id_bytes]
pool, pool_bump = find_pda([b"pool", video_id_bytes], PROGRAM_ID)

# ParticipantEntry: [b"entry", pool_key, link_hash]
entry, entry_bump = find_pda([b"entry", pool_key, link_hash], PROGRAM_ID)
```

---

## 15. Polling Loop Implementation

### 15.1 Arquivo: src/main.py

O loop principal precisa implementar:

```python
async def run(self):
    """Run the oracle agent polling loop."""
    self.running = True
    logger.info("Oracle Agent started")
    
    while self.running:
        try:
            # 1. Buscar pools ativos
            await self.check_active_pools()
            
            # 2. Verificar novas entries
            await self.check_new_entries()
            
            # 3. Atualizar métricas
            await self.update_all_metrics()
            
            # 4. Verificar pools expiradas
            await self.check_expired_pools()
            
            await asyncio.sleep(config.POLL_INTERVAL_SECONDS)
            
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"Error in polling loop: {e}")
```

### 15.2 Métodos do Polling

**Baseado em llms-full.txt getProgramAccounts**:

```python
import httpx

async def get_program_accounts(program_id: str, encoding: str = "base64") -> list[dict]:
    """
    Busca todas as accounts de um programa.
    
    Based on llms-full.txt: getProgramAccounts RPC
    """
    async with httpx.AsyncClient() as client:
        response = await client.post(
            RPC_URL,
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "getProgramAccounts",
                "params": [program_id, {"encoding": encoding}]
            }
        )
        return response.json()["result"]


async def get_account_info(pubkey: str, encoding: str = "base64") -> dict:
    """
    Busca info de uma account específica.
    
    Based on llms-full.txt: getAccountInfo RPC
    """
    async with httpx.AsyncClient() as client:
        response = await client.post(
            RPC_URL,
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "getAccountInfo",
                "params": [pubkey, {"encoding": encoding}]
            }
        )
        return response.json()["result"]


# Exemplo JSON-RPC:
# getProgramAccounts
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "getProgramAccounts",
  "params": ["J45dp2TMQXx5v5RDygsF3im7URJqu7QQ996V1kqXeNxN", {"encoding": "base64"}]
}

# getAccountInfo
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "getAccountInfo",
  "params": ["<pool_pda>", {"encoding": "base64"}]
}


async def check_active_pools(self) -> list[dict]:
    """
    Busca VideoPool com status = Open.
    
    RPC: getProgramAccounts(VideoPool)
    Filtro: account.status == 0 (Open)
    
    Returns:
    [{
        'pool_pda': str,
        'original_video_id': str,
        'creator': str,
        'expiry_timestamp': i64,
        'scoring_rules': {'views_weight': u16, 'likes_weight': u16, 'comments_weight': u16},
        'participant_count': u32,
        'total_score': u64,
    }]
    """

async def get_entries_for_pool(self, pool_pda: str) -> list[dict]:
    """
    Busca ParticipantEntry para uma pool específica.
    
    RPC: getProgramAccounts(ParticipantEntry)
    Filtro: account.pool == pool_pda
    
    Returns:
    [{
        'entry_pda': str,
        'pool': str,
        'user': str,
        'clip_link': str,
        'channel_id': str,
        'views': u64,
        'likes': u64,
        'comments': u64,
        'score': u64,
        'claimed': bool,
    }]
    """

async def check_new_entries(self):
    """
    Para cada pool ativa:
    1. Buscar entries não validadas (score == 0)
    2. Para cada entry nova:
       a. Obter video_id do clip_link
       b. Obter canais do creator (do UserProfile)
       c. Chamar validator.validate()
       d. Se FRAUD -> executar slash_user()
    """

async def check_expired_pools(self):
    """
    Para cada pool ativa:
    1. Verificar se clock.unix_timestamp >= pool.expiry_timestamp
    2. Se expirada -> executar close_and_payout()
    """
```

---

## 16. Score Calculation

### 16.1 Fórmula Correta

O score deve usar as scoring_rules da pool:

```python
def calculate_score(metrics: dict, scoring_rules: dict) -> int:
    """
    Calculate weighted score using pool's scoring rules.
    
    scoring_rules:
    - views_weight: u16 (ex: 5000 = 50%)
    - likes_weight: u16 (ex: 3000 = 30%)
    - comments_weight: u16 (ex: 2000 = 20%)
    
    SCORE_BASE = 10_000 (100%)
    
    score = (views * views_weight + likes * likes_weight + comments * comments_weight) / SCORE_BASE
    """
    views = metrics.get('views', 0)
    likes = metrics.get('likes', 0)
    comments = metrics.get('comments', 0)
    
    score = (
        (views * scoring_rules['views_weight']) +
        (likes * scoring_rules['likes_weight']) +
        (comments * scoring_rules['comments_weight'])
    ) // 10000
    
    return score
```

---

## 17. Estado Atual e Próximos Passos

### 17.1 Status Implementação

| Componente | Status | Notas |
|-----------|--------|-------|
| Transcript Validation | ✅ Feito | src/services/transcript_service.py |
| Frame Validation | ✅ Feito | src/services/similarity_service.py |
| Channel Verification | ✅ Feito | src/services/channel_service.py |
| Metrics API Client | ✅ Feito | src/services/metrics_api_client.py |
| Database | ✅ Feito | src/db/database.py |
| SolanaMCP Client | ✅ Feito | src/solana/mcp_client.py |
| SolanaConnection | ✅ Feito | src/solana/connection.py |
| MCP Config (opencode.json) | ✅ Feito | opencode.json |
| OracleCPI.update_metrics | ✅ Feito | src/solana/connection.py |
| OracleCPI.slash_user | ✅ Feito | src/solana/connection.py |
| OracleCPI.close_and_payout | ✅ Feito | src/solana/connection.py |
| Polling Loop | ✅ Feito | src/main.py |
| Score Calculation | ✅ Feito | src/solana/connection.py |

### 17.2 Próximos Passos

| # | Componente | Status |
|---|-----------|--------|
| 1 | Testar com blockchain real | 📋 Pendente |
| 2 | Configurar oracle keypair | 📋 Pendente |

### 17.3 Referências

- Solana Docs: https://solana.com/docs
- SKILL.md: https://solana.com/SKILL.md
- llms-full.txt: https://solana.com/llms-full.txt
- AnchorPy: https://anchorpy.readthedocs.io/
- CPI: https://solana.com/docs/core/cpi
- PDAs: https://solana.com/docs/core/pda
- RPC API: https://solana.com/docs/rpc/http

---

## 18. Solana MCP Integration

### 18.1 O que é o MCP

O **Solana MCP (Model Context Protocol)** é um servidor que permite agentes de IA interagirem com a blockchain Solana de forma simples.

**Documentação**: https://solana.com/developers/guides/getstarted/intro-to-ai

### 18.2 Configuração

Adicionar ao settings.json do IDE:

```json
{
  "mcpServers": {
    "solana": {
      "command": "npx",
      "args": ["mcp-remote", "https://mcp.solana.com/mcp"]
    }
  }
}
```

### 18.3 Funções Disponíveis

| Função | Descrição |
|--------|----------|
| `solana_get_account_info` | Buscar info de uma account |
| `solana_get_program_accounts` | Listar accounts de um programa |
| `solana_get_transaction` | Verificar status de transação |
| `solana_invoke_signed` | Executar instruções CPI |

### 18.4 Arquitetura com MCP

```
Oracle Agent
├── MCP Client (src/solana/mcp_client.py)
│   ├── get_account_info()
│   ├── get_program_accounts()
│   └── invoke_signed()
├── Validator (existente)
│   ├── TranscriptService
│   ├── SimilarityService
│   └── ChannelService
├── Metrics API (existente)
│   └── MetricsApiClient
└── Database (existente)
    └── Database
```

### 18.5 Novo Arquivo: src/solana/mcp_client.py

**Baseado em llms-full.txt RPC API**:

```python
"""Solana MCP Client."""
import httpx
from solders.pubkey import Pubkey

class SolanaMCPClient:
    """Cliente para interagir com Solana via MCP ou RPC direto."""
    
    def __init__(self, rpc_url: str = "https://api.devnet.solana.com", program_id: str = None):
        self.rpc_url = rpc_url
        self.program_id = program_id or "J45dp2TMQXx5v5RDygsF3im7URJqu7QQ996V1kqXeNxN"
    
    async def _rpc_call(self, method: str, params: list) -> dict:
        """Executa JSON-RPC call via HTTP."""
        async with httpx.AsyncClient() as client:
            response = await client.post(
                self.rpc_url,
                json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params}
            )
            return response.json()["result"]
    
    async def get_account_info(self, pubkey: str, encoding: str = "base64") -> dict:
        """
        Busca info de uma account.
        
        Based on llms-full.txt: getAccountInfo RPC
        """
        return await self._rpc_call("getAccountInfo", [pubkey, {"encoding": encoding}])
    
    async def get_program_accounts(self, program_id: str = None, encoding: str = "base64") -> list[dict]:
        """
        Busca todas as accounts de um programa.
        
        Based on llms-full.txt: getProgramAccounts RPC
        """
        pid = program_id or self.program_id
        return await self._rpc_call("getProgramAccounts", [pid, {"encoding": encoding}])
    
    # === Funções de Busca ===
    
    async def get_global_config(self) -> dict:
        """Busca GlobalConfig."""
        global_config_pda, _ = self._find_pda(b"global_config_v1")
        return await self.get_account_info(global_config_pda)
    
    async def get_active_pools(self) -> list[dict]:
        """Busca pools com status = Open."""
        accounts = await self.get_program_accounts()
        return [a for a in accounts if a.get("status") == 0]  # 0 = Open
    
    async def get_entries_for_pool(self, pool_pda: str) -> list[dict]:
        """Busca participant entries de uma pool."""
        accounts = await self.get_program_accounts()
        return [a for a in accounts if a.get("pool") == pool_pda]
    
    async def get_user_profile(self, authority: str) -> dict:
        """Busca UserProfile de um usuário."""
        profile_pda, _ = self._find_pda(b"user_profile", authority.encode())
        return await self.get_account_info(profile_pda)
    
    # === CPI Functions (placeholder usando invoke_signed quando disponível) ===
    
    async def update_metrics(
        self,
        entry_pda: str,
        pool_pda: str,
        views: int,
        likes: int,
        comments: int,
        link_hash: list,
        oracle_keypair: "Keypair",
    ) -> str:
        """
        Executa update_metrics instruction via CPI.
        
        Args:
        - entry_pda: ParticipantEntry address
        - pool_pda: VideoPool address
        - views: u64
        - likes: u64
        - comments: u64
        - link_hash: [u8; 32] - hash do clip_link
        - oracle_keypair: keypair do oracle
        """
        # TODO: Implementar via invoke_signed do MCP quando disponível
        pass
    
    async def slash_user(
        self,
        user_authority: str,
        oracle_keypair: "Keypair",
    ) -> str:
        """Executa slash_user instruction via CPI."""
        # TODO: Implementar via invoke_signed do MCP quando disponível
        pass
    
    async def close_and_payout(
        self,
        pool_pda: str,
        video_id: str,
        oracle_keypair: "Keypair",
    ) -> str:
        """Executa close_and_payout instruction via CPI."""
        # TODO: Implementar via invoke_signed do MCP quando disponível
        pass
    
    # === Helpers ===
    
    def _find_pda(self, seed: bytes, *extra_seeds) -> tuple[str, int]:
        """
        Calcula PDA com bump seed.
        
        Based on llms-full.txt: PublicKey.findProgramAddressSync()
        """
        program_id = Pubkey.from_string(self.program_id)
        all_seeds = [seed] + list(extra_seeds)
        pda, bump = Pubkey.find_program_address(all_seeds, program_id)
        return str(pda), bump
```

### 18.6 PDAs a Calcular (simplificado)

```python
from solders.pubkey import Pubkey

PROGRAM_ID = Pubkey.from_string("J45dp2TMQXx5v5RDygsF3im7URJqu7QQ996V1kqXeNxN")

# GlobalConfig: [b"global_config_v1"]
global_config, _ = Pubkey.find_program_address([b"global_config_v1"], PROGRAM_ID)

# VideoPool: [b"pool", video_id_bytes]
pool, _ = Pubkey.find_program_address([b"pool", video_id_bytes], PROGRAM_ID)

# ParticipantEntry: [b"entry", pool_key, link_hash]
entry, _ = Pubkey.find_program_address([b"entry", pool_key, link_hash], PROGRAM_ID)

# UserProfile: [b"user_profile", authority]
user_profile, _ = Pubkey.find_program_address([b"user_profile", authority_bytes], PROGRAM_ID)

# StakeAccount: [b"stake", authority]
stake_account, _ = Pubkey.find_program_address([b"stake", authority_bytes], PROGRAM_ID)
```

### 18.7 Installation

```bash
# Dependências Python
pip install httpx solders

# MCP Server (opcional)
npm install @anthropic/mcp-remote
```

---

## 19. Resumo: Próximos Passos

### Pendências Atuais (Maio 2025)

| # | Componente | Prioridade | Status |
|---|-----------|-----------|--------|
| 1 | OracleCPI.update_metrics | 🔴 Alta | ❌ Faltando |
| 2 | OracleCPI.slash_user | 🔴 Alta | ❌ Faltando |
| 3 | Polling Loop (main.py) | 🔴 Alta | ❌ Faltando |
| 4 | OracleCPI.close_and_payout | 🟡 Média | ❌ Faltando |
| 5 | Score Calculation | 🟡 Média | ⚠️ Parcial |

### Files já Criados

| Arquivo | Ação |
|--------|------|
| `opencode.json` | ✅ Criado |
| `src/solana/mcp_client.py` | ✅ Criado |
| `src/solana/connection.py` | ✅ Modificado |
| `requirements.txt` | ✅ Modificado |

### Para Implementar

1. **OracleCPI** - src/solana/connection.py
2. **Polling Loop** - src/main.py
3. **Score Calculation** - src/main.py

---

## 20. Recursos Oficiais Solana

### 20.1 SKILL.md

- **URL**: https://solana.com/SKILL.md
- **Install**: `npx skills add https://github.com/solana-foundation/solana-dev-skill`
- **Skills disponíveis**:
  - Common Errors & Solutions
  - Version Compatibility Matrix
  - IDL & Client Code Generation
  - Testing Strategy
  - Security Checklist

### 20.2 llms-full.txt

- **URL**: https://solana.com/llms-full.txt
- **Conteúdo relevante para Oracle**:
  - PDA derivation examples (TypeScript, Rust, Python)
  - RPC API reference (getAccountInfo, getProgramAccounts)
  - CPI examples
  - Account structure

### 20.3 Links Adicionais

- Docs: https://solana.com/docs
- Cookbook: https://solana.com/developers/cookbook
- RPC API: https://solana.com/docs/rpc/http
- Anchor: https://solana.com/docs/programs/anchor
- PDAs: https://solana.com/docs/core/pda
- CPI: https://solana.com/docs/core/cpi

### 20.4 OpenCode MCP Config

Para usar Solana MCP no OpenCode, adicione ao `opencode.json`:

```json
{
  "$schema": "https://opencode.ai/config.json",
  "mcp": {
    "solana": {
      "type": "remote",
      "url": "https://mcp.solana.com/mcp",
      "enabled": true
    }
  }
}
```

---

## Resumo: Implementação Completa

| # | Seção | Status |
|---|------|--------|
| 14.2 | ✅PDA derivation |
| 15.2 | ✅JSON-RPC examples |
| 17.3 | ✅Links oficiais |
| 18 | ✅MCP client |
| **20** | ✅Recursos Oficiais |