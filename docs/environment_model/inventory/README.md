# 環境とシナリオのモデリングの前に、今のコードがしていることを書き出した記録

環境とシナリオをドメインモデルとして作り直す (#1771 / #1339) ための材料。モデルを描く前に、今のコードがしている振る舞いと、守っている (または守っていない) 規則を、ファイルと行の根拠つきで書き出した。

- 調べた版: a〜d は origin/main `21a33e4c9`、e〜g は `f231eb62a` (どちらも 2026-11-01)。行番号はそれぞれの版のもの
- サブエージェント 4 つに範囲を分けて読ませた。各ファイルの中で、コードで確かめた事実と推測を分けてある
- 一部の主張は、調整役のセッションがコードで確かめ直した (下の表の「確かめ直した主張」)

| ファイル | 範囲 |
|---|---|
| [a_scenario_loading.md](a_scenario_loading.md) | シナリオの読み込み。宣言できるもの、読み込みで弾くもの・黙って受け付けるもの |
| [b_world_tick.md](b_world_tick.md) | 世界の 1 tick。手番の割り当て、時間で進む処理、終わりの判定、観測の配り方 |
| [c_interactions_effects.md](c_interactions_effects.md) | 働きかけと効果。行動 1 件が世界を変えるまでの流れ、効果の種類ごとの状態の持ち主 |
| [d_world_state.md](d_world_state.md) | 世界の状態の持ち主。集約・値オブジェクト、集約になっていない状態、snapshot に入るもの |
| [e_actions_objects_items_people.md](e_actions_objects_items_people.md) | 行為: 物体・道具・人への操作、使う、介抱する、渡す、拾う、置く、探す、小部屋に移る (`f231eb62a`) |
| [f_actions_movement_speech_meeting.md](f_actions_movement_speech_meeting.md) | 行為: 移動、攻撃、話す、耳を澄ます、待つ、死体の報告、投票、行動しながらの一言 (`f231eb62a`) |
| [g_actions_trade_market.md](g_actions_trade_market.md) | 行為: 商人との売買、人どうしの取引、掲示板の市場 (`f231eb62a`) |

## 確かめ直した主張

| 主張 | 確かめた場所 |
|---|---|
| 終わりの判定に使う役 `"crew"` が実行の側に直書きされている | `application/world_runtime/world_runtime.py:4144` |
| 手番が回っている間、`WorldRuntime._tick` は 1 つ前の tick の値のまま。値を最新にするのは tick の処理の後 | `application/world_runtime/world_runtime.py:824-830` |
| 攻撃のダメージは装備を見ず、`base_stats.attack` をそのまま使う (ツールの説明は「武器で威力が変わる」) | `domain/monster/service/spot_player_attack_service.py:64`、`application/llm/services/tool_catalog/spot_graph.py:467` |
| 介抱で回復する HP の割合は 0.6 (docstring は 0.4) | `application/llm/services/executors/spot_graph_tool_executor.py:2904, 2978` |
| 市場の注文の値を変える・取り下げる行為は、売り注文しか指定できない (`side` の enum が `sell` だけ) | `application/llm/services/tool_catalog/spot_graph.py:884, 915` |
| 所持金の行は、商人を宣言した世界でしかプロンプトに出ない | `application/world_graph/spot_graph_current_state_builder.py:1520` |
| `PlayerStatusAggregate` の居場所は `__init__` で代入するだけで、移動で更新されない。発言の処理と声が届く相手を探す処理がこの値を読む | `domain/player/aggregate/player_status_aggregate.py:107`、`application/speech/services/player_speech_service.py:123`、`application/observation/services/player_audience_query_service.py:73` |
| 効果の対象の物体が見つからないと、操作した物体を対象にする | `domain/world_graph/service/effect_application/object_target.py:33` |

この記録は調べた時点の写しで、コードを直しても書き換えない。直したものは、それぞれの Issue と設計判断に残す。
