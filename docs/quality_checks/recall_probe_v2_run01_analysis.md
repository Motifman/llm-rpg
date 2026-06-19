# recall_probe_v2 run01 分析 (中立 objective + passive 痩せ / 2026-06-19)

## 設定

| 項目 | v1 (前回) | v2 (今回) |
|---|---|---|
| シナリオ | recall_probe_v1 | **recall_probe_v2** |
| `llm_objective_text` | 「シキの質問に...思い出してから話す」(= 明示指示) | **「漂流島で生き延びる」** (= 中立) |
| connections | 拠点↔浜辺/森 接続あり | **空 (= 拠点孤立)** |
| LLM / 他設定 | DeepSeek V4 Flash / rolling_summary / thread_pool / stable_to_volatile | 同じ |
| 過去 episode 注入 | 2 件 (浜辺釣り / 森薬草) | **同じ** |

trace: [`var/runs/recall_probe_v2_run01/`](../../var/runs/recall_probe_v2_run01/)

## 仮説 vs 結果

### 仮説

passive を痩せさせれば、LLM は能動 recall を呼ばざるを得なくなる。

### 結果: **仮説は外れた**

| 軸 | 観測 |
|---|---|
| **passive 痩せ?** | ✅ 成功 (= 全 tick で `candidates: 0`)。`place_spot:1` のみが cue として立ち、過去 episode (= spot_id 2/3) は引かれない |
| **`memory_recall_episodes` 呼出** | **❌ 0 回** (= v1 の 2 回から退行) |
| **`speech_speak` 呼出** | **❌ 0 回** (= LLM はシキに返事しない) |

## LLM の振る舞いを inner_thought から読む

```
tick 1: 「私は今、拠点に立っている。深夜だが、まずはこの場所に何があるかしっかり調べよう。流木の屋根、焚き火跡…他に使えるものはないか確認したい。」
tick 2: 「【当面の目標】漂流島で生き延びる。拠点の焚き火跡がある。ハルとシキが根城にしているが今はいない。」
tick 4: 「【現在の場所】拠点（中央）。ハルとシキは今いない。」
```

⚠ **LLM は自分を「ハル」として認識していない**。「ハルとシキは今いない」と
**三人称** で語っている。シキの speech 観測 (= probe_a/b/d) は届いているが、
「自分が質問されている」として処理していない。

その後の行動は **完全に独立した探索者** として振る舞う:
- tick 1, 5-11: `spot_graph_explore` / `spot_graph_listen` / `spot_graph_interact` で拠点を調べる
- tick 12: `spot_graph_travel_to(destination_label="海岸")` — でも `connections=[]` なので移動できない
- tick 13: 「拠点には移動先がなく...膠着状態」memo
- 最後まで recall も speech も呼ばずに終了

## ⚠ 重要な発見: objective_text が「演技指導」として機能していた

v1 の objective_text を read back する:

> 「仲間のシキが投げてくる『今日のこと』についての質問に、自分の記憶を頼りに
> 自然に答える。**質問が来たら一旦立ち止まり、自分が浜辺と森で経験したことを
> 思い出してから話す**。」

これは単なる「目的」ではなく **「シキが来る」「思い出してから話せ」** という
**シナリオの行動規範** を直接書いていた。LLM はこれを **演技指導** として
解釈し、

- 「シキが質問してくる」前提で待ち構える
- 質問を受けたら recall ツールを呼ぶ
- recall 結果を speech に反映する

を実行していた。v2 で objective を「漂流島で生き延びる」に中立化すると、
LLM は **persona block の「あなたはハル」を半分しか取り込めず**、独立した
探索者として振る舞ってしまった。

## Issue #526 の問い直し

v1 + v2 の比較は **「agent-driven 想起」が実 LLM で何によって駆動されるか**
を露わにした:

- **v1**: objective_text の演技指導 → tool 呼ぶ → 結果を発話に反映 (成功)
- **v2**: 中立 objective → 自分を ハル と認識せず → tool も呼ばず speech も無し

**つまり「agent-driven 想起」は LLM が「自分のことだ」と認識する **identity
strength** に強く依存する**。passive 痩せの仮説は当たったが、**「passive が
痩せれば自動で tool を呼ぶ」というのは誤り** だった。**「自分が会話の主体
である」と認識する文脈** が無いと、ツールがあっても呼ばない。

これは Issue #526 の **不在 4 (メタ層)** に直接接続する所見:
- LLM は「自分が今どの役割を演じているか」を毎ターン promptから再構築する
- persona block だけでは弱く、objective text もしくは現在の文脈 (= 相手が居る、
  返事を待っている) からの強い signal が必要
- **「自己の継続性」** (= 不在 0) の欠如がここで実体化している

## 次に試したい変更 (= 仮説のリファインメント)

| 案 | 目的 |
|---|---|
| **(α) persona block を強化** | 「あなたはハルだ。シキはあなたを呼んだら必ず答える関係だ」を persona block に書く。objective には書かない |
| **(β) 「現在地と周囲」section にシキを明示** | 「シキの声が遠くから届いている」を環境記述に乗せて、LLM に「自分は呼びかけられている主体だ」を空間情報として伝える |
| **(γ) NPC として実装** | 当初検討した「シキを control_type=HUMAN で player_spawn に追加」案。同 spot に居れば「現在地と周囲」に自然に出る |

僕は **(γ) が最も自然** だと思います。

理由:
- v1/v2 の振る舞い差は「LLM がコンテキストから役割を読み取れるか」次第
- 役割を読み取る最も自然な signal は **物理的に同 spot に NPC が居ること**
- これは scenario design の問題であり、prompt engineering より構造的解決

## シキ NPC 実装の調査結果 (= 別 PR の宿題)

調査済 (前回コメント):
- `ControlType.HUMAN` enum は存在し、`ObservationTurnScheduler` の gate も既に機能
- ただし escape_game runtime は `_EscapeSpawnAllPlayersLlmResolver` で **全 spawn を LLM 制御**
- Resolver を差し替えれば NPC 化可能 (= 中規模変更、別 PR が適切)

## 改訂履歴

- **2026-06-19**: v2 初回 run の分析。v1 との比較で「objective_text が演技指導として機能していた」発見
