# 敵対・仲間・標的選択のテスト監査

## なぜ

最近距離の入力はマンハッタン距離でも同じ対象を選び、Z軸の入力は高さを無視しても成功していた。
群れIDを同じインスタンスで共有する準備、対象が1体しかいない代替選択、既定値を明示指定する準備も、説明している契約の一部を検査していなかった。
既存の入力と確認を全て残し、異なる答えになる対照を同じ主試験へ足す。

## 範囲と結果

基準は `00aeddef745aba1ec7743ca3118bbe239a01b3c3`。旧基準 `d209c63707827317f9c6c1409ce873b91a0af713` から所有者・呼出元・関連試験・依存固定・CI・作業指針の38ファイルが変わっていないことも照合した。

- 全5ファイル88宣言を全文で監査し、独立した第二読取で81件保持・7件修理を確認
- 元88宣言、元の入力を作る文、元の確認式、既存の準備関数（fixture）を全て保持。宣言やファイルの削除・統合はなし
- 試験1002行から1061行へ。内包するfixture・補助関数170行は変更なし。試験差分は60行追加・1行置換による純59行増
- 製品・独立支援ファイルの差分は0。変異を復元した後、製品1599ファイルが基準とバイト単位で同一
- この変更は試験の検出力を改善する。製品の敵対・選択・忘却の挙動を変更したとは主張しない

## 主担当の境界

- `PackAllegianceService` が群れの値による味方判定を持つ。`BehaviorService` は注入された味方判定を用いて候補から味方を除く
- `ConfigurableHostilityService` が個体の脅威/獲物指定、勢力、種族表を読む。`HostilityService` の3公開述語は関係種別を異なる意味の真偽値へ変換する
- `BehaviorService.build_observation` が視界と敵対候補を組み立て、対象選択へ渡す。既定の選択連鎖は `PreyPriorityTargetPolicy` → `PackLeaderTargetPolicy` → `HighestThreatTargetPolicy`
- `NearestTargetPolicy`、`LowestHpTargetPolicy`、`PackAllegianceService` の具体型を本番内で構築する箇所は確認できなかった。公開された型と注入可能な契約を保持する判断であり、既定構成で使われるという主張はしない
- `MonsterTargetContextBuilder` が実ストアの脅威値と群れのリーダー対象を作る。HP辞書を作る本番経路は未確認。最低HP政策の試験は公開APIの保証として残す
- `AggroMemoryPolicy.is_forgotten` は実ストアが利用する。復讐フラグは現在の忘却判定に影響しないが、SQLiteの保存・復元対象である
- `PackId` は群れ取得、モンスター検索、スポーン、保存復元で使う識別子。正規化・比較・ハッシュ・不変性・拒否を独立した値型契約として保持する

対象を観測から選ぶことと、その後の攻撃・被弾時の反応・行動通知は別の契約である。
別の観測試験やモンスターの状態遷移試験を、この政策試験の代わりとは扱わない。
生態反応の既存スキップ5件は今回の範囲外で、その保持・撤去も行わない。

## 同時作業との区別

[PR #1758](https://github.com/Motifman/llm-rpg/pull/1758) は観測出力、技能射程の高さ、観測等値、成長境界を扱う。
今回の候補選択政策の距離・未登録値や群れの値比較とは所有者が異なる。関連試験46件に含むBehaviorServiceの6件は基準main版であり、未統合PRの追加保証を基準の保証とは数えない。
公開準備時の89件の未統合PRの変更パスと、対象5試験・5所有者・監査文書を照合し、直接重複はなかった。公開直前には再確認する。

## 7件の修理

| 主試験 | 残した入力・確認 | 追加した対照 |
| --- | --- | --- |
| `TestPackAllegianceService.test_same_pack_is_ally` | 同じ `p1` インスタンスを持つ2体が味方 | 別に生成した値 `p1` を持つ相手も味方 |
| `TestNearestTargetPolicy.test_select_target_returns_nearest_by_euclidean_distance` | actor `(5,5)`、候補 `(6,5)` と `(9,9)`、近いIDと座標 | `(8,8)` と `(10,5)` で前者。直線距離は √18 < 5、マンハッタン距離は6 > 5 |
| `TestNearestTargetPolicy.test_select_target_z_axis_considered` | actor `(0,0,0)`、候補 `(0,0,1)` と `(3,4,0)`、前者のID | `(0,0,2)` と `(1,0,0)` で後者。両方とも視界5以内 |
| `TestHighestThreatTargetPolicy.test_select_target_missing_id_in_threat_uses_zero` | `{2:5}`、順序 `[1,2]` で2 | `{2:1}` でも2。未登録を1と誤設定した同点では先頭1が選ばれて失敗する |
| `TestLowestHpTargetPolicy.test_select_target_missing_id_in_hp_uses_one` | `{1:0.1}` で近い1 | `{2:0.9}` で遠い2。未登録の近い1を満タンとして扱う |
| `TestPackLeaderTargetPolicy.test_select_target_falls_back_when_pack_leader_target_not_in_candidates` | leader999、候補2だけで2 | 遠い候補1を先頭に追加しても近い2 |
| `TestAggroMemoryPolicy.test_revenge_never_forget_default_false` | 明示False、閾値10、経過11で忘却True | フラグを省略した別生成でFalse |

追加期待値は被試験関数から計算しない。元の呼び出し・確認の後に対照を置き、元の準備を置換しない。
同順位の選択順、返す対象の深い等値、復讐行動を新たな仕様にはしない。

## 履歴による根拠

- [5386f882](https://github.com/Motifman/llm-rpg/commit/5386f882e2834b507552dcbda5c05b5f4a147409): Nearestの導入時から「ユークリッド距離で比較」と明記し、距離とZ軸の試験を同時追加。現在の式だけを根拠に距離規則を固定したものではない
- [5a86251e](https://github.com/Motifman/llm-rpg/commit/5a86251e29afa0cdb619d97289ae6969d3c89f88): 脅威・HPの正常、未登録、同順位、文脈省略/空辞書の試験を追加
- [f21d7565](https://github.com/Motifman/llm-rpg/commit/f21d756597105a9c5538acb0f9f28f1376058f9b): 群れのリーダー対象を導入し、候補外なら代替政策へ委譲すると明記
- [8f84c499](https://github.com/Motifman/llm-rpg/commit/8f84c499c78d5cb628c0632462a0b4684061eee6): PackIdの生成、専用例外、比較、不変性と味方除外を整備
- [21fb1b60](https://github.com/Motifman/llm-rpg/commit/21fb1b602e5451779b3f93d4368e5ce56c237318): 最終視認tick、忘却政策、ストア、シミュレーションへの接続を追加
- [5123277e](https://github.com/Motifman/llm-rpg/commit/5123277e703f96fee0905bc26f50a9905fa50790) と [ada252ca](https://github.com/Motifman/llm-rpg/commit/ada252ca84df89ff4da3648a17caf1e463c8c5e2): 関係種別とNone入力例外、個体の脅威/獲物指定の優先を追加
- [1a018a36](https://github.com/Motifman/llm-rpg/commit/1a018a369348feb4bccc6fce818030b026f6ab45): 非アクター入力がAttributeErrorになる欠陥の回帰を追加。今回も専用例外の確認を保持

## 削除しなかった理由

3公開述語×5関係の15試験は実際の関係表を使い、それぞれ異なる真偽変換を守る。
5政策の空入力や代替選択も、異なる具体型と分岐に属するため一括で削除しない。
文脈なしと空辞書、片側なしと両側なし、同順位と単一候補には異なる回帰がある。
値型の取得、既定値、不変性は公開契約として保持し、単純な見た目だけで不要と判断しない。
`test_hash` は別生成の同値IDのハッシュ一致を守り、衝突が起きないという保証には広げない。
順序を逆転した入力の等値確認は順序不変条件であり、同一実行の自己比較ではない。

## 試験と変異対照

Python 3.10.22、外部通信を遮断し、読み込む製品が対象チェックアウトのものであることを確認した環境で実行した。

- 旧基準: 主5ファイル88成功
- 新基準の未編集状態: 主88成功、関連46成功
- 編集後と変異復元後: 主88成功、関連46成功、失敗・スキップなし
- 関連46件: `test_behavior_service.py` 6件、`test_monster_target_context_builder.py` 5件、実アグロストア17件、座標13件、WorldSimulationServiceの技能/対象文脈節5件
- 対象3ファイルのRuff、`git diff --check` は成功。全体試験は未実施。公開後CIの成功をここで先取りしない

各変異は製品を1か所だけ誤変更し、全旧88件と全候補88件を逐次実行した。
7件とも旧版は88成功、候補は対応する追加の結果確認だけが失敗し、残り87件は成功した。
失敗は視界や入力検査の例外ではなく、期待したID/真偽値と異なる実際の結果だった。
各回の後で元の製品へ戻し、最終的に製品1599ファイルの完全一致を検証した。

| 変異 | 候補で観測した差 |
| --- | --- |
| 群れ比較を `==` から `is` へ | 別生成の同値群れがFalseになる |
| Nearestだけマンハッタン距離へ | ID3の代わりにID4を選ぶ |
| NearestだけZ成分を除く | ID4の代わりにID3を選ぶ |
| 未登録脅威を0から1へ | ID2の代わりにID1を選ぶ |
| 疎なHP辞書だけ距離へ戻す | ID2の代わりにID1を選ぶ |
| 候補外leader時だけ先頭を返す | ID2の代わりにID1を選ぶ |
| 復讐フラグの既定をTrueへ | 省略生成のFalse確認に失敗 |

通常の再実行対象:

```sh
uv run pytest tests/domain/world/service/test_allegiance_service.py tests/domain/world/service/test_hostility_service.py tests/domain/world/service/test_target_selection_policy.py tests/domain/world/value_object/test_aggro_memory_policy.py tests/domain/world/value_object/test_pack_id.py
uv run pytest tests/domain/world/service/test_behavior_service.py tests/application/world/services/test_monster_target_context_builder.py tests/infrastructure/aggro/test_in_memory_aggro_store.py tests/domain/world/value_object/test_coordinate.py tests/application/world/services/test_world_simulation_service.py::TestWorldSimulationApplicationService::TestSkillContextAndTargetContext
```

通常CIはPython3.10で `uv run --frozen pytest -n auto` を実行し、この5ファイルを自動収集する。CI一覧やマーカーは変更しない。

## 全宣言の判定

Rは契約を保持、Fは契約と元入力を保持して確認を補強する。削除・統合対象はない。

### `tests/domain/world/service/test_allegiance_service.py`

- F `TestPackAllegianceService.test_same_pack_is_ally`: 同じp1群れは味方
- R `TestPackAllegianceService.test_different_pack_not_ally`: p1とp2は味方でない
- R `TestPackAllegianceService.test_none_pack_not_ally`: 片側だけ群れなしは両方向で味方でない
- R `TestPackAllegianceService.test_both_none_pack_not_ally`: 双方群れなしは味方でない
- R `TestPackAllegianceService.test_actor_component_without_pack_not_ally`: 自律型でないActorComponentの群れなし同士も味方でない

### `tests/domain/world/service/test_hostility_service.py`

- R `TestConfigurableHostilityServiceGetDisposition.test_neutral_when_no_table`: テーブルが空のとき NEUTRAL を返すこと
- R `TestConfigurableHostilityServiceGetDisposition.test_non_actor_component_raises_component_required`: アクターでない component を渡すと ComponentRequiredForDispositionException になる。 race / faction は ActorComponent の属性で、基底の WorldObjectComponent には無い。以前は基底型で受けており、アクター以外を渡すと AttributeError になっていた。
- R `TestConfigurableHostilityServiceGetDisposition.test_race_disposition_table_hostile`: race_disposition_table で HOSTILE が返ること
- R `TestConfigurableHostilityServiceGetDisposition.test_race_disposition_table_prey`: race_disposition_table で PREY が返ること
- R `TestConfigurableHostilityServiceGetDisposition.test_race_disposition_table_threat`: race_disposition_table で THREAT が返ること
- R `TestConfigurableHostilityServiceGetDisposition.test_race_disposition_table_ally`: race_disposition_table で ALLY が返ること
- R `TestConfigurableHostilityServiceGetDisposition.test_race_disposition_table_actor_race_not_in_table`: actor_race がテーブルに無いとき NEUTRAL
- R `TestConfigurableHostilityServiceGetDisposition.test_race_disposition_table_target_race_not_in_table`: target_race が actor のテーブルに無いとき NEUTRAL
- R `TestConfigurableHostilityServiceGetDisposition.test_faction_hostility_takes_precedence`: 勢力テーブルが種族より優先され HOSTILE になること
- R `TestConfigurableHostilityServiceIsHostile.test_hostile_true_for_hostile`: HOSTILE のとき True
- R `TestConfigurableHostilityServiceIsHostile.test_hostile_true_for_prey`: PREY のとき True（敵対の一種）
- R `TestConfigurableHostilityServiceIsHostile.test_hostile_false_for_threat`: THREAT のとき False（攻撃対象にしない）
- R `TestConfigurableHostilityServiceIsHostile.test_hostile_false_for_neutral`: NEUTRAL のとき False
- R `TestConfigurableHostilityServiceIsHostile.test_hostile_false_for_ally`: ALLY のとき False（攻撃対象にしない）
- R `TestConfigurableHostilityServiceIsThreat.test_threat_true_for_threat`: THREAT のとき True
- R `TestConfigurableHostilityServiceIsThreat.test_threat_false_for_hostile`: HOSTILE のとき False
- R `TestConfigurableHostilityServiceIsThreat.test_threat_false_for_prey`: PREY のとき False
- R `TestConfigurableHostilityServiceIsThreat.test_threat_false_for_neutral`: NEUTRAL のとき False
- R `TestConfigurableHostilityServiceIsThreat.test_threat_false_for_ally`: ALLY のとき False
- R `TestConfigurableHostilityServiceIsPrey.test_prey_true_for_prey`: PREY のとき True
- R `TestConfigurableHostilityServiceIsPrey.test_prey_false_for_hostile`: HOSTILE のとき False
- R `TestConfigurableHostilityServiceIsPrey.test_prey_false_for_threat`: THREAT のとき False
- R `TestConfigurableHostilityServiceIsPrey.test_prey_false_for_neutral`: NEUTRAL のとき False
- R `TestConfigurableHostilityServiceIsPrey.test_prey_false_for_ally`: ALLY のとき False
- R `TestConfigurableHostilityServiceComponentRequired.test_get_disposition_actor_comp_none_raises_exception`: get_disposition で actor_comp が None のとき ComponentRequiredForDispositionException
- R `TestConfigurableHostilityServiceComponentRequired.test_get_disposition_target_comp_none_raises_exception`: get_disposition で target_comp が None のとき ComponentRequiredForDispositionException
- R `TestConfigurableHostilityServiceComponentRequired.test_is_hostile_actor_comp_none_raises_exception`: is_hostile で actor_comp が None のとき ComponentRequiredForDispositionException
- R `TestConfigurableHostilityServiceComponentRequired.test_is_hostile_target_comp_none_raises_exception`: is_hostile で target_comp が None のとき ComponentRequiredForDispositionException
- R `TestConfigurableHostilityServiceComponentRequired.test_is_threat_actor_comp_none_raises_exception`: is_threat で actor_comp が None のとき ComponentRequiredForDispositionException
- R `TestConfigurableHostilityServiceComponentRequired.test_is_threat_target_comp_none_raises_exception`: is_threat で target_comp が None のとき ComponentRequiredForDispositionException
- R `TestConfigurableHostilityServiceComponentRequired.test_is_prey_actor_comp_none_raises_exception`: is_prey で actor_comp が None のとき ComponentRequiredForDispositionException
- R `TestConfigurableHostilityServiceComponentRequired.test_is_prey_target_comp_none_raises_exception`: is_prey で target_comp が None のとき ComponentRequiredForDispositionException
- R `TestConfigurableHostilityServiceComponentThreatPreyRaces.test_threat_races_returns_threat`: actor の threat_races に target.race が含まれるとき THREAT
- R `TestConfigurableHostilityServiceComponentThreatPreyRaces.test_prey_races_returns_prey`: actor の prey_races に target.race が含まれるとき PREY
- R `TestConfigurableHostilityServiceComponentThreatPreyRaces.test_threat_races_overrides_race_disposition_table`: threat_races が race_disposition_table より優先されること
- R `TestConfigurableHostilityServiceComponentThreatPreyRaces.test_prey_races_overrides_race_disposition_table`: prey_races が race_disposition_table より優先されること
- R `TestConfigurableHostilityServiceComponentThreatPreyRaces.test_empty_threat_races_falls_back_to_table`: threat_races が空のとき race_disposition_table で判定

### `tests/domain/world/service/test_target_selection_policy.py`

- R `TestNearestTargetPolicy.test_select_target_returns_none_when_empty`: 候補が空のとき None を返すこと
- R `TestNearestTargetPolicy.test_select_target_returns_single_candidate`: 候補が1体のときその候補を返すこと
- F `TestNearestTargetPolicy.test_select_target_returns_nearest_by_euclidean_distance`: 複数候補のとき最も近い1体を返すこと（ユークリッド距離）
- R `TestNearestTargetPolicy.test_select_target_order_independent`: 候補の並び順に依存せず最近距離を選ぶこと
- R `TestNearestTargetPolicy.test_select_target_same_distance_returns_one`: 同じ距離の候補が複数いる場合でも1体を返すこと
- F `TestNearestTargetPolicy.test_select_target_z_axis_considered`: Z軸を含む距離で比較すること
- R `TestHighestThreatTargetPolicy.test_select_target_returns_none_when_empty`: 候補が空のとき None を返すこと
- R `TestHighestThreatTargetPolicy.test_select_target_without_context_returns_nearest`: context がないときは最近距離の候補を返すこと（NearestTargetPolicy と同様）
- R `TestHighestThreatTargetPolicy.test_select_target_with_threat_by_id_returns_highest_threat`: context.threat_by_id があるときは脅威値が最も高い候補を返すこと
- R `TestHighestThreatTargetPolicy.test_select_target_threat_tie_returns_one`: 脅威値が同点の候補が複数いる場合でも1体を返すこと
- F `TestHighestThreatTargetPolicy.test_select_target_missing_id_in_threat_uses_zero`: threat_by_id に含まれない ID は脅威 0 として扱うこと
- R `TestHighestThreatTargetPolicy.test_select_target_empty_threat_by_id_falls_back_to_nearest`: context はあるが threat_by_id が空のときは最近距離を返すこと
- R `TestLowestHpTargetPolicy.test_select_target_returns_none_when_empty`: 候補が空のとき None を返すこと
- R `TestLowestHpTargetPolicy.test_select_target_without_context_returns_nearest`: context がないときは最近距離の候補を返すこと
- R `TestLowestHpTargetPolicy.test_select_target_with_hp_percentage_returns_lowest_hp`: context.hp_percentage_by_id があるときは HP% が最も低い候補を返すこと
- R `TestLowestHpTargetPolicy.test_select_target_hp_tie_returns_one`: HP% が同点の候補が複数いる場合でも1体を返すこと
- F `TestLowestHpTargetPolicy.test_select_target_missing_id_in_hp_uses_one`: hp_percentage_by_id に含まれない ID は 1.0 として扱うこと（満タン）
- R `TestLowestHpTargetPolicy.test_select_target_empty_hp_percentage_falls_back_to_nearest`: context はあるが hp_percentage_by_id が空のときは最近距離を返すこと
- R `TestPackLeaderTargetPolicy.test_select_target_returns_none_when_empty`: 候補が空のとき None を返すこと
- R `TestPackLeaderTargetPolicy.test_select_target_prefers_pack_leader_target_when_in_candidates`: context.pack_leader_target_id が候補に含まれるときその候補を返すこと
- F `TestPackLeaderTargetPolicy.test_select_target_falls_back_when_pack_leader_target_not_in_candidates`: pack_leader_target_id が候補に含まれないときはフォールバックで選ぶこと
- R `TestPackLeaderTargetPolicy.test_select_target_falls_back_when_context_none`: context が None のときはフォールバックで選ぶこと
- R `TestPackLeaderTargetPolicy.test_select_target_falls_back_when_pack_leader_target_id_none`: context.pack_leader_target_id が None のときはフォールバックで選ぶこと
- R `TestPreyPriorityTargetPolicy.test_select_target_returns_none_when_empty`: 候補が空のとき None を返すこと
- R `TestPreyPriorityTargetPolicy.test_select_target_prefers_prey_over_hostile`: PREY を HOSTILE より優先して選択すること（獲物が遠くても選ぶ）
- R `TestPreyPriorityTargetPolicy.test_select_target_falls_back_when_no_prey`: 獲物がいないときはフォールバック（最近距離）で選ぶこと
- R `TestPreyPriorityTargetPolicy.test_select_target_single_prey_returns_it`: 獲物が1体だけのときその1体を返すこと

### `tests/domain/world/value_object/test_aggro_memory_policy.py`

- R `TestAggroMemoryPolicy.test_none_never_forgets`: forget_after_ticks=Noneでは1000/0と1000/999で忘れない
- R `TestAggroMemoryPolicy.test_forget_after_ticks_zero_elapsed_not_forgotten`: 閾値10で経過0と9を忘れない
- R `TestAggroMemoryPolicy.test_forget_after_ticks_elapsed_forgotten`: 閾値10で経過11と100を忘れる
- F `TestAggroMemoryPolicy.test_revenge_never_forget_default_false`: 明示Falseで経過11を忘れる。元本文では省略既定を未検査。今回、省略生成でFalseを確認
- R `TestAggroMemoryPolicy.test_revenge_never_forget_true_does_not_affect_is_forgotten`: revenge_never_forget は is_forgotten の戻り値は変えず、将来の拡張用
- R `TestAggroMemoryPolicy.test_immutability`: AggroMemoryPolicy.forget_after_ticksの再代入を拒否する
- R `TestAggroMemoryPolicyValidation.test_negative_forget_after_ticks_raises`: 負の閾値-1をValueErrorと理由で拒否する
- R `TestAggroMemoryPolicyValidation.test_forget_after_ticks_zero_allowed`: 閾値0では同tickを保持し次tickで忘れる

### `tests/domain/world/value_object/test_pack_id.py`

- R `TestPackId.test_create_from_string`: 文字列wolf_pack_1から識別子を作り値を保持する
- R `TestPackId.test_create_from_int`: 整数42を文字列42へ正規化する
- R `TestPackId.test_create_strips_whitespace`: 前後の空白を除去してalphaを保持する
- R `TestPackId.test_empty_raises`: createと直接構築の空文字を専用例外で拒否する
- R `TestPackId.test_whitespace_only_raises`: 空白およびタブ改行だけのcreateを専用例外で拒否する
- R `TestPackId.test_none_raises`: Noneを文字列化せず専用例外で拒否する
- R `TestPackId.test_equality`: 数値1と文字列1は同値、aとbは不等
- R `TestPackId.test_hash`: 別生成の同値xは同じハッシュを持つ
- R `TestPackId.test_str`: strでp1を返す
- R `TestPackId.test_immutability`: PackId.valueの再代入を拒否し元値を保持する
- R `TestPackId.test_equality_with_non_pack_id`: 同じ内容の文字列・None・整数と型を越えて等しくしない
