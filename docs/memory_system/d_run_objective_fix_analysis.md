# D run 分析: scenario 駆動 objective が物語を変えた (2026-06-13)

PR #454 (max_retries=0) / #455 (objective JSON 駆動) / #456 (system prompt hardcoded 撤廃)
/ #457 (選択的 retry) の集大成検証 run。途中で打ち切ったが、**最も知りたい
ことは既にデータが出ている** ので分析する。

## 0. run の素性

| 項目 | 値 |
|---|---|
| シナリオ | `survival_island_v2.json` |
| 目標 tick | 140 |
| **実際の到達 tick** | **57 (world_tick=122)** |
| provider | DeepInfra fp8 (途中で切替) |
| model | google/gemma-4-31b-it |
| short_term_memory_kind | rolling_summary |
| scheduler_mode | inline (= ブロッキング) |
| section_order | stable_to_volatile |
| episodic | OFF |
| LLM call | 291 |
| L4 生成 | 35 |
| L5 生成 | 23 |
| 完了状況 | **途中打切 (~50min 経過、DeepInfra の遅さで判断)** |

## 1. ⭐ 最大の発見: 「狼煙で救助」が物語の初期から駆動した

C run v3 (PR-A/B/C 前) では **200 tick 走破中、誰一人として狼煙台に向かわなかった**。
廃屋探索と物資収集ループに陥り、全員 DEAD で run 終了。

D run では **tick 4-5 (= シナリオ開始直後)** で既に狼煙が L4 unresolved に出ている:

### L4 サンプル (tick=4-5, run 開始直後)

```
[tick=4 pid=1 エイダ]
activity: ノアが火打ち石を、リオがナイフとロープを確保した。
          私とカイで流木の山から燃料を回収し、救助に必要な準備を進めた。
unresolved: ['山頂で火を上げるために必要な枯れ葉を確保すること']

[tick=4 pid=3 リオ]
activity: ...流木と火打ち石を確保した。
          現在は救助信号のための狼煙を上げる準備を進めている。
unresolved: ['狼煙に必要な枯れ葉の回収',
             '枯れ葉をどこで探すべきかの特定',
             '山頂への移動と点火']

[tick=4 pid=4 カイ]
unresolved: ['狼煙に必要な「枯れ葉」を確保すること',
             '山頂へ向かうための具体的な経路の特定']

[tick=5 pid=2 ノア]
activity: ...生存のために山頂で狼煙を上げる計画が話し合われた。
unresolved: ['狼煙に必要な枯れ葉を確保すること',
             '枯れ葉をどこで探すべきか決定すること',
             '山頂まで移動して火を上げること']
```

= **シナリオの勝利条件 (狼煙台で救助) が運開始 4-5 tick で 4 player 全員の
L4 に確立**。これは objective が prompt に届いた瞬間に効いた証拠。

### 早期の inner_thought サンプル

```
[tick=4 pid=1] 物資の状況が概ね把握できました。あとは枯れ葉さえ見つかれば、
              狼煙の準備は整います。
[tick=14 pid=2] カイとエイダが食料の話に盛り上がっているが、リーダーとして
                優先順位を明確にする。救助の条件である狼煙の準備が最優先だ。
```

ノアが**「リーダーとして救助を最優先」** と明示的に振る舞っている。persona が
保たれつつ、scenario の win condition と整合した行動選択がなされている。

## 2. キーワード浸透の定量比較

### L4 / L5 でのキーワード出現率

| キーワード | L4 (35 件中) | L5 (23 件中) | 解釈 |
|---|---|---|---|
| 狼煙 | 6 (17%) | 3 (13%) | scenario の中核概念が記憶に染み込んだ |
| 救助 | 3 (9%) | **9 (39%)** | L5 (世界観) で最も浸透 |
| 山頂 | 9 (26%) | 5 (22%) | 移動先として認識 |
| 枯れ葉 | 14 (40%) | 0 | L4 短期素材として頻出、L5 では抽象化 |
| 流木 | 17 (49%) | 0 | 同上 |
| 火打ち | 4 (11%) | 1 | 同上 |
| **脱出** | **0** | 3 ※ | **旧 hardcoded 「廃墟脱出」が完全消滅** |
| **廃墟** | **0** | **0** | 同上 |

※ L5 の「脱出」は新たに獲得した語で、「**山頂から狼煙を上げることが
脱出への鍵**」のように「島からの脱出 = 救助」という意味で使われている。
旧 hardcoded「廃墟から外へ脱出する」とは別物 (= LLM が自発的に救助 ≒ 脱出と
解釈した正しい使い方)。

### L5 サンプル

```
[tick=30 pid=2 ノア gen=1]
self_image: 私はこの過酷な環境で生き延びることを最優先とする探索者だ。
            慎重に周囲を観察し、手元の火打ち石という確かな手段を最大限に
            活かして、確実に生存への道を切り拓きたい。
world_view: この島は生存のための資材が点在しているが、同時に未知の危険が
            潜む不安定な場所だ。**山頂から狼煙を上げることが脱出への鍵
            となるため**、今はそこへ至るための準備を整える必要がある。
```

→ scenario の勝利条件が world_view に **構造化された形** で取り込まれている。

C run v3 では 11 世代経っても world_view に「救助」「狼煙」が現れなかった。
D run では gen=1 (= 最初の L5) から既に「狼煙が脱出の鍵」と書かれている。
これは **PR #455 の決定的な勝利**。

## 3. 行動 pattern の変化

### tool 使用比率 (288 actions)

| tool | 件数 | 比率 |
|---|---|---|
| speech_speak | 81 | 28.1% |
| spot_graph_wait | 76 | 26.4% |
| spot_graph_interact | 39 | 13.5% |
| spot_graph_travel_to | 24 | 8.3% |
| spot_graph_explore | 17 | 5.9% |
| memo_add | 13 | 4.5% |
| spot_graph_pickup_item | 12 | 4.2% |
| spot_graph_drop_item | 10 | 3.5% |
| memo_done | 5 | 1.7% |
| spot_graph_use_item | 5 | 1.7% |
| spot_graph_listen | 4 | 1.4% |
| spot_graph_give_item | 2 | 0.7% |

### C run v3 との比較

| tool | C run v3 (200 tick) | D run (122 tick) | 解釈 |
|---|---|---|---|
| speech_speak | 18% | **28%** | 大幅増。役割分担の会話が活発化 |
| spot_graph_wait | 28% | 26% | 同水準 (後期疲労時の wait) |
| spot_graph_travel_to | 16% | 8% | **半減**。無駄移動が減った (狼煙計画が明確) |
| memo_add | 2% | 4.5% | 2 倍。明示的に計画を書き留めるように |
| spot_graph_pickup_item | n/a | 4.2% | 物資収集が「狼煙の素材」として目的化 |

= **「狼煙のために何を集めて誰がどこに行くか」を 4 player が会話で調整する**
パターンに変わった。C run v3 の「無計画に移動 → 疲労 → wait」とは別のゲームに
なっている。

## 4. 性能 (DeepInfra fp8 の課題)

### per-call latency

| | D run (DeepInfra fp8) | C run v3 (Parasail fp8) |
|---|---|---|
| n | 291 | 431 |
| p50 | **7s** | 4.5s |
| p90 | 16s | n/a |
| p99 | 40s | 32s |
| max | 45s | **222s** (retry outlier) |
| mean | 8.9s | n/a |

**outlier (222s) は消えた** (PR #454 max_retries=0 が機能) が、**p50 が 1.5× 遅い**。

### prefix cache

> ⚠️ **訂正 (2026-06-13)**: C run v3 列の「1,802,545 cached / 48.0%」は元 doc の誤り。
> 実 trace を直接読むと C run v3 も `cached_tokens=0 / 0.0%`。
> 詳細: [CORRECTION_cache_hit_was_always_zero.md](CORRECTION_cache_hit_was_always_zero.md)。
> → 「DeepInfra で cache が消えた」という結論は誤りで、**全 run で cache hit は最初から 0%** が正しい。

| | D run | C run v3 (訂正後) |
|---|---|---|
| 総 prompt tokens | 2,818,115 | 3,751,641 |
| 総 cached tokens | 0 | ~~1,802,545~~ → **0** |
| **cache hit rate** | 0.0% | ~~48.0%~~ → **0.0%** |

= **OpenRouter 経由では (provider に関わらず) `cached_tokens=0` で返ってくる**。
DeepInfra 固有の問題ではなく、構造的な問題。per-call latency 増加の主因と
していたが、C run v3 と同じ条件なので **latency 増加の主因は別** (DeepInfra
endpoint 自体の per-call latency が長いこと)。

### cost

| | D run | C run v3 |
|---|---|---|
| 総 cost | $0.38 | $0.42 |
| call | 291 | 431 |
| **cost / call** | **$0.00130** | $0.00097 |

D run は **call あたり 34% 高い**。cache がないため input token を毎回フル課金。

### wall_time

- D run: 57/140 tick で打切 (~50min 経過、ETA 残 70min+) = 全体 **~120min** 予測
- C run v3: 200 tick 完走で **43min**
- = **2-3 倍遅い** (= 「使い物にならない」)

主因:
1. DeepInfra per-call latency 自体が長い (p50 7s vs 4.5s)
2. **prefix cache が無い** → 毎回 12k token をフル処理
3. inline scheduler の同期ブロッキング (これは Parasail でも同じ条件)

## 5. 残った物語的課題

PR #455 で大半は解決したが、データの 50% 地点までで残る課題:

### 5.1. 「狼煙への執着」が中盤で薄れる

L4 では「狼煙に必要な枯れ葉」が tick=4-17 で頻出するが、L5 が育つにつれて:

```
[player 1 tick=120 gen=6]
world_view: この島は協力して基盤を築ける場所だが、物資の不足が生存を直接的に
            脅かす厳しい環境だ。... 確実に物資を揃えなければならない不安定
            な場所である。
```

= 「物資を揃える」が中心になり、**「狼煙→救助」が後ろに退いている**。

これは **動的階層計画 (Plan tier) の不在** が露呈した部分。中期目標
(current_strategy) を保持する layer がないので、L5 の reflect で「いま注力
していること = 物資収集」に world_view が引き寄せられる。

→ [research_threads/dynamic_hierarchical_planning.md](../research_threads/dynamic_hierarchical_planning.md)
の問い「Plan tier が必要か」への答えは **YES、必要**。

### 5.2. 後期の wait 連打

tick 81+ で疲労 100 / 空腹 80+ になり、wait しかできない:

```
[tick=81 pid=1] 空腹と疲労が81に達しましたね。医師として、この数値は意識
                混濁やショック状態を招く極めて危険な領域です。... 死んで
                しまえば、救助されること...
[tick=102 pid=2] 疲労が100……。... もう一度実を確保し、少しでも気力を繋ぐ。
                リーダーとして、ここで脱落することは許されない。
```

= 認識はあるが物理的に動けない。これは scenario design + Plan tier 双方の
問題。「6 日目までに狼煙を上げる」という時間制約を中期目標として保持して
いれば、4-5 日目で山頂への移動を始めただろう。

### 5.3. 山頂への実際の移動なし (途中打切で確認できず)

122 world_tick まで進んだ範囲では誰も summit に到達していない。L4/L5 では
「山頂へ向かう」が unresolved に出続けたが、実行段階に至らなかった。

これも Plan tier 不在の症状。「次の数 tick で何をする」(L4.next_steps) が
明示的に prompt に乗らないため、毎ターン LLM が状況に流されて wait/explore を
選び続けてしまう。

## 6. 結論

### ⭐ PR #454/455/456/457 は本来の目的を達成した

| 項目 | 旧 (C run v3) | 新 (D run) |
|---|---|---|
| 狼煙が L4 に出る | 0 件 | 6 件 (run 開始直後から) |
| 救助が L5 に出る | 0 件 | **9/23 (39%)** |
| 廃墟脱出の混入 | 残留 | **0** |
| 物資収集の目的性 | ループ化 | 「狼煙の素材」として目的化 |
| リーダーシップ | 弱い | ノアが救助フローを牽引 |
| 222s outlier | あり | **無し** (max 45s) |
| timeout 効果 | 名ばかり | 実効上限 ≈ self._timeout_seconds |

### ⚠️ 残課題

1. **DeepInfra fp8 は使えない**: per-call 7s + cache 0% で wall_time 2-3 倍
   → 次は Parasail fp8 に戻して E run
2. **Plan tier が要る**: L5 後半で狼煙への執着が薄れる → L4.next_steps /
   L5.current_strategy の導入を検討
3. **inline scheduler のブロッキング**: thread_pool で E run 試す

### 次の手

| 優先 | 内容 |
|---|---|
| ⭐⭐⭐ | **E run**: Parasail fp8 + `SHORT_TERM_MEMORY_SCHEDULER_MODE=thread_pool` で同条件再走。cache 復活 + 非同期化の合わせ技で wall_time を測る |
| ⭐⭐⭐ | **F run (Plan tier 仮実装)**: L4 に `next_steps` 追加 (最小実装) して E run 比較。docs/research_threads/dynamic_hierarchical_planning.md の問いに empirical 答え |
| ⭐⭐ | scenario の「6 日目までに」という時間制約を objective_text に明示できているか再確認 (現状 4日目/6日目/7日目は書いてあるが、LLM が tick→日変換できているか) |
| ⭐ | cache hit が消えた件 = DeepInfra 構造的問題。実験 default を Parasail に固定する判断 |

---

実験日: 2026-06-13
担当: Motifman + Claude Opus 4.7
関連 PR: #454 / #455 / #456 / #457
関連 doc: [research_threads/dynamic_hierarchical_planning.md](../research_threads/dynamic_hierarchical_planning.md)
状態: **途中打切 (57/140 tick, world_tick=122)**。データ価値は十分。
