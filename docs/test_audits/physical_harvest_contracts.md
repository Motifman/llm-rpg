# 採集の開始・進行・受け取りの試験監査

## 結果

対象は採集の所有範囲5ファイル、元55宣言。保持34・修復3・統合18・削除のみ0とした。政策単体の16宣言を実物のセッション入口へ移し、既存の開始成功2宣言も同じ表へ統合した。製品コードは変更していない。

- 元の試験: 5ファイル、1258行、55宣言、55ケース
- 変更後: 4ファイル、889行、38宣言、51ケース。試験は369行減少
- 専用の試験支援ファイルは前後とも0、製品差分0。この監査文書は別計上
- 未編集基準: 所有55＋関連30＝85件成功
- 移管元の政策を残した段階: 新保持先51＋元政策16＋関連30＝97件成功
- 政策ファイル除去後: 所有51＋関連30＝81件成功
- 13種の意図的誤変更を、元55と候補51で比較。各回に製品を元のバイト列へ復元
- 独立した第二読で未開始状態の移管漏れを発見し、編集前に計画を修正。修復後の保持レビューも実施

基準のmainは `ba942f5a9cad4b6d362c9e2ce59566cc8ce3396f`。公開前にmainと開いているPRの先頭・変更ファイルを再確認する。全体試験や公開後CIの成功を、このローカル結果には含めない。

## なぜ変えるか

採集開始の条件を政策へ、開始・完了・取消をセッションサービスへ順に抽出した際、同じ条件の試験が複数層に残った。政策はセッションからだけ呼ばれる。実コンポーネントを動かすセッション試験なら、条件の判断だけでなく、その結果が資源占有と通知へ届くことも守れる。

完了時刻ちょうどの `is_busy=False` は、解除を省いても期限経過だけで成立していた。また「別の行為者」を意図したセッションの排他試験は、補助関数が双方にID100を割り当てていた。前者は公開 `busy_until is None` を追加し、後者は元の同ID再試行を残したうえで別ID101を加えた。

## 層ごとの保持先

- `test_harvest_session_domain_service.py`: 開始条件、返却通知、資源所有者、期限、未完了のNone、取消理由、型拒否を所有する。廃止する政策16宣言の全入力・例外型・文言を先に移管した
- `test_physical_map_harvest.py`: IDからの実オブジェクト取得、通知蓄積・抑制、採集中の移動拒否を保持する。内部タイル辞書への書込みは公開の構築引数へ置き換えた
- `test_harvestable_component.py`: 構築入力変換・拒否、回復の時刻境界と上限、直接返却値、取消後拒否、出力形式を保持する
- `test_harvest_domain_service.py`: 数量2と消費15、受取先None、抽選無し時の消費を保持する。モックは呼出を記録するだけで報酬処理を実装せず、生成されるItemAggregateは実物
- 関連アプリケーション30件は編集しない。保存、例外変換、通知配送、向き変換、世界tickからの自動完了は別契約

同一マスの元サービス入力は、双方ともblocking=True。集約配置ではこの組合せが拒否されるため、集約へ移す都合でblockingを変えず、実サービスの入力として保持した。構築既定値、任意引数、出力辞書も「小さい検査」という理由では削除していない。試験専用の製品公開口は見つからず、政策・サービス・コンポーネントはいずれも実稼働の呼出があるため削除していない。

## 第二読で見つかった移管漏れ

政策のH52/H53は、新しく構築した未開始資源を許容する試験だった。開始後の完了へ移すだけでは、元のcurrent_actor_id=Noneが消える。そこで未開始max1/既定期間5とmax5/期間10の2行をサービスの完了入口へ渡し、型拒否ではなく `HarvestNotStartedException` まで届くことを検査した。政策が未開始資源を誤って `NotHarvestableException` で拒否する変更は、旧政策2件と新しい2行の双方で失敗した。

## 公開期限を検査する根拠

完了後の `WorldObject.busy_until` は公開された状態であり、[現在状態の構築](../../src/ai_rpg_world/application/world/services/player_current_state_builder.py)が期限後でもDTOのbusy_until_tickへ写し、[SQLite保存](../../src/ai_rpg_world/infrastructure/repository/sqlite_physical_map_repository.py)もNoneと古い終了時刻を区別する。このため正規の開始→完了後にNoneを検査する。巻戻しや内部呼出の監視は使っていない。

なお、現在状態の表示処理にはis_busyの外側の条件がある。古い期限が必ず観測文へ表示されるとは主張しない。

## 全55宣言の対応

Rは保持、Fは元の契約を残した修復、Cは保持先へ全入力・検査を統合。行番号は基準mainのもの。

### `tests/domain/world/aggregate/test_physical_map_harvest.py`

| 元の宣言・行 | 判定 | 実際の契約と入力 | 保持先 |
|---|---|---|---|
| H01 `TestPhysicalMapHarvest::test_start_harvest_success` L67 | R | 時刻100、東隣の資源200、期間10。行為者100がbusy、期限110、開始通知のactor/target/finish_tick。集約のID解決と通知蓄積を守る。 | 同名の集約試験 |
| H02 `TestPhysicalMapHarvest::test_start_harvest_out_of_range` L86 | R | (0,0)→(2,0)、東向き、時刻100。InteractionOutOfRangeException。集約入口までのID解決後に距離拒否が届く。 | 同名の集約試験 |
| H03 `TestPhysicalMapHarvest::test_start_harvest_wrong_direction` L107 | R | 西向きで東隣資源、時刻100。NotFacingTargetException。 | 同名の集約試験 |
| H04 `TestPhysicalMapHarvest::test_start_harvest_not_harvestable` L117 | R | 東隣のPLAYER101、ActorComponentの既定南向き。NotHarvestableException。 | 同名の集約試験 |
| H05 `TestPhysicalMapHarvest::test_finish_harvest_success` L132 | F | 開始100→完了110、期間10、資源1→0、完了通知actor/target/LootTableId(1)、is_busy(110)=False。現状は期限切れだけで解除検査が通る。公開busy_until=Noneを追加し、古い期限が公開現在状態DTO・永続化へ残る退行を検出する。 | 同名の集約試験。元の全検査を保持し公開busy_untilを追加 |
| H06 `TestPhysicalMapHarvest::test_finish_harvest_too_early` L158 | R | 開始100、期間10、109で完了要求。完了通知なし、数量1を保持。集約がサービスのNoneを通知へ積まない。 | 同名の集約試験 |
| H07 `TestPhysicalMapHarvest::test_cancel_harvest` L175 | R | 開始100後、同時刻にreason=interruptedで中断。is_busy=False、所有者None、取消通知actor/reason。期限前なので解除検査は有効。 | 同名の集約試験 |
| H08 `TestPhysicalMapHarvest::test_concurrency_prevention` L197 | R | 行為者100が東向きに開始、別ID101を(1,1)北向きに置いて同資源へ時刻100に開始。HarvestInProgressException。 | 同名の集約試験。タイルは公開create入力へ置き、_tiles書込みを不要にする |
| H09 `TestPhysicalMapHarvest::test_actor_busy_prevention` L220 | R | 採集100→110中の105に通行可能な南タイルへmove_actor。ActorBusyException。採集と移動の横断連携。 | 同名の集約試験。南タイルは公開create入力へ置く |

### `tests/domain/world/entity/test_harvestable_component.py`

| 元の宣言・行 | 判定 | 実際の契約と入力 | 保持先 |
|---|---|---|---|
| H10 `TestHarvestableComponent::test_constructor_success` L18 | R | loot=1,max=5,respawn=100,initial=3,last=50,tool=pickaxe。LootTableId変換、道具名、50時点数量3。構築・既定の公開契約。 | 同名のコンポーネント試験 |
| H11 `TestHarvestableComponent::test_validation_invalid_params` L32 | R | loot空文字/id/0の3入力→LootTableIdValidationException。max0/respawn-1/initial-1/initial6>max5を各固有例外と文言で拒否。値オブジェクトだけではこの構築入口の変換を守れない。 | 同名のコンポーネント試験。7拒否入力をすべて保持 |
| H12 `TestHarvestableComponent::test_lazy_recovery_scenarios` L57 | R | max5,initial2,last100,interval100。時刻100/199/200/350/1100/50の順に2/2/3/4/5/2。境界・整数回復・上限・過去参照・非変更参照。 | 同名のコンポーネント試験 |
| H13 `TestHarvestableComponent::test_harvest_flow` L86 | R | loot2,max1,interval100,initial1,last0。10→20完了で0、30開始は枯渇例外、120で1、120→130再採集で0。完了時刻を回復基準にする。 | 同名のコンポーネント試験 |
| H14 `TestHarvestableComponent::test_harvest_trial_flow_success` L113 | R | loot3,期間10、行為者1、開始100→期限110。開始戻り値110/所有者1、109未完了/110完了、finish=True、数量0、所有者None。公開判定はアプリも直接使う。 | 同名のコンポーネント試験 |
| H15 `TestHarvestableComponent::test_harvest_trial_interruption` L138 | R | loot3期間10、行為者1、開始100→取消。所有者が1からNone、110の完了はHarvestNotStartedException。 | 同名のコンポーネント試験 |
| H16 `TestHarvestableComponent::test_harvest_trial_concurrency` L156 | R | loot3の既定期間5、行為者1が100開始、別ID2の同時開始はHarvestInProgressException。 | 同名のコンポーネント試験 |
| H17 `TestHarvestableComponent::test_to_dict_and_properties` L171 | R | loot4,max10,initial5,interval500,last1000,tool=special_pickaxe。型名harvestable、HARVEST、interaction_data完全辞書、to_dictの6値と文字列ID。出力形式の公開契約。 | 同名のコンポーネント試験 |

### `tests/domain/world/service/test_harvest_domain_service.py`

| 元の宣言・行 | 判定 | 実際の契約と入力 | 保持先 |
|---|---|---|---|
| H18 `TestHarvestDomainService::test_process_reward_with_player_success` L56 | R | スタミナ15、loot spec101数量2、新ID500。status.consume_stamina(15)とinventory.acquire_item(500,item_spec_id_value=101)を各1回、生成品ID500/数量2。モックは結果を実装せず呼出を記録し、ItemAggregateは実物。 | 同名の報酬サービス試験。アプリの数量1/消費10と異なる入力・複数品生成を保持 |
| H19 `TestHarvestDomainService::test_process_reward_with_npc_success` L87 | R | loot spec101数量1/newID501があってもinventory/status=Noneなら生成品None、events空。任意引数のAPI契約で、本番アプリが現在必須化していても削除しない。 | 同名の報酬サービス試験 |
| H20 `TestHarvestDomainService::test_process_reward_no_loot` L107 | R | loot/spec/newID=None、inventory/status有り、コスト15。消費1回、取得呼出なし、生成品None。空抽選でも労力を消費する。 | 同名の報酬サービス試験 |

### `tests/domain/world/service/test_harvest_session_domain_service.py`

| 元の宣言・行 | 判定 | 実際の契約と入力 | 保持先 |
|---|---|---|---|
| H21 `TestStartHarvest::TestSuccessCases::test_returns_event_and_sets_actor_busy` L63 | R | 時刻10、(0,0)東→(1,0)、期間10。開始イベント型/actor100/target200/期限20、busy/期限20、資源所有者100。 | TestStartHarvest::TestSuccessCases::test_returns_event_and_sets_actor_busy を表形式に拡張 |
| H22 `TestStartHarvest::TestSuccessCases::test_adjacent_facing_south_succeeds` L82 | C | 時刻10、(0,0)南→(0,1)、既定期間5。event非None、busy=True。 | 上記開始表のsouth-default行へ全入力・検査を移管 |
| H23 `TestStartHarvest::TestSuccessCases::test_same_cell_succeeds` L93 | C | 時刻10、(1,1)同一マス、東向き、既定期間5。event非None。 | 上記開始表のsame-cell-east行。政策側の北向き行と区別 |
| H24 `TestStartHarvest::TestExceptionCases::test_raises_when_actor_busy` L104 | R | 時刻10、東隣、busy_until20。ActorBusyExceptionと小文字busy文言。 | 同名のサービス拒否試験 |
| H25 `TestStartHarvest::TestExceptionCases::test_raises_when_too_far` L116 | R | 時刻10、東向き、(2,2)対象。InteractionOutOfRangeException。政策のfar/too文言を加え(2,0)も表で保持。 | 同名のサービス距離拒否表。斜め2/直線2を別行 |
| H26 `TestStartHarvest::TestExceptionCases::test_raises_when_not_facing` L125 | R | 時刻10、西向きで東隣。NotFacingTargetException。政策側facing文言を移管。 | 同名のサービス方向拒否試験 |
| H27 `TestStartHarvest::TestExceptionCases::test_raises_when_target_not_harvestable` L134 | R | 東隣のPLAYER/ActorComponent(WEST)。NotHarvestableException。政策側harvestable\|not文言を移管。 | 同名のサービス対象拒否試験 |
| H28 `TestStartHarvest::TestExceptionCases::test_raises_when_component_none` L148 | R | 東隣RESOURCE/component=None。NotHarvestableException。政策側harvestable\|not文言を移管。 | 同名のサービス対象欠落拒否試験 |
| H29 `TestStartHarvest::TestExceptionCases::test_raises_when_already_harvesting` L162 | F | 元は(0,0)東のID100が開始後、(2,0)西の別WorldObjectだが同じID100で再開始しHarvestInProgressException。別行為者という名前は入力と不一致。 | 同名試験をID100再試行とID101他者の2行にする。座標・向き・busy無しを維持し意図する資源排他へ到達 |
| H30 `TestStartHarvest::TestExceptionCases::test_raises_when_resource_exhausted` L174 | R | 時刻10、東隣、max1 initial0 last10。ResourceExhaustedException。回復がまだ起きない枯渇入力。 | 同名のサービス枯渇拒否試験 |
| H31 `TestFinishHarvest::TestSuccessCases::test_returns_event_and_clears_actor_busy_when_complete` L193 | F | 開始10→完了20、期間10、完了イベント型/actor/target/loot、is_busy(20)=False、所有者None。期限切れだけで解除検査が通る。 | 同名の完了試験へ公開busy_until=Noneを追加。政策の未開始2入力は別の未開始完了拒否表で保持 |
| H32 `TestFinishHarvest::TestSuccessCases::test_resource_quantity_decreases` L214 | R | max3,期間5、開始10→完了15、event非None、数量2。複数在庫から1のみ消費。 | 同名のサービス数量試験 |
| H33 `TestFinishHarvest::TestReturnsNoneWhenNotComplete::test_returns_none_when_time_not_elapsed` L232 | R | 期間10、開始10→19で完了。戻り値None、busy=True、所有者100保持。集約とは異なる返却APIの契約。 | 同名のサービス未完了試験 |
| H34 `TestFinishHarvest::TestExceptionCases::test_raises_when_target_not_harvestable` L248 | R | PLAYER/ActorComponent既定SOUTHへfinish、時刻10。NotHarvestableException。 | 同名の完了対象拒否試験。政策由来EASTも別行、harvestable\|notを保持 |
| H35 `TestFinishHarvest::TestExceptionCases::test_raises_when_component_none` L262 | R | RESOURCE/component=Noneへfinish、時刻10。NotHarvestableException。 | 同名の完了対象欠落試験、政策文言harvestable\|notを保持 |
| H36 `TestCancelHarvest::TestSuccessCases::test_returns_event_and_clears_actor_busy` L281 | R | 既定期間5、10開始後interruptedで取消。取消イベント型/actor/target/reason、busy=False、所有者None。 | 同名のサービス取消試験 |
| H37 `TestCancelHarvest::TestSuccessCases::test_default_reason_is_cancelled` L297 | R | 10開始後reason省略。返却イベントreason=cancelled。公開既定値の契約。 | 同名のサービス既定理由試験 |
| H38 `TestCancelHarvest::TestExceptionCases::test_raises_when_target_not_harvestable` L307 | R | PLAYER/ActorComponent既定SOUTHへcancel(reason=test)。NotHarvestableException。finishと独立の取消入口。 | 同名の取消対象拒否試験。政策由来EASTも別行、harvestable\|notを保持 |
| H39 `TestCancelHarvest::TestExceptionCases::test_raises_when_component_none` L321 | R | RESOURCE/component=Noneへcancel(reason=test)。NotHarvestableException。 | 同名の取消対象欠落試験、政策文言harvestable\|notを保持 |

### `tests/domain/world/service/test_harvest_session_policy.py`

| 元の宣言・行 | 判定 | 実際の契約と入力 | 保持先 |
|---|---|---|---|
| H40 `TestValidateCanStartHarvest::TestSuccessCases::test_adjacent_facing_target_succeeds` L32 | C | (0,0)東→(1,0)、時刻10、loot1,max1,duration10。検証が例外なく通る。 | サービス開始表east-duration10行。実通知・期限・資源所有者で成功を確認 |
| H41 `TestValidateCanStartHarvest::TestSuccessCases::test_same_cell_succeeds` L56 | C | (1,1)同一マス、北向き、時刻10、loot1既定。検証が例外なく通る。 | サービス開始表same-cell-north行。元の東向き行とは別に保持 |
| H42 `TestValidateCanStartHarvest::TestSuccessCases::test_diagonal_adjacent_succeeds` L76 | C | (0,0)南東→(1,1)、時刻10、loot1既定。8方向距離1の許容。 | サービス開始表diagonal-southeast行。実物Coordinateのまま |
| H43 `TestValidateCanStartHarvest::TestSuccessCases::test_harvestable_with_all_params_succeeds` L96 | C | (0,0)南→(0,1)、時刻10、loot1,max5,respawn100,duration15,stamina20。許容。 | サービス開始表south-explicit行。期限25も固定期待値で検査 |
| H44 `TestValidateCanStartHarvest::TestActorBusy::test_raises_when_actor_busy` L123 | C | 東隣、時刻10、busy_until20→ActorBusyException、busy文言。 | サービスtest_raises_when_actor_busy。既存入力・例外・文言が一致 |
| H45 `TestValidateCanStartHarvest::TestActorBusy::test_passes_when_busy_until_passed` L146 | C | 東隣、時刻10、busy_until5、既定資源。期限超過後の開始を許容。 | サービス開始表busy-expired行。任意追加の期限ちょうどbusy_until10も別行 |
| H46 `TestValidateCanStartHarvest::TestDistance::test_raises_when_too_far` L168 | C | 東向きで対象(2,2)、時刻10→InteractionOutOfRangeException、小文字farまたはtoo。 | サービスtest_raises_when_too_farのdiagonal-two行。元文言条件を保持 |
| H47 `TestValidateCanStartHarvest::TestDistance::test_raises_when_distance_exactly_2` L192 | C | 東向きで対象(2,0)、時刻10→InteractionOutOfRangeException。 | 同距離拒否表straight-two行。斜め2で代用しない |
| H48 `TestValidateCanStartHarvest::TestDirection::test_raises_when_not_facing_adjacent_target` L214 | C | 西向きで東隣、時刻10→NotFacingTargetException、小文字facing。 | サービスtest_raises_when_not_facingに文言移管 |
| H49 `TestValidateCanStartHarvest::TestDirection::test_passes_when_facing_correct_direction` L236 | C | 東向きで東隣、時刻10、loot1既定duration5。許容。 | サービス開始表east-default行。duration10行と分離 |
| H50 `TestValidateCanStartHarvest::TestHarvestable::test_raises_when_target_not_harvestable` L257 | C | 東隣のPLAYER/ActorComponent(WEST)、時刻10→NotHarvestableException、小文字harvestableまたはnot。 | サービス開始対象拒否の同一入力に文言移管 |
| H51 `TestValidateCanStartHarvest::TestHarvestable::test_raises_when_component_none` L285 | C | 東隣RESOURCE/component=None、時刻10→NotHarvestableException、小文字harvestableまたはnot。 | サービス開始対象欠落拒否の同一入力に文言移管 |
| H52 `TestValidateIsHarvestable::TestSuccessCases::test_harvestable_component_passes` L314 | C | RESOURCE(1,0),loot1既定。validate_is_harvestableが例外なく通る。 | サービスの未開始完了拒否表max1/default5行。資源所有者NoneのままfinishしHarvestNotStartedExceptionまで到達する。先にstartしない |
| H53 `TestValidateIsHarvestable::TestSuccessCases::test_harvestable_with_all_params_passes` L326 | C | RESOURCE(1,0),loot1,max5,duration10。validate_is_harvestableが例外なく通る。 | サービスの未開始完了拒否表max5/duration10行。資源所有者NoneのままfinishしHarvestNotStartedExceptionまで到達する。max3で代用しない |
| H54 `TestValidateIsHarvestable::TestExceptionCases::test_raises_when_component_none` L343 | C | RESOURCE(1,0),component=None→NotHarvestableException、小文字harvestableまたはnot。 | サービスfinish/cancel両入口のcomponent=None拒否に文言移管 |
| H55 `TestValidateIsHarvestable::TestExceptionCases::test_raises_when_component_not_harvestable` L359 | C | PLAYER(1,0),ActorComponent(EAST)→NotHarvestableException、小文字harvestableまたはnot。 | サービスfinish/cancel両入口の非採集対象表にEAST行を移管。元SOUTHも保持 |

## 意図的誤変更による比較

各変更は本番の所有者へ一つずつ適用し、同じ変更を元の55件と候補51件で直列実行した。失敗数の差だけで価値を主張せず、対象の検査が意図した理由で失敗することを確認した。

| 誤変更 | 元55の失敗 | 候補51の失敗 |
|---|---:|---:|
| 完了時に古い公開期限を残す | 0 | 2 |
| 同IDだけ拒否し他者の資源上書きを許す | 2 | 3 |
| 同一マスにも方向計算を強制する | 2 | 2 |
| 8方向距離をマンハッタン距離へ誤変更する | 1 | 1 |
| 期限経過後もbusy_untilの存在だけで拒否する | 1 | 2 |
| 期限ちょうどの再開始を拒否する | 0 | 1 |
| 指定採集期間を無視して5へ固定する | 6 | 7 |
| 型検証で未開始の採集資源も拒否する | 2 | 2 |
| busy例外の原因文言を失う | 2 | 1 |
| 距離例外のfar/too文言を失う | 1 | 2 |
| 方向例外のfacing文言を失う | 1 | 1 |
| 対象型例外のharvestable/not文言を失う | 4 | 8 |
| 非採集対象の型拒否を省く | 11 | 9 |

完了時の期限解除漏れと期限ちょうどの誤拒否は元55件が全成功し、候補がそれぞれ2件・1件で検出した。他者の上書きは元の集約・コンポーネントでも2件が検出していた。候補では新しいサービスの別ID行も加わって3件失敗するため、全体で未検出だったとは書かない。指定期間固定は元でも6件が失敗し、候補では元の政策が通るだけだった期間15も通知期限25の検査で落ちる。

各回で旧・新両方の製品ファイルを復元し、SHA256が変更前と一致することを確認した。全13種の比較を終えた後、所有＋関連81件を再実行した。

## 試験の範囲と再現

Python3.10.22、対象作業場のsrcを使い、秘密情報とプロキシ設定を除いた環境、ネットワーク遮断、実行ごとの新しいキャッシュで検証した。有料LLMや実APIは呼んでいない。最初の基準試行は関連1件のクラス名を誤指定して収集前に終了したため実行0件として残し、完全名を照合して新しい証跡名で85件を実行し直した。

関連30件の内訳:

- `tests/application/harvest/services/test_harvest_command_service.py`: 22件
- `tests/application/harvest/services/test_harvest_resource_harvested_publish.py`: 5件
- `tests/application/harvest/services/test_player_harvest_service.py`: 2件
- `tests/application/world/services/test_world_simulation_service.py::TestWorldSimulationApplicationService::test_tick_auto_completes_due_player_harvest`: 1件

最終範囲を通常の開発環境で実行するコマンド:

```bash
uv run pytest \
  tests/domain/world/aggregate/test_physical_map_harvest.py \
  tests/domain/world/entity/test_harvestable_component.py \
  tests/domain/world/service/test_harvest_domain_service.py \
  tests/domain/world/service/test_harvest_session_domain_service.py \
  tests/application/harvest/services \
  tests/application/world/services/test_world_simulation_service.py::TestWorldSimulationApplicationService::test_tick_auto_completes_due_player_harvest
```

変更試験のRuff 0.16.8による静的検査・整形確認と差分の空白検査を行った。CIはPython3.10で `uv run --frozen pytest -n auto` を自動収集するため、廃止ファイルの別登録変更は不要。quality/live_apiは通常の選択外で、全体CIは公開後に別途確認する。

## 履歴と実稼働の呼出

- [a27a6ef](https://github.com/Motifman/llm-rpg/commit/a27a6efaf77ca3a45de673c06f7ce577972f79d2): 資源採取・時間・枯渇/回復を導入
- [ddc8572](https://github.com/Motifman/llm-rpg/commit/ddc8572b46ab18571499885b98fa9ac4ae2a4a15): プレイヤーデータ存在・busy・距離・向き・二重採集の強化
- [f21d756](https://github.com/Motifman/llm-rpg/commit/f21d756597105a9c5538acb0f9f28f1376058f9b): LootTableIdの値オブジェクト化と採食
- [d899b55](https://github.com/Motifman/llm-rpg/commit/d899b5530f6329692234ab518a4c2ffdb6246b4d): 集約から開始政策を抽出
- [f1d2989](https://github.com/Motifman/llm-rpg/commit/f1d2989956c102c127da66f4ddcc6542b0b71f09): セッションサービスへ開始・完了・取消を抽出し、政策・サービスの試験を追加
- [c1b3476](https://github.com/Motifman/llm-rpg/commit/c1b34769a7a79185d12e460fdabe34c667609189): 型を絞ったコンポーネントを政策の戻り値に変更

実稼働の主経路は PlayerHarvestApplicationService → HarvestCommandService → PhysicalMapAggregate → HarvestSessionDomainService → HarvestSessionPolicy/HarvestableComponent。自動完了はWorldSimulationHarvestStageServiceから同じコマンドサービスへ入る。資源の現在所有者と終了時刻は現在状態の構築・SQLite入出力でも使う。

## 分離した製品上の問題

既存の基準85件に失敗はなかった。別の未変更製品プローブでは、回復間隔0の構築・開始10・完了15が通った後、公開 `get_available_quantity(15)` がZeroDivisionErrorになることを確認した。正値100の対照は成功した。私有状態の書換えはしていない。

同梱設定から0を使う経路は見つかっておらず、0が無効・即時回復・回復なしのどれを意味するかは独立した仕様から確定できていない。入力受理後に算術例外へ到達する観測だけを分離し、このPRでは製品修正や新しい仕様決定をしない。
