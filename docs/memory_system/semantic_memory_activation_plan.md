# Semantic Memory 活性化計画

> このドキュメントは、既に途中まで実装されている **エピソード → セマンティック**
> 経路を、LLM 生成 + scalable な想起経路を加えて活性化する計画。
>
> **関連**: 短期記憶側の設計は
> [short_term_memory_design.md](./short_term_memory_design.md)。
> エピソード記憶全体像は [../episodic_memory_overview.md](../episodic_memory_overview.md)。

---

## 1. 現状診断 (2026-06-07 時点)

実コードを点検した結果:

| 機能 | コード存在 | wiring | 機能 ON | 備考 |
|---|---|---|---|---|
| episodic chunk 生成 | ✓ | ✓ | ✓ | 検証中 |
| chunk 主観文 (`recall_text`) の LLM 生成 | ✓ | ✓ | ✓ | #23 で動作確認 |
| passive recall (situation_cues) | ✓ | ✓ | ✓ | 検証中 |
| memory link 生成 (Hebbian co-recall 強化) | ✓ | ✓ | ✓ | 自動連想 |
| link spreading activation (recall 時の連想伝播) | ✓ | ✓ | ✓ | |
| **semantic cluster promotion** | ✓ | ✓ (`agent_orchestrator.on_after_tool_turn`) | ✓ だが内容は concat のみ | §2 で詳述 |
| `memory_explore_related` tool (LLM 能動探索) | ✓ | flag 経路あり、**全シナリオで `episodic_explore_related_enabled=False`** | ✗ | §5 で配線 |
| **semantic を prompt に表示** | ✗ | ✗ | ✗ | §4 で新規 |
| **LLM ベース semantic gist** | ✗ (フックは想定済み、port 未定義) | ✗ | ✗ | §3 で実装 |
| `memory_search_semantic` tool (能動 semantic 検索) | ✗ | ✗ | ✗ | §5 で新規 |
| Reflection (Generative Agents 風) | ✗ (docs にあるが実装無し) | ✗ | ✗ | §7 で立場整理 |
| **episodic reinterpretation** | ✓ (`EpisodicReinterpretationCoordinator`) | ✓ (build pipeline で構築される) | △ (active 経路は要確認) | §8 で扱い決定 |

「semantic infra が揃っている」と最初思っていたが、**生成パイプはあるが
prompt 表示と LLM 化が未着** が正確な状態。

---

## 2. 現状の `_deterministic_gist` の中身

`src/ai_rpg_world/application/llm/services/episodic_semantic_cluster_promotion.py:132`:

```python
def _deterministic_gist(episodes):
    parts = [ep.interpreted or ep.recall_text or ep.what for ep in episodes]
    return " / ".join(parts)[:1200]
```

- **要約ではなく単なる concat + 1200 字 truncate**
- docstring に「LLM 脱文脈化は未接続時はスキップし、決定論要約のみ」とある
- **LLM 化のフックは設計済みだが未実装**

つまり現状の semantic store の内容はエピソード本文をくっつけたものに過ぎず、
「学び」にはなっていない。

---

## 3. LLM ベース semantic gist 生成 (§3 = Phase 1b)

### 3.1 新規 port

```python
class ISemanticGistCompletionPort(Protocol):
    def complete_semantic_gist(
        self,
        *,
        player_name: str,
        persona_block: str,
        cluster_episodes: List[SubjectiveEpisode],
        existing_related_semantic: List[SemanticMemoryEntry],
    ) -> SemanticGistResult | None: ...


@dataclass(frozen=True)
class SemanticGistResult:
    gist_text: str          # 50 字以内の命題
    importance_score: int   # 1-10
    tags: List[str]         # 検索用 (例: ["タカシ", "信頼"])
```

### 3.2 生成プロンプト

```
あなた = {player_name}
あなたの性格 = {persona_block}

以下は最近、強く関連付けられた記憶群です。これらに共通する「学び・教訓・
関係性の理解」を一つ、抽象化して書いてください。

【ルール】
- 個別シーンの再話ではなく、一般化された認識を書く
- 50 字以内、命題形式 (例: 「タカシは信頼できる」「北の洞窟は危険」)
- 確信度に応じて修飾を変える: 確信 → 言い切り / 仮説 → 「〜かもしれない」
- 重要度 (1-10) を別フィールドで出力
- プレイヤー・スポット・オブジェクトは必ず固有名詞で書く (P1 等のラベル禁止)

【記憶群】
{cluster_episodes_subjective}

【既存の関連 semantic (重複避けの参考)】
{existing_related_semantic}

出力 JSON:
{
  "gist_text": "...",
  "importance_score": 1-10,
  "tags": ["..."]
}
```

### 3.3 既存パイプとの接続

`EpisodicSemanticClusterPromotionService.on_after_tool_turn`:
- cluster 検出は既存ロジックを残す
- 検出後、現在の `_deterministic_gist` を呼ぶ箇所を **scheduler 経由の LLM 呼出** に差し替え
- LLM 失敗時は `_deterministic_gist` にフォールバック (既存挙動を保持)

非同期スケジューラは既存 `EpisodicChunkSubjectiveScheduler` と同じ
ThreadPool パターンを再利用する。

---

## 4. Passive top-K による prompt 表示 (§4 = Phase 1c)

### 4.1 なぜ top-K か

長期運用 (数千ターン) を想定すると semantic store は数百〜数千件規模になる。
全件 prompt 表示は不可能。

**Generative Agents 方式**:
```
score(entry) = α × recency + β × importance + γ × relevance
```

- **recency**: 最後に強化された tick からの経過 (指数減衰)
- **importance**: 生成時の LLM 出力 (1-10)
- **relevance**: 現在の situation_cues との一致度 (passive_recall と同じロジック)

top-K (K=3 程度) のみ §3 として prompt に出す。

### 4.2 prompt 表示

```
【関連する学び】 (最大 3 件、状況に応じて)
- タカシは漁の名手で、私を頼る (信頼度 high)
- 北の洞窟は熊の巣 (危険度 high)
- 嵐の前は鳥がいなくなる
```

3 件 × 50 字 ≈ 150 字。scale しても prompt は太らない。

### 4.3 配線

`prompt_builder` の `_run_passive_recall` を拡張する形で:
- 既存の episodic passive recall に加えて
- semantic passive top-K を **同じ situation_cues** で実行
- 結果を新規セクション §3 として組み込む

---

## 5. Active retrieval tools (§5 = Phase 1a + 1d)

### 5.1 Phase 1a: `memory_explore_related` を有効化 (既存)

`src/ai_rpg_world/application/llm/services/executors/episodic_memory_explore_tool_executor.py`
は既に実装済み。**全シナリオで `episodic_explore_related_enabled=False`** なので、
survival_island_v2 で有効化するだけ。

ただし **§9 (デフォルト OFF 方針) に従い、scenario config で明示的に有効化したときだけ動かす**。

### 5.2 Phase 1d: `memory_search_semantic` 新規

新規 tool:
```python
@dataclass(frozen=True)
class MemorySearchSemanticArguments:
    query: str           # 例: "タカシについて知っていること"
    inner_thought: str   # subjective_action 必須
```

実装:
- query を tag/keyword と照合 (将来は embedding)
- 上位 5 件を返す
- 結果は次ターンの `recent_events_text` に「思い出した: ...」として現れる

### 5.3 デフォルト OFF の方針

Phase 1a/d の active retrieval tool は **wiring を整える** が、scenario config で
明示的に有効化したときだけ動かす:

```json
{
  "memory": {
    "episodic_explore_related_enabled": false,
    "semantic_search_enabled": false
  }
}
```

理由: §9 参照。

---

## 6. 経路全体図 (Phase 完了後)

```
                  episodic chunks
                       │
            ┌──────────┴───────────────┐
            ▼                          ▼
   ┌────────────────┐         ┌────────────────────┐
   │ memory links   │         │ subjective filling  │
   │ (Hebbian)      │         │ (LLM recall_text)   │
   └────────────────┘         └────────────────────┘
            │                          │
            │ strong cluster           │
            ▼                          │
   ┌────────────────────────────┐    │
   │ semantic promotion         │◀───┘
   │   ★ LLM gist (§3)           │
   │   ★ importance score        │
   │   + tags                    │
   └────────────────────────────┘
            │
            ▼
   ┌─────────────────────────────────────────┐
   │ semantic store (大量の学びが蓄積)         │
   └─────────────────────────────────────────┘
            │
   ┌────────┴───────────────────┐
   ▼                            ▼
 (§4) passive top-K       (§5) active tools
   situation_cues          ・memory_explore_related
   + recency               ・memory_search_semantic
   + importance
   + relevance
   │                            │
   ▼                            ▼
prompt §3 (常時)         tool call の返答
最大 3 件                (LLM の next turn input)
```

---

## 7. Reflection の立場 (整理)

### 7.1 「Reflection」を独立モジュールにしない

Generative Agents の reflection は **「クラスタ検出 + LLM 抽象化」** で
構成される。我々のシステムでは:

- **クラスタ検出** = `EpisodicSemanticClusterPromotionService` (既存)
- **LLM 抽象化** = §3 `ISemanticGistCompletionPort` (Phase 1b)

→ **Reflection = この 2 段を組み合わせたものに名前を付け直す程度** で、新規
モジュールは作らない。

将来「定期的に semantic を見直して再 gist する」追加 trigger を入れる場合は
名称として `reflect()` を使う余地はあるが、Phase 1 では含めない。

### 7.2 LLM 化の段階性

| Step | 内容 |
|---|---|
| 現状 | `_deterministic_gist` = concat + truncate |
| Phase 1b | LLM gist 生成 (cluster 検出時のみ) |
| 将来 | 定期 reflection (時間 trigger で既存 semantic を再評価) |

---

## 8. Episodic reinterpretation の扱い

### 8.1 背景

過去に「**エピソード記憶がリコールされた際に、それを今のコンテキストで
再解釈する**」機能の実装を試みた経緯がある (人間がエピソード記憶を文脈で
再解釈する現象から発想)。

実コード:
- `src/ai_rpg_world/application/llm/ports/episodic_reinterpretation_completion_port.py`
- `src/ai_rpg_world/application/llm/services/episodic_reinterpretation_coordinator.py`
- `prompt_builder._join_passive_recall_texts` で `active.current_recall_text` 上書き経路あり

`EpisodicReinterpretationCoordinator` は wiring (`_shared_builders.py:180`) で
構築されているが、active な再解釈 trigger が走っているかは要確認。

### 8.2 立場

今回の整理では **Reflection と Semantic promotion を優先** し、再解釈は別系統
として温存する。

理由:
- 再解釈は「想起のたびに LLM 呼出」になる可能性があり、レイテンシ影響が大きい
- semantic gist (LLM) が入れば「クラスタ単位の抽象化」は別経路でカバーできる
- 再解釈の本来価値 (1 つのエピソードを違う角度で見直す) は semantic とは
  別物なので、必要性が顕在化したら独立 PR で活性化させる

### 8.3 動作確認 TODO

Phase 1 着手前に:
- `EpisodicReinterpretationCoordinator` が実際にどこから呼ばれているか確認
- もし呼ばれていない (dead wiring) なら明示的に OFF にする trace を出す
- 呼ばれているなら、Phase 1b の semantic gist と内容が衝突しないか確認

---

## 9. デフォルト OFF の方針 (重要)

Phase 1a–1d で実装する semantic 系機能は **wiring を整えるが、scenario config で
明示的に有効化したときだけ動かす**。

### 9.1 なぜ OFF か

現在は **エピソード記憶 (chunk 生成 / passive recall) の検証が途中**。
semantic を同時に有効化すると 2 つの変数が交絡して検証が崩れる。

→ まず episodic を固めてから、別実験回で semantic を ON にする。

### 9.2 用語の明確化

「配線をする = 機能を ON にする」ではない。

| 用語 | 意味 |
|---|---|
| **配線する (wire)** | コードパスを通し、dependency を inject する。default は不活性 |
| **有効化する (enable)** | scenario config / feature flag で実際に動作させる |

Phase 1a–1d は **配線まで** やる。**有効化** は別 PR で実験回ごとに切替。

### 9.3 config 例

```json
{
  "memory": {
    "semantic_llm_gist_enabled": false,
    "semantic_passive_top_k": 0,
    "episodic_explore_related_enabled": false,
    "semantic_search_enabled": false
  }
}
```

すべて `false` / `0` をデフォルトとし、Phase 1 完了後の比較実験で意図的に
ON にする。

---

## 10. 実装フェーズ

| Phase | 内容 | 工数 | デフォルト |
|---|---|---|---|
| **1a** | `memory_explore_related` の wiring 整備 (既存 tool を survival_island_v2 で flag 経由で有効化可能に) | 半日 | OFF |
| **1b** | `ISemanticGistCompletionPort` 実装 + `EpisodicSemanticClusterPromotionService` を LLM 化 (失敗時 concat fallback) | 3-5日 | OFF |
| **1c** | semantic passive top-K を prompt §3 に配線 (score = recency + importance + relevance) | 2日 | OFF (top_k=0 がデフォルト) |
| **1d** | `memory_search_semantic` tool 新規 | 2-3日 | OFF |
| **計測** | trace 拡張: `SEMANTIC_GIST_GENERATED` / `SEMANTIC_PASSIVE_RECALL` event 追加 | 1日 | 常時 ON |

---

## 11. メトリクスと検証

新規 trace event:

| event kind | payload | 目的 |
|---|---|---|
| `SEMANTIC_GIST_GENERATED` | `cluster_episode_count`, `gist_text_snippet`, `importance_score`, `latency_ms` | LLM gist 品質と生成コスト |
| `SEMANTIC_PASSIVE_RECALL` | `situation_cues`, `top_k_count`, `entries[].id`, `entries[].score` | top-K 想起の発火頻度 |
| `SEMANTIC_SEARCH_ACTIVE` | `query`, `result_count` | LLM の能動検索行動 |
| `MEMORY_EXPLORE_RELATED_CALLED` | `seed_episode_id`, `explored_count` | 既存 tool の使用頻度 |

実験で見たい指標:
- **semantic store 件数の時系列**: 数百件規模に達するか
- **passive top-K の hit 率**: 検索結果が prompt に出ても LLM が使ったか
  (これは observation prose で間接的に判断)
- **active tool 呼出頻度**: LLM が memory_search_semantic / explore_related を
  どれくらい使うか

---

## 12. リスク

### 12.1 LLM gist が抽象化に失敗する (= 再話になる)

50 字制限と命題形式を強制しても、cluster 内エピソードの単純連結を返す
可能性がある。

対策:
- few-shot 例をプロンプトに 2-3 件入れる (良い gist / 悪い gist)
- 失敗判定: 出力が cluster 内エピソードの recall_text とほぼ同一 → concat fallback

### 12.2 top-K が偏る (同じ semantic が常に top)

importance が高い entry が永遠に top を占める。新しい学びが想起されない。

対策:
- recency 重みを高くする (Generative Agents は β/γ を小さめに)
- top-K 内で diversification (tag 単位で重複排除)

### 12.3 ラベル混入

`_deterministic_gist` 時代の semantic entry にはラベル文字列 (P1, OBJ2) が
含まれている可能性がある。LLM gist 化後はラベル禁止だが、過去 entry に
ラベルが残ると参照が腐る。

対策:
- Phase 1b リリース時、既存 semantic store を **clear or re-generate** する
- 新規生成は固有名詞のみ (プロンプトで明文化済み)

---

## 13. 完了の定義

- [ ] Phase 1a: `episodic_explore_related_enabled=True` で `memory_explore_related`
  tool が action trace に出る
- [ ] Phase 1b: `semantic_llm_gist_enabled=True` で生成された gist が
  cluster の単純連結と異なる (5 件 eyeball で確認)
- [ ] Phase 1c: `semantic_passive_top_k=3` で §3 に semantic が表示される
- [ ] Phase 1d: `semantic_search_enabled=True` で `memory_search_semantic` が
  action trace に出る
- [ ] 全 Phase OFF 時、現行 episodic 経路の挙動が変わらない (regression なし)

---

## 14. 用語表 (今後の混乱回避)

| 用語 | 定義 |
|---|---|
| **配線する (wire)** | dependency を inject してコードパスを通す。default で動かない |
| **有効化する (enable)** | scenario config / feature flag で実際に動作させる |
| **Semantic memory** | エピソードクラスタから生成される「時を超えた事実」(関係性・世界ルール・教訓) |
| **Reflection** | クラスタ検出 + LLM 抽象化。本プロジェクトでは独立モジュールにせず、semantic promotion の LLM 化として実装 |
| **Episodic reinterpretation** | 想起時に今のコンテキストで episode 主観文を書き換える機能。別系統で温存 |
| **Passive top-K** | 状況連想で semantic store から上位 K 件を自動表示 (LLM 呼出無し) |
| **Active retrieval** | LLM が tool 呼出で能動的に memory を検索する |
