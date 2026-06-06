# 短期記憶 (Short-Term Memory) 設計

> このドキュメントは、現在の `DefaultSlidingWindowMemory` (固定容量 20 件の
> sliding window) を補完する **rolling summary 型** の短期記憶モジュールの
> 設計を確定した版。実験 #25 (Issue #356) の trace 分析を出発点に、
> **prefix cache 効率** と **連続性のある記憶** の両立を目的とする。
>
> **関連**: 長期記憶側の整理は
> [semantic_memory_activation_plan.md](./semantic_memory_activation_plan.md)。
> エピソード記憶パイプライン全体像は
> [../episodic_memory_overview.md](../episodic_memory_overview.md)。

---

## 1. なぜ作るか

### 1.1 実験 #25 で観測された 2 つの bloat

OFF run (episodic 無し / 143 ticks / n=743 LLM calls) の trace 分析より:

| メトリクス | 値 | 解釈 |
|---|---|---|
| `lat_ms` ≈ 1.622 × prompt_tokens − 4110 | linear fit, R² 高 | 1 prompt token ≈ 1.6ms TTFT (キャッシュなし水準) |
| TPS (effective input throughput) | tick 進行で 1280 → 760 に低下 | prefix cache が効いていない / 効いていてもごく一部 |
| prompt_tokens p95 | OFF 11238 vs ON_FULL 15571 (+38.6%) | episodic recall がテールを押し上げる |
| OFF prompt_tokens 推移 | tick 40 で 9591 → tick 180 で 10658 (+11%) | sliding window 飽和後も何かが伸び続けている |

prefix cache が効かない根本理由は **「user content 上位 (current_state) が毎ターン変動する」**
と **「sliding window が evict を始めると prefix が毎ターンずれる」** の二段。

### 1.2 連続性の不在

長期 (episodic) と短期 (sliding window 20 件 ≈ 数ターン) の間に **中期帯
(15–100 ターン) の記憶が無い**。sliding window から evict された観測は
そのまま捨てられる。「最近 30 ターン何をしてきたか」の連続感が AI 側で
失われる。

---

## 2. 設計原則

### 2.1 prefix cache 優先 × LLM 混乱回避

| 原則 | 効果 |
|---|---|
| **stable → volatile 順で並べる** | vLLM auto prefix cache の prefix match を最大化 |
| **「今ここ」を末尾近くに置く** | Lost-in-the-middle 緩和。判断精度向上 |
| **時間スケール 大 → 小 → 指示** の流れ | 認知的に自然 (人間の語り順) |
| **更新頻度が低いもの = 上、高いもの = 下** | cache 寿命を最大化 |

### 2.2 narrative continuity に責務を絞る

このモジュールは **「最近やったこと」「今の気分」「自分の語り口」** だけを
担う。学び (タカシは信頼できる) や世界ルール (毒キノコ = 赤い斑点) は
**episodic → semantic の経路** に任せる ([semantic_memory_activation_plan.md](./semantic_memory_activation_plan.md) 参照)。

これは Tulving の memory taxonomy に近い分離:
- **episodic** = 「あの時あの場所」(具体エピソード)
- **semantic** = 「世界はそういうもの」(時を超えた事実)
- **rolling summary** = 「最近の自分の流れ」(narrative voice)

### 2.3 動的ラベルを焼かない

ターン局所のラベル (`P1`, `P2`, `O3`, ...) は **ターンごとに違う実体を指す
ことがある**。要約や long-term store に焼き込むと参照が腐る。

→ rolling summary は必ず **永続名 (`player_name` 等の固有名詞)** で表現する。
ラベルへの対応付けは current_state_text 側の責務。

---

## 3. レイヤー構造

| Layer | 役割 | 容量 | 寿命 | 1 件のサイズ目安 |
|---|---|---|---|---|
| **L1 raw queue** | 鮮度 | 15 件 | 容量超で最古を畳む | 50–200 tok / 件 |
| **L4 mid summary** | 連続性 (中期) | 直近 3 世代 (≒ 45 raw 分) | L4 4 世代目が来たら最古を L5 に統合 | 250–400 tok / 件 |
| **L5 long summary** | アイデンティティ | 1 件のみ | L4 が L5 を更新するたび置き換え | 300–500 tok |

合計上限: ≈ 2000–4000 tok。現状の `DefaultSlidingWindowMemory` (3000–6000 tok) より
軽く、prefix cache 寿命が伸びる。

> **L2 / L3 を欠番にしている理由**: ドキュメント中の番号は
> [../episodic_memory_overview.md](../episodic_memory_overview.md) の
> エピソード階層 (L0 raw → L2 chunk → L3 episode) と整合させるため。

### 3.1 状態遷移

```
新しい observation 到着
  ↓
L1 に append
  ↓
L1.size >= 15 ?
  ├─ No  → 終了
  └─ Yes → 古い 15 件を取り出し、L4 生成タスクを scheduler に投げる (非同期)
            ↓
       L4 生成完了 (worker thread で 2-5s 想定)
            ↓
       L4 に新世代として prepend、L1 は 15 件削除
            ↓
       L4.size > 3 ?
            ├─ No  → 終了
            └─ Yes → 最古の L4 + 現在の L5 を取り出し、L5 統合タスクを scheduler に投げる
                      ↓
                 L5 生成完了
                      ↓
                 L5 を置き換え、L4 から最古世代を削除
```

このフローは既存の `EpisodicChunkSubjectiveScheduler` パターンと同型なので、
同じ ThreadPool 基盤に乗せる。

### 3.2 非同期生成中の挙動

L4 生成が走っている間に L1 が 15 を超えたら:
- **soft cap 15** で trigger 投入 (越えても新規 trigger は出さない)
- **hard cap 25** を越えそうなら **template fallback** (raw 連結を要約とみなして L4 に詰め、L1 空に)

template fallback は LLM 失敗時にも使う。既存 episodic の
`draft → subjective_filled` パターンを踏襲し、「失敗で死なない」原則を守る。

prompt 表示時は **生成中の世代を待たない**: 現状の L4 をそのまま表示する。
要約待ちのレイテンシは prompt build 側に伝播させない。

---

## 4. 生成プロンプト

### 4.1 L4 生成 (mid summary)

```
あなた = {player_name}
あなたの性格 = {persona_block}
あなたの役割 = {role}

以下は直近 {N} ターンの体験です。あなた自身の主観的な記憶として一人称で
振り返り、JSON で出力してください。

【絶対のルール】
- プレイヤー・スポット・オブジェクトを指すときは必ず固有名詞を使う
- P1, P2, OBJ3 のような短縮ラベルは絶対に使わない (ターンごとに変わるため)

【絶対に落としてはいけない】
- 約束・誓い・取引 (誰と・何を・いつまで)
- 死亡・重傷・大損失 (自他問わず)
- 新規知識 (例: 「毒キノコは赤い斑点」)
- 未解決の脅威・目標
- アイデンティティ更新 (例: 「自分は泳げない」)
- 関係性転換 (信頼/裏切り)

【圧縮していい】
- 連続移動 → 方向と結果のみ ("北東方面を探索したが収穫薄")
- 試行失敗の細部 → 回数だけ
- 既知 NPC への定型挨拶

【落としてよい】
- 重複する環境観測 (天気・景観)
- 失敗 tool の引数違い

出力 (この schema 厳守):
{
  "compressed_activity": "行動の流れ (2-3 文)",
  "emotional_summary": "今の感情の中核 (1 文)",
  "unresolved": ["未解決の脅威/目標 0-3 件"]
}

【参考: 直前の中期記憶】
{previous_l4_latest_or_empty}

【直近 {N} ターン】
tick {t1}: {raw_obs_1}
...
```

**意図的に schema から外したもの**:
- `relationships` → semantic に任せる
- `world_model_updates` → semantic に任せる
- `key_facts` → 「事実」は semantic、ここは narrative voice に絞る

### 4.2 L5 生成 (long summary 更新)

```
あなた = {player_name}
あなたの性格 = {persona_block}

現在のあなたの自己像:
{previous_l5_or_initial_persona}

まもなく忘れる中期記憶 (これから自己像に溶かす):
{oldest_l4_being_evicted}

これら 2 つを統合し、新しい自己像と世界観を JSON で出力してください。

【統合のルール】
- 細部 (tick / 個別 action) は捨てる
- 「次の行動選択に効く根本」だけ残す
- 信念が変わったら **古い信念を上書きする** (両論併記しない)
- 性格 (persona) は previous_l5 のものを保つ。揺れるのは事実認識のみ
- 固有名詞のみ (ラベル禁止)

出力 (この schema 厳守):
{
  "self_image": "今の自分 (2-3 文、narrative voice)",
  "world_view": "この島について (2-3 文、narrative voice)"
}
```

**意図的に schema から外したもの**:
- `key_relationships` → semantic に任せる
- `core_goals` → memos と passive recall に任せる

---

## 5. prompt 表示順 (確定)

```
=== system ===
[persona + role + race + element + game_description]
[tools 仕様]

=== user ===
§1 【現在の目的】              (static)             ← scenario 固定
§2 【自己像と世界観】 (L5)     (~50+ turns stable)
§3 【関連する学び】 (semantic top-K)  (cluster 昇格時のみ更新、最も安定) ★
§4 【最近の流れ】 (L4 ×3)      (~15 turns stable)
§5 【進行中のメモ】 (memos)    (semi-static)
§6 【所持・判明した物証】       (mid-volatile)
§7 【関連する記憶】 (episodic recall)  (mid-volatile)
§8 【直近の出来事】 (L1 raw)    (volatile)
§9 【現在地と周囲】             (most volatile)
§10 【次の行動を選んでください】(static)
```

★ §3 は [semantic_memory_activation_plan.md](./semantic_memory_activation_plan.md) で配線する semantic top-K を表示する位置。L4/L5 と並列に空セクションとして枠だけ先に確保しても良い。

### 5.1 各 section の更新頻度 (cache 寿命の根拠)

| section | 更新頻度 (per turn 確率) | cache 寿命 |
|---|---|---|
| system | ≈ 0 (per-player 固定) | run 全体 |
| §1 objective | ≈ 0 (scenario 固定) | run 全体 |
| §2 L5 self/world | ~3% (世代交代時のみ、~30 ターンに 1 回) | 30+ ターン |
| §3 semantic top-K | ~5% (cluster 昇格時のみ、状況変化で top-K 入替) | 10+ ターン |
| §4 L4 mid | ~7% (15 ターンに 1 回世代追加、内容は確定後不変) | 15 ターン |
| §5 memos | ~2% (memo_add/done 時のみ) | 数十ターン |
| §6 inventory | ~20% (アイテム取得/消費時) | 5 ターン |
| §7 recall | ~70% (situation_cues が変わるたび) | 1-3 ターン |
| §8 raw | ~95% (毎ターン append) | 1 ターン |
| §9 current_state | ~99% (位置/可視物変動) | 1 ターン |
| §10 instruction | 0 | run 全体 |

### 5.2 LLM 混乱回避の配慮

「Lost in the Middle」(Liu et al. 2023): LLM の attention は **先頭と末尾が強く中央が弱い**。

- **「今ここ」(§9)** を末尾近くに置く → 判断精度向上
- **「指示」(§10)** を末尾に置く → tool_choice="required" との相性が良い
- **時間スケール大 → 小** (§2 long → §4 mid → §8 raw → §9 now) → 認知的に自然

§3 (semantic) と §2 (L5) はどちらも非常に stable。**§2 を先** にする理由:
「読み手 = この性格の私」という人称設定が先に来て、§3 の学び (事実) を主観で受け取れる順序として自然。

---

## 6. 実装フェーズ

| Phase | 内容 | 工数 | デフォルト | 検証対象 |
|---|---|---|---|---|
| **0** | prompt section 順入替 (現状の sliding window のまま) | 1日 | **ON** | prefix cache 効率 (`cached_tokens / prompt_tokens` 比) |
| **1** | `RollingSummaryShortTermMemory` 実装 (L1 + L4) | 1週間 | **OFF** (#371 マージ後の experiments では sliding window のまま) | L4 生成品質・要約スキーマ妥当性 |
| **2** | L5 統合 | 3日 | **OFF** | 自己像の連続性 |
| **3** | 計測 & tune (raw 件数 / L4 世代数 / prompt 文体) | 1週間 | 個別 ON/OFF | 行動精度への影響 |

### 6.1 デフォルト OFF の方針 (重要)

Phase 1/2 で実装する `RollingSummaryShortTermMemory` は **wiring を整える
が、scenario config で明示的に有効化したときだけ動く** ようにする。

理由:
- 現在は episodic 記憶 (生成 / passive recall / chunk 主観文 LLM 化) の検証が
  途中。短期記憶のアーキテクチャを同時に切り替えると 2 つの変数が交絡して
  検証が崩れる
- まず episodic を固めてから rolling を入れる順序にする

config 例 (案):
```json
{
  "memory": {
    "short_term_memory_kind": "sliding_window"  // default
    // "short_term_memory_kind": "rolling_summary"  // 切替時のみ
  }
}
```

wiring 側で `IShortTermMemory` の実装を分岐選択する。`RollingSummaryShortTermMemory`
を作っても scenario が明示しなければ instantiate しない。

### 6.2 既存 `DefaultSlidingWindowMemory` の扱い

維持する。Phase 1 以降も削除しない。理由:
- A/B 実験の比較対象として残す
- 短いシナリオ (escape_game のような数十ターンで完結する) では sliding window で十分

---

## 7. エピソード記憶との関係

| 軸 | episodic | rolling summary |
|---|---|---|
| 単位 | 1 シーン (3-7 行動) | 連続 15 raw |
| トリガ | scene_boundary / category_shift | L1 容量到達 |
| 内容 | 「あの瞬間」の主観文 1 段落 | 構造化 JSON (activity / emotional / unresolved) |
| 呼出 | passive recall (situation_cue 連想) | 常に prompt 表示 |
| 不変性 | 一度書いたら不変 | 世代 sliding で消える (L5 に溶ける) |
| LLM 入力 | 1 シーンの raw | 15 raw 連結 + 直前 L4 |
| LLM 出力 | recall_text (再体験文体) | 俯瞰文体 JSON |
| 役割 | 「ふと思い出す」flashback | 「最近何をしてきたか」narrative |

完全に責務直交。生成プロンプトを意図的に違える:
- episodic: 「あの場面を再体験するように 1 段落で語ってください」
- rolling: 「俯瞰して圧縮してください、絶対落とすなリスト遵守」

重複は完全には防げないが、文体・表示位置・呼出経路が違うので LLM の
attention 上は補完関係に見えるはず。実験で重複率を計測して問題があれば
dedup を後から入れる。

---

## 8. 公開 API スケッチ

### 8.1 interface

既存 `IShortTermMemory` (旧 `ISlidingWindowMemory`、リネーム検討は別 issue) を
そのまま使う。`RollingSummaryShortTermMemory` は同じ interface を満たす別実装。

```python
class IShortTermMemory(ABC):
    def append(self, player_id: PlayerId, entry: ObservationEntry) -> None: ...
    def append_all(self, player_id: PlayerId, entries: List[ObservationEntry]) -> List[ObservationEntry]: ...
    def get_recent(self, player_id: PlayerId, limit: int) -> List[ObservationEntry]: ...
```

### 8.2 拡張点

rolling 実装は加えて以下を持つ:
- `get_mid_summary(player_id) -> List[L4Entry]` — prompt 表示用
- `get_long_summary(player_id) -> L5Entry | None` — prompt 表示用

prompt_builder 側は `isinstance` で分岐するか、`IShortTermMemory` に
optional method を足すか、別 port にするかを Phase 1 着手時に決定する。

### 8.3 LLM 生成 port

```python
class IRollingSummaryCompletionPort(Protocol):
    def complete_mid_summary(
        self,
        *,
        player_name: str,
        persona_block: str,
        role: str,
        raw_observations: List[ObservationEntry],
        previous_l4: Optional[L4Entry],
    ) -> L4Entry | None: ...

    def complete_long_summary(
        self,
        *,
        player_name: str,
        persona_block: str,
        previous_l5: Optional[L5Entry],
        evicted_l4: L4Entry,
    ) -> L5Entry | None: ...
```

失敗時は None を返す = template fallback に縮退。

---

## 9. メトリクスと検証

PR #371 で追加した trace event を活用:

| 観測したい指標 | 取得元 |
|---|---|
| section 別 token (chars) | `PROMPT_SECTION_BREAKDOWN.{system,objective,recent_events,recall,...}_chars` |
| prefix cache 効率 | `llm_call.cached_tokens / prompt_tokens` |
| L4 1 件あたりサイズ | (新 trace event 追加検討: `ROLLING_SUMMARY_WRITTEN.l4_chars`) |
| L4 生成 latency | (新 trace event: `ROLLING_SUMMARY_LATENCY_MS`) |
| L4 生成失敗率 (template fallback) | (新 trace event: `ROLLING_SUMMARY_FALLBACK`) |

Phase 3 (計測 & tune) で:
- raw 件数 (15 → 10 or 20)
- L4 保持世代数 (3 → 5)
- prompt 表示の文体

を A/B 取って決める。

---

## 10. リスクと検討事項

### 10.1 LLM 生成失敗の連鎖

L4 生成が連続で失敗 → template fallback 連発 → 「raw 連結」が L4 として
表示され続ける = sliding window と等価になる。

対策:
- template fallback 時も `compressed_activity` の代わりに raw を圧縮表示する
  (例: 「直近 15 ターンの観測ログ (要約失敗中)」)
- 連続失敗を loop_guard 的に検知して trace で警告

### 10.2 中期 → 長期の伝播でアイデンティティが drift する

毎回 L5 を「previous_l5 + evicted_l4」で書き直すと、世代を経るたびに性格が
変わるリスク。

対策:
- L5 生成プロンプトに「**性格 (persona) は previous_l5 のものを保つ。
  揺れるのは事実認識のみ**」を強く書く (4.2 のテンプレに既に入れた)
- persona_block を常に併載

### 10.3 prefix cache の section 順入替で行動精度が落ちる可能性

Lost-in-the-middle 緩和が逆方向に出る可能性がある (具体的には §1 objective
が末尾でなくなると LLM が目的を忘れる、など)。

対策:
- Phase 0 (section 順入替) は **scenario config で順序切替できる** ように作る
- 実験 #25 後続で旧順序と新順序を A/B 取って判定

---

## 11. 完了の定義

- [ ] Phase 0: section 順入替で `cached_tokens / prompt_tokens` の中央値が
  現状から有意改善 (目標: 0.0 → 0.3+)
- [ ] Phase 1: L4 生成 latency p95 < 5s、失敗率 < 5%
- [ ] Phase 2: L5 が 5 世代を経ても persona が drift しない (eyeball 確認)
- [ ] Phase 3: 同シナリオ条件で sliding window と rolling summary の行動
  品質スコアが同等以上

---

## 12. 参考研究

- **Generative Agents** (Park et al. 2023): observation → importance score →
  reflection (LLM 抽象化) の階層。本設計の L4/L5 は reflection の影響を受けている
- **MemGPT** (Packer et al. 2023): OS-paging 風の階層メモリ。LLM が tool で
  working memory を管理する設計は active retrieval (semantic plan) に近い
- **ReadAgent** (Lee et al. 2024, Google): gist memory。L4 の compressed_activity
  に相当する概念
- **Lost in the Middle** (Liu et al. 2023): 長文 prompt の attention 偏り。
  section 順入替の根拠
- **HippoRAG** (Gutiérrez et al. 2024): 海馬風 PageRank 想起。既存の memory link
  spreading activation と近い
