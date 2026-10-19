# スキル装備・仕様・保存口の試験監査

## 基準と範囲

基準: `ba942f5a9cad4b6d362c9e2ce59566cc8ce3396f`。4ファイル416行・41宣言を全文確認した。判定は保持25、修理15、統合1、削除0。試験の修理は集約と保存口の2ファイルに限定し、製品は変更していない。

| ファイル | 元宣言 | 元ケース |
|---|---:|---:|
| `tests/domain/skill/aggregate/test_skill_loadout_aggregate.py` | 23 | 23 |
| `tests/domain/skill/repository/test_skill_repository_ports.py` | 3 | 3 |
| `tests/domain/skill/value_object/test_skill_ids.py` | 6 | 6 |
| `tests/domain/skill/value_object/test_skill_spec.py` | 9 | 13 |

## 変更の理由

- 集約が正しい状態を作っても、誤ったロードアウトや解除スキルを通知すると本人への観測が壊れる。配信・整形試験はイベントを自分で作るため、生成の証明にはならない
- 前提スキルは装備先の置換後デッキから判定する。別デッキや置換される枠は前提を満たさない
- 冷却や詠唱制限、所有者違い、覚醒中の再発動による拒否は既存の公開状態と保留通知を保存する
- 覚醒待機の元入力は整数結果だけだったため、端数の切上げを見逃していた
- 空デッキだけの容量変更では、既存装備が消えても分からなかった
- 保存口の抽象性は独立した設計契約だが、継承元や別メソッドが抽象なだけで検査に成功していた。固有の必須操作が欠けた実装と、完全な実装を対照にする

ID変換、型固有の例外、照準範囲の0・正値・既定1は公開契約として残した。短い構築試験という理由では除去しない。冷却開始イベントは観測対象外であり、ここでは公開イベント生成の契約として確認する。イベント日時・乱数ID・異種イベントの順序は固定しない。

## 全宣言の判定

R=保持、F=契約を保持して判定を修理、C=契約を保持先へ統合。

### `tests/domain/skill/aggregate/test_skill_loadout_aggregate.py`

| 元の宣言 | 判定 | 守る契約 |
|---|:---:|---|
| `TestSkillLoadoutAggregate::TestEquipSkill::test_equip_success` | F | 指定デッキ・枠への装備と所有ロードアウトを指す装備通知 |
| `TestSkillLoadoutAggregate::TestEquipSkill::test_equip_fails_when_skill_already_equipped` | R | 同一デッキの別枠には同じスキルを重複装備できない |
| `TestSkillLoadoutAggregate::TestEquipSkill::test_equip_same_skill_to_same_slot_is_allowed` | R | 同じ枠への再装備は重複エラーにしない |
| `TestSkillLoadoutAggregate::TestEquipSkill::test_equip_fails_when_capacity_exceeded` | R | 費用が容量を超える装備を拒否する |
| `TestSkillLoadoutAggregate::TestEquipSkill::test_equip_fails_when_prerequisite_not_met` | F | 装備先デッキの置換後にも必要な前提スキルが揃わなければ拒否する |
| `TestSkillLoadoutAggregate::TestEquipSkill::test_equip_success_when_prerequisite_met` | R | 同じデッキの別枠に前提がある装備は許可する |
| `TestSkillLoadoutAggregate::TestEquipSkill::test_equip_different_deck_same_skill_allowed` | R | 通常と覚醒の両デッキへ同一スキルを装備できる |
| `TestSkillLoadoutAggregate::TestEquipSkill::test_equip_at_exact_capacity` | R | 容量と同額の装備を許可し残容量0を返す |
| `TestSkillLoadoutAggregate::TestUnequipSkill::test_unequip_success` | F | 指定枠を外し、外したスキルとデッキの通知を1件生成する |
| `TestSkillLoadoutAggregate::TestUnequipSkill::test_unequip_fails_when_slot_empty` | R | 空枠の解除には SkillNotFoundInSlotException を返す |
| `TestSkillLoadoutAggregate::TestUnequipSkill::test_unequip_prerequisite_skill_current_behavior` | R | 前提スキルを外しても依存する既装備スキルは残る |
| `TestSkillLoadoutAggregate::TestUseSkill::test_use_skill_success` | F | 使用スキルを返し、詠唱制限と待機期限を更新して使用通知を生成する |
| `TestSkillLoadoutAggregate::TestUseSkill::test_use_skill_just_after_cooldown_ends` | F | 詠唱制限が切れた後も冷却期限直前は拒否し、期限ちょうどに再使用できる |
| `TestSkillLoadoutAggregate::TestUseSkill::test_use_skill_fails_when_owner_mismatch` | F | 他人の使用を拒否し、現在のデッキ・詠唱制限・使用可否・通知を変えない |
| `TestSkillLoadoutAggregate::TestUseSkill::test_use_skill_fails_when_on_cooldown` | C | 詠唱制限終了直後 tick 11 でも冷却中は拒否する |
| `TestSkillLoadoutAggregate::TestUseSkill::test_use_skill_fails_when_cast_locked` | F | あるスキルの詠唱制限中は別スキルも使えず、制限終了ちょうどには使える |
| `TestSkillLoadoutAggregate::TestAwakenedMode::test_activate_awakened_mode_success` | F | 覚醒状態・期限を更新して、その期限を持つ発動通知を1件生成する |
| `TestSkillLoadoutAggregate::TestAwakenedMode::test_activate_awakened_mode_fails_when_already_active` | F | 覚醒中の再発動を拒否し、元の期間・軽減率・通知を保存する |
| `TestSkillLoadoutAggregate::TestAwakenedMode::test_awakened_mode_reduces_cooldown` | F | 覚醒中の待機時間は軽減後の小数を切り捨て、短縮後期限ちょうどに再使用できる |
| `TestSkillLoadoutAggregate::TestTick::test_tick_expires_awakened_mode` | F | 期限直前は覚醒、期限ちょうどで通常へ戻り終了通知は一度だけ |
| `TestSkillLoadoutAggregate::TestUpdateCapacity::test_update_capacity_success` | F | 容量の変更は両デッキの既存装備を保持し、変更容量を通知する |
| `TestSkillLoadoutAggregate::TestUpdateCapacity::test_update_capacity_fails_when_current_cost_exceeds_new_capacity` | R | 通常デッキの費用を下回る容量への更新は拒否する |
| `TestSkillLoadoutAggregate::TestValidation::test_invalid_slot_index_raises_error` | R | 装備の上限外・解除の負の枠には専用検証例外を返す |

### `tests/domain/skill/repository/test_skill_repository_ports.py`

| 元の宣言 | 判定 | 守る契約 |
|---|:---:|---|
| `test_skill_loadout_repository_is_abstract` | F | 所有者で検索する保存口を未実装の実装は生成できない |
| `test_skill_deck_progress_repository_is_abstract` | F | 進行状況の所有者検索を未実装の保存口は生成できない |
| `test_skill_spec_writer_is_abstract` | F | 定義書込み口は置換・削除の両方を実装する必要がある |

### `tests/domain/skill/value_object/test_skill_ids.py`

| 元の宣言 | 判定 | 守る契約 |
|---|:---:|---|
| `TestSkillIds::TestSkillLoadoutId::test_create_from_int_and_str` | R | SkillLoadoutId は整数と数字文字列を同じ数値IDへ変換する |
| `TestSkillIds::TestSkillLoadoutId::test_invalid_values_raise` | R | SkillLoadoutId の非正IDと数字でない文字列は型固有の例外にする |
| `TestSkillIds::TestSkillLoadoutId::test_int_and_str_conversion` | R | SkillLoadoutId は数値と十進文字列へ変換できる |
| `TestSkillIds::TestSkillDeckProgressId::test_create_from_int_and_str` | R | SkillDeckProgressId は整数と数字文字列を同じ数値IDへ変換する |
| `TestSkillIds::TestSkillDeckProgressId::test_invalid_values_raise` | R | SkillDeckProgressId の非正IDと数字でない文字列は型固有の例外にする |
| `TestSkillIds::TestSkillDeckProgressId::test_int_and_str_conversion` | R | SkillDeckProgressId は数値と十進文字列へ変換できる |

### `tests/domain/skill/value_object/test_skill_spec.py`

| 元の宣言 | 判定 | 守る契約 |
|---|:---:|---|
| `TestSkillSpec::TestValidation::test_skill_spec_accepts_optional_cost_none` | R | 費用が全て None の仕様は費用なしとして扱う |
| `TestSkillSpec::TestValidation::test_skill_spec_has_resource_cost_when_any_positive` | R | MP費用が正なら費用ありとして扱う |
| `TestSkillSpec::TestValidation::test_skill_spec_rejects_negative_fields` | R | 装備費用・詠唱制限・冷却時間は非負でなければならない |
| `TestSkillSpec::TestValidation::test_skill_spec_rejects_non_positive_power_multiplier` | R | 威力倍率0は拒否する |
| `TestSkillSpec::TestValidation::test_skill_spec_rejects_negative_optional_costs` | R | MP・体力・スタミナ各費用の負値を拒否する |
| `TestSkillSpec::TestValidation::test_skill_spec_rejects_negative_targeting_range` | R | 負の照準範囲を専用例外で拒否する |
| `TestSkillSpec::TestValidation::test_skill_spec_accepts_zero_targeting_range` | R | 範囲0は合法な指定値として保持する |
| `TestSkillSpec::TestValidation::test_skill_spec_accepts_positive_targeting_range` | R | 明示した正の照準範囲を保持する |
| `TestSkillSpec::TestValidation::test_skill_spec_default_targeting_range_is_one` | R | 未指定の照準範囲は1 |

## 契約の移管と残す層

`test_use_skill_fails_when_on_cooldown` の時刻11は、詠唱制限が終わったちょうどの時刻でも冷却が残ることを示す。`test_use_skill_just_after_cooldown_ends` の表へ時刻11を先に運び、既存の14で拒否・15で許可も残してから統合した。前提拒否の元の空デッキ行と、覚醒待機の軽減率0.4の元行も残した。

保存先は同じ集約試験と保存口試験。ファイル退役・製品の試験専用口削除はない。別層のアプリケーションは取得・資源消費・保存と当たり判定生成、保存実装は所有者検索と永続化、観測層は整形と配信を守るので維持する。アプリケーション試験の簡易作業単位は取消しを実装しておらず、集約の拒否後保存を代替する根拠にはしない。

## 意図した変異による確認

19種類それぞれで、変更前2ファイルの26ケースは成功し、変更後の該当保持先は狙った検証で失敗した。基準45ケースは4ファイル全体、変異対照の26ケースは修理した2ファイルである。

| 変異 | 新しい保持先の失敗 |
|---|---|
| 装備通知のロードアウトIDを999へ変更 | 対象IDの不一致 |
| 前提を両デッキの和集合で判定 | 別デッキ行で専用例外が出ない |
| 置換される枠も前提として算入 | 置換枠行で専用例外が出ない |
| 解除通知のスキルIDを999へ変更 | 外したスキルの不一致 |
| 使用したスキルを返さない | 返却がNone |
| 冷却拒否時に通知を全消去 | 拒否前の通知との不一致 |
| 所有者拒否時に詠唱制限を更新 | 詠唱制限が0から11へ変化 |
| 詠唱拒否時に通知を全消去 | 拒否前の通知との不一致 |
| 覚醒発動通知の終了時刻を1遅らせる | 通知の終了時刻31と期待30の不一致 |
| 発動中の再発動拒否で状態を初期化 | 覚醒状態の不一致 |
| 軽減待機を切上げにする | 端数行で時刻12に使用不可 |
| 覚醒デッキ選択の期限比較を含む側へ変更 | 期限ちょうどに覚醒側が残る |
| 覚醒終了済みでも終了通知を再生成 | 二度目の時刻更新で通知が増える |
| 検証後の通常容量再構築で装備を消す | 通常側の既存枠が空になる |
| 検証後の覚醒容量再構築で装備を消す | 覚醒側の既存枠が空になる |
| 装備保存口の所有者検索を任意にする | 欠落実装が生成できてしまう |
| 進行保存口の所有者検索を任意にする | 欠落実装が生成できてしまう |
| 定義書込み口の置換を任意にする | 削除だけの実装が生成できてしまう |
| 定義書込み口の削除を任意にする | 置換だけの実装が生成できてしまう |

各実行後に製品ソースをバイト単位で復元した。同サイズの変異を短時間で切り替えた初回はPythonキャッシュ再利用の疑いがあったため、対象キャッシュを削除し書込みを禁止して全19種類を再実行した結果だけを最終証拠にした。単純なslots引数削除は既存の縮小拒否試験でも検出したため、新しい試験の追加価値には数えていない。

## 実行結果

- 未編集4ファイル45ケース: 全成功
- 未編集の関連144ケース: 全成功
- 最終4ファイル51ケース: 2回とも全成功
- 最終の関連150ケース: 全成功
- 変更試験2ファイルのruff、git diff --check: 成功
- 試験差分: +218/-87行。製品・共通支援の変更: 0行
- 元41宣言→40宣言、展開後45ケース→51ケース。件数削減を目的にせず必要な境界行を追加
- 別担当の第二読・最終差分と全変異の保存確認: 合格

関連範囲は `tests/domain/skill`、`tests/application/skill`、`tests/infrastructure/repository/test_in_memory_skill_repositories.py`、`tests/infrastructure/repository/test_sqlite_skill_repositories.py`、`tests/application/observation/formatters/test_skill_formatter.py`、`tests/application/observation/services/test_skill_recipient_strategy.py`。資格情報を除去し、外部通信を禁止した実行器で検証した。LLM・実API試験は実行していない。全リポジトリの試験と、公開後の正確な差分コミットのCI結果はこのローカル検証に含まない。

## 別に残す容量の問題

覚醒側の新容量が既存装備費用を下回ると、`update_capacity(20, 5)` は専用例外を投げるが、先に更新された通常側容量20だけが残ることを別の調査で確認した。通常側が先に拒否する `update_capacity(2, 20)` は両デッキを保持した。これは既存基準の失敗ではなく追加調査である。

製品呼出元は見つかっておらず、ゲーム操作からの実害は未確認。再現は同じ集約を再利用する場合に限り、保存済みストアが拒否だけで変わることを示してはいない。拒否後の原子性は期待するドメイン契約としての提案で、明示仕様は未発見。今回の試験修理へ製品修正や部分更新を正当化する期待値は混ぜず、既存の通常側拒否試験を保持した。

## 参照した履歴と限界

- [スキル発動と当たり判定の接続](https://github.com/Motifman/llm-rpg/commit/48bed90ceddee509b85932fbe5a09ae16b395563)
- [スキルを含む保存形式の正規化](https://github.com/Motifman/llm-rpg/commit/202662716fa35d2d17578e63d04fb1bf2a669565)
- [本番の文字列IDを通す修理](https://github.com/Motifman/llm-rpg/commit/3baaf663b63dcca6b12227160fb570accb08bded)

各宣言の最初の導入理由は完全には特定できていない。この不足を推測で埋めて削除することはしていない。
