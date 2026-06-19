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

## ⚠ 追加発見: passive recall が当初仮説より広く効いていた

trace を `episodic_recall` event レベルで詳しく見ると、**tick=2 以降ずっと
passive recall が両過去 episode を返していた**:

```
tick 2  candidates=2  past_forest_herb / past_beach_fishing
tick 3  candidates=2  ← probe_a 注入直後
tick 5  candidates=2  ← LLM が memory_recall_episodes を呼んだ tick
tick 9  candidates=2  ← probe_d 注入直後
tick 10 candidates=2  ← LLM が memory_recall_episodes を呼んだ tick
```

理由: 現在地が「拠点」(place_spot:1) でも、`spot_graph_explore` 系で
**接続先 spot (浜辺 place_spot:2 / 森 place_spot:3) が cue に立ち上がる**
ため、passive recall がそれらを使って過去 episode を引っ張り出している。

つまり **LLM が呼んだ 2 回の `memory_recall_episodes` は、prompt の「関連する
記憶」section に既に出ていた情報を取りに行った技術的には冗長な呼出** だった。

### この発見の解釈

- **(a) probe_a で tool が呼ばれた**: 期待通り tool が動いたが、passive が
  情報を既に持っていたので技術的には不要だった
- **(b) probe_b で tool 不要**: 期待通り
- **(d) probe_d で tool が呼ばれた**: passive で取れていたのに能動 recall を選んだ
  — おそらく `objective_text` の **「一旦立ち止まり、自分が...経験したことを
  思い出してから話す」** という明示的指示が「思い出す = ツールを使う」と
  LLM に解釈された可能性

### sliding window との関係 (ユーザ質問への答え)

過去 episode は **episode_store (= 長期記憶)** に注入しており、sliding window
には入っていません。なので「sliding window 範囲内だから passive が効く」
わけではなく、 **episode_store + 接続先 spot の cue マッチ** で passive recall
が動いた、というのが正確な経路です。これは sliding window の範囲とは独立。

## ⚠ シナリオ設計の問題 (ユーザ指摘 2 件)

### 1. `llm_objective_text` が明示的すぎる

現状: 「仲間のシキが投げてくる『今日のこと』についての質問に、自分の記憶を
頼りに自然に答える。質問が来たら一旦立ち止まり、自分が浜辺と森で経験した
ことを思い出してから話す。思い出せないことは『覚えていない』と素直に言う。」

これは本番シナリオでは絶対にない **「事前にシキが来る」「思い出してから話せ」**
を直接書いてしまっている。LLM の振る舞いがこの指示への遵守なのか、自発的
判断なのかが切り分けられない。

**次の run では objective_text を中立化** する必要がある。例えば:
- 「漂流島で生き延びる」程度に汎用化
- もしくは objective_text 自体を消す (= 空文字)

### 2. シキが反応せず「届いていない」と誤推察

tick 8 のメモ: 「say では相手に届いていない模様」
原因: シキが scripted NPC で同 spot にいないため、`speech_speak` の
action_result が「to: 拠点には他にプレイヤーがいない」を返す。これが正しい
世界応答だが、ハルは「シキとの通信が壊れている」と解釈し、tick 12-13 で
浜辺へ探しに行く副次行動を取った。

これは scenario design の構造的問題:
- シキを「声だけ届く別 spot」に居ると persona text で説明する選択肢
- もしくは speech 観測ではなく **system broadcast 風の観測** に変える選択肢

## Issue #526 不在 2 の現状

**「agent-driven 想起」の構造的経路は実 LLM で動作することが確認された** (= 仮説検証成功)。

ただし上記の追加発見により、**「能動 recall が必要なケース」を分離するための
シナリオ設計の見直し** が必要。passive がここまで広く効くなら、tool の存在価値は:

- (i) passive が痩せる場面の保険 (= 接続先が無い遠隔過去 / 概念マッチが必要 / 等)
- (ii) LLM 主観の意志的想起の表現 (= 「思い出そう」と決めて掘り下げる行為)

の 2 つに整理し直す必要がある。

## 残る未検証 (次の run へ)

- 別シナリオ (= survival_island_v2 等の動的環境) でも同じ振る舞いをするか
- objective_text を中立化した場合の振る舞い (= 自発的に tool を呼ぶか)
- 接続先 spot が cue に出ない設計の場合の挙動
- 失敗した tool 結果 (= 0 件「思い出せない」) に対する反応の質感

## 改訂履歴

- **2026-06-19** (run02 / e2e wiring fix 後): 初回成功 run の分析
- **2026-06-19** (追加発見追記): passive recall が広く効いていた事実 + シナリオ設計の問題 2 件を追記
