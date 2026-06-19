# recall_probe_v3 run01 詳細分析 (2026-06-19)

## 設定

| 項目 | v1 | v2 | **v3** |
|---|---|---|---|
| シナリオ | recall_probe_v1 | recall_probe_v2 | **recall_probe_v3** |
| llm_objective_text | 「シキの質問に...思い出してから話す」(= 演技指導) | 「漂流島で生き延びる」 | **同じ (= 中立)** |
| connections | 接続あり | 空 | **空** |
| persona | 「あなたは recall_probe 本人」(= デフォルト) | 同左 (= persona_prompt 反映されず) | **「あなたはハル」(= persona_prompt 反映)** |
| player_spawns | ハル のみ | ハル のみ | **ハル + シキ (= NPC)** |
| LLM 制御 | ハル のみ | ハル のみ | **ハル のみ (= runner で シキ 抑制)** |
| 過去 episode 注入 | 浜辺釣り + 森薬草 | 同左 | **同左** |
| LLM | DeepSeek V4 Flash @ DeepInfra fp4 | 同左 | **同左** |
| elapsed | 108s | 56s | **94s** |

設計バグ修正 (= 同 PR): **`escape_game_runtime` の per-player persona builder が `len(player_spawns) > 1` のときにしか走らない** 設計を撤去。1 player 構成でも `persona_prompt` が反映されるように。

trace: [`var/runs/recall_probe_v3_run01/`](../../var/runs/recall_probe_v3_run01/)

## 動作概要

| 軸 | 結果 |
|---|---|
| `memory_recall_episodes` 呼出 | **0 回** (v1 = 2 回 → v2/v3 = 0 回) |
| `speech_speak` 呼出 | **8 回** (= probe 3 つ全てに少なくとも 1 回返答) |
| ハルが自分を「ハル」として認識? | ✅ persona 正しく適用 |
| シキは LLM 制御下で動いた? | ❌ 抑制成功 (= 0 turn) |
| 過去 episode は passive で引かれたか? | **probe 依存** (= 下記) |

## probe ごとの詳細

### probe_a (tick=3): 「今日何してた?」

prompt 内の `episodic_recall` cues:
```
["action:spot_graph_explore", "outcome:success", "place_spot:1",
 "entity:spot_graph_player_2"]  ← place_spot:2/3 無し、過去 episode は cue マッチしない
```

passive recall: **candidates=0** (= 期待通り。passive 痩せ成功)

LLM の応答 (tick 4-5):
```
tick=4: 「ああ、シキ。今日は特に変わったことはなかったな。お前は何か気付いたことあるか？」
tick=5: 「今日は何も見つからなかったよ。お前は？何か気になることあったか？」
```

⚠ **ハルは「何もなかった」と答える hallucination**。実際は浜辺で釣り (6h 前) + 森で薬草 (3.5h 前) があるのに、それを思い出していない。**能動 recall ツールを呼ばなかった** ため、過去にアクセスできず誤答した。

これが Issue #526 の **不在 2 (agent-driven 想起)** の症状そのもの。

### probe_b (tick=6): 「浜辺で何か見つけた?」

prompt 内の `episodic_recall` cues:
```
tick=7: [..., "place_spot:2"]  ← 「浜辺」が cue 化された
candidates: [past_beach_fishing]
```

passive recall: **candidates=1** (= 「浜辺」固有名詞経由)

LLM の応答 (tick 7-8):
```
tick=7: 「ああ、今朝浜辺で釣りをしてたんだ。真鯛が一匹釣れた。お前は何か見つけたのか？」
tick=8: 「そうだ、今朝釣った真鯛が一匹だけ。食料にはなるな。」
```

✅ **正しく応答**。passive recall が「浜辺」cue で過去 episode を引いた → speech に反映。

### probe_d (tick=9): 「魚と薬草、どっちが先に手に入った?」

prompt 内の `episodic_recall` cues:
```
tick=10: [..., "place_spot:2"]  ← 浜辺だけ。森 (place_spot:3) は無い
candidates: [past_beach_fishing]
```

⚠ **`past_forest_herb` は passive に乗っていない**。質問に「薬草」が含まれるが、noun_matcher に「薬草」が item として登録されていない (or 森が cue 化されない) ため。

LLM の応答 (tick 10):
```
「魚だな。今朝、浜辺で真鯛を釣った。薬草はまだ見つけてない。お前は知ってるのか？」
```

⚠ **部分的に誤答**。「魚が先」は正しいが「薬草はまだ見つけてない」は false (= 3.5h 前に森で採取済)。passive にも能動にも引けなかった → 知らないものとして答えた。

## 質感判定: probe 別

| probe | passive 動作 | tool 呼出 | speech 内容 | 結論 |
|---|---|---|---|---|
| (a) 時間質問 | ❌ 候補 0 | ❌ 0 回 | ❌ 「何もなかった」(hallucination) | **能動 recall が要る場面で誰も recall していない** |
| (b) 場所質問 | ✅ 候補 1 (浜辺) | ❌ 0 回 | ✅ 「真鯛を釣った」 | passive で十分 |
| (d) 順序質問 | △ 候補 1 (浜辺のみ) | ❌ 0 回 | △ 「魚が先 / 薬草はまだ見つけてない」 | passive 不完全 + 能動なし → 半端な誤答 |

## ⚠ 重要な発見

### 1. 能動 recall は v1 でしか発火していなかった

| 試行 | 能動 recall | objective_text |
|---|---|---|
| v1 | ✅ 2 回 | 「思い出してから話す」(= 演技指導あり) |
| v2 | ❌ 0 回 | 中立 |
| v3 | ❌ 0 回 | 中立 (persona / NPC 修正済) |

→ **LLM (DeepSeek V4 Flash) は明示的指示なしでは `memory_recall_episodes` を自発的には呼ばない**。これは v1 の「成功」が **演技指導の効果** であり、tool の存在が agent の自発的判断で使われているわけではなかったことを確定する。

### 2. passive 痩せの効果は確認できた

v1 では `connections` 経由で接続先 spot が常に cue に出ていた (= place_spot:2/3 が常時 active)。v2/v3 で `connections: []` にしたら `place_spot:1` (拠点) のみが立ち、過去 episode は質問の固有名詞経由でしか引けなくなった。

### 3. probe_a の hallucination が示す危険

「今日何してた?」のような **時間表現のみで固有名詞無しの質問** に対して:
- passive: 何も引けない (固有名詞 cue 無し)
- 能動 recall: LLM が呼ばない
- 結果: **LLM は「何もなかった」と作り話** で答える

これは **Issue #526 不在 2 (agent-driven 想起)** + **不在 5 (情報源タグ)** の合わせ技で発生する誤動作。recall した結果として「無い」のと、recall しないで「無い」と答えるのは違うが、現状は両者が区別できない。

### 4. 質感面: シキとの自然な対話は成立した

ハルの speech は persona に沿った口調 (「〜だな」「〜したよ」「お前は？」) で、シキとの自然な対話が成立。persona_prompt + シキを同 spot に置くことで「会話の主体」としての identity は確立した。

## Issue #526 不在 2 への直接示唆

**現状の `memory_recall_episodes` tool は LLM 自発的には呼ばれない**。これは:

- (i) tool description が「思い出そうとするときに使う」と書いてあっても、LLM はそれを「使うべきタイミング」として認識しない
- (ii) 「思い出せない」と「無い」を区別する **動機** が無い (= 「無い」と答えても罰されない)
- (iii) passive recall が結果として存在するため、LLM は「与えられた情報の範囲で答える」mode に入りやすい

これを解決するには、tool 呼出を促す仕組みが必要:

1. **system prompt の self-model section**: 「あなたは memory_recall_episodes で過去を能動的に思い出せる」を明示
2. **質問駆動 recall trigger** (= システム駆動の前 PR で議論した B 案): 観測種別 = speech_message + "?" のときに自動 recall
3. **「無い」と答える前に recall を強制する prompt 規範**: agent loop に「過去を確認してから無いと答える」を組み込む

これは Issue #526 の議論を一段深める材料。tool は存在するだけでは「使われない」。

## 改訂履歴

- **2026-06-19** v3 run01: persona + シキ NPC の修正後、tool は依然呼ばれず passive 不在で hallucinate。能動 recall が「演技指導」依存だった事実を確定。
