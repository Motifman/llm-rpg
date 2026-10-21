# 所持品の探索・復元・予約試験の監査

## 対象と基準

- 所有者: `src/ai_rpg_world/domain/player/aggregate/player_inventory_aggregate.py` の `PlayerInventoryAggregate` と `AvailableSlotLookup`
- 基準: `ba942f5a9cad4b6d362c9e2ce59566cc8ce3396f`。ローカルでは同じ内容を再構成した `d2a11ae023ad55ff0dc5b0dcf9864cd88e43d2d0` を使用
- 対象4ファイル81宣言は、入力と検査内容を含めて全件読解。基準の実行結果は81件成功、失敗なし
- 集約本体634行、値オブジェクト、イベント、呼出先と実行入口、関連試験、履歴を確認。製品コードは変更しない
- 編集前の全宣言台帳と移管計画を別の読解で照合し、編集後に失われた検査がないか確認した

| 元のファイル（`tests/domain/player/aggregate/`） | 行数 | 宣言 | 基準結果 |
|---|---:|---:|---|
| `test_find_slot_skips_reserved.py` | 130 | 6 | 6件成功 |
| `test_player_inventory_aggregate.py` | 829 | 48 | 48件成功 |
| `test_player_inventory_iter_slots.py` | 274 | 15 | 15件成功 |
| `test_player_inventory_reservation.py` | 158 | 12 | 12件成功 |

## 判断と移管

- R（保持）55、F（契約を保持して検査を修復）16、C（保持先へ統合）9、D（契約を検査していない試験を削除）1
- `test_find_slot_skips_reserved.py` の6宣言を、既存の `test_player_inventory_iter_slots.py` へ統合。未所持、予約だけで見つからない状態、未予約の同品目、鮮度の一致と不一致を残す
- 探索の戻り値は `found`、`slot_id`、`item_instance_id`、`blocked_by_reservation` の4項目を確認する。枠と品が食い違った結果は、存在判定だけでは見つからない
- 取得済みの品が消えたことや、列挙された枠の対応・順序を、公開APIの結果で確認する。新規作成の昇順を検査し、任意順に与えた復元辞書へ昇順は要求しない
- 私有の検証メソッドの再演は公開 `restore_from_data` に集める。疎な辞書と容量ちょうどの枠番号は独立した境界なので残す
- 予約不整合の設定は私有辞書を書き換えず、同じ品100が予約集合にあり、全所持枠から消えた保存状態を `restore_from_data` で作る
- `test_validate_equipment_slots_extra_types` は余分なキーを渡さず `pass` するだけだったため削除する。新たに余分な装備種別の仕様を作る変更はしない
- 公開照会、既定値、空と満杯、イベント順序の試験は保持する。ソース内の私有辞書参照を禁止する既存試験も、動作試験とは別の設計契約として保持する

### 入力差を確認した内容

- 予約探索の容量4と5はいずれも1個または2個しか持たず、容量境界を作っていない。品目10と101、品100と7001はどちらも有効な識別値で、今回の分岐に差はない
- 空の所持品・空の見た目写像は鮮度不一致と異なる入力なので、`empty-inventory` 行として残す
- 元の腐敗品への新鮮要求と腐敗要求は、`spoiled-is-not-fresh` と `spoiled-match` の両行で残す。既存の新鮮品への腐敗要求も残す
- 容量5、枠0=品100、枠5=品200という私有検証の入力は、そのまま復元拒否の `at-capacity` 行へ移す。既存の容量10・枠0〜14の入力も保持する
- 有効な疎辞書は枠0=品100、枠2=品200、枠4=Noneを維持。復元後の枠0/2の品、省略枠1/3と明示空枠4のNoneを公開照会する
- 装備の有効辞書は両方とも全列挙値を持ち、武器と防具だけが占有。値100/200と300/400の違いは検証に影響しない。欠損辞書はいずれも武器/兜の2キーだけ。検証は値を読まずキーの集合だけを見る

## 保持先と実呼出

探索・列挙の保持先は `test_player_inventory_iter_slots.py`、復元・状態遷移は `test_player_inventory_aggregate.py`、予約状態遷移は `test_player_inventory_reservation.py`。下の表は同名の別集約の呼出を除き、実際に所持品集約を受け取る場所を確認したもの。

| メソッド | 確認した非試験の呼出先 |
|---|---|
| `_validate_equipment_slots` | `src/ai_rpg_world/domain/player/aggregate/player_inventory_aggregate.py:99（__init__経由）` |
| `_validate_inventory_slots` | `src/ai_rpg_world/domain/player/aggregate/player_inventory_aggregate.py:87（__init__経由）` |
| `acquire_item` | `src/ai_rpg_world/application/world_graph/spot_graph_item_transfer_service.py:474,641` / `src/ai_rpg_world/application/trade/services/trade_command_service.py:215` |
| `complete_equip_item` | 現行の `src` に呼出元を確認できない。公開APIの契約として保持 |
| `complete_inventory_compaction` | 現行の `src` に呼出元を確認できない。公開APIの契約として保持 |
| `create_new_inventory` | 現行の `src` に呼出元を確認できない。公開APIの契約として保持 |
| `drop_item` | `src/ai_rpg_world/application/world/services/drop_item_service.py:106` |
| `find_available_slot_by_item_spec_id_and_spoilage` | `src/ai_rpg_world/application/llm/services/executors/spot_graph_tool_executor.py:471,497` / `src/ai_rpg_world/application/trade/services/trade_freeze_service.py:110` |
| `find_slot_by_item_spec_id` | 現行の `src` に呼出元を確認できない。公開APIの契約として保持 |
| `find_slot_by_item_spec_id_and_spoilage` | 現行の `src` に呼出元を確認できない。公開APIの契約として保持 |
| `get_inventory_summary` | `src/ai_rpg_world/application/world_graph/spot_inventory_helpers.py:243,267` |
| `get_item_instance_id_by_equipment_slot` | `src/ai_rpg_world/infrastructure/repository/sqlite_trade_command_codec.py:156` / `src/ai_rpg_world/application/world_graph/spot_inventory_helpers.py:40` |
| `get_item_instance_id_by_slot` | `src/ai_rpg_world/infrastructure/repository/sqlite_trade_command_codec.py:152` / `src/ai_rpg_world/application/world_graph/spot_inventory_helpers.py:33,86,149` |
| `has_item` | `src/ai_rpg_world/application/world/services/chest_command_service.py:118` |
| `is_inventory_full` | `src/ai_rpg_world/application/world_graph/spot_graph_item_transfer_service.py:469,628` / `src/ai_rpg_world/application/trade/services/trade_command_service.py:193` |
| `is_item_reserved` | `src/ai_rpg_world/application/world_graph/spot_inventory_helpers.py:92,115,152` |
| `iter_occupied_slots` | `src/ai_rpg_world/application/world_graph/spot_inventory_helpers.py:55,112` / `src/ai_rpg_world/application/inventory/services/player_inventory_query_service.py:30` |
| `iter_slots` | `src/ai_rpg_world/application/world_graph/spot_graph_merchant_trade_service.py:479` |
| `move_item` | 現行の `src` に呼出元を確認できない。公開APIの契約として保持 |
| `remove_item` | `src/ai_rpg_world/application/world_graph/spot_inventory_helpers.py:155` |
| `remove_item_for_placement` | `src/ai_rpg_world/application/llm/services/executors/spot_graph_tool_executor.py:1356` / `src/ai_rpg_world/application/world/services/place_object_service.py:183` |
| `remove_item_for_storage` | `src/ai_rpg_world/application/world_graph/spot_graph_item_transfer_service.py:360,636` / `src/ai_rpg_world/application/world/handlers/item_stored_in_chest_handler.py:50` |
| `remove_reserved_item` | `src/ai_rpg_world/application/trade/services/trade_command_service.py:205` / `src/ai_rpg_world/application/quest/services/quest_progress_reaction_service.py:264` |
| `request_equip_item` | 現行の `src` に呼出元を確認できない。公開APIの契約として保持 |
| `request_inventory_compaction` | 現行の `src` に呼出元を確認できない。公開APIの契約として保持 |
| `request_inventory_sort` | 現行の `src` に呼出元を確認できない。公開APIの契約として保持 |
| `reserve_item` | `src/ai_rpg_world/application/trade/services/trade_command_service.py:94` / `src/ai_rpg_world/application/trade/services/trade_freeze_service.py:115` |
| `restore_from_data` | `src/ai_rpg_world/infrastructure/repository/sqlite_player_state_codec.py:58` / `src/ai_rpg_world/infrastructure/repository/sqlite_trade_command_codec.py:177` / `src/ai_rpg_world/application/being/world_subsystems/player_inventory_codec.py:140` |
| `unequip_item` | 現行の `src` に呼出元を確認できない。公開APIの契約として保持 |
| `unreserve_item` | `src/ai_rpg_world/application/trade/services/trade_command_service.py:286,337` / `src/ai_rpg_world/application/trade/services/trade_freeze_service.py:141` |

`complete_equip_item`、`complete_inventory_compaction`、`find_slot_by_item_spec_id`、鮮度だけを指定する探索など、現行の呼出元が見つからなかった公開APIも、この試験限定の変更で撤去しない。私有検証は集約の初期化から到達し、永続化の復元処理も同じ入口を使う。

## 履歴と保持する設計検査

- [集約の祖先導入（99b0d4b）](https://github.com/Motifman/llm-rpg/commit/99b0d4bc34dd33b0cc9dbd17575c9774cb85067e) は `InventorySlots` / `PlayerInventoryId` 時代の由来。現行の復元試験や私有検証試験の導入を直接証明するものとは扱わない
- [予約導入（3f3e4fe）](https://github.com/Motifman/llm-rpg/commit/3f3e4fe07444fb324f6a32c4af3131ea559d7bb3) は予約状態・操作拒否・不整合解除試験を追加。同時点の [集約試験](https://github.com/Motifman/llm-rpg/blob/3f3e4fe07444fb324f6a32c4af3131ea559d7bb3/tests/domain/player/aggregate/test_player_inventory_aggregate.py) に、現行の私有検証、空の試験、整理設定が存在することも確認。これらの正確な初出コミットは未特定
- [公開走査APIの導入（fed26ae、#386）](https://github.com/Motifman/llm-rpg/commit/fed26ae6664ea65ec78de06ebd7bb1a8040bcdcf) は、存在しない `inv.slots` 参照で全使用が失敗した事故への対策。公開APIを通し、私有辞書への依存を戻さない意図を明示している
- [予約品を消費対象から除外（f583f76）](https://github.com/Motifman/llm-rpg/commit/f583f76655d9757f511f1375383908f3023626e1) で予約回避探索と、今回統合する6宣言を導入
- [見た目写像への移行（e9a3402、#1180）](https://github.com/Motifman/llm-rpg/commit/e9a34024110ace40f80ade91b6c4a38119c71ef7) で、両探索試験を現在の `InventoryItemAppearance` 入力に変更

`test_executor_inv_inventory_slots` は特定の綴りに依存する弱点がある。しかし、実 `run_turn` で使用が成功することと「私有辞書へ依存しない」ことは別契約である。初稿の削除案を撤回し、Rとして保持した。新しい構文解析器や製品の検査専用入口は追加しない。

## 全81宣言の台帳

行番号は編集前の基準を示す。全行の製品所有者は `PlayerInventoryAggregate`。上記メソッド別の呼出先と履歴を共通の根拠とする。R/Fは同じ名前の試験が保持先（改名は注記）、Cは表の保持先へ検査を先に移し、Dは検査していない主張を削除する。危険度は低いが、入力差・戻り値・例外型を独立確認し、下記の変異と実行結果で保存を確かめた。製品の検査専用入口の削除はなく、重複ファイルの補助関数2個を撤去する。

### test_find_slot_skips_reserved.py

| 判定 | 元の宣言・行 | 実際の契約と検出する故障 | 保持先・変更 |
|---|---|---|---|
| C | `TestReservedItemsAreNotOffered.test_an_unreserved_item_is_found`:50 | 未予約一致でslot!=None/blocked=False。容量5/ID100/spec10は既存容量4/ID7001/spec101と同じ分岐で非境界値。結果4項目を残す | test_player_inventory_iter_slots.py::TestFindAvailableSlotByItemSpecIdAndSpoilage.test_returns_unreserved_matching_slot |
| C | `TestReservedItemsAreNotOffered.test_a_reserved_item_is_not_returned`:62 | 予約一致でslot=None。全予約保持試験のfound=Falseに加えslot=Noneを明示移管 | test_player_inventory_iter_slots.py::TestFindAvailableSlotByItemSpecIdAndSpoilage.test_all_matches_reserved_reports_blocked |
| C | `TestReservedItemsAreNotOffered.test_the_reason_says_it_is_reserved`:74 | 同じ予約1個設定でblocked=Trueだけ。全予約保持試験が既に持つ | test_player_inventory_iter_slots.py::TestFindAvailableSlotByItemSpecIdAndSpoilage.test_all_matches_reserved_reports_blocked |
| C | `TestReservedItemsAreNotOffered.test_not_owning_it_is_not_reported_as_reserved`:89 | 空の所持品/空写像のslot=None/blocked=False。既存保持試験は腐敗不一致なので空行を追加移管 | test_player_inventory_iter_slots.py::TestFindAvailableSlotByItemSpecIdAndSpoilage.test_lookup_distinguishes_absence_from_spoilage（空入力行） |
| C | `TestReservedItemsAreNotOffered.test_an_unreserved_copy_is_preferred_over_a_reserved_one`:101 | 同spec2個の先頭予約でslot1/blocked=False。既存保持試験へID結果もまとめる | test_player_inventory_iter_slots.py::TestFindAvailableSlotByItemSpecIdAndSpoilage.test_prefers_unreserved_when_one_of_two_is_reserved |
| C | `TestReservedItemsAreNotOffered.test_spoilage_is_still_matched`:114 | 腐敗1個の新鮮要求でNone、腐敗要求で存在。既存保持試験は逆向き否定のみなので腐敗肯定と反対向き否定を移管 | test_player_inventory_iter_slots.py::TestFindAvailableSlotByItemSpecIdAndSpoilage.test_lookup_distinguishes_absence_from_spoilage（腐敗不一致/一致の対照行） |

### test_player_inventory_aggregate.py

| 判定 | 元の宣言・行 | 実際の契約と検出する故障 | 保持先・変更 |
|---|---|---|---|
| R | `TestPlayerInventoryAggregate.test_create_new_inventory`:98 | 新規作成の所有者・容量・全所持枠/装備枠の空状態・未発行イベントを守る。初期品混入、容量無視、初期イベント発火を検出 | 同じ宣言を保持 |
| R | `TestPlayerInventoryAggregate.test_restore_from_data`:124 | 保存値から所持枠と装備枠、空き、所有者/容量を復元しイベントを出さない。復元時の品の喪失・誤配置を検出 | 同じ宣言を保持 |
| F | `TestPlayerInventoryAggregate.test_restore_from_data_invalid_inventory_slots`:162 | 容量10に対するslot10..14の復元を拒む。上限検査欠落を検出。slot==maxの小さい疎辞書ケースを私有検査から追加 | 同じ宣言を修復 |
| R | `TestPlayerInventoryAggregate.test_restore_from_data_invalid_equipment_slots`:179 | 装備2種だけの保存データを復元時に拒む。装備集合の検証欠落を検出 | 同じ宣言を保持 |
| R | `TestPlayerInventoryAggregate.test_get_item_instance_id_by_slot_normal`:200 | 離れたslot0/5の正しいIDと空slot1のNoneを公開照会で返す。所持枠照会の取り違えを検出 | 同じ宣言を保持 |
| R | `TestPlayerInventoryAggregate.test_get_item_instance_id_by_slot_invalid_slot`:210 | 容量10の外slot15を照会した際のInvalidSlotException。範囲外を欠損扱いする退行を検出 | 同じ宣言を保持 |
| R | `TestPlayerInventoryAggregate.test_get_item_instance_id_by_equipment_slot`:217 | WEAPON/ARMORのIDとHELMETの空を公開照会する。装備と所持の照会混同を検出 | 同じ宣言を保持 |
| R | `TestPlayerInventoryAggregate.test_acquire_item_normal`:230 | 最初の空き枠に入手し正しい所有者/IDのItemAddedを1件発行。未配置や誤イベントを検出 | 同じ宣言を保持 |
| R | `TestPlayerInventoryAggregate.test_acquire_item_inventory_full`:247 | 満杯入手でInventorySlotOverflowを正しい品/理由で1件発行。満杯を成功入手扱いする退行を検出 | 同じ宣言を保持 |
| R | `TestPlayerInventoryAggregate.test_move_item_normal`:268 | 0→3の移動後に元枠が空、無関係slot2の品は維持、イベント無し。複製や周辺枠消去を検出 | 同じ宣言を保持 |
| R | `TestPlayerInventoryAggregate.test_move_item_same_slot`:287 | 同一枠移動をInvalidSlotで拒否。同一キーの上書きで品が消える退行を検出 | 同じ宣言を保持 |
| R | `TestPlayerInventoryAggregate.test_move_item_from_empty_slot`:296 | 空枠から移動をItemNotInSlotで拒否。存在しない品の移動成功を検出 | 同じ宣言を保持 |
| R | `TestPlayerInventoryAggregate.test_move_item_to_occupied_slot`:303 | 占有先へ移動をInvalidSlotで拒否。先の品の上書き消失を検出 | 同じ宣言を保持 |
| R | `TestPlayerInventoryAggregate.test_drop_item_normal`:312 | 指定品だけを除き正しいslot/所有者/品のDroppedを1件発行。隣接品削除や誤った観測材料を検出 | 同じ宣言を保持 |
| R | `TestPlayerInventoryAggregate.test_remove_item_empties_the_slot_and_is_not_a_drop`:332 | 効果による除去で指定品だけを除きRemovedだけ1件。消費を自発的廃棄と誤伝達する退行を検出 | 同じ宣言を保持 |
| R | `TestPlayerInventoryAggregate.test_remove_item_from_empty_slot_raises`:345 | 空枠除去をItemNotInSlotで拒み無イベント。空操作から観測が出る退行を検出 | 同じ宣言を保持 |
| R | `TestPlayerInventoryAggregate.test_drop_item_from_empty_slot`:353 | 空枠廃棄のItemNotInSlot。存在しない廃棄成功を検出 | 同じ宣言を保持 |
| R | `TestPlayerInventoryAggregate.test_request_equip_item_normal`:360 | 装備要求の所有者/元slot/品/対象部位を1件発行。装備操作ハンドラへ誤対象を渡す退行を検出 | 同じ宣言を保持 |
| R | `TestPlayerInventoryAggregate.test_request_equip_item_from_empty_slot`:377 | 空枠装備要求をItemNotInSlotで拒否。空アイテム要求イベントを検出 | 同じ宣言を保持 |
| R | `TestPlayerInventoryAggregate.test_complete_equip_item_normal`:384 | 所持から装備へ移し正しいfrom/to/品イベント1件。複製・装備先間違いを検出 | 同じ宣言を保持 |
| R | `TestPlayerInventoryAggregate.test_complete_equip_item_with_replacement_has_space`:410 | 装備交換で旧品を空きslot1に戻し新装備のイベント1件。旧品喪失や二重イベントを検出 | 同じ宣言を保持 |
| F | `TestPlayerInventoryAggregate.test_complete_equip_item_with_replacement_inventory_full`:439 | 満杯交換で旧装備のoverflow→新装備イベントの順序を守る。旧品の無通知消失を検出。ただし元slot0=1000なのに入力100なので実在IDへ修復 | 同じ宣言を修復 |
| R | `TestPlayerInventoryAggregate.test_unequip_item_normal`:472 | 装備解除で最初の空きへ戻し元部位/先slot/品を通知。重複や通知先の誤りを検出 | 同じ宣言を保持 |
| R | `TestPlayerInventoryAggregate.test_unequip_item_empty_slot`:493 | 空装備解除をItemNotInSlotで拒否。空解除の成功を検出 | 同じ宣言を保持 |
| R | `TestPlayerInventoryAggregate.test_unequip_item_inventory_full`:500 | 満杯解除で装備を空にしoverflow→unequipped(to=None)を発行。品の無通知消失を検出 | 同じ宣言を保持 |
| R | `TestPlayerInventoryAggregate.test_is_inventory_full`:530 | 空/満杯の公開判定を守る。購入前の空きガードが逆転する退行を検出 | 同じ宣言を保持 |
| R | `TestPlayerInventoryAggregate.test_get_inventory_summary`:544 | 5枠中2品/装備2の集計項目を検査。所持と装備の二重集計や空き数誤りを検出 | 同じ宣言を保持 |
| R | `TestPlayerInventoryAggregate.test_get_inventory_summary_full_inventory`:565 | 満杯集計の0空き、非空、満杯表示。境界だけのオフバイワンを検出 | 同じ宣言を保持 |
| R | `TestPlayerInventoryAggregate.test_get_inventory_summary_empty_inventory`:581 | 空集計の全空き、空、非満杯表示。空状態のフラグ逆転を検出 | 同じ宣言を保持 |
| R | `TestPlayerInventoryAggregate.test_request_inventory_compaction`:593 | 整理要求1件に正しい所有者を載せる。要求を落とす退行を検出 | 同じ宣言を保持 |
| F | `TestPlayerInventoryAggregate.test_complete_inventory_compaction`:605 | 整理済み配置の反映と無イベントを守る。現設定は全空から追加だけなので、移動元の占有枠消去を守る設定へ修復 | 同じ宣言を修復 |
| R | `TestPlayerInventoryAggregate.test_request_inventory_sort`:629 | 指定ITEM_TYPEの整理イベントに所有者を載せる。明示引数の取り落としを検出 | 同じ宣言を保持 |
| R | `TestPlayerInventoryAggregate.test_request_inventory_sort_default_criteria`:642 | 省略時ITEM_TYPEを1件発行。既定値が変わる退行を検出 | 同じ宣言を保持 |
| F | `TestPlayerInventoryAggregate.test_validate_inventory_slots_valid`:654 | 疎なslot0/2/4の辞書を許可。完全な辞書しか許さない退行を検出できるので公開restoreに書き換えて保存結果を照会 | TestPlayerInventoryAggregate.test_restore_from_sparse_inventory_slots |
| C | `TestPlayerInventoryAggregate.test_validate_inventory_slots_invalid_range`:671 | 容量5でslot5を拒否。等号境界の見逃しを検出。公開restoreへ同じ入力/例外を移管 | test_player_inventory_aggregate.py::TestPlayerInventoryAggregate.test_restore_from_data_invalid_inventory_slots（容量5/slot5の行） |
| C | `TestPlayerInventoryAggregate.test_validate_equipment_slots_valid`:684 | 全装備種別+WEAPON100/ARMOR200を私有検査へ渡して例外無しを見る。既存restoreの全種別+WEAPON300/ARMOR400が同契約を既に検査 | test_player_inventory_aggregate.py::TestPlayerInventoryAggregate.test_restore_from_data |
| C | `TestPlayerInventoryAggregate.test_validate_equipment_slots_missing_types`:700 | WEAPON100/HELMET200だけの辞書を私有検査で拒否。restore側の同キー2種(None値)拒否と同じ検査。検証は値を読まずkeysのみ | test_player_inventory_aggregate.py::TestPlayerInventoryAggregate.test_restore_from_data_invalid_equipment_slots |
| D | `TestPlayerInventoryAggregate.test_validate_equipment_slots_extra_types`:714 | 集約作成後passのみで余分な装備種別を与えていない。主張する契約を全く検査していない | 検査無しで契約の証明が存在しない。全種別受理/欠損拒否のrestore試験は保持 |
| R | `TestPlayerInventoryAggregate.test_event_accumulation_multiple_operations`:723 | 取得2件/廃棄/装備要求/整理/ソートの6件を順番/品つきで保持。複数操作で前イベントを上書きする退行を検出 | 同じ宣言を保持 |
| R | `TestPlayerInventoryAggregate.test_event_clearing`:758 | 取得イベントをclear後再取得できる。clearが永続的に通知を止める退行を検出 | 同じ宣言を保持 |
| R | `TestPlayerInventoryAggregate.test_has_item_in_inventory`:774 | 所持枠の保有/未保有IDを判定。装備だけを見る誤実装を検出 | 同じ宣言を保持 |
| R | `TestPlayerInventoryAggregate.test_has_item_in_equipment`:780 | 装備枠の保有/未保有IDを判定。所持枠だけを見る誤実装を検出 | 同じ宣言を保持 |
| R | `TestPlayerInventoryAggregate.test_remove_item_for_storage_success`:786 | 収納による除去は所持/枠から消えイベント無し。収納と廃棄の二重通知を検出 | 同じ宣言を保持 |
| R | `TestPlayerInventoryAggregate.test_remove_item_for_storage_raises_when_not_in_slot`:795 | 非所持ID収納をItemNotInSlotで拒否。誤った成功を検出 | 同じ宣言を保持 |
| R | `TestPlayerInventoryAggregate.test_remove_item_for_storage_raises_when_reserved`:801 | 予約品収納をItemReservedで拒否。取引品を別保管へ逃がす退行を検出 | 同じ宣言を保持 |
| R | `TestPlayerInventoryAggregate.test_remove_item_for_placement_success`:808 | 設置で元枠を空にし削除IDを返し無イベント。別品設置や二重通知を検出 | 同じ宣言を保持 |
| R | `TestPlayerInventoryAggregate.test_remove_item_for_placement_raises_when_empty_slot`:818 | 空枠設置をItemNotInSlotで拒否。架空の設置を検出 | 同じ宣言を保持 |
| R | `TestPlayerInventoryAggregate.test_remove_item_for_placement_raises_when_reserved`:824 | 予約品設置をItemReservedで拒否。取引品を消費する退行を検出 | 同じ宣言を保持 |

### test_player_inventory_iter_slots.py

| 判定 | 元の宣言・行 | 実際の契約と検出する故障 | 保持先・変更 |
|---|---|---|---|
| F | `TestIterSlots.test_all_slot_order_yield`:62 | 初期3枠すべてのNoneを検査するがslotも順序も見ない。正確な(SlotId,None)列を期待し、重複slot/逆順の退行を検出する | 同じ宣言を修復 |
| F | `TestIterSlots.test_includes_empty_slot`:72 | 1品を含む4枠の件数と占有数を検査するが対応位置を見ない。正確な混在列で空slot欠落・位置誤りを検出する | 同じ宣言を修復 |
| F | `TestIterOccupiedSlots.test_item_slot_yield`:87 | 占有2件のID集合は見るがslotと順序を見ない。正確な組列へ修復して品を誤slotに渡す退行を検出 | 同じ宣言を修復 |
| R | `TestIterOccupiedSlots.test_empty_inventory_empty_iter`:97 | 空所持品の占有列挙が空。None混入を検出 | 同じ宣言を保持 |
| F | `TestFindSlotByItemSpecId.test_returns_slot_id_iid`:106 | spec一致のIDは見るがslotを無視。正確な組で一致品のslot取り違えを検出 | 同じ宣言を修復 |
| F | `TestFindSlotByItemSpecIdAndSpoilage.test_returns_spoiled_slot_when_same_spec_has_fresh_and_spoiled`:120 | 同一specの新鮮品を飛ばして腐敗品IDを返す。slotも確認し腐敗品を指定したのに新鮮slotを返す退行を検出 | 同じ宣言を修復 |
| F | `TestFindSlotByItemSpecIdAndSpoilage.test_returns_fresh_slot_when_same_spec_has_fresh_and_spoiled`:138 | 同一specの新鮮IDを返す。slotも確認し品と枠が食い違う退行を検出 | 同じ宣言を修復 |
| R | `TestFindSlotByItemSpecIdAndSpoilage.test_none`:156 | spec999が無いとNone。異なる品目を返す退行を検出。実際は腐敗無しAPIの試験なので対応クラスへ移動 | TestFindSlotByItemSpecId.test_none |
| R | `TestFindSlotByItemSpecIdAndSpoilage.test_aggregate_orphan_skip_none`:165 | 見た目写像に品IDが無くてもNone。欠損照会がKeyErrorになる退行を検出。対応クラスへ移動 | TestFindSlotByItemSpecId.test_aggregate_orphan_skip_none |
| F | `TestFindSlotByItemSpecIdAndSpoilage.test_returns_match`:174 | 同spec2件で先に取得したIDを選ぶ。slotも検査し返却対の誤りを検出、対応クラスへ移動 | TestFindSlotByItemSpecId.test_returns_match |
| F | `TestFindAvailableSlotByItemSpecIdAndSpoilage.test_returns_unreserved_matching_slot`:193 | 未予約一致のfound/blocked/IDを検査。slotを追加して消費対象の誤指定を検出し重複元を吸収 | 同じ宣言を修復 |
| F | `TestFindAvailableSlotByItemSpecIdAndSpoilage.test_all_matches_reserved_reports_blocked`:207 | 全一致予約時found=False/blocked=True。slotとIDがNoneも検査し消費不能品を返す退行を検出 | 同じ宣言を修復 |
| F | `TestFindAvailableSlotByItemSpecIdAndSpoilage.test_prefers_unreserved_when_one_of_two_is_reserved`:221 | 先頭予約を飛ばしてslot1/found=True/blocked=False。IDを追加し予約品IDを漏らす退行を検出 | 同じ宣言を修復 |
| F | `TestFindAvailableSlotByItemSpecIdAndSpoilage.test_no_match_is_not_blocked`:240 | 現在は非予約新鮮1個に腐敗要求する入力のみ。空入力と腐敗不一致→一致の両制御を移管し全4結果項目を検査 | TestFindAvailableSlotByItemSpecIdAndSpoilage.test_lookup_distinguishes_absence_from_spoilage |
| R | `TestPrivateAccessRemoval.test_executor_inv_inventory_slots`:260 | 特定ファイルのinv._inventory_slots文字列だけを拒否。名前依存で元故障inv.slotsも別名私有属性へのアクセスも見逃すが、#386で明示された私有辞書依存を戻さない設計契約は実run_turnと別なので保持する | 同じ宣言を保持 |

### test_player_inventory_reservation.py

| 判定 | 元の宣言・行 | 実際の契約と検出する故障 | 保持先・変更 |
|---|---|---|---|
| R | `TestPlayerInventoryReservation.test_reserve_item_success`:40 | 予約の戻りID/予約状態/Reservedイベント対象。予約が状態だけ又は通知だけになる退行を検出 | 同じ宣言を保持 |
| R | `TestPlayerInventoryReservation.test_reserve_item_already_reserved`:54 | 同品再予約をItemAlreadyReservedで拒否。重複予約を検出 | 同じ宣言を保持 |
| R | `TestPlayerInventoryReservation.test_reserve_empty_slot`:61 | 空枠予約をItemNotInSlotで拒否。架空予約を検出 | 同じ宣言を保持 |
| R | `TestPlayerInventoryReservation.test_unreserve_item_success`:66 | 予約解除で状態falseとCancelled対象イベント。解除漏れを検出 | 同じ宣言を保持 |
| R | `TestPlayerInventoryReservation.test_remove_reserved_item_success`:81 | 成約除去で枠空/予約解除/Removed発行、Dropped無し。品・予約残留や自発廃棄誤通知を検出 | 同じ宣言を保持 |
| R | `TestPlayerInventoryReservation.test_remove_non_reserved_item`:98 | 未予約品の成約除去をItemNotReservedで拒否。不正な決済を検出 | 同じ宣言を保持 |
| R | `TestPlayerInventoryReservation.test_drop_reserved_item_should_fail`:105 | 予約品廃棄をItemReservedで拒否。取引品の消失を検出 | 同じ宣言を保持 |
| R | `TestPlayerInventoryReservation.test_move_reserved_item_should_fail`:112 | 予約品移動をItemReservedで拒否。予約対象のslot変動を検出 | 同じ宣言を保持 |
| R | `TestPlayerInventoryReservation.test_equip_reserved_item_should_fail`:119 | 予約品の装備要求をItemReservedで拒否。取引品の装備を検出 | 同じ宣言を保持 |
| R | `TestPlayerInventoryReservation.test_complete_equip_reserved_item_should_fail`:126 | 予約品の装備確定をItemReservedで拒否。要求後予約された品の装備を検出 | 同じ宣言を保持 |
| F | `TestPlayerInventoryReservation.test_remove_reserved_item_not_in_slot`:134 | 予約集合にあるが枠にない品の成約除去はItemNotInSlot+予約解除。私有属性の直接書換えを公開restore入力へ置換して不整合保存データの契約を保持 | 同じ宣言を修復 |
| R | `TestPlayerInventoryReservation.test_unreserve_non_reserved_item`:149 | 未予約品解除はfalseのまま無イベント。再試行で架空解除通知が出る退行を検出 | 同じ宣言を保持 |

## 変異による保存確認

一度に一つだけ所有者の処理を意図的に壊し、対象の保持試験が落ちることを確認。構文エラーや収集エラーはなく、すべて対象の検査で失敗した。毎回元のソースへ戻し、最後にバイト同一を検査した。下記のうち10種類は旧試験では成功し、修復後だけが失敗する対照も採った。

| 変異 | 対象 | 修復後の失敗数 | 旧試験の対照 |
|---|---|---:|---|
| `at-capacity` | `_validate_inventory_slots` | 1 | 保存する既存契約なので比較省略 |
| `sparse-getter` | `get_item_instance_id_by_slot` | 1 | 成功（見逃す） |
| `equipment-valid` | `_validate_equipment_slots` | 1 | 保存する既存契約なので比較省略 |
| `equipment-missing` | `_validate_equipment_slots` | 1 | 保存する既存契約なので比較省略 |
| `all-slot-order` | `iter_slots` | 2 | 成功（見逃す） |
| `occupied-slot-pair` | `iter_occupied_slots` | 1 | 成功（見逃す） |
| `spec-slot-pair` | `find_slot_by_item_spec_id` | 2 | 成功（見逃す） |
| `spoilage-slot-pair` | `find_slot_by_item_spec_id_and_spoilage` | 2 | 成功（見逃す） |
| `available-slot-pair` | `find_available_slot_by_item_spec_id_and_spoilage` | 1 | 成功（見逃す） |
| `blocked-id-leak` | `find_available_slot_by_item_spec_id_and_spoilage` | 1 | 成功（見逃す） |
| `preferred-id-leak` | `find_available_slot_by_item_spec_id_and_spoilage` | 1 | 成功（見逃す） |
| `blocked-reason` | `find_available_slot_by_item_spec_id_and_spoilage` | 1 | 保存する既存契約なので比較省略 |
| `empty-reason` | `find_available_slot_by_item_spec_id_and_spoilage` | 1 | 保存する既存契約なので比較省略 |
| `spoilage-mismatch` | `find_available_slot_by_item_spec_id_and_spoilage` | 2 | 保存する既存契約なので比較省略 |
| `spoilage-positive` | `find_available_slot_by_item_spec_id_and_spoilage` | 1 | 保存する既存契約なので比較省略 |
| `reserved-exclusion` | `find_available_slot_by_item_spec_id_and_spoilage` | 2 | 保存する既存契約なので比較省略 |
| `equip-original-slot` | `complete_equip_item` | 1 | 成功（見逃す） |
| `compaction-clear` | `complete_inventory_compaction` | 1 | 成功（見逃す） |
| `reservation-cleanup` | `remove_reserved_item` | 1 | 保存する既存契約なので比較省略 |

## 実行結果と差分

- 基準: 対象4ファイル81件成功。関連の実行経路2ファイル27件成功
- 候補: 所持品3ファイル75件と関連27件、計102件成功
- 変異復元後: `tests/domain/player` 全体と `tests/demos/test_item_tools_end_to_end.py`、`tests/demos/test_offered_items_cannot_be_spent.py`、計545件成功。これは関連検証の範囲であり、他の宣言まで監査完了と数えない
- 実LLMを呼ばず、外向き通信を遮断し、資格情報を除いた環境で実行。各実行で対象作業ツリーの `src` を読み込んでいることを確認
- 変更する試験3ファイルの `ruff check` と `git diff --check` は成功
- `ruff format --check` は基準・候補とも3ファイルが未整形。現行CIは `ruff check` が検査で、書式再整形は要求していない。既存関数全体の無関係な折り返しや空白変更を避け、今回の変更境界の空行だけ調整した
- `pytest.ini` と `.github/workflows/ci.yml` は対象を自動収集するため経路表の更新なし。品質確認用・実API用の試験は通常実行から除外されたまま
- 元の試験1391行 → 1224行（167行減）。うち上位補助関数の定義は106行 → 91行。この補助関数行数は試験行数に含まれるので二重計上しない
- 元81宣言 → 71宣言、入力表展開後75件。製品コードの変更0行
- リポジトリ全体の試験とCIは、この文書のローカル実行結果に含めない。公開後に対象コミットのCI結果を別に確認する

## 別件として残す製品挙動

満杯装備の元試験は、所持枠0の品が1000なのに未所持の100を `complete_equip_item` に渡し、成功することを前提にしていた。今回の設定は実在する1000へ直し、元枠が空になることと旧装備のあふれ通知→新装備通知を確認する。製品側には品IDと元枠の一致を確かめる処理がなく、その挙動は変更していない。現行 `src` にこの確定メソッドの非試験呼出元を確認できず、実運用への影響も未確認なので、到達性と入力契約を別途判断する必要がある。
