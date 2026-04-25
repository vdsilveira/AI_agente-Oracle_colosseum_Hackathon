# Oracle Agent Rules

## 1. Visão Geral

O **Oracle Agent** é um serviço off-chain que valida submissões de vídeos e atualiza métricas na blockchain Solana. Ele opera como um "juiz automatizado" que verifica se os clips submetidos são autênticos e pertencem aos canais dos criadores.

### Objetivo
- Validar submissions de vídeos contra o vídeo original da pool
- Atualizar métricas (views, likes, comments) dos participantes
- Detectar fraudes e banir usuários fraudulentos
- Encerrar pools expiradas (habilitar saque dos participantes)

---

## 2. Responsabilidades Principais

### 2.1 Polling Loop (Monitoramento Contínuo)

O agente executa um loop a cada `POLL_INTERVAL_SECONDS` (padrão: 10800s)://3 horas ou  antes de encerrar a pool


```
1. Buscar pools ativas (status = Open)
2. Para cada pool:
   a. Verificar novas entries (score = 0)
   b. Validar cada nova submission
   c. Atualizar métricas de entries válidas
   d. Verificar pools expiradas
```

### 2.2 Validação de Submissões

O agente valida cada nova submission através de 3 verificaçãoes:

| Verificação | Threshold | Descrição |
|-------------|-----------|-----------|
| **Channel Check** | Exact match | Vídeo B está em canal registrado do editor? |
| **Transcript Check** | ≥70% | Similaridade de transcrição com vídeo original |
| **Frame Check** | 3/5 (SSIM ≥0.70) | Similaridade visual de frames |

### 2.3 Decisões de Validação

| Status | Condição | Ação do Oracle |
|--------|----------|----------------|
| **VALID** | Channel ✓ + Transcript ≥70% + Frames 3/5 | Contar pontos, atualizar métricas |
| **WRONG_CHANNEL** | Vídeo em outro canal do Editor | Ignorar entry, logar motivo, alert frontend |
| **INVALID_TRANSCRIPT** | Transcript < 70% | Ignorar entry, logar motivo |
| **INVALID_FRAMES** | Frames < 3/5 | Ignorar entry, logar motivo |
| **FRAUD** | Canal de outro creator (não registrado) | Executar `slash_user()`, banir usuário |

---

## 3. CPI Instructions (On-Chain)

O agente interage com o programa Solana através de CPI:

### 3.1 update_metrics

**Quando**: A cada poll para entries válidas

**Accounts**:
- `entry`: ParticipantEntry (mut) - a entry a ser atualizada
- `pool`: VideoPool (mut) - a pool da entry
- `config`: GlobalConfig - configuração global (verifica oracle)
- `oracle`: Signer - chave do oracle

**Dados**:
- `views`: u64
- `likes`: u64
- `comments`: u64
- `link_hash`: [u8; 32] - hash do clip_link

**Score Calculation**:
```python
score = (views * views_weight + likes * likes_weight + comments * comments_weight) / 10000
```

### 3.2 slash_user

**Quando**: Fraud detectado (vídeo pertence a outro creator não registrado)

**Accounts**:
- `config`: GlobalConfig (verifica admin ou oracle)
- `user_profile`: UserProfile (mut) - perfil do usuário
- `stake_account`: StakeAccount (mut) - stake do usuário
- `treasury`: UncheckedAccount (mut) - recebe fundos slashados
- `caller`: Signer - oracle

**Ações**:
1. Marca `user_profile.is_banned = true`
2. Transfere 50% do stake para treasury
3. Atualiza `stake_account.amount`

### 3.3 close_and_payout

**Quando**: Pool expirada (clock.unix_timestamp >= pool.expiry_timestamp)

**Accounts**:
- `pool`: VideoPool (mut) - pool a ser fechada
- `prize_vault`: PrizeVault (mut) - vault do prêmio
- `creator`: UncheckedAccount (mut) - recebe dust/rent
- `caller`: Signer - oracle (verificado contra config.oracle)
- `config`: GlobalConfig
- `treasury`: UncheckedAccount (mut) - recebe payout fee

**Ações do Oracle**:
1. Transfere payout_fee (2.5%) para treasury
2. Altera status da pool para `Distributed`

**Nota**: O Oracle **não** distribui prêmios diretamente. Após `close_and_payout`, os participantes devem chamar `claim_prize` para sacar seus prêmios proporcionais à pontuação.

### 3.4 claim_prize (não é responsabilidade do Oracle)

Esta instrução é chamada **pelos participantes**, não pelo Oracle:

**Quando**: Usuário quer sacar seu prêmio

**Accounts**:
- `pool`: VideoPool - deve ter status = Distributed
- `prize_vault`: PrizeVault (mut) - vault do prêmio
- `entry`: ParticipantEntry (mut) - entry do usuário (não pode ter sido sacada)
- `user_profile`: UserProfile - perfil do usuário (não banido)
- `stake_account`: StakeAccount - stake do usuário
- `config`: GlobalConfig
- `authority`: Signer - usuário que está sacar

**Cálculo do Prêmio**:
```
prize = (entry.score / pool.total_score) * net_prize_amount
```
Onde `net_prize_amount = prize_amount * 97.5%`

---

## 4. Thresholds de Validação

| Parâmetro | Valor | Descrição |
|-----------|-------|-----------|
| `TRANSCRIPT_MIN_SCORE` | 0.70 | 70% mínimo de similaridade |
| `FRAME_SIMILARITY_THRESHOLD` | 0.70 | SSIM mínimo por frame |
| `FRAME_MIN_MATCHES` | 3 | Frames que precisam passar (de 5) |
| `FRAME_TOTAL_SAMPLES` | 5 | Total de frames comparados |
| `POLL_INTERVAL_SECONDS` | 10800 | Intervalo de polling (3 horas) |

---

## 5. Integração com Solana

### 5.1 Configuração

O agente usa as seguintes configurações do `.env`:

```
SOLANA_RPC_URL=https://api.devnet.solana.com
ORACLE_PUBLIC_KEY=your_oracle_public_key_here
ORACLE_PRIVATE_KEY=your_oracle_private_key_here
PROGRAM_ID=4RAbxbEVCsYaaK3WR8r7eYwrofTJ7yqdZ3hqSYRLPfT4
```

### 5.2 PDAs Derivados

O agente deriva os seguintes PDAs dinamicamente:

| Account | Seeds |
|---------|-------|
| GlobalConfig | [b"global_config_v1"] |
| VideoPool | [b"pool", video_id_bytes] |
| ParticipantEntry | [b"entry", pool_key, link_hash] |
| UserProfile | [b"user_profile", authority] |
| StakeAccount | [b"stake", authority] |
| PrizeVault | [b"vault", pool_key] |

### 5.3 Oracle Keypair

O agente usa um keypair armazenado em `keys/oracle.json` para assinar transações. Este keypair deve estar cadastrado em `GlobalConfig.oracle` no programa Solana.

---

## 6. Fluxo Completo de Execução

```
                    ┌─────────────────────────────────────────┐
                    │           ORACLE AGENT                  │
                    │      (Polling Loop - 10800s/3h)         │
                    └──────────────────┬──────────────────────┘
                                       │
                                       ▼
                    ┌─────────────────────────────────────────┐
                    │  1. get_active_pools()                  │
                    │     → Busca pools com status = Open     │
                    └──────────────────┬──────────────────────┘
                                       │
                                       ▼
                    ┌─────────────────────────────────────────┐
                    │  2. Para cada pool:                     │
                    │     a. get_entries_for_pool()           │
                    │     b. Filtra entries com score = 0     │
                    └──────────────────┬──────────────────────┘
                                       │
                                       ▼
                    ┌─────────────────────────────────────────┐
                    │  3. Validar cada nova submission:       │
                    │                                          │
                    │  ┌─────────────────┐    ┌─────────────┐  │
                    │  │ CHANNEL CHECK   │───►│ Canal OK?   │  │
                    │  └─────────────────┘    └──────┬──────┘  │
                    │                               │         │
                    │                    ┌──────────┼─────────┐│
                    │                   YES         │        NO│
                    │                    │          │         ││
                    │                    ▼          ▼         ▼│
                    │           ┌───────────┐ WRONG   FRAUD   ││
                    │           │CONTINUE   │ CHANNEL         ││
                    │           └─────┬─────┘                 ││
                    │                 │                       ││
                    │                 ▼                       ││
                    │  ┌─────────────────────────┐            ││
                    │  │   TRANSCRIPT CHECK      │            ││
                    │  │     (≥70% match)        │            ││
                    │  └────────────┬────────────┘            ││
                    │               │                         ││
                    │      ┌────────┼────────┐                ││
                    │     PASS      │      FAIL               ││
                    │      │        │        │                ││
                    │      ▼        ▼        ▼                ││
                    │  ┌───────┐ INVALID  INVALID             ││
                    │  │NEXT   │ TRANSCRIPT                   ││
                    │  └──┬────┘                               ││
                    │     │                                    ││
                    │     ▼                                    ││
                    │  ┌─────────────────────────┐            ││
                    │  │    FRAME CHECK          │            ││
                    │  │   (3/5 SSIM ≥0.70)      │            ││
                    │  └────────────┬────────────┘            ││
                    │               │                         ││
                    │      ┌────────┼────────┐                ││
                    │     PASS      │      FAIL               ││
                    │      │        │        │                ││
                    │      ▼        ▼        ▼                ││
                    │  ┌───────┐ INVALID  INVALID             ││
                    │  │VALID  │ FRAMES                      ││
                    │  └──┬────┘                               ││
                    │     │                                    ││
                    └─────┼────────────────────────────────────┘
                          │
                          ▼
                    ┌─────────────────────────────────────────┐
                    │  4. update_all_metrics()                │
                    │     → API metrics → CPI update_metrics  │
                    └──────────────────┬──────────────────────┘
                          ┌────────────┴────────────┐
                          │                         │
                          ▼                         ▼
                    ┌─────────┐              ┌──────────────┐
                    │ VALID   │              │ WRONG/INVALID│
                    │ entries │              │    entries   │
                    └────┬────┘              └──────────────┘
│                        
                          ▼                        
                    ┌─────────────────────────────────────────┐
                    │  5. check_expired_pools()               │
                    │     → Para pools expiradas:             │
                    │       CPI close_and_payout()            │
                    │       (status → Distributed)            │
                    │       Usuários chamam claim_prize()     │
                    └─────────────────────────────────────────┘
```

---

## 7. Anti-Fraude

### 7.1 Regras de Validação

| Verificação | Regra | Ação se Falhar |
|-------------|-------|----------------|
| Channel | Vídeo B em canal do creator? | WRONG_CHANNEL ou FRAUD |
| Transcript | ≥70% similaridade | INVALID_TRANSCRIPT |
| Frames | 3/5 com SSIM ≥0.70 | INVALID_FRAMES |

### 7.2 Tipos de Fraude

| Tipo | Descrição | Ação |
|------|-----------|------|
| **WRONG_CHANNEL** | Vídeo em outro canal do creator (já registrado) | Ignorar, não contar pontos |
| **FRAUD** | Vídeo pertence a outro creator (não registrado) | `slash_user()` + ban |

### 7.3 Fluxo de Slash

```
FRAUD DETECTADO
      │
      ▼
┌─────────────────┐
│ slash_user CPI  │
│ (caller=oracle) │
└────────┬────────┘
         │
         ▼
┌─────────────────┐     ┌─────────────────┐
│ is_banned = true│     │ 50% stake →    │
│ no UserProfile  │     │ treasury        │
└─────────────────┘     └─────────────────┘
```

---

## 8. API de Métricas

O agente busca métricas de vídeos através de uma API externa:

**Endpoint**: `POST {METRICS_API_URL}/api/metrics/batch`

**Request**:
```json
{
  "videos": [
    {"url": "https://youtube.com/watch?v=...", "platform": "youtube", "user_handle": "..."}
  ]
}
```

**Response**:
```json
{
  "summary": [
    {
      "videos": [
        {
          "url": "...",
          "metrics": {"views": 1000, "likes": 100, "comments": 50}
        }
      ]
    }
  ]
}
```

**Headers**: `Authorization: Bearer {JWT_TOKEN}`

---

## 9. Banco de Dados (Off-Chain)

O agente persiste dados em SQLite para auditoria:

### Tabelas

**validations**
- entry_pda, pool_pda, video_a_id, video_b_id, status, transcript_score, frame_score, reason, created_at

**metrics**
- entry_pda, views, likes, comments, score, updated_at

---

## 10. Alertas

O agente envia alertas para um webhook quando:

| Evento | Tipo | Dados |
|--------|------|-------|
| FRAUD detectado | Error | entry_pda, user_wallet, reason |
| WRONG_CHANNEL | Warning | entry_pda, creator_wallet, editor_wallet, channel_id |

---

## 11. Configuração de Ambiente

```env
# JWT Token para API de métricas
JWT_TOKEN=your_jwt_token_here

# Solana Devnet
SOLANA_RPC_URL=https://api.devnet.solana.com

# Oracle Keys (generate with scripts/generate_oracle_keypair.py)
ORACLE_PUBLIC_KEY=your_oracle_public_key_here
ORACLE_PRIVATE_KEY=your_oracle_private_key_here

# API de Métricas
METRICS_API_URL=https://backend-views-solana.onrender.com

# Thresholds
TRANSCRIPT_MIN_SCORE=0.70
FRAME_SIMILARITY_THRESHOLD=0.70
FRAME_MIN_MATCHES=3
FRAME_TOTAL_SAMPLES=5
POLL_INTERVAL_SECONDS=10800

# Database
DATABASE_URL=sqlite:///oracle.db

# Solana Program ID
PROGRAM_ID=4RAbxbEVCsYaaK3WR8r7eYwrofTJ7yqdZ3hqSYRLPfT4

# Alerts
ALERT_WEBHOOK_URL=
```

---

## 12. Comandos

```bash
# Instalar dependências
pip install -r requirements.txt

# Gerar oracle keypair
python scripts/generate_oracle_keypair.py

# Rodar agente
python -m src.main

# Rodar uma única iteração (testes)
python -m src.main --once

# Rodar testes
pytest tests/
```

---

## 13. Erros Comuns e Soluções

| Erro | Causa | Solução |
|------|-------|---------|
| `Unauthorized` | Oracle não é o signer esperado | Verificar se oracle.key() == config.oracle |
| `PoolNotOpen` | Pool já fechou | Não fazer update_metrics |
| `PoolExpired` | Pool expirou | Verificar expiry_timestamp antes de atualizar |
| `UserAlreadyBanned` | Usuário já foi banido | Não executar slash_user novamente |

---

## 14. Fluxo de Saque (claim_prize)

Após o Oracle executar `close_and_payout`:
1. Pool status = Distributed
2. Usuários podem chamar `claim_prize` para sacar seus prêmios
3. Cálculo: `(entry.score / pool.total_score) * net_prize_amount`

**O Oracle NÃO distribui prêmios diretamente.**

---

## 15. Referências

- **Solana Program**: `programs_colosseum_Hackathon/programs/colosseum-hackathon/src/lib.rs`
- **Oracle Agent**: `AI_agente-Oracle_colosseum_Hackathon/src/`
- **PLAN.md**: Documento original de planejamento