# survival_island_v2 × 想起階層 ON 初観察実験 — 2026-06-27

PR-F (#593) / PR-G (#594) / PR-H (#595) で snapshot 拡張 + fail-fast を入れた直後の、想起階層 (slot + afterglow + recall_by_handle tool + habituation) を survival_island_v2 で初めて走らせた記録。

## 走行条件

- シナリオ: `data/scenarios/survival_island_v2.json` (4 player / 14 day = 140 driver tick)
- モデル: `openrouter/deepseek/deepseek-v4-flash` (DeepSeek 公式 provider routing)
- LLM 並列度: 4
- short-term memory: `rolling_summary`
- prompt section: `stable_to_volatile`
- snapshot: 取らない (= 単発 140 tick で完走)

| Run | episodic | slot | afterglow | habituation | recall_by_handle tool |
|---|---|---|---|---|---|
| **X (baseline)** | OFF | — | — | — | — |
| **Y (想起階層 ON)** | ON_FULL | ON | ON | ON | ON (自動配線) |

## 結果サマリ

| 指標 | X (baseline) | Y (想起階層 ON) |
|---|---|---|
| outcome | TIMEOUT | TIMEOUT |
| elapsed | 635 秒 | 650 秒 (+2.4%) |
| total actions | 448 | 412 (-8%) |
| memo_add / done | 31 / 27 | 23 / 13 |
| 協力イベント (speech+give) | 99 | 109 |
| **memory_recall_by_handle 呼出** | (n/a) | **2** |
| **L4 (mid summary) 発火** | (n/a) | 56 |
| **L5 (long summary) 発火** | (n/a) | **44** ← 実走で初観測 |
| episodic_chunk_written | (n/a) | 129 |
| episodic_recall events | (n/a) | 412 |
| cache_hit_pct | 67.0% | 63.7% |
| LLM p50 latency | 2247ms | 2447ms |
| LLM p95 latency | 4016ms | 3799ms |
| LLM max latency | 56.7s (cold start 1 件) | 5.4s |
| decode stall (>60s) | 0 | 0 |

Y 固有の想起階層メトリクス (per-tick 平均):

- candidate_count_mean: **3.40** (recall_probe Run D は 1.77)
- recall_chars_mean: **1230** (Run D は 415)
- slot_size_mean: 3.40 (capacity N=4 の中で安定)
- afterglow_size_mean: **7.54** / max: 10 (= 上限 M=10 に張り付く)
- slot_evicted entries: 220
- weak_recall entries: 2886

→ survival_island_v2 は recall_probe より遥かに多くの episode を生成するので、recall section が大幅に太る (240 字 → 1230 字)。長走でこれが prompt cache にどう効くかは別途検証要。

## 質感観察

### 1. memo の使い方 (X / Y 共通)

Player は memo を「**時刻 + 場所 + 物資状況**」の構造的 dump として使う:

> 【現状整理】狼煙必要物資: 流木 (確保済み) + 枯れ葉 (未確保) + 火打ち石 (リオ所持) / 救助チャンス: Day4, Day6, Day7 の 3 回

> Day1 22:00 拠点。焚き火はついた (リオが火打ち石で着火)。狼煙用物資: 流木 (俺), 枯れ葉 (リオ), ...

memo は agent の Plan-tier に相当する。X (baseline) のほうが書き込みが多く (31 vs 23)、Y は memo の代わりに想起階層が記憶補助になっている可能性。

### 2. 協力の質感 (X tick 1 エイダ)

initial 自己組織化:

> 「皆さん、まずは自己紹介と現状確認をしませんか。私はエイダ、医師です。船員から聞いた話では、この島の山頂に狼煙台があって、火を灯せば救助を呼べるそうです。ただ必要な物資が 3 種類 — 流木、枯れ葉、火打ち石 — 必要だとのこと。今ここに集まった 4 人で何を持っているか確認したいのですが。」

医師ロールを名乗りつつ「全員で物資を共有しよう」という呼びかけ。X / Y どちらでも 100 件前後の speech イベントが出て、4 人協力ゲームとして成立している。

### 3. recall_by_handle の自発呼び出し (Y tick 74 player 2)

```
[call] tick 74 p2: args={'handle': 'ep_81855a'}
[result] tick 74 p2: success=True | 
  [深い森で野犬に襲われた] 私は深い森の周辺を探っていた。しかし、目立った発見はなかった。
  その隙に野犬に襲われた。最初は 17 時半頃、次は 18 時、さらに 18 時半にも襲われた。
  合計で 45 ものダメージを受けた。HP は危険域まで低下していた。カイとはぐれてしまった。狼...
```

「ぼんやり覚えていた野犬被害の見出し」から本文を引き戻して詳細を再構成している。recall_probe Run D の 1 件 (= 「声が届かなかった」エピソード) と同じく、文脈整合性の高い使い方。

### 4. 発見した silent failure 2 件

#### (a) `speech_speech` tool 名タイプミスが UNSUPPORTED_TOOL

Y tick 後半で生存危機 (疲労 100 / 空腹 94 / 夜) のプレイヤーが、エイダに火打ち石で火を起こすよう必死の発話を試みた:

> 「エイダ、カイ、聞こえるか。もう夜だ。俺は動けないが、お前らも同じだな。地面に流木と枯れ葉は揃ってる。エイダ、お前が火打ち石を持ってるはずだ。手が届くなら、擦ってみてくれ。火がつけば暖が取れて、少しは回復できる。何とか試してほしい。」

LLM が `tool_name=speech_speak` を `speech_speech` と誤って出力。tool dispatch で `UNSUPPORTED_TOOL` に化け、命を救う可能性のあった発話が**世界に届かなかった**。

PR #591 の起動時 fail-fast は handler 不整合は止めるが、LLM 側の typo は捕まえられない。**「LLM の tool 名 typo を fuzzy match で許容する / typo を agent に教える」**が次の改善候補。

#### (b) Player 3 の沈黙 (tick 33 以降一切 action なし)

Y player 3 は tick 33 で `spot_graph_travel_to("干潟への岩道")` が `INVALID_DESTINATION_LABEL` で失敗。それ以降:
- observation は届き続けている (tick 128 まで 99 件)
- LLM ターンが一切起動していない
- physical state は alive のまま

`action_failed_emitter` (PR #225 / #344) が `schedules_turn=True` 観測を生成して LLM を起こし直す責務だが、今回は起きていない。idle_timer も発火しなかった。**もう 1 件の silent failure 候補**。

PR-G の `fallback_used` ログ追加で配線漏れは検出できるが、本件は configuration ではなく **runtime の起床ロジック自体**の問題。別 issue 立てて掘る価値あり。

## 結論

- **想起階層 ON × 実シナリオで初観察成立**: snapshot 配線 (PR-F/G/H) のおかげで blocker なし、L4/L5 発火 + recall_by_handle 自発呼出を初めて実走で確認できた
- **cache hit 67% / 64% で安定**、DeepSeek 公式 provider は vLLM ハードルなし
- **decode stall ゼロ件** (= vLLM 第30回の 608s スパイク問題は再現せず)
- **2 件の silent failure を観察**:
  - LLM tool 名 typo (`speech_speech`) は fuzzy match で救う余地
  - action_failed → 起床経路の取りこぼし (= Player 3 silence)

両方とも今回の PR シリーズ (F/G/H) の対象外で、別の改善候補。

## 次の検証候補

1. Player 3 沈黙の原因 (action_failed_emitter / idle timer の協調) を trace で深掘り
2. LLM tool 名 typo を「最寄り tool 名へ fuzzy match + warning」で救うか議論
3. recall section が 240 → 1230 字に膨らんだ件: prompt cache 効率にどう効くか別途測定
4. 同じシナリオを **複数 run** 走らせて completion (rescue) 到達率を統計化する
