# 戦闘イベント処理のテスト監査（2026-10-13）

## なぜ

`assert True` を含む9件は、例外が漏れないことは確認するが、状態の誤更新や不要イベントの発行を見逃す。さらに、非アクター攻撃の検査はモンスターを登録せず型だけを確認し、場所情報なしの飢餓検査は未登録の討伐者という別の条件で止まっていた。

削除件数ではなく、公開 `handle` の保証が実際に壊れたとき失敗することを優先した。製品の動作変更はない。

## 範囲と順序

- 基準の上流: `0b51eb28d4692635a932dcf4063ab9b231768bf0`
- 所有者に確認した作業ディレクトリを利用し、上流3574個のファイルの内容を照合した。通常の履歴付き clone ではないため、変更理由は固定SHAを基点にGitHubの履歴で確認した
- 基準4ファイル全37件を3回実行 → 全宣言台帳 → 別の読み取りによる主所有者・層の確認 → 編集 → 旧新テストでの変異比較 → 全範囲再実行、の順に進めた
- 消費・所持品・採食の別ハンドラ、および進行中の記憶・予期・設定・SNS変更は編集対象外

## 残す層と削除しない理由

- 被弾、脅威、報酬、移動、技能の公開イベント入口: `test_combat_handlers.py`
- 飢餓、死亡時の地図除去、出現時の配置: それぞれの専用ファイル
- 衝突から死亡報酬までの同期配送: `TestCombatIntegration`。直接呼出しではイベント登録漏れを検出できないため残す
- 例外変換、任意の脅威ストアなし、脅威の時計/忘却、出現と再出現の別イベント受付は独立した契約として残す
- 地図除去の「場所不明／地図消滅でも例外を出さない」2件も有効な受理契約。無検証と決めつけて削除しない
- 現在の実験が使うスポットグラフからタイル戦闘は呼ばれないが、[D1514-3](../design_decisions.md#d1514-3-世界の側の乱数は用途ごとにシードと回の番号から作る)でも区別されている。本領域全体の廃止を推測しない

`CombatEventHandlerRegistry` / `MonsterEventHandlerRegistry` が生産側の同期登録を所有する。下位の集約・リポジトリ・脅威ストアと、上位の世界進行試験も確認した。試験のための新しい生産用引数、公開関数、切替は追加しない。退役ファイルや削除する生産経路はない。

関連履歴: [被弾と報酬の導入](https://github.com/Motifman/llm-rpg/commit/4a08ce4432306db65ee1117159d0f73d2558f836)、[失効イベントの例外処理](https://github.com/Motifman/llm-rpg/commit/ce41ebad119b1c33c60dd3d87376cea5d8dd82ee)、[脅威と消失ケース](https://github.com/Motifman/llm-rpg/commit/050dfc6d3861d229081bf901a891c8b18d22a1bd)、[状態のMonster移管](https://github.com/Motifman/llm-rpg/commit/220bc4bd2fe2b06b45c2be1134ede7782474cec3)、[死亡時処理](https://github.com/Motifman/llm-rpg/commit/793ddde0c8d6fdbb89621abeda47587810f9ba49)。

## 修復と統合

1. 死亡済みの被弾: 死亡をtick 5、処理をtick 10に分け、HP・死亡状態・死亡時刻と追加発行なしを確認。準備時の死亡イベントは明示的に除く
2. 消失イベント: 生きている保存先を用意し、HP、報酬、脅威、技能装備の不要な更新を検出する。技能の地図不在ケースは実モンスターに使用可能な技能を装備し、別の欠落条件で停止しないようにする
3. 非アクター攻撃: 実モンスターと実脅威ストアを用意し、型検査を標的・脅威の不変検査へ置換する
4. 飢餓: 獲物／非獲物の重複準備を共通化。成功表の `prey-without-spot` は実在する討伐者の飢餓0.9→0.5を確認する。元の未登録討伐者の無例外契約も `unknown-killer` 行に残す
5. 効果の除去は私有配列でなく公開 `active_effects` を確認する。出現試験が検査していない逃走閾値についての説明だけを訂正する

重要な観測点: `TransactionalScope` は終了時に確定イベントを消すので、ここで `get_committed_events() == []` を検査すると空振りする。接続された発行器の公開履歴を確認した。技能の試験は生の `InMemoryUnitOfWork` なので確定イベントを確認できる。

## 基準と最終結果

すべて直列、Python 3.10.22 / pytest 8.4.1。外部ネットワーク接続を禁止し、秘密情報を環境から除外した既存の固定依存環境で実行。対象作業木の `src` が読み込まれることを毎回確認した。

| ファイル（`tests/application/world/handlers/`） | 基準 | 最終 | 行数 前→後 |
| --- | --- | --- | --- |
| `test_combat_handlers.py` | 26/26成功 ×3 | 26/26成功 ×3 | 1299→1344 |
| `test_monster_death_hunger_handler.py` | 4/4成功 ×3 | 5/5成功 ×3 | 235→142 |
| `test_monster_died_map_removal_handler.py` | 3/3成功 ×3 | 3/3成功 ×3 | 166→166 |
| `test_monster_spawned_map_placement_handler.py` | 4/4成功 ×3 | 4/4成功 ×3 | 280→280 |

- 収集: 37→38件、宣言: 37→35。飢餓の二つの宣言が5行を持つ。収集漏れ・基準失敗なし
- 関連回帰: ハンドラ全体と `test_world_simulation_service.py` の148件成功。リポジトリ全試験はこの作業では未実施
- `ruff check` は対象4ファイルで成功、`git diff --check` 成功。CIは通常の全収集で対象を含むため登録変更不要
- テストファイル: 1980→1932行（48行減）。この内数の支援関数: 497→515行。重複した本文を共通準備へ移したため内数は増えた。独立支援ファイルは0→0
- 生産8ハンドラ: 896→896行。生産差分0。試験規則とこの記録は文書として別計上

### 繰り返し計時

起動・収集込みの秒数は基準 `1.733 / 1.265 / 1.091`、最終 `1.440 / 1.506 / 1.354`。中央値は `1.265→1.440` 秒。各ケースの準備・実行・後片付けの中央値合計は約259→313ms。以前の候補計測では約255msで、最終測定では未変更のケースにも変動があるため、差を変更の効果だけとは断定しない。高速化は主張しない。別作業と交差した候補1回は比較から除外した。

以下は各ケースの3回中央値（準備＋実行＋後片付け、ms）。統合先を持つ行は対応する新しい行と比較する。飢餓の無例外だけだったケースは、実集約を用意することで数ms増えても新しい検出力がある。

## 宣言別台帳

R=保持、F=保証を修復、C=残す主所有者へ統合、D=削除。Dは0。位置は変更前、名前は元宣言。Fの観測点は上記の通り発行履歴へ補正した。

### `test_combat_handlers.py`

| 判定・元行 | 宣言 | 実際の保証・判断 | ms 前→後 |
| --- | --- | --- | --- |
| R 272 | `TestHitBoxDamageHandler::test_apply_damage_with_snapshot_stats` | 攻撃生成時の値を優先し、現在の攻撃力を誤用しない。HP 55 の実値が根拠。 | 8.40→11.36 |
| F 306 | `TestHitBoxDamageHandler::test_apply_damage_filters_expired_buffs` | 期限切れ効果の除去と被ダメージ85。私有 _active_effects の検査を公開 active_effects に移す。 | 5.40→5.69 |
| R 342 | `TestHitBoxDamageHandler::test_monster_hp_updated_in_aggregate_only` | モンスターHP54を実リポジトリから再取得。プレイヤー専用更新への退行を検出。Component型だけの付随検査は主証拠に数えない。 | 7.37→9.10 |
| F 385 | `TestHitBoxDamageHandler::test_skip_damage_when_target_already_dead` | 死亡済みへの追加被弾を無例外で処理。現在は例外漏出のみ検出。HP0、死亡状態、過去の死亡時刻、発行イベントなしへ強化。 | 5.82→6.41 |
| F 414 | `TestHitBoxDamageHandler::test_handle_hit_box_not_found` | 消滅したHitBoxを無例外で無視。現在は例外漏出のみ。既存プレイヤーHPと発行イベントなしも確認。 | 1.68→2.55 |
| F 432 | `TestHitBoxDamageHandler::test_handle_map_not_found` | 消滅したマップを無例外で無視。HitBoxは実在する。既存プレイヤーHPと発行イベントなしを確認。 | 1.84→2.82 |
| F 454 | `TestHitBoxDamageHandler::test_handle_defender_disappeared` | 消滅した被弾者を無例外で無視。所有者とHitBoxは実在する。既存プレイヤーHPと発行イベントなしを確認。 | 4.26→6.58 |
| F 494 | `TestCombatAggroHandler::test_aggro_skipped_when_attacker_not_actor` | 非アクター攻撃者から脅威を記録しない。型だけの検査と未登録Monsterではガード欠落を見逃す。実Monster/脅威ストアへ修復。 | 4.71→5.99 |
| F 539 | `TestCombatAggroHandler::test_aggro_skipped_when_target_not_actor` | 非アクター被弾者を無例外で無視。脅威ストアが空で発行イベントなしを確認。AutonomousBehaviorComponentガードとの重複は削除理由としない。 | 4.02→5.06 |
| R 578 | `TestCombatAggroHandler::test_aggro_store_receives_aggro_when_target_is_autonomous` | 被弾でMonster標的と脅威ストアの双方を更新。どちらかの保存忘れを検出。 | 6.47→7.64 |
| R 630 | `TestCombatAggroHandler::test_aggro_stored_with_current_tick_when_game_time_provider_injected` | 注入時計50で記録した脅威が59に残り61で失効。既定tick0誤用を検出。 | 5.62→5.75 |
| R 679 | `TestCombatAggroHandler::test_aggro_store_not_called_when_aggro_store_none` | 任意の脅威ストアがなくてもMonster標的更新を保存。構成互換性の独立契約。 | 5.61→7.24 |
| F 720 | `TestCombatAggroHandler::test_handle_hit_box_not_found` | 消滅HitBoxの脅威処理は無例外。実脅威ストアと発行イベントなしの確認へ。 | 1.45→2.08 |
| F 734 | `TestCombatAggroHandler::test_handle_map_not_found` | マップ消滅の脅威処理は無例外。HitBox実在、実脅威ストアと発行イベントなしの確認へ。 | 1.66→1.76 |
| F 759 | `TestCombatAggroHandler::test_handle_combatant_disappeared` | 被弾者消滅の脅威処理は無例外。所有者/HitBox実在、実脅威ストアと発行イベントなしの確認へ。 | 3.70→3.96 |
| R 786 | `TestCombatAggroHandler::test_handle_unexpected_exception_raises_system_error_exception` | リポジトリ障害を原因付きSystemErrorExceptionへ変換。正常フローでは届かない運用契約。 | 5.90→6.60 |
| R 855 | `TestMonsterDeathRewardHandler::test_grant_rewards_and_loot` | 死亡イベントから経験値・通貨・確定ドロップを保存。統合試験はアイテム報酬を検査しない。 | 2.96→3.56 |
| F 896 | `TestMonsterDeathRewardHandler::test_skip_rewards_when_no_killer` | 討伐者不在を無例外で無視。実プレイヤー/所持品を置き、報酬・アイテム・発行イベントなしを確認。 | 1.62→2.54 |
| R 917 | `TestMonsterDeathRewardHandler::test_handle_player_status_not_found` | 未知討伐者のPlayerNotFoundException。無条件成功や低層例外漏出を検出。 | 2.35→1.87 |
| R 935 | `TestMonsterDeathRewardHandler::test_handle_loot_table_not_found` | 未知ドロップ表をApplicationExceptionで報告。実プレイヤー/所持品あり、到達性を確保。 | 2.47→2.68 |
| R 976 | `TestMonsterDecidedToMoveHandler::test_handle_move_success` | 移動イベントから実マップ座標を保存。移動保存忘れを検出。 | 5.79→7.55 |
| R 1004 | `TestMonsterDecidedToMoveHandler::test_handle_map_not_found_skips` | 未知マップへの移動を無例外で無視しマップを新規作成しない。 | 1.59→1.78 |
| R 1020 | `TestMonsterDecidedToMoveHandler::test_handle_domain_exception_skips` | 移動禁止のドメイン例外を飲み込み、座標を保存変更しない。障害注入は外部依存境界で、検査動作を模倣していない。 | 4.05→5.19 |
| F 1090 | `TestMonsterDecidedToUseSkillHandler::test_handle_map_not_found_skips` | 未知マップで技能を実行しない。実モンスターと装備済み技能を用意し、MP20不変・HitBox不生成・装備未保存を確認。地図ガード削除が実サービスへ到達して失敗する。 | 2.53→5.17 |
| F 1106 | `TestMonsterDecidedToUseSkillHandler::test_handle_monster_not_found_skips` | 未知モンスターで技能を実行しない。マップは実在。HitBox不生成、装備未保存、確定イベントなしへ。 | 3.88→4.13 |
| R 1260 | `TestCombatIntegration::test_full_combat_to_reward_flow` | tick→衝突→同期イベント→死亡→経験値/通貨を実接続で検査。直接ハンドラでは検出できない配送退行の最終所有者。 | 15.92→17.39 |

### `test_monster_death_hunger_handler.py`

| 判定・元行 | 宣言 | 実際の保証・判断 | ms 前→後 |
| --- | --- | --- | --- |
| R 89 | `TestMonsterDeathHungerHandler::test_prey_kill_reduces_killer_hunger` | 獲物撃破の飢餓0.9→0.5を実リポジトリから確認。表形式の主所有者にする。 | 84.38→103.93 |
| F 151 | `TestMonsterDeathHungerHandler::test_skip_when_killer_world_object_id_none` | 討伐者識別子なしを無例外で無視。不要map fixtureを削除、実キラー飢餓不変を確認。未登録キラーも別行として残す。 | 3.44→2.96 |
| C 167 | `TestMonsterDeathHungerHandler::test_skip_when_spot_id_none` | 説明は場所なしでも飢餓低下だが実入力はキラー未登録で別ガードに停止。成功テストのspot_id=None行へ移し0.5を検査。旧未登録キラーの無例外は直前の表へ持ち越す。 | 1.69→4.55 |
| C 183 | `TestMonsterDeathHungerHandler::test_skip_when_dead_not_prey` | 非獲物で飢餓0.9不変の契約を成功テストのprey_races=ORC行へ移し、重複集約準備を除去。 | 4.41→3.76 |

### `test_monster_died_map_removal_handler.py`

| 判定・元行 | 宣言 | 実際の保証・判断 | ms 前→後 |
| --- | --- | --- | --- |
| R 82 | `TestMonsterDiedMapRemovalHandler::test_removes_dead_monster_object_from_map` | 死亡イベントでマップから対象を除去。実地図のget_object失敗が証拠。 | 7.99→7.24 |
| R 127 | `TestMonsterDiedMapRemovalHandler::test_skip_when_spot_id_none` | 場所不明イベントを無例外で無視。履歴上の後方互換契約であり無検証として削除しない。 | 3.40→2.58 |
| R 143 | `TestMonsterDiedMapRemovalHandler::test_skip_when_map_not_found` | 消滅マップを無例外で無視。Monsterが実在し想定ガードへ届く。 | 3.81→2.99 |

### `test_monster_spawned_map_placement_handler.py`

| 判定・元行 | 宣言 | 実際の保証・判断 | ms 前→後 |
| --- | --- | --- | --- |
| R 151 | `TestMonsterSpawnedMapPlacementHandler::TestHandleMonsterSpawnedEvent::test_places_object_on_map_with_component` | 出現イベントの座標、NPC種別、視野、技能情報を実マップへ写す。flee_thresholdを検証するとの説明は現行Componentに存在せず説明のみ是正。 | 13.16→16.24 |
| R 198 | `TestMonsterSpawnedMapPlacementHandler::TestHandleMonsterSpawnedEvent::test_handles_respawned_event_same_as_spawned` | 再出現イベントもマップ配置を行う。別イベント型の公開受付契約。 | 13.12→14.86 |
| R 237 | `TestMonsterSpawnedMapPlacementHandler::TestHandleMonsterSpawnedEvent::test_monster_not_found_raises` | 未知MonsterをID付き例外で通知。マップ実在で手前ガードに遮られない。 | 4.38→5.82 |
| R 253 | `TestMonsterSpawnedMapPlacementHandler::TestHandleMonsterSpawnedEvent::test_map_not_found_raises` | 未知マップをID付き例外で通知。Monster実在で手前ガードに遮られない。 | 2.10→2.79 |

未登録討伐者の受理を明示的に持ち越した `unknown-killer` は最終 2.68ms。元の場所なしケースが偶然見ていた契約を独立させた追加行であり、新しい製品機能ではない。

## 変異による検出力の確認

本体を計10種類、1種類ずつ意図的に壊し、変更前の試験と変更後の試験を同じ環境で比較した。各実行終了後に元のバイト列へ復元し、ハッシュ一致と生産差分なしを確認した。

| 変異 | 変更前 | 変更後の失敗理由 |
| --- | --- | --- |
| 非アクター攻撃者のガードを除去 | 成功 | 標的がNoneではなく500になる |
| 飢餓処理に場所なしを拒むガードを追加 | 成功 | 飢餓0.9が残り、期待0.5と不一致 |
| 死亡済みへの被弾ガードを除去 | 成功 | 実MonsterDamagedEventが追加発行される |
| 技能実行の地図不在ガードを除去 | 成功 | 実モンスター・実技能を経て、地図なしのまま実行しSystemErrorExceptionになる |
| 被弾の存在確認前に保存済みプレイヤーへ1ダメージ | 3件成功 | 消失3ケースすべてHP99を検出 |
| 脅威処理で入力イベントを再発行 | 4件成功 | 対象外／消失4ケースすべて発行履歴が空でなくなる |
| 討伐者不明の報酬を既存プレイヤーへ付与 | 成功 | 経験値50を検出 |
| 技能の存在確認前に空の装備を保存 | 2件成功 | 2ケースすべて禁止された保存を検出 |
| 不明／未登録討伐者の代わりに別モンスターの飢餓を更新 | 2件成功 | 2ケースすべて飢餓0.5を検出 |
| 被弾前の期限切れ効果除去を省略 | 失敗 | 公開プロパティへの置換後も同じ未除去効果を検出 |

先頭4種は直接のガード退行で、それぞれ以前の見逃しを検出した。次の5種は観測点が生きていることを確かめるための意図的な副作用注入であり、実在した製品不具合や自然に起きる変更と同一視しない。最後の1種は既存保証の維持を確認した。特に死亡済みのガード除去は実イベント発行まで通るため、「空に見えるだけの観測点」ではないことも確認できる。

## 保存レビュー

編集担当とは別の読み取りで元試験と残す試験を比較し、保証の喪失なしと確認した。討伐者の各条件、任意ストアなしの構成、イベント観測点の違い、変異後の本体復元と成功記録を確認した。追加で、技能の地図不在ケースを実モンスターと装備済み技能へ強化し、地図ガード削除で実サービスに到達することを再レビューした。

## 再実行と限界

標準環境では次で対象4ファイルを実行できる。

```bash
uv run --frozen pytest tests/application/world/handlers/test_combat_handlers.py tests/application/world/handlers/test_monster_death_hunger_handler.py tests/application/world/handlers/test_monster_died_map_removal_handler.py tests/application/world/handlers/test_monster_spawned_map_placement_handler.py
uv run --frozen pytest tests/application/world/handlers tests/application/world/services/test_world_simulation_service.py
uv run --frozen ruff check tests/application/world/handlers
```

今回の記録は同じpytest引数をネットワーク禁止の測定用起動器へ渡したもの。生ログ・JUnit・各ケースの3段階計時・変異対照は作業証拠へ保存した。外部API、実LLM、有料実験、全リポジトリCIの成功はこの記録から主張しない。

変異試験は網羅的ではない。技能の地図不在ケースは使用可能な技能を持つ実モンスターで独立性を確保し、無例外・MP不消費・HitBox不生成・装備未保存を確認する。

別途判断すること: タイル世界自体の継続・廃止、現行スポットグラフとの責務統合は今回のテスト監査だけでは決めない。基準で見つかった製品不具合はなく、製品修正の別コミットは不要。
