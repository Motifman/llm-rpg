# クエスト値の達成判定を既存の上限試験へ集約

## 範囲と判断

クエストの値4ファイル、全34宣言を監査し、R33 / F0 / C1 / D0 とした。`test_quest_objective.py` の `test_is_completed_when_met` だけを、同じファイルの `test_with_progress_caps_at_required` へ統合する。製品コードや集約試験は変更しない。

基準は `ba942f5a9cad4b6d362c9e2ce59566cc8ce3396f`。試験は34→33宣言/ケース、308→298行で、追加0行・削除10行。製品・試験支援の増減は0。実行時間の改善は主張しない。

## 保持先と入力の包含

削除する例は KILL_MONSTER / 対象101 / 必要数2 / 現在数2 / 副IDなしを構築し、達成判定がTrueであることだけを確認する。

残す上限試験は現在数1・必要数2へdelta5を加える。`with_progress` は結果を返す際、上と同じ種別・対象・必要数・現在数・副IDで `QuestObjective` を構築する。試験は現在数2と同じ `is_completed() is True` を既に確認している。このため入力や断言の追加は不要。

独立した再点検で、達成済み構築の例を別の復元契約として残す根拠はないと確認した。既存SQLite試験は現在数0を復元するもので、達成済み値の独立した証明ではない。

値の過大deltaを切り詰める契約は、集約が達成済み目標への通知を無視する契約とは分けて保持する。元の進捗値の不変性、宝箱の副IDの持越し、ID変換・数値拒否、報酬と範囲の既定値も保持する。hashの試験は同値のhash一致と集合の重複除去を検査し、異値のhash不一致は要求していない。

## 来歴と範囲の分離

- [クエスト基盤の導入](https://github.com/Motifman/llm-rpg/commit/569186222a2e725ab6eb28daa2bceb50863728cf)で、今回の値と基本試験が同時に追加された
- [宝箱進捗の導入](https://github.com/Motifman/llm-rpg/commit/dc40aaca5e38f371059c73801c56992b93e0f04b)で副IDの構築と更新時の持越しが追加された。この2契約はそのまま残す
- [#1678](https://github.com/Motifman/llm-rpg/pull/1678)は集約の遷移・拒否後の原状保持・全目標判定を扱う別監査。値4ファイルとは変更範囲が重ならない

2026-10-14 01:54 UTCにmainと開いている36件のPRの先頭を再確認し、対象の値4所有者・4試験の変更競合はなかった。記憶の移管やSNSの契約をこの監査の保持先には使わない。

## 保全と試験

Python 3.10.22 / pytest 8.4.1、固定済み依存、対象作業ツリーのソースで直列実行した。資格情報を除きネットワークを遮断した実行器を使用し、実LLM・有償APIは呼んでいない。

- 変更前の4ファイル: 34成功
- 変更前の関連5ファイル: 108成功
- `is_completed` の `>=` を `>` に変えた同一の一時改変: 旧保持先・旧統合対象・削除後保持先の3実行が全て、同一の2/2入力のTrue断言で失敗
- 製品を元のバイト列へ戻した後: 対象33成功、関連108成功

変異試験は各回、対象のPythonキャッシュを除去して書込みも禁止した。収集失敗や準備失敗を捕捉の証拠にしていない。製品所有者の復元前後SHA-256は `5cd4d7ebec6327c806c2470d104e53ccfee3d6c0afc57cc573f6bf55f9ab989f` で一致した。これは検出力を追加した変更ではなく、既存の等号境界の検出を保った統合である。

関連108件は集約33、コマンド27、進捗ハンドラ33、SQLite保存2、観測配信13。対象34/33件を含めず、監査済み宣言にも加算しない。全リポジトリ試験と公開先コミットのCIは別途確認する。

再実行は `uv run --frozen pytest tests/domain/quest/value_object` と、上の関連5ファイルを指定したpytest。変更試験のruffと差分の空白検査も成功した。

## 全34宣言の台帳

行は変更前の基準。Rは保持、Cは既存の保持先への統合。各値の公開構築・拒否・変換が主担当で、集約遷移、報酬決済、通知配信、保存方式の接続はそれぞれの層が担当する。

|試験ファイル|行|分類|宣言|守る契約|
|---|---:|---|---|---|
|`test_quest_id.py`|10|R|`test_create_positive_int_id`|正の最小ID 1を変えずに構築できる|
|`test_quest_id.py`|15|R|`test_create_large_positive_int_id`|大きな正のID 999999も変えずに構築できる|
|`test_quest_id.py`|20|R|`test_create_from_int_create_method`|create(123)が値123を持つQuestIdを返す|
|`test_quest_id.py`|26|R|`test_create_from_str_create_method`|create("456")が整数456を持つQuestIdを返す|
|`test_quest_id.py`|32|R|`test_create_zero_id_raises_error`|直接構築の0をQuestIdValidationExceptionで拒否する|
|`test_quest_id.py`|37|R|`test_create_negative_id_raises_error`|直接構築の-1と-100をQuestIdValidationExceptionで拒否する|
|`test_quest_id.py`|44|R|`test_create_from_negative_str_raises_error`|create("-5")が変換後も負数を拒否する|
|`test_quest_id.py`|49|R|`test_create_from_zero_str_raises_error`|create("0")が変換後も0を拒否する|
|`test_quest_id.py`|54|R|`test_create_from_invalid_str_raises_error`|文字列abc・12.5・空文字をドメイン例外へ揃える|
|`test_quest_id.py`|63|R|`test_str_conversion`|ID 789の文字列表現は数字だけの789になる|
|`test_quest_id.py`|68|R|`test_int_conversion`|ID 101のint変換は101になる|
|`test_quest_id.py`|73|R|`test_equality`|同値・異値のQuestIdと文字列・裸の整数の等価性を区別する|
|`test_quest_id.py`|81|R|`test_hash`|別インスタンスの同値IDは同じhashとなり集合内で重複しない|
|`test_quest_objective.py`|10|R|`test_create_kill_monster_objective`|討伐目標の種別・対象101・必要数3・進捗0を保持し未達成になる|
|`test_quest_objective.py`|24|R|`test_with_progress_increases_count`|with_progress(1)で0→1になり必要数3と元の進捗0を保つ|
|`test_quest_objective.py`|37|R|`test_with_progress_caps_at_required`|現在1/必要2へdelta5を加えても2で止まり達成になる|
|`test_quest_objective.py`|49|C|`test_is_completed_when_met`|同じ2/2入力と達成Trueをtest_with_progress_caps_at_requiredが保持|
|`test_quest_objective.py`|59|R|`test_required_count_zero_raises`|必要数0の目標をValueErrorで拒否する|
|`test_quest_objective.py`|69|R|`test_current_count_negative_raises`|現在数-1/必要3をValueErrorで拒否する|
|`test_quest_objective.py`|79|R|`test_current_count_over_required_raises`|現在数4/必要3をValueErrorで拒否する|
|`test_quest_objective.py`|89|R|`test_create_take_from_chest_with_target_id_secondary`|宝箱目標の種別・場所10・宝箱20・必要1・現在0を保持する|
|`test_quest_objective.py`|104|R|`test_with_progress_preserves_target_id_secondary`|宝箱目標を進めても副ID20を維持し進捗1になる|
|`test_quest_reward.py`|10|R|`test_of_empty_reward`|引数なしのof()は金0・経験値0・空tupleを返す|
|`test_quest_reward.py`|17|R|`test_of_gold_exp_only`|金100・経験値50を指定しアイテムを省略すると両数値と空tupleを保つ|
|`test_quest_reward.py`|24|R|`test_of_with_items`|金10・経験値5と異なる2報酬のID/数量/順序を保つ|
|`test_quest_reward.py`|37|R|`test_negative_gold_raises`|負の金-1をValueErrorで拒否する|
|`test_quest_reward.py`|42|R|`test_negative_exp_raises`|負の経験値-1をValueErrorで拒否する|
|`test_quest_reward.py`|47|R|`test_item_quantity_zero_raises`|アイテム数量0をValueErrorで拒否する|
|`test_quest_scope.py`|12|R|`test_public_scope`|公開範囲はPUBLIC、宛先/ギルドなし、公開だけTrueになる|
|`test_quest_scope.py`|22|R|`test_direct_scope`|直接範囲はDIRECT、指定PlayerId、ギルドなし、direct True/public Falseになる|
|`test_quest_scope.py`|32|R|`test_guild_scope`|ギルド範囲はGUILD_MEMBERS、ギルド10、宛先なし、guild Trueになる|
|`test_quest_scope.py`|40|R|`test_direct_scope_without_target_raises`|DIRECTで宛先NoneをQuestScopeValidationExceptionで拒否する|
|`test_quest_scope.py`|45|R|`test_guild_scope_without_guild_id_raises`|GUILD_MEMBERSでguild_id Noneをドメイン例外で拒否する|
|`test_quest_scope.py`|50|R|`test_public_scope_with_extra_raises`|PUBLICへ宛先またはギルドを個別に足す両入力を拒否する|

## 今回証明していないこと

全API入力の網羅を主張しない。既定delta・負のdelta、報酬入力リストの別名防止、全フィールドの不変性などを追加検証した変更ではない。値の既存ValueErrorを別の例外へ変える製品修正も含めない。`QuestId.create` と `QuestScope.is_public` は現在の製品直接呼出しが見つからないが、初回導入から提供される公開APIであり、この変更で除去しない。
