# 環境とシナリオのモデリングの前に、今のコードがしていることを書き出した記録

環境とシナリオをドメインモデルとして作り直す (#1771 / #1339) ための材料。モデルを描く前に、今のコードがしている振る舞いと、守っている (または守っていない) 規則を、ファイルと行の根拠つきで書き出した。

- 調べた版: origin/main `21a33e4c9` (2026-11-01)。行番号はこの版のもの
- サブエージェント 4 つに範囲を分けて読ませた。各ファイルの中で、コードで確かめた事実と推測を分けてある
- 一部の主張は、調整役のセッションがコードで確かめ直した (下の表の「確かめ直した主張」)

| ファイル | 範囲 |
|---|---|
| [a_scenario_loading.md](a_scenario_loading.md) | シナリオの読み込み。宣言できるもの、読み込みで弾くもの・黙って受け付けるもの |
| [b_world_tick.md](b_world_tick.md) | 世界の 1 tick。手番の割り当て、時間で進む処理、終わりの判定、観測の配り方 |
| [c_interactions_effects.md](c_interactions_effects.md) | 働きかけと効果。行動 1 件が世界を変えるまでの流れ、効果の種類ごとの状態の持ち主 |
| [d_world_state.md](d_world_state.md) | 世界の状態の持ち主。集約・値オブジェクト、集約になっていない状態、snapshot に入るもの |

## 確かめ直した主張

| 主張 | 確かめた場所 |
|---|---|
| 終わりの判定に使う役 `"crew"` が実行の側に直書きされている | `application/world_runtime/world_runtime.py:4144` |
| 手番が回っている間、`WorldRuntime._tick` は 1 つ前の tick の値のまま。値を最新にするのは tick の処理の後 | `application/world_runtime/world_runtime.py:824-830` |
| `PlayerStatusAggregate` の居場所は `__init__` で代入するだけで、移動で更新されない。発言の処理と声が届く相手を探す処理がこの値を読む | `domain/player/aggregate/player_status_aggregate.py:107`、`application/speech/services/player_speech_service.py:123`、`application/observation/services/player_audience_query_service.py:73` |
| 効果の対象の物体が見つからないと、操作した物体を対象にする | `domain/world_graph/service/effect_application/object_target.py:33` |

この記録は調べた時点の写しで、コードを直しても書き換えない。直したものは、それぞれの Issue と設計判断に残す。
