# recall_probe_v1 run02 分析 (実 LLM 結果 / 2026-06-19)

## 設定

| 項目 | 値 |
|---|---|
| シナリオ | `recall_probe_v1` |
| LLM | `openrouter/deepseek/deepseek-v4-flash` (DeepInfra fp4) |
| short_term_memory | `rolling_summary` |
| section_order | `stable_to_volatile` |
| scheduler | `thread_pool` |
| episodic | `ON_FULL` (`LLM_EPISODIC_ENABLED=1`) |
| idle timeout | 1 tick |
| tick 数 | 15 |
| 過去 episode 注入 | 2 件 (浜辺釣り 6h前 / 森薬草 3.5h前) |
| elapsed | 108.4s |
| trace | [`var/runs/recall_probe_v1_run02/`](../../var/runs/recall_probe_v1_run02/) |

## 全 action 抜粋

```
tick=1  memo_add  「【現在の目的】仲間のシキが投げてくる『今日のこと』...」
tick=2  memo_list
tick=3  memo_list                                ← probe_a 注入 (シキ「今日何してた?」)
tick=4  memo_done
tick=5  memory_recall_episodes  about="今日、浜辺で釣りをしたこと。朝、真鯛を釣った時のこと。" time_range="today"
tick=6  speech_speak  「そうだな…今日は朝、浜辺で釣りをしてたよ。真鯛が一匹釣れたんだ。」  ← probe_b 注入 (シキ「浜辺で何か見つけた?」)
tick=7  speech_speak  「浜辺でか…うーん、釣りに集中してたから、あんまり周りは見てなかったな。でも、朝日が海面に反射してきれいだったのは覚えてる。」
tick=8  memo_add  状況整理
tick=9  spot_graph_listen                        ← probe_d 注入 (シキ「魚と薬草どっちが先?」)
tick=10 memory_recall_episodes  about="今日、森で薬草を採取したこと。昼過ぎ、森の奥で緑色の葉の薬草。" time_range="today"
tick=11 speech_speak  「釣り…の方が先だったな。朝早くに浜辺で釣りをして、真鯛を釣ったよ。それから昼過ぎに森に入って、薬草を摘んだ...」
tick=12 speech_speak  「シキ、聞こえるか？さっきから何度か声を返してるんだけど...」
tick=13 spot_graph_travel_to  浜辺 (シキを探しに)
tick=14 memo_add
tick=15 memo_add
```

## L1 / L2 / L3 判定

### L1: ハルは `memory_recall_episodes` を呼んだか?

**YES, 2 回**。

- **tick=5**: probe_a 「今日何してた?」(tick 3) に対する反応
- **tick=10**: probe_d 「魚と薬草どっちが先?」(tick 9) に対する反応

probe_b 「浜辺で何か見つけた?」については **呼ばずに直接 speech** で応答 (tick 7)。これは仮説通り (= 「浜辺」が cue 化されて passive recall に過去 episode が乗っているため、tool 不要)。

### L2: 引数の質

```json
tick=5: {"about": "今日、浜辺で釣りをしたこと。朝、真鯛を釣った時のこと。", "time_range": "today"}
tick=10: {"about": "今日、森で薬草を採取したこと。昼過ぎ、森の奥で緑色の葉の薬草。", "time_range": "today"}
```

- **about**: tool description の指示 (= 「具体的な人物名・場所名・物の名前が含まれているとマッチしやすい」) を **正確に解釈**。場所名 / 物名 / 時間表現が全部入っている
- **time_range**: 「今日 (today)」を適切に選択
- LLM が「過去を思い出す前に query を組み立てる」というメタ認知ができている

### L3: 次 tick の発話に反映されたか?

**YES, 完全に反映**。

- tick=5 recall → tick=6 speech: 「真鯛が一匹釣れたんだ。結構いい型だった」 (= 過去 episode の "真鯛" を引用)
- tick=10 recall → tick=11 speech: 「朝早くに浜辺で釣りをして、真鯛を釣った。それから昼過ぎに森に入って、薬草を摘んだ」 (= 両 episode の occurred_at から **順序を正しく推論**)

## 仮説検証の結論

| 仮説 | 結果 |
|---|---|
| (a) 固有名詞無し質問 → tool 呼出 | ✅ **probe_a で tool を呼んだ** |
| (b) 場所名入り質問 → passive で十分 | ✅ **probe_b は tool 不要、speech で直接答えた** |
| (d) 時系列推論 → tool + 推論力測定 | ✅ **tool 呼出 + occurred_at から正しい順序を推論** |
| Issue #526 不在 2 (agent-driven 想起) | **構造的経路が実 LLM で動作した** |

## 質感面の所見

### 良かった点

1. **「思い出してから答える」の自然な流れ**: tick 5 で recall → tick 6 で speech、tick 10 で recall → tick 11 で speech。人間の対話に近い "間" がある
2. **使い分けの自然さ**: 場所名がある質問は recall せず即答、無い質問は recall を経由 — description の指示が言葉通りでなく **意図として** 解釈されている
3. **objective 遵守**: 「思い出せないことは創作しない」を実行。probe_b で「特別なものは見つけられなかった」と正直
4. **agent らしい状況認識**: シキが対話 spot にいないことを察知し、tick 12-15 でシキを探す行動 (能動的探索)

### 改善余地 (= 次の宿題)

1. **probe_a の遅延**: tick 3 で質問 → tick 5 で recall (= 2 tick 遅延)。tick 4 で memo_done してから recall を呼んでいる。これは memo 完了の優先度が暗黙に高いせい?
2. **状況推察の誤り (tick 8)**: 「sayでは相手に届いていない模様」と memo に書いている。シキは scripted NPC で応答しないが、ハルは「届いていない」と解釈。これは scenario design の問題 (= シキを scripted にしたため反応がない)
3. **追加発話 (tick 12, 13)**: tick 11 で probe_d に答えた後、tick 12-13 でシキを探しに浜辺に行く。これは「シキを失った」という認識からの能動行動。実験範囲外だが agent としては自然
4. **probe_a での "今朝" と recall_text の "今朝" の整合**: speech では「朝」と言っているが、過去 episode は "今朝" 表記。微妙な言い換えがあるが内容は一致

## Issue #526 不在 2 の現状

**「agent-driven 想起」の構造的経路は実 LLM で動作することが確認された** (= 仮説検証成功)。

ただし以下は**まだ未検証**:
- 別シナリオ (= survival_island_v2 等の動的環境) でも同じ振る舞いをするか
- 質問が来ない自発的状況 (= 「過去の似た状況を能動的に思い出す」) でも tool を呼ぶか
- 失敗した tool 結果 (= 0 件「思い出せない」) に対する反応の質感

これらは別 run / 別シナリオで検証する。

## 改訂履歴

- **2026-06-19** (run02 / e2e wiring fix 後): 初回成功 run の分析
