# 名前漏れの正の対照だけを短くする監査

## 対象と基準

2026-10-13、`0b51eb28d4692635a932dcf4063ab9b231768bf0` の内容を固定して確認した。
変更は `tests/demos/test_unknown_names_vanish_from_the_prompt.py` だけ。
関連する次の3ファイルも全文を読み、変更前後とも全件実行した。

- `tests/scripts/test_fuzz_scenario_with_random_agents.py`: 検出・分類・再現情報の持ち主
- `tests/scripts/test_fuzz_action_names_in_action_lines.py`: 行動要約に出る操作名の持ち主
- `tests/application/being/test_player_acquaintances_names.py`: 呼び方と名前の学習の持ち主

基準は4ファイル72件すべて成功。基準失敗はない。
3+26+4+24の計57宣言を確認し、すべて契約を保持する `R` と判断した。
削除や別の層への移動はしない。

## 変更対象の契約台帳と残す層

以下はすべて `TestUnknownNamesVanish` に属し、各宣言を山村と二班の2シナリオで実行する。

| 宣言 | 判定 | 保護する契約と検出する退行 | 保持する実行量 |
| --- | --- | --- | --- |
| `test_no_turn_shows_the_name_of_someone_not_yet_named` | R | 実際の本文・ツール定義の名前漏れ、手番識別の脱落、見た目の検査の空振り | 各4シード×12 tick |
| `test_check_catches_names_shown_in_the_list` | R | 一覧と対象候補を実名に戻しても検出器が反応しない退行 | 各1シード×2 tick |
| `test_check_catches_names_left_in_observations` | R | 保存前の観測の名前置換を外しても検出器が反応しない退行 | 各1シード×2 tick |

通常の探索、一覧の検出経路、観測の検出経路は別の契約であり、対照を削除してはいけない。
両シナリオとも既知と未知が混在する。山村ではハルとミオ、ゲンとサヨが互いに既知。
山村は道具や対人操作が豊富で、二班は別の世界構成を通るため、両方を残す。
短縮後に検出した観測も、山村は探索、二班は叫びと異なる。
引用内の言葉、既知の相手、名乗り、呼びかけ、囁き、記録検索や置換の失敗時の処理は
`test_player_acquaintances_names.py` に残す。乱数探索だけでこれらの条件分岐を代替しない。
検出器の兄弟にある例外・ERRORログ・既知の穴・時刻・入れ子のツール定義・候補表・
操作名の判定も削らない。

## なぜ短くできるか

正の対照は、既知の壊し方を検出できることを確かめる試験である。
正常な世界の組み合わせを探す4シード×12 tickを、そのまま両対照にも繰り返していた。
対照に限って `run_random_agents(scenario, seed=0, max_world_ticks=2)` を直接呼ぶ。
通常探索の `_run`、シード数、tick数、assertion、シナリオは変更しない。
新しい共通の助け関数や製品側の試験専用引数を増やす必要もない。

由来は [Issue #1581](https://github.com/Motifman/llm-rpg/issues/1581)、
[導入コミット c14acf66](https://github.com/Motifman/llm-rpg/commit/c14acf66974a61ca8ed04ca5006a4b2d0162bd24)、
`design_decisions.md` の D1581 と D1557。
初対面の4人が名前で呼び合った実例に対し、一覧と観測の両方を守る必要があった。
製品の接続は `world_runtime.py` の `viewer_name_resolver` と `recipient_view`。
`ObservationAppender` は保存前に `PlayerAcquaintances.view_for` を通し、
検出器は実際のLLM入口で本文とツール定義を読む。これらの接続は変更しない。

## 対照と変異の証拠

短縮後の実際の所見を、返却値を変更せずに記録した。

| 対照 | シナリオ | `stranger_name` のtick | 所見数 |
| --- | --- | --- | ---: |
| 一覧 | 山村 | 1 | 24 |
| 一覧 | 二班 | 1, 2 | 20 |
| 観測 | 山村 | 2 | 1 |
| 観測 | 二班 | 2 | 1 |

観測で拾った実文は、山村の「ハルが周囲を探索している。」と
二班の「サヤが叫んだ: 「でたらめに選んだ行動」」。
観測が生成され、後続のプロンプトへ届くところまで2 tick回す。
山村ではtick 2のP1の探索が同じtickのP3のプロンプトへ届く。

検出器の `_ObservedClient.invoke` 内で、所見追加の種類を一時的に
`stranger_name` から `leak` へ変え、名前漏れとして収集されなくなる退行を作った。
`-k test_check_catches` の4件はすべて `assert [] != []` で失敗した。
例外や起動失敗で落ちたのではない。撤去後の検出器のSHA-256は撤去前と一致し、
製品・スクリプトの差分は0。復旧後は関連72件すべて成功した。

## 実行条件と結果

Python 3.10.22、pytest 8.4.1、同一の依存環境、逐次実行。
外部接続を遮断し、鍵を外し、実LLMは使用していない。
変更前後で他の重い試験とは実行時間帯を分け、watcherを動かさずに編集した。
実際の実行は固定環境の `python -m pytest` にネットワーク遮断と計測のプラグインを追加したもの。
リポジトリ標準の再現用コマンドは次のとおり。

```sh
uv run --frozen pytest tests/demos/test_unknown_names_vanish_from_the_prompt.py
uv run --frozen pytest tests/demos/test_unknown_names_vanish_from_the_prompt.py -k test_check_catches
uv run --frozen pytest tests/demos/test_unknown_names_vanish_from_the_prompt.py tests/scripts/test_fuzz_scenario_with_random_agents.py tests/scripts/test_fuzz_action_names_in_action_lines.py tests/application/being/test_player_acquaintances_names.py
uv run --frozen ruff check tests/demos/test_unknown_names_vanish_from_the_prompt.py
git diff --check
```

- 収集数: 対象6件→6件、関連4ファイル72件→72件。変更前後ともすべて成功
- 対象6件の実行本体合計: 変更前54.41秒 / 51.45秒、変更後20.96秒 / 21.53秒
- うち正の対照4件: 変更前33.22秒 / 30.34秒、変更後1.29秒 / 1.26秒
- 正の対照4件だけを別プロセスで起動した所見記録は実時間9.05秒。上記の実行本体合計には含まれない初回読み込みを伴う
- 対象6件だけを起動したときの実時間: 変更前54.48秒、変更後24.07秒 / 24.50秒
- 基準1回目は関連72件を同時に実行したため、そのプロセスの実時間74.61秒を上記6件の比較には使わない
- 復旧後の関連72件: pytest 36.64秒。ruff 0.16.8と差分の空白検査も成功

行数は対象試験105→111行、関連試験総計989→995行。
差分は試験+8/-2行、製品0行、独立した試験支援0行。この記録は別計上。
削除件数や行数を目標にせず、同じ検出契約の重複実行だけを減らした。

## 限界

リポジトリ全体の試験はこの局所検証には含めず、通常のCIで確認する。
この局所計時を並列CI全体の短縮幅へ外挿しない。
条件分岐の網羅率を数値で比較した結果ではない。通常探索を変更せず、
上記の各契約と正の対照を残したこと、検出器の変異を捕まえることを確認した。
シードによる行動列は候補の変更で変わり得る。今後2 tick内で観測が生まれなくなれば
正の対照が失敗するため、空振りを成功として扱わず、対照の条件を見直す。
