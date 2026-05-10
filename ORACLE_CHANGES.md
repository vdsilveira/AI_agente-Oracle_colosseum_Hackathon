# Oracle Agent - Fluxo de Validação Refatorado

## Resumo das Mudanças

O Oracle Agent foi refatorado para seguir o fluxo correto de validação:

### ✅ Antes (Incorreto)
- Validava criador da pool (não o editor)
- Fazia `continue` quando criador não tinha canais, pulando a métrica de TODAS as pools
- Nunca chamava `update_all_metrics()`

### ✅ Depois (Correto)
- Valida **editor** que submeteu o clipe (primeira validação)
- Apenas atualize métricas em submissões subsequentes (sem revalidação)
- Garante que `update_all_metrics()` é sempre chamado

---

## Novo Fluxo no Loop Principal

```python
Para cada pool ativa:
  ├─ Buscar entries novas (score=0)
  │  └─ Para cada entry nova:
  │     ├─ Obter canais registrados do EDITOR (via on-chain)
  │     ├─ Chamar API para validar se clip pertence aos canais
  │     ├─ Se válido: marcar como validado ✓
  │     └─ Se fraude: slashar editor ⚠️
  │
  └─ Atualizar métricas de TODAS as entries validadas
     ├─ Chamar API de análise de vídeos
     ├─ Obter views, likes, comments
     └─ Chamar update_metrics() no blockchain
```

---

## Arquivos Modificados

### 1. `src/main.py`

#### Mudança 1: Loop Principal (linhas ~271-319)
**Antes:**
```python
# ❌ Tentava validar criador
creator_channels = await conn.get_creator_channels(creator)
if not creator_channels:
    continue  # ← Pulava update_all_metrics!
```

**Depois:**
```python
# ✅ Valida editor
result = await self.validate_editor_authorship(
    clip_url=clip_url,
    entry_pda=entry_pda,
    pool_pda=pool_pda,
    editor_wallet=editor_wallet,
)
# update_all_metrics() sempre é chamado
await self.update_all_metrics(pools)
```

#### Mudança 2: Novo Método `validate_editor_authorship()`
- Obter perfil do editor: `await conn.get_user_profile(editor_wallet)`
- Validar clip na API: `await metrics_api.validate_clip_ownership(...)`
- Se clip não pertence aos canais do editor: FRAUD → slashar

---

### 2. `src/services/metrics_api_client.py`

#### Novo Método: `validate_clip_ownership()`
```python
async def validate_clip_ownership(
    clip_url: str,
    editor_channels: list[str]
) -> str:
    """
    Valida se um clip pertence a um dos canais do editor.
    
    POST /api/v1/validate-ownership
    {
        "clip_url": "https://tiktok.com/...",
        "expected_channels": ["UCxxxx", "UCyyyy"]
    }
    
    Response:
    {
        "channel_id": "UCxxxx"  // ou null se não encontrado
    }
    """
```

---

### 3. `src/solana/mcp_client.py`

#### Melhorado: `get_user_profile()`
Agora faz parsing correto de Borsh:
- Discriminator (8 bytes) → skip
- Authority (32 bytes)
- Vec<String> channel_ids (u32 len + strings)
- is_banned (bool)
- bump (u8)

**Retorna:**
```python
{
    "authority": "...",
    "channelIds": ["UCxxxx", "UCyyyy"],  # ← Liste de canais registrados
    "is_banned": False,
    "bump": 254
}
```

---

## Fluxo de Validação Detalhado

### Cenário 1: Editor válido (primeira submissão)
```
1. Oracle detecta entry com score=0
2. Obter canais registrados do editor (on-chain)
   → Editor tem: ["UCxxxx"]
3. Chamar API validate_clip_ownership(clip_url, ["UCxxxx"])
   → API retorna: "UCxxxx" ✓
4. Clip validado!
5. Na próxima iteração, update_all_metrics() vai buscar métricas
```

### Cenário 2: Editor fraude (clipe de outro canal)
```
1. Oracle detecta entry com score=0
2. Obter canais registrados do editor (on-chain)
   → Editor tem: ["UCxxxx"]
3. Chamar API validate_clip_ownership(clip_url, ["UCxxxx"])
   → API retorna: None (clipe é de "UCyyyy") ✗
4. FRAUD DETECTED!
5. Chamar slash_user() → bloquear editor
```

### Cenário 3: Update subsequente (entry já validada)
```
1. Oracle detecta entry com score > 0
2. Não chama validate_editor_authorship() novamente ✓
3. Apenas atualiza métricas na próxima iteração
```

---

## Testes Inclusos

### `test_oracle_flow.py`
Testa o fluxo completo:
1. ✅ Detecta pools ativas
2. ✅ Detecta entries novas
3. ✅ Valida autoria do editor
4. ✅ Testa API de métricas

```bash
cd AI_agente-Oracle_colosseum_Hackathon
python test_oracle_flow.py
```

### `test_metrics_api.py`
Testa especificamente a API:
1. ✅ Health check
2. ✅ Batch analysis
3. ✅ Validate ownership endpoint

```bash
cd AI_agente-Oracle_colosseum_Hackathon
python test_metrics_api.py
```

---

## Checklist de Validação

- [ ] API de métricas está respondendo em `https://backend-views-solana.onrender.com`
- [ ] Endpoint `/api/v1/validate-ownership` existe e valida clips
- [ ] Oracle consegue parsear UserProfile do editor
- [ ] Oracle executa `validate_editor_authorship()` para entries novas
- [ ] Oracle sempre chama `update_all_metrics()` (não há mais `continue`)
- [ ] Oracle consegue atualizar métricas no blockchain
- [ ] Fraudes são detectadas e usuários são slashados

---

## Debug Esperado nos Logs

```
[Oracle] Found 5 active pools
[Oracle] Validating first submission for entry Adx... from editor GaN...
[Oracle] Editor GaN... has 2 registered channels: ['UCxxxx', 'UCyyyy']
[Oracle] Authorship validated for editor GaN... - clip from channel UCxxxx
[Oracle] Updating metrics for 3 entries in pool Bdy...
[Oracle] Updated AdX: V=1250 L=45 C=8 → Score=6325, tx=5Aq...
```

---

## Próximas Etapas

1. **Verificar API**: Confirmar que `/api/v1/validate-ownership` existe
2. **Testar flow**: Executar `test_oracle_flow.py` para validar integração
3. **Monitor logs**: Acompanhar logs do Oracle para ver o novo fluxo em ação
4. **Testar fraude**: Submeter clipe de canal não registrado e verificar slashing
