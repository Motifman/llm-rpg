# 行動予約の順序と取り消しの契約監査

## 結論

`tests/domain/intent` の4ファイル33宣言を全文確認した。30宣言を保持し、2宣言を補修、1宣言を同じ集約の保持試験へ統合した。製品コードと公開 API は変更していない。

- `OTHER` も含む5フェーズの順序を実入力で検証する
- 投稿時刻が ID より先に比較される契約を、既存の同時刻の確認と同じ表で検証する
- 取り出した予約が消える確認を、未来の予約が期限に達して最後の1件まで無くなる一連の試験へ統合する
- `Intent` / `IntentId` / `IntentPriority` の18宣言は保持し、3ファイルとも内容を変更しない

基準は `ba942f5a9cad4b6d362c9e2ce59566cc8ce3396f`。監査対象はこの4ファイル全体であり、変更した1ファイルだけではない。下の台帳は基準の原宣言を一度ずつ数える。

## なぜこの境界で残すか

`IntentQueue` が予約の重複禁止、取り出し順、期限、取り消し、一括投入の全件取消を所有する。`IntentResolutionService.submit_and_resolve_immediately` は `submit` 後に自分の ID を `remove` で取り出し、`drain_ready_for_tick` は呼ばない。そのため上位の正常処理が成功しても、フェーズ順や未来の予約が正しいとは限らない。

[導入コミット](https://github.com/Motifman/llm-rpg/commit/33dca987fc0561747c34d63aece488960f0edb4f) は、0を有効な ID とすること、不変な `Intent`、将来の持続時間・遅延対象解決向けの公開データ、`extend` の全件取消を意図的な契約として記録している。現在の内部呼出が少ないことだけを理由に公開 API を削除しない。

ID の値比較、優先度の比較可能性、既定0、負優先度、bool拒否、不変性は、簡単な構築試験でも異なる破損を検出する。特に queue は `priority.value` を直接使うため、queue の並べ替え試験は `IntentPriority` の比較演算子を代替しない。

## 全33宣言の台帳

Rは保持、Fは同じ所有者で入力・検証を補修、Cは記載した保持先への統合を表す。Dは0件。行番号と宣言名は基準時点のもの。保持先が「同宣言」のものはその宣言を残す。

### `tests/domain/intent/aggregate/test_intent_queue.py`

| 原宣言（基準行） | 判定 | 守る契約 / 検出する退行 | 保持先 |
|---|---|---|---|
| `TestIntentQueueDraining.test_empty_queue_returns_empty_list`（46） | R | 空の予約一覧を WorldTick(0) で取り出すと [] を返す / 空集合に対する先頭参照・例外化・None 返却 | 同宣言 |
| `TestIntentQueueDraining.test_phase_order_is_respected`（51） | F | MOVEMENT→INTERACTION→ATTACK→SOCIAL→OTHER の順序を守る / フェーズ順逆転を検出するが、OTHER の誤配置は現状入力に無く見逃す | 同宣言に OTHER を追加 |
| `TestIntentQueueDraining.test_within_phase_higher_priority_wins`（68） | R | 同じフェーズ内では優先度 5→3→0 の順で返す / 優先度を昇順にする、並べ替えキーから落とす | 同宣言 |
| `TestIntentQueueDraining.test_id_breaks_tie_for_same_phase_and_priority`（78） | F | フェーズと優先度が同じなら投稿時刻昇順、その時刻も同じなら ID 昇順になる / 既存の1行は ID キーの欠落・逆転を検出するが、投稿時刻キーの削除は全件同時刻のため通過する | `TestIntentQueueDraining.test_submission_tick_then_id_breaks_tie` の2行 |
| `TestIntentQueueDraining.test_future_intents_stay_in_queue`（88） | R | 期限到来分だけ取り出し、未来の別プレイヤーの予約は保持する / 全件を取り出す、未来分を捨てる、準備済みを残す、期限の <= を < に変える | 同宣言 |
| `TestIntentQueueDraining.test_drained_intents_are_removed`（99） | C | 取り出した1件を予約一覧から除く / drain が内容を返すだけで _items を除去しない | `TestIntentQueueDraining.test_future_intents_stay_in_queue` |
| `TestIntentQueueDraining.test_drain_invalid_tick_type_rejected`（106） | R | drain に整数を直接渡すと IntentValidationException / WorldTick ガード消失で AttributeError を漏らす、整数を黙って受理 | 同宣言 |
| `TestIntentQueueSubmit.test_same_player_same_tick_double_submit_rejected`（116） | R | 同一 player と submitted tick の二重登録を拒否 / 重複ガード削除、片方だけの条件比較による見逃し | 同宣言 |
| `TestIntentQueueSubmit.test_same_player_different_tick_allowed`（123） | R | 同じプレイヤーの異なる投稿 tick は共存する / プレイヤー一致だけで重複扱いにする | 同宣言 |
| `TestIntentQueueSubmit.test_different_players_same_tick_allowed`（131） | R | 異なるプレイヤーは同じ tick に共存できる / 投稿 tick の一致だけで重複扱いにする | 同宣言 |
| `TestIntentQueueSubmit.test_submit_non_intent_rejected`（138） | R | Intent 以外の登録を IntentValidationException で拒否 / ガード削除で文字列を登録する、または属性エラーを漏らす | 同宣言 |
| `TestIntentQueueCancel.test_remove_existing_intent`（148） | R | 指定 ID の予約だけ除いて返し、他予約を保持する / 別 ID の予約を除く、全件消去する、誤った予約を返す | 同宣言 |
| `TestIntentQueueCancel.test_remove_unknown_id_raises`（159） | R | 無い ID の除去は UnknownIntentException / 無い ID を None/成功扱いにする、一般例外に変える | 同宣言 |
| `TestIntentQueueExtend.test_extend_inserts_all_intents`（169） | R | extend が正常な複数予約を全件追加する / 先頭1件だけ追加する、反復を忘れる | 同宣言 |
| `TestIntentQueueExtend.test_extend_with_duplicate_rolls_back`（179） | R | extend 途中で重複すると追加全体を戻し事前予約を保持する / 途中までの追加を残す、事前状態まで消す、例外を吸収する | 同宣言 |

### `tests/domain/intent/value_object/test_intent.py`

| 原宣言（基準行） | 判定 | 守る契約 / 検出する退行 | 保持先 |
|---|---|---|---|
| `TestIntent.test_default_intent_is_instant`（50） | R | 投稿 tick と完了 tick が等しければ is_instant=True / 即時判定を常時 False にする、比較を > にする | 同宣言 |
| `TestIntent.test_future_complete_tick_is_not_instant`（55） | R | 完了 tick が未来なら is_instant=False / 即時判定を常時 True にする、complete >= submitted にする | 同宣言 |
| `TestIntent.test_complete_before_submitted_is_rejected`（60） | R | 完了時刻が投稿時刻より前の Intent は生成不可 / 時刻逆転ガードを削除する、符号を反転する | 同宣言 |
| `TestIntent.test_empty_tool_name_is_rejected`（65） | R | 空 tool_name を IntentValidationException で拒否 / 空文字を許容し呼出対象が失われる | 同宣言 |
| `TestIntent.test_arguments_must_be_mapping`（70） | R | arguments に list を渡すと IntentValidationException / Mapping 検査を削除して一覧を保持する | 同宣言 |
| `TestIntent.test_target_descriptor_optional`（75） | R | target_descriptor=None を有効な省略表現として保持 / None を空辞書へ置換する、必須化する | 同宣言 |
| `TestIntent.test_target_descriptor_accepts_mapping`（80） | R | target_descriptor の辞書を損なわず保持 / descriptor を無視して None にする、内容を捨てる | 同宣言 |
| `TestIntent.test_frozen_immutable`（85） | R | Intent の属性再代入を FrozenInstanceError で拒否 / frozen を外し投稿後に tool_name を変更できる | 同宣言 |

### `tests/domain/intent/value_object/test_intent_id.py`

| 原宣言（基準行） | 判定 | 守る契約 / 検出する退行 | 保持先 |
|---|---|---|---|
| `TestIntentId.test_valid_non_negative_int_is_accepted`（14） | R | IntentId は 0 と正整数を有効値として保持 / 0 を未割当扱いで拒否する、値を切り上げる | 同宣言 |
| `TestIntentId.test_negative_int_is_rejected`（19） | R | 負の IntentId を専用の IntentIdValidationException で拒否 / 負数ガードを削除する、別例外に変える | 同宣言 |
| `TestIntentId.test_non_int_is_rejected`（24） | R | 文字列の IntentId を専用例外で拒否 / 整数へ黙って変換する、型検査を削除し TypeError を漏らす | 同宣言 |
| `TestIntentId.test_bool_is_rejected`（29） | R | bool は int の派生型でも IntentId には使えない / isinstance(int) だけに単純化して True=1 を受理する | 同宣言 |
| `TestIntentId.test_equality_uses_value`（34） | R | 独立した同値 ID は等しく、異値 ID は等しくない / eq=False で参照同一性に戻す、常に同値扱いにする | 同宣言 |

### `tests/domain/intent/value_object/test_intent_priority.py`

| 原宣言（基準行） | 判定 | 守る契約 / 検出する退行 | 保持先 |
|---|---|---|---|
| `TestIntentPriority.test_default_value_is_zero`（16） | R | 引数省略の IntentPriority は中立値0 / 既定を1などに変え明示0との差を作る | 同宣言 |
| `TestIntentPriority.test_negative_value_is_accepted`（20） | R | 負の優先度 -5 をそのまま受理する / 一般的な正値バリデーションを誤って流用する | 同宣言 |
| `TestIntentPriority.test_non_int_is_rejected`（24） | R | 文字列の優先度を IntentPriorityValidationException で拒否 / 文字列を保持し後の並べ替えで壊れる、勝手に値へ変換する | 同宣言 |
| `TestIntentPriority.test_bool_is_rejected`（29） | R | bool を優先度として受理しない / int 判定だけへ変更し True を数値として受理する | 同宣言 |
| `TestIntentPriority.test_order_comparison`（34） | R | IntentPriority の < と > は数値順で比較できる / order=True を外す、大小方向を反転する | 同宣言 |

## 元の入力と統合後の保持

### フェーズ順

元の SOCIAL / MOVEMENT / ATTACK / INTERACTION の投入を残し、その前に OTHER を追加した。期待結果は MOVEMENT → INTERACTION → ATTACK → SOCIAL → OTHER。期待値を製品の並べ替え処理から生成せず、意味のある順序を明記する。

### 投稿時刻と ID

元の ID `7, 2, 5`、プレイヤー `10, 11, 12`、投稿・完了・現在時刻すべて `1` の入力を、そのまま表の1行目に残した。結果は `2, 5, 7`。

追加した2行目だけ投稿時刻を `1, 2, 3`、完了・現在時刻を `5` にする。同じ ID `7, 2, 5` に対して結果は `7, 2, 5` となり、投稿時刻が ID 順に優先することを確かめる。フェーズや優先度との複合条件まで無制限に拡張していない。

### 未来の予約と最後の除去

元の「時刻1でID1を取り出し、時刻3が期限のID2だけ残る」を維持した。同じ時刻で取り出しても空、時刻3でID2だけ取り出す、残数0、その後もう一度取り出しても空、までを同じ時間経過に加えた。

削除した `test_drained_intents_are_removed` が持つ契約について、最後の1件が消えない退行を旧試験と新しい保持先の両方が検出することを、同じ製品変異で確かめた。

## 4種類の変異による比較

各行について旧試験と候補をそれぞれ実行し、毎回 domain 全体33例を収集した。全8実行に収集エラー・想定外の例外・省略は無い。意図的な破損を検出した試験の失敗だけを数えた。

| 製品へ一時的に加えた破損 | 旧試験 | 候補の保持試験 |
|---|---|---|
| OTHER を先頭の値0に変更 | 33例とも成功し見逃す | `test_phase_order_is_respected` だけ失敗 |
| 投稿時刻の並べ替えキーだけ除去 | 33例とも成功し見逃す | `test_submission_tick_then_id_breaks_tie[earlier_submission_before_id]` だけ失敗 |
| 残り1件のときだけ取り出した予約を残す | 元の `test_drained_intents_are_removed` が失敗 | `test_future_intents_stay_in_queue` が失敗 |
| 準備済み予約を取り出しても一覧から除かない | 元の未来予約・単件除去の2宣言が失敗 | `test_future_intents_stay_in_queue` が失敗 |

変異後の製品は保存した原本へバイト単位で復元し、差分0を確認した。変異を残したまま成功試験を数えていない。

## 実行結果

通信を遮断した検証環境で Python 3.10.22 / pytest 8.4.1 を使い、対象の作業ツリーにある製品実装を読み込んだことを確認した。

- 基準: domain33例が成功。domain外の application/intent と mapper は別の50例が成功
- 候補: 同じ対象33例・domain外50例が成功
- 変異から復元後: 両方を単一の pytest 呼出で実行し、domain33＋domain外50＝83例が成功
- 最終 JUnit の classname/name は83一意。二つの経路を重複して数えていない
- 最終実行の失敗・例外・省略は0。Ruff、`git diff --check` も成功
- リポジトリ全体の試験と `test_two_agent_world_smoke.py` は今回実行していない

同じ範囲を通常のリポジトリ環境で確認するコマンド:

```bash
uv run --frozen pytest tests/domain/intent tests/application/intent tests/application/llm/test_tool_command_mapper_intent_path.py
uv run --frozen ruff check tests/domain/intent/aggregate/test_intent_queue.py
git diff --check
```

## 規模と変更範囲

- 元の試験: 4ファイル33宣言、353行
- 候補の試験: 4ファイル32宣言、368行。表の追加行があるので実行例は33例のまま
- 試験差分: 1ファイル、28行追加・13行削除、純増15行
- 同居する試験補助関数: 計45行で変更なし。353/368行に含まれるため別加算しない
- 製品所有者: 4ファイル306行、変更0。例外・列挙・再輸出などを含む domain/intent 全体423行にも最終差分なし
- 追加文書は試験・製品の行数に混ぜない。削減数を目標にせず、失われる証明が無いことを優先した

公開 API、補助関数、既存の例外、CI対象は変更しない。今回は `pending()` を不要にする変更ではなく、残る集約試験と application の予約分離試験が引き続き使う。

## 別の監査で確認すべき範囲

`tests/application/intent/test_intent_resolution_service.py` の `TestResolveDrained.test_resolves_each_intent_in_order` は `_resolve_drained` の説明を持つが、実際には即時実行メソッドだけを呼ぶ。`test_arguments_are_defensively_copied` も元データの変更が処理完了後で、コピーの効果そのものを確認していない。これらを今回のドメイン契約の保持証拠にせず、application側の監査候補として残す。製品不具合があるという結論ではない。
