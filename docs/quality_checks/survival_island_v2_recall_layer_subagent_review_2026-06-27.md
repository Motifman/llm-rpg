# 無人島シナリオ × 想起階層 ON — subagent 4 体レビューの合成と次の宿題 (2026-06-27)

PR #596 で記録した初観察結果に対し、4 体の subagent (silent-failure-hunter ×2 / general-purpose ×2) に「公平に厳しく」trace を読ませた追加分析。意見をマージしつつ、最重要の宿題 (LLM の tool 名 typo 救済) を私の追加調査で深掘りした記録。

## 1. Player 3 沈黙の根因 (silent-failure-hunter agent 1)

「INVALID_DESTINATION_LABEL の reschedule 漏れ」が私の初回観察だったが、subagent はより深い真因を見つけた。

### 真因 (確度: 高)

- tick 34 に **`monster_attacked_player`** event で `target_incapacitated=true` が p3 に届いている (野犬被害の続き)
- これにより `PlayerStatusAggregate._is_down = True` になり、以降 `_WorldLlmTurnTrigger._can_player_act(3)` が **永続的に False** を返す
- 観測は届き続けて `schedule_turn` も呼ばれるが、`run_scheduled_turns` の `to_run` フィルタで `_can_player_act = False` のため除外され続ける

### 副次原因

- `_handle_travel_to` (runtime_manager.py:1578) は `INVALID_DESTINATION_LABEL` を返すとき `should_reschedule=True` を **設定していない**
- `_RESCHEDULE_ERROR_CODES` には `INVALID_DESTINATION_LABEL` が入っているのに、ハンドラ側で `should_reschedule_for_next_tick()` を呼ばずに DTO を素で構築している
- 結果、reschedule policy が定義されていても **配線が断たれている**

### 修正案

1. `_handle_travel_to` の DTO 構築で `should_reschedule=should_reschedule_for_next_tick(...)` を呼ぶ (副次原因の解消)
2. `is_down` プレイヤーを `pending_player_ids` から discard する (= 真因の解消、または revive 経路の設計)
3. `is_down` からの自然回復 / 仲間による救助経路の追加 (= シナリオ設計レベル)

---

## 2. 協力プレイの質感比較 (general-purpose agent 2)

### 件数で見た変化

| 協力タイプ | X (baseline) | Y (想起階層 ON) |
|---|---|---|
| 依頼 / 分担 | 47 | **63** (+34%) |
| 計画提案 | 44 | **62** (+41%) |
| 自状況報告 (空腹/疲労/HP) | 22 | **44** (+100%) |
| 所持報告 | 32 | 25 |
| 拒否 / 反対 | 2 | **6** (+200%) |
| 物資受け渡し | 5 | **10** (+100%) |
| 共在 tick (≥2 人同 spot) | 112 | 126 |

### 質的観察

- 想起階層 ON で「**物資トポロジの記憶**」が安定: 「誰が何を持っているか」を踏まえた発話・受け渡しが増えた
- 終盤 (tick 134-) で「動けないなら火打ち石を持つエイダが擦れ」「無理だ、休もう」という、互いの状態を踏まえた呼びかけと反対が成立
- 物理的協力 (= 同 spot で同作業) の総量は微増のみ。**変化したのは「誰が何を持つか」の記憶密度** であり、joint action 自体は増えていない

---

## 3. 想起階層は本当に行動を変えたか (general-purpose agent 3 — 厳しい判定)

agent 2 と一見矛盾する結論。subagent 3 は「効いていない反証」を探す role で見たため、より厳しい。

| 質問 | 判定 | 根拠 |
|---|---|---|
| Q1: recall → 次行動への反映 | **効いていない** | recall_chars 平均 1230 字消費、prompt に乗るが inner_thought は直近 observation のみ参照 |
| Q2: afterglow → handle 再呼出 | **完全に効いていない** | afterglow entries 累計 3106 件、再呼出は trace 全体で **0 件** (Y 全体で recall_by_handle 2 件のうち afterglow 経由が無い可能性) |
| Q3: L4/L5 summary → 行動変化 | **効いていない** | tick 27 の L5「医師として慎重に観察」生成後も `explore`/`travel_to` を漫然と継続 |
| Q4: slot 滞在 episode は活用された? | **逆効果** | 同 episode が 15 tick 連続 top に固定、recall が `gather_dry_leaves` 4 連続失敗を **強化** |
| Q5: habituation | **部分的** | penalty 値が 3-4 で頭打ち、4 候補中 3 が tick 30-33 固定 |

### 設計の弱点

- **recall ranking が positive narrative を優先**: UNSUPPORTED_TOOL や precondition 失敗のような agent が真に学習すべき **negative episode を recall に乗せられない**
- **afterglow → handle 経路がほぼ dead code**: prompt に見出しは載るが、LLM がツールで引き戻す動機が弱い設計

### agent 2 と agent 3 の判定の食い違いをどう読むか

両方とも正しい:
- **発話の密度・幅は確かに変化した** (agent 2)
- ただし **行動の質的変化 (失敗を学習する / loop を抜ける) は起きていない** (agent 3)

= 「会話を上手にする想起階層」になっており、「行動を改める想起階層」にはまだなっていない。**recall ranking で failure episode を重み付けする** 改修が次の検証ポイント。

---

## 4. silent failure 網羅 sweep (silent-failure-hunter agent 4)

### Required action (修正に値する)

| ID | 内容 | 重要度 |
|---|---|---|
| **SF-1** | 疲労 100 で `spot_graph_wait` を 40+ tick 連続発行しても回復しない / フィードバックも無い | 高 |
| **SF-2** | `spot_graph_give_items` (複数形) が `RESOLVER_DISPATCH_MISSING` を返す。tool schema には載っているのに resolver 未実装。Y t51 で発生 | 高 |
| **SF-3** | `ITEM_NOT_CONSUMABLE` が同一文面で繰り返し返るがヒント無し。Y player 1 で 4 回繰り返し | 中高 |
| **SF-4** | 無効な destination_label への travel 連続失敗。recall_layer 有でも改善せず | 中高 |

### Observation (記録のみ)

- **OBS-1**: LLM が学習データから `spot_graph_gather` / `spot_graph_harvest` を **想像**して呼ぶ (Y player 4 で 4 件)
- **OBS-3**: ナイフを give した後も自分でナイフを使おうとする (X player 2 で 8 回)
- **OBS-4**: 「枯れ葉は既に集めた、風を待て」を 7 回繰り返す (Y player 2)
- **OBS-5**: 自己観察「魚焼きアクションだった」と気付いても次 tick で同じ失敗

→ 全体的に「**失敗から学ぶ経路**」が agent に届いていない。recall ranking の failure 重み付け (3 の指摘) と同型の問題。

**SF-2 (`give_items` RESOLVER_DISPATCH_MISSING) は要確認**: PR #591 で `targets` / `resolver_targets` に追加したはずなので、trace の error_code が私の修正前の状態を反映している可能性。要 cross check。

---

## 5. 私の追加調査: LLM tool 名 typo 救済

### typo の頻度

| run | typo 件数 | total actions | 割合 | typo の中身 |
|---|---|---|---|---|
| X (baseline) | **0** | 448 | 0.0% | — |
| Y (想起階層 ON) | **5** | 412 | **1.2%** | `spot_graph_gather` ×2 / `spot_graph_harvest` ×2 / `speech_speech` ×1 |

X で 0 件、Y で 5 件は意外な発見。仮説:
- 想起階層 ON で prompt が膨らみ (recall_chars 平均 1230 字 = 全体の 5-10%) LLM の精度が落ちた
- 想起階層 ON で行動の幅が広がり、未存在 tool を「想像する」頻度が増えた

### 既存救済機構の調査

- `_RESCHEDULE_ERROR_CODES` に `UNSUPPORTED_TOOL` は **入っていない** (`dtos.py:13-18`)。typo した agent は `should_reschedule=False` で 起床せず、Player 3 沈黙と同型構造に化ける
- `_execute_tool` の error message は `"未対応のツールです: {name}"` の 1 行のみ。**修正ヒントもバリッド tool 一覧もない** (`runtime_manager.py:1514-1520`)
- 既存の fuzzy match / suggestion 機構は **存在しない**

### fuzzy match の効きを実測

`difflib.get_close_matches` で計測:

| typo | top match (cutoff=0.5) | 救えるか |
|---|---|---|
| `speech_speech` | `speech_speak`, `speech_whisper` | ✅ 救える |
| `spot_graph_pickup` (短縮) | `spot_graph_pickup_item` | ✅ 救える |
| `spot_graph_gather` (想像) | `spot_graph_wait`, `spot_graph_interact`, `spot_graph_listen` | ❌ 関連性低 |
| `spot_graph_harvest` (想像) | `spot_graph_travel_to`, `spot_graph_wait` | ❌ 関連性低 |
| `say` (極短縮) | (none) | ❌ |

→ fuzzy 単独では **想像由来の typo を救えない**。3 層救済が筋。

### 救済設計案 (PR-I 候補)

**3 層構造**:

1. **fuzzy suggestion** (`difflib.get_close_matches`): cutoff=0.6 で「もしかして 'X' を呼びたかったですか?」を message に追記
2. **valid tool 一覧の併記**: 「現在使える tool: <カテゴリ別リスト>」を message に必ず含める。長くなるが LLM が次 tick で正しい tool を選び直せる
3. **`UNSUPPORTED_TOOL` を `_RESCHEDULE_ERROR_CODES` に追加**: typo した tick の agent を次 tick で起床させる

実装スケッチ (`runtime_manager.py:_execute_tool`):
```python
if handler is None:
    valid = sorted(self._tool_handlers.keys())
    suggestion = self._closest_tool_name(name, valid)  # difflib
    hint = f" もしかして '{suggestion}' ですか?" if suggestion else ""
    tools_list = ", ".join(valid)
    return LlmCommandResultDto(
        success=False,
        message=f"未対応のツールです: {name}。{hint} 現在使える tool: [{tools_list}]",
        error_code="UNSUPPORTED_TOOL",
        should_reschedule=True,  # 次 tick で agent に修正させる
    )
```

(+) `dtos.py` の `_RESCHEDULE_ERROR_CODES` に `"UNSUPPORTED_TOOL"` を追加

### この救済の限界

- recall ranking で failure を強調しない限り、LLM は **同じ typo を再発する** リスクあり。「次 tick で修正」は救うが「学習」は別問題
- valid tool 一覧を message に毎回入れると **prompt cache 親和性が下がる** 可能性 (= 失敗の度に prompt 末尾が変動)。トレードオフ評価が要る
- 想像由来 (`gather` / `harvest`) は fuzzy では救えない。これは **シナリオ側で `gather_shellfish` / `harvest_leaves` のような action_name で interact 経由で表現する** のが現状の設計。LLM への「`spot_graph_interact(action_name=...)` で表現してください」hint が message に必要かも

---

## 6. 次の宿題まとめ (優先順位順)

| 優先 | 内容 | 関連 | 想定 PR |
|---|---|---|---|
| **A** | `should_reschedule_for_next_tick()` を `_handle_travel_to` 等で実際に呼ぶ (= reschedule policy 配線断 fix) | Player 3 沈黙 / typo 救済 | PR-I |
| **B** | `UNSUPPORTED_TOOL` を `_RESCHEDULE_ERROR_CODES` に追加 + fuzzy match suggestion + valid 一覧 | typo 救済 | PR-I |
| **C** | `is_down` プレイヤーを `pending_player_ids` から除外 + 回復経路の設計 | Player 3 沈黙の真因 | 別 PR |
| **D** | recall ranking で failure episode を重み付け (= negative experience の学習) | 想起階層が行動を変えない問題 | 別 PR |
| **E** | `spot_graph_wait` の result_summary に状態変化を含める (SF-1) | 疲労 100 sleep loop | 別 PR |
| **F** | `give_items` resolver の実装または schema 撤去 (SF-2) | tool catalog 矛盾 | 別 PR |

A + B は同 PR でまとめるのが筋 (= reschedule policy 配線統一 + tool typo 救済)。C-F は別建てで段階的に。
