# 廃坑の灯り・ガス・食料: 試験監査

## 結論

対象は `tests/demos/test_mine_village_light_gas_and_food.py` 509 行、31 宣言、引数展開後 33 件。全宣言・全行・2 組の引数表を読んだ。基準は上流 `0b51eb28` に対応する調査用 `6dc7e34`。AGENTS.md と CLAUDE.md は同文で、両方確認。依頼された SKILL.md / CAMPAIGN.md も確認した。

ガスの 400 tick 上限の自然待ちを、既存の再現実験用設定 `SCENARIO_RANDOM_SEED` で固定した。ガス発生・消散を実際の `advance_tick()` に任せたまま20 tickへ短縮した。公開済みの `create_world_runtime(..., config=...)` を使えるため、製品コードの追加口も、フラグや記録時刻の捏造も、条件評価器の模造も不要。

基準試験・第二読解後に2宣言だけ修正した。主ファイルは変更前後とも2反復すべて33件成功、関連する7ファイルも変更前後それぞれ111件成功。基準失敗なし。最終分類は R29/F2/C0/D0。宣言数31・展開数33を維持し、製品コードの恒久変更・試験削除はない。

## 仕様・導入履歴

- `docs/mine_village_scenario_design.md:186-200,345-352`: R6 はカナリアからガスを学び安全な時に予備燃料を取る、R7 は油の有限性とたいまつ、R9 は有限在庫の回復。灯16 tick周期、たいまつ24 tick周期。ガスは毎 tick確率0.08、発生から8 tickで消散。条件を説明文で教えず経験から学ぶという独立した設計契約。
- https://github.com/Motifman/llm-rpg/issues/1508 : 経験から規則を学べる世界を作り、シナリオ固有判断を記憶実装へ入れないという上位目的。
- https://github.com/Motifman/llm-rpg/commit/fd0961e5d69283e55292282b529d53ed2b8a3283 : 2026-10-10 の本ファイル導入。R6/R7/R9を埋める実装で、ガス8 tick・カナリア操作を常時2つ出す理由・足もとへの灯投棄を禁止する理由が明記される。ガスの再発後7 tick維持は導入時点から存在し、後付けの偶然ではない。
- https://github.com/Motifman/llm-rpg/issues/1569 : 3回目の実験で北の油1本が協力を強い、燃え尽きが「何かのアイテムを捨てました」と観測された問題。
- https://github.com/Motifman/llm-rpg/commit/c82ff7a870bb566e8c72e945dad0b47ca1ff3d20 : 北の油を2本へ。単独チームで進める契約を保つ数値改定。
- https://github.com/Motifman/llm-rpg/commit/9452158f7561119fb3f4b850871c5ea6d8691418 : 品名の観測配線、消費と投棄の区別、出来事による除去だけの燃え尽き文。盗まれた灯を燃え尽きと誤報しない試験の根拠。
- ファイル履歴は上流SHAを指定した GitHub commits API で取得。上記3変更と併合 `ebe0109f` を確認。ローカルの監査用コミット履歴だけで導入意図を推測していない。

## 本番の所有境界・呼出経路

### ガス（変更候補の全経路）

1. `data/scenarios/mine_village_v1.json:4292-4345`: `gas_seeps_in` と `gas_clears` はともに `ON_TICK`, `once:false`。前者は `FLAG_NOT_SET` と `PROBABILITY(0.08)`、効果は `SET_FLAG` と `RECORD_OBJECT_STATE_TICK(gas_tracker.since)`。後者は `FLAG_SET` と `OBJECT_STATE_TICK_AT_LEAST(...,8)`、効果は `CLEAR_FLAG`。
2. `world_runtime.py:4986,5459,6364-6394`: 公開 config → `world_random(seed, round_number, "scenario")` → `ScenarioConditionEvaluator(random_source=...)` → イベント段階へ共有。天候、抽選、攻撃、モンスター行動の乱数は別系統。このJSONの `PROBABILITY` はガスの1件のみ。
3. `WorldRuntime.advance_tick():950` → `SpotGraphSimulationApplicationService._tick_impl():112-120`: 先に時計を進め、出来事段階を実行。実運用のゲーム進行もこの入口を使う。
4. `SpotGraphScenarioEventStageService.run()`: 定義順に通常の出来事を評価。条件合致時は本番の command scope 内で `_apply_event` と進捗記録。`once:false` は再発できる。発生が先、消散が後なので、消散した同じ tickには再発しない。
5. `ScenarioConditionEvaluator._evaluate_all():396-416`: AND は先頭の偽で短絡する。ガス中は `FLAG_NOT_SET` で止まるため乱数を消費しない。`PROBABILITY:530-551` は本物の乱数を閾値と比較する。`OBJECT_STATE_TICK_AT_LEAST:729-773` は実際の記録値+8と現在時刻を比較する。
6. `SpotGraphScenarioEventStageService._resolve_acting_object()` は条件または効果の対象オブジェクトを解決し、該当 interior を処理・保存する。`effect_application/handlers/object_state.py:239-267` は現在tickを対象の状態に書き、隠れたキーとして扱う。次回発生時も同じ経路で上書きする。
7. `world_random.py` は1回目の scenario 用なら `random.Random(seed)` と同じ列を作る。用途分離と回番号は製品の再現実験に必要な口で、テスト専用ではない。

### その他の保持契約

- `WorldRuntime.do_interact():3170` / `do_interact_with_item():3252` → `SpotInteractionApplicationService`。実操作へ現在tickを渡すことが、水・食料の遅延在庫回復を成立させる。`stock_pool_regen.py` が共通回復計算、JSONが個別在庫と間隔を所有する。
- `lamp/light_lamp` は油の所持条件→油除去→灯付与。`lamp_flames_burn_out` と `torches_burn_out` は周期出来事で所持品を除去。品定義 `is_light_source` が文脈に渡り、本人・同室者の暗所可視性が決まる。
- 出来事除去は `spot_inventory_helpers.remove_items_of_specs_from_inventory(..., by_world_event=True)` を経由する。出来事時だけ品定義の `event_removal_message` が観測に出る。テストの観測バッファは実際の配信結果を読む。
- `_WorldLlmWiring._execute_tool` を使う暗所拒否、水・食料消費は、直接操作とは違うツール入口の保護も担う。`llm_client=object()` はモデル呼出を行わない。
- `SpotGraphNeedsDecayStageService` は本番 command scope の所持者状態へ毎tick欲求と飢餓ダメージを適用。`world_runtime.py:6445-6458` がシナリオ設定を接続する。
- 詳細に追跡した変更経路はガス。その他の一般機構全体を変更・削除するための調査ではない。

## 全宣言台帳（第二読解で承認した最終分類）

同じファイル内のクラス名と変更前の宣言行。Rは保持。Fは契約を保持して試験の表現・条件を修正する。分類は29 R、2 F、0 C、0 D。第二読解で変更対象の範囲を承認した。

| クラス | 行・宣言 | 分類 | 実際の保護と具体的な退行 |
|---|---|---|---|
| TestLampOil | 161 `test_south_carries_more_oil_than_north` | R | 北2・南3と全員のカンテラ。初期装備改定が北を再び詰ませる |
| 同 | 168 `test_an_unlit_lamp_shows_nothing_in_the_dark` | R | 未点灯品を光源にしてしまう誤設定 |
| 同 | 174 `test_lighting_the_lamp_uses_one_oil_and_shows_the_room` | R | 油の消費漏れ、灯の光源接続漏れ |
| 同 | 184 `test_no_oil_no_light` | R | 油なしでも何度も点灯できる前提条件欠落 |
| 同 | 194 `test_the_flame_burns_out_and_the_room_goes_dark` | R | 15/16境界のずれ、除去しても暗さが戻らない |
| 同 | 207 `test_without_light_the_tool_refuses_to_touch_the_generator` | R | 暗所のツール拒否を通過し燃料を消費する |
| 同 | 217 `test_holder_hears_the_flame_burned_out_by_name` | R | #1569の品名欠落・燃焼を投棄と誤報する再発 |
| 同 | 228 `test_lighting_tells_the_oil_left_the_hand_by_name` | R | 消費経路だけ旧投棄イベントに戻る |
| 同 | 236 `test_a_stolen_flame_is_not_said_to_have_burned_out` | R | 品ごとの燃え尽き文を盗難経路にも出す |
| 同 | 249 `test_a_flame_lit_late_burns_out_at_the_same_time_as_the_rest` | R | 周期を点灯起算に変える、たいまつまで16で消す。16 tickは仕様上必要 |
| 同 | 260 `test_a_flame_cannot_be_set_down_to_stop_it_burning` | R | drop_item復活による燃焼回避。give_itemを残す陽性対照もある |
| 同 | 267 `test_a_teammates_flame_lights_the_room_for_both` | R | 光源を本人にしか適用しなくなる |
| 同 | 276 `test_the_lamp_description_does_not_say_how_long_it_burns` | R | 時間を説明で漏らす。単なるソース文字列照合ではなく独立した秘匿契約 |
| TestTorchFromTheSmithy | 287 `test_a_torch_lights_the_dark_room` | F | たいまつの光源契約は必要。ただし「油の切れたハル」は現在の初期2本に対して1回しか点灯せず実現していない。実際の灯切れを前提とする説明へ訂正し、灯なし・暗いという対照を追加した |
| 同 | 298 `test_the_smithy_has_rags_for_two_torches` | R | 2本を超える無限生成、2本目まで拒否する数量誤設定 |
| 同 | 308 `test_a_torch_burns_out_too` | R | 23/24境界のずれ、たいまつ除去の欠落 |
| 同 | 319 `test_the_recipe_is_not_written_down` | R | 作る前から答えを表示する説明・操作ラベルの漏洩 |
| TestGasAndTheCanary | 331 `test_gas_blocks_the_spare_fuel` | R | ガス拒否の欠落/別理由の拒否/燃料付与の先行。拒否文と非所持を保護 |
| 同 | 341 `test_without_gas_the_spare_fuel_can_be_taken` | R | 初期状態の清浄時に取得可能である陽性経路。405は拒否後の状態破壊を区別する。この変更では拒否後の回復と初期正常経路をともに残す |
| 同 | 350 `test_the_canary_cage_hangs_in_the_miners_rest` | R | 籠の入手失敗、2人目にも重複付与 |
| 同 | 359 `test_the_canary_tells_whether_there_is_gas` | R | 行 `(True,"鳴きやん")` と `(False,"さえずって")` の双方。各行でa/b両操作の文と成功がちょうど1件であること。片方の失敗文だけ古いままになる |
| 同 | 369 `test_the_inventory_line_looks_the_same_with_or_without_gas` | R | ガス有無で操作候補が変わり、行動せず状態を知れる漏洩。状態を変えた比較であり自己比較ではない |
| 同 | 385 `test_gas_seeps_in_now_and_then_and_clears_after_a_while` | F | 自発発生、7/8境界、再発、記録時刻の再設定を残して決定的入力にする。詳細は下記 |
| 同 | 405 `test_once_the_gas_clears_the_spare_fuel_can_be_taken` | R | 拒否が燃料在庫を消費してしまう状態破壊。自然消散を検証しているわけではない |
| 同 | 416 `test_the_canary_action_names_do_not_tell_its_state` | R | 操作識別子/表示名だけで状態を知らせる漏洩 |
| 同 | 424 `test_south_knows_what_a_silent_canary_means_and_north_does_not` | R | 南の事前知識欠落、北への漏洩、観測文と知識の表現不一致 |
| 同 | 436 `test_nothing_in_the_world_text_names_the_gas` | R | 世界説明やラベルにガスを直書きし学習課題を壊す |
| TestWaterAndFood | 462 `test_taking_runs_it_dry_and_it_comes_back_one_at_a_time` | R | 水 `(well,well_bucket,draw_water,4,6)`、食料 `(storehouse,food_box,take_food,3,24)`。初期在庫、間隔-1/間隔、1個のみ回復。JSONごとの回復設定漏れ |
| 同 | 476 `test_eating_the_preserved_food_eases_hunger` | R | 取得した保存食のツール使用が空腹を40減らさない |
| 同 | 488 `test_drinking_well_water_restores_hp` | R | 取得した水のツール使用がHPを8戻さない |
| 同 | 500 `test_starving_wears_down_hp` | R | シナリオ飢餓設定の未接続、非飢餓者も傷つく。2 tick継続を確認 |

## 層の計画・残す試験

- シナリオのガス発生/消散/再発の主担当は本ファイルの385行。一般確率試験へ移さない。一般の評価器だけではJSONの trigger、once、対象ID、時刻記録の接続を守れない。
- `tests/application/world_graph/test_scenario_condition_probability.py` は0/1/0.5、同seed、AND/NOT、範囲検証。`test_scenario_condition_predicate_result.py` は短絡時の乱数非消費等。いずれもガスの8 tick契約を所有しない。
- `test_scenario_condition_evaluator_dynamic_world.py::TestObjectStateTickAtLeastCondition` は記録5+10の14/15境界。`test_object_state_tick_at_least_null.py` は未記録/null・不正型・対象不存在等。`tests/domain/world_graph/test_record_object_state_tick_effect.py` は現在tickの書込、明示対象、実操作伝搬、不足値。これらは実シナリオの再発時リセットの代わりにはならない。
- `tests/application/world_runtime/test_world_random.py` は用途・回番号・実ランタイムへの接続。公開設定を使う案の先例がある。世界の乱数初期化口を新設する必要はない。
- `test_mine_village_map_and_start.py:240` は明るさのプロンプト表現（暗い→薄暗い）。本ファイルは実物の可視性/油消費/ツール拒否を担当し、別の退行を保護するため自動統合しない。
- `test_mine_village_clues_and_recovery.py:331-386` は油樽2本/12 tick、夜にも回収できる配置と秘匿。水4/6、食料3/24とはJSONの別配置・別数値が対象。
- 燃料を取る water/noise_and_lift/capacity_and_fuel の補助処理はガスを手で抜くので、自然発生試験を代替しない。
- 退役ファイルなし。製品コード削除なし。テスト専用製品口の削除解放なし。変更は本ファイルのガス1宣言とその限定的設定、たいまつ1宣言の説明と対照だけ。共有 fixture 全体にseedを適用せず、無関係な試験の前提を変えない。

## ガス候補の具体案と独立した失敗条件

### 推奨: 既存の公開設定を使う

`ResolvedLlmRuntimeConfig.from_mapping(values={"SCENARIO_RANDOM_SEED":"560"})` を当該試験だけの `create_world_runtime` に渡す。既定は呼出をしないトリガで、必要なら既存の先例同様に `LLM_CLIENT` / `TYPED_JUDGMENT_PROVIDER` をstubと明示する。ファイル共通fixtureを使った余分な runtime を先に作らないよう、当該試験の `runtime` 引数を外すか、限定fixtureにする。

標準ライブラリだけで確認した先頭4値:

`0.7607426616434038, 0.04429433849745856, 0.7389517833452284, 0.0037910469920241496`

実ランタイムで確認した経過:

- T0: ガスなし。T1: 抽選不成立、なし
- T2: 本物の発生出来事でガスあり、時刻が記録される
- T3〜T9: ガス中は再発抽選に入らず、T9（発生+7）まであり
- T10（+8）: 本物の消散出来事でなし
- T11: 次の抽選不成立、なし
- T12: 再発し、新しい発生時刻が記録される
- T19（再発+7）: あり。T20（+8）: なしも追加し、2回目の消散まで確認した

この案は20回の実tickで、現状の期待約40回（2×12.5+8+7）、最大815回を置き換える。期待・上限は構造上の計算であり、秒数の改善実測ではない。通常の契約には発生時刻T2/T12という固定値は無いので、docstringには「この乱数条件で発生・未発生双方を通し、発生から8 tick」と説明し、世界全体が常にT2に発生する仕様に見せない。

検出する退行:

- 発生triggerをON_TICK以外へ変更: T2に現れず失敗
- 確率条件を除去/常時成立: T1の非発生が失敗
- 確率条件を常時偽: T2が失敗
- 発生/消散のonceをtrue: T12再発またはT20再消散が失敗
- 期間を7/9へ変更: T9維持またはT10消散が失敗
- `RECORD_OBJECT_STATE_TICK` の欠落/対象の誤り: T10で消えない
- 再発時に時刻を更新しない: T12直後に前回起算で消えてしまい失敗
- ガス中も発生効果を適用: シードの4番目が低値なので持続中に時刻を更新し、T10消散が遅れて失敗する（変異で確認済み）

### リスクと採らない案

将来このシナリオに別の確率出来事が加わると列の消費順が変わるため、固定seedを再選定する必要がある。これは長い自然待ちより狭い依存だが、利点と比較すべき。回数をassertして評価器の内部実装を固定する必要はない。期待値を同じ乱数関数から動的生成すると独立性が弱まるので避ける。

- フラグや `gas_tracker.since` を直接書いて消散だけを見る案は、発生の接続と再設定を失うので不可
- current tickを直接20へ飛ばす案は実tick配線を失うので不可
- 評価結果や `_matches_conditions` を模造する案は、試験側が発生を実装してしまうので不可
- `random.random()` の内部差し替えは可能性があるが、既存の公開configで足りるので優先しない
- 灯16・たいまつ24・食料24のtickは境界そのもの。数が大きいだけで除かない

## 事前に定めた基準・第二読解・検証の順序

1. 他担当の計測終了後、未編集基準で `uv run --frozen pytest tests/demos/test_mine_village_light_gas_and_food.py --durations=10`。31宣言/33件の結果と失敗を保存。失敗は削除理由にしない
2. 独立読解者が本台帳と仕様からガス1宣言の保持契約を確認。基準と20 tick案を承認するまで編集しない
3. 当該ノードの20 tick案を実行し、T1/T2/T9/T10/T11/T12/T19/T20が実経路で成立することを確かめる。未成立ならconfig初期消費・順序を追跡し、製品動作を曲げない
4. `uv run --frozen pytest tests/demos/test_mine_village_light_gas_and_food.py tests/application/world_graph/test_scenario_condition_probability.py tests/application/world_graph/test_scenario_condition_evaluator_dynamic_world.py tests/application/world_graph/test_object_state_tick_at_least_null.py tests/domain/world_graph/test_record_object_state_tick_effect.py tests/application/world_runtime/test_world_random.py`
5. 変更前後で同一ノードを同じ実行環境・条件で計測。全ファイルでも比較する
6. 一時的な退行投入の許可後、trigger変更、期間7/9、発生once、再発時刻更新欠落、消散once等が該当観測で赤くなるか確認。毎回製品ファイルをバイト単位で復元。実施結果は下記の変異記録を参照
7. `uv run --frozen ruff check tests/demos/test_mine_village_light_gas_and_food.py`、`git diff --check`、`git diff --numstat`、独立した保存確認レビュー。削除数を成果にしない

CI `.github/workflows/ci.yml` はPython3.10、`uv sync --locked --extra export` 後 `uv run --frozen pytest -n auto`。別jobでruffとmypy。`pytest.ini` は `not quality and not live_api` を既定にしており対象ファイルは通常CIに含まれる。今回は実LLM/API、quality再生成、温まり通知・station freezeの別担当領域には踏み込まない。

## 基準試験結果と安全条件

実行環境はPython3.10.22、固定lockの環境を共用し、対象worktreeのsrcから読み込んだことを確認。認証環境変数とproxyを除去し、network_blockを有効にした専用runnerを使った。試験の並列実行なし。実LLM/API呼出なし。

| 測定名 | 結果 | pytest秒 | 外側実時間秒 | ガス呼出秒 |
|---|---|---:|---:|---:|
| env-baseline1 | 33成功 | 23.211 | 25.857 | 3.974 |
| env-baseline2 | 33成功 | 24.108 | 26.808 | 5.897 |
| env-baseline-related | 111成功 | 18.810 | 21.442 | 対象外 |

関連7ファイルは検証手順4の6ファイルのうち主ファイルを除いた5ファイルに、`test_mine_village_map_and_start.py` と `test_mine_village_clues_and_recovery.py` を加えたもの。全8ファイルの基準結果を取得済み。生ログ・JUnit・段階別JSONは監査担当の証拠保存先に保管した。

## たいまつの修理案と範囲判断

導入時にはハルの油は1本だったため「油が切れた」は正しかった。#1569で2本へ増えた後、当該試験は1回だけ点灯するので油が1本残る。たいまつの作成はlamp_oilを消費せず、鍛冶場の備蓄だけで成立する。守るべき観測は、灯の燃え尽きで見えなくなった部屋をたいまつで再び見られること。

単純に2回灯して16tick待つ修理は不可。`plan_item_removals_from_inventory` は要求された個数（出来事のREMOVE_ITEMは1個）だけ除去するため、灯が1個残り、たいまつが光らなくても可視性のassertが通る。

推奨する小修理は、docstringを「カンテラの灯が燃え尽きたハル」と正し、既存の16tick待機後に灯が無いことと機械室の発電機が隠れることを確認してから、鍛冶場でたいまつを作り、機械室で再び見えることを確認する。同じファイル・同じ環境機構の試験品質改善であり、製品動作や待機期間を変えない。油0自体を条件に加えるなら2周期の消費等が必要になるが、この試験の光源契約には不要。第二読解者の範囲承認後、この小修理を適用した。

## 変更後の計測・変異・限界

変更後の再計測は同じPython・安全runner・逐次実行条件で行った。

| 測定名 | 結果 | pytest秒 | 外側実時間秒 | ガス呼出秒 |
|---|---|---:|---:|---:|
| env-candidate1 | 33成功 | 20.135 | 22.913 | 2.001 |
| env-candidate2 | 33成功 | 19.786 | 22.571 | 2.111 |
| env-candidate-related | 111成功 | 18.401 | 21.269 | 対象外 |

ガスの自然待ちの上限は815 tickから20 tickへ。今回の2測定ではガス呼出は3.974/5.897秒から2.001/2.111秒、主ファイル全体は23.211/24.108秒から20.135/19.786秒となった。変更前は乱数により待機長が変わるため、この小標本から一定の改善率や全CIの短縮量を主張しない。最初にガスだけを実行すると初回構築の遅延がcallへ含まれるので、比較は同じ全ファイルの実行順で行った。

### 意図的な退行の検出

一度に1個だけシナリオまたは所有実装に自然な誤りを入れ、対象1件を安全runnerで実行した。読み込み例外による失敗は認めず、狙った観測assertが失敗することを確認した。各実行の終了後に原本のbyte列へ戻し、SHA-256を記録した。

| 変異 | 検出点 |
|---|---|
| ガス確率条件を削除 | T1の未発生assertで失敗 |
| 発生triggerを有効なON_CHAINへ変更 | T2の発生assertで失敗（定義は正常に読み込まれる） |
| ガス期間を7へ | T9の維持assertで失敗 |
| ガス期間を9へ | T10の消散assertで失敗 |
| 発生をonce=trueへ | T12の再発assertで失敗 |
| 消散をonce=trueへ | T20の2回目消散assertで失敗 |
| 時刻記録をsetdefaultへ変え、再発時に更新しない | T12で古い記録により即消散し、再発assertで失敗 |
| 発生のFLAG_NOT_SETを削除 | 持続中の再抽選で起算を延長し、T10の消散assertで失敗 |
| たいまつのis_light_sourceをfalseへ | 作成後の発電機可視assertで失敗 |

以上9個の変異は各1件失敗・読み込みエラー0件。

10個目は `lamp_flames_burn_out.trigger` を `ON_CHAIN` にし、灯が燃え尽きない誤りを入れた。変更後のたいまつ試験は、作成前の「lamp_flameを持たない」で失敗。同じ変異を残し、当該宣言だけ変更前の本文へ戻すと成功してしまった。元の試験では残っている灯が部屋を照らし、たいまつ単独の働きを確認できなかったことを実証した。この比較後もシナリオと変更後テストの両方を原本byteへ復元した。

### 保証しないこと

- 確率0.08の分布推定やすべてのシードでの振る舞いは、この時間境界試験の目的ではない。一般確率条件の試験は維持した
- 後日、同じシナリオに別の確率条件が加わると乱数の消費順が変わり得る。その場合は仕様を確認して固定seedと入力順を再選定する
- 実LLM、API、全リポジトリ試験、品質サンプル再生成は実施していない。今回は環境機構の主・関連8ファイルの証明
- 北の油2本を1本へ戻す変更、油切れ状態を捏造する変更、製品へのテスト専用入口追加は行わない

### 最終の差分と静的検査

- 製品コード・シナリオ: 恒久差分0行。変異後のSHA-256一致、git差分なしを確認
- 主試験: 509行→514行、追加25/削除20行。31宣言・33件を維持。共有補助ファイルの変更なし
- 文書: この監査記録を追加
- `ruff check tests/demos/test_mine_village_light_gas_and_food.py`: 成功（監査用の既存devtoolsを使用。試験用環境にはruffが無かったため、依存追加せず別の既存環境で実行）
- `git diff --check`: 成功
- 独立した保存確認レビュー: 契約保持、実経路、変異、復元、計測根拠を照合し承認済み

復元後の最終主ファイル試験 `env-restored-final` は33件成功、pytest段階 20.407秒。製品差分を残さず、修正版のまま成功することを再確認した。
