# 取引イベントの発行件数と内容を同じ主試験で守る

## 結果

同じ準備・操作・引数でイベントを二度確認していた4組を統合した。全項目を確認する既存4例へ `len(events) == 1` を移し、型・取引ID・投影に使う情報を全部残した。

- 対象は `tests/domain/trade/test_trade_aggregate.py` の全41宣言。分類は R37 / F0 / C4 / D0
- 収集・合格数は41→37。基準41件を2回、変更後37件を2回実行し、全件合格
- 関連4ファイルは基準・変更後とも96件合格
- 試験ファイルは735→664行、+8/-79行。支援関数1つ・フィクスチャ13個は変更なし
- 製品コードと公開口の差分は0。状態遷移や拒否の仕様は変えていない
- 4種類の独立した重複発行の改変で、件数の確認が残す側へ移ったことを検証した
- ruff、差分の空白検査と独立保全レビューは合格。リモートCIは公開後に別途確認する

目的は、同じ発行契約の主担当を1例に揃え、片方だけへ確認が増えていく二重管理を解消すること。短い試験なので、以下の所要時間から高速化は主張しない。

## 範囲と経緯

基準試験と改変比較の上流コミット: `0b51eb28d4692635a932dcf4063ab9b231768bf0`

公開前に追随した上流コミット: `f8224b8cc805107785524d7255a68b88e1e4b65f`

所有者は `TradeAggregate` の出品・受託・取消・辞退によるイベント発行。市場注文と同席取引は別のモデルであり、その試験を代替証拠として数えない。trade領域全体を監査済みとする変更ではない。

- [最初の取引モデルと試験群](https://github.com/Motifman/llm-rpg/commit/994a3b5f009a67c3a8b2599b92c9ea58a4faad9c) に、出品・受託・取消の発行例と全項目例が同時に存在する。別の回帰原因を記した履歴はない
- [辞退機能の追加](https://github.com/Motifman/llm-rpg/commit/9ea6aca19fc3465114495ec7107551e33baef01d) でも辞退イベントの2例が同時に追加されている
- [投影情報の追加](https://github.com/Motifman/llm-rpg/commit/ff0868c060dd1bd4a667b1fb2748773249578cd1) は出品・受託の全項目例だけを強めている。取引後に別の保存先を再読込せず表示用モデルを組み立てるための情報なので、こちらを残す

## 統合先と移した確認

いずれも `TestTradeAggregate` 内。右側の既存例が、左側と同一の準備・引数で呼び出す主試験になる。

| 吸収した宣言 | 残す主試験 |
|---|---|
| `TestCreateNewTrade.test_create_trade_adds_trade_offered_event` | `TestDomainEvents.test_trade_offered_event_contains_all_fields` |
| `TestAcceptBy.test_accept_adds_trade_accepted_event` | `TestDomainEvents.test_trade_accepted_event_contains_all_fields` |
| `TestCancelBy.test_cancel_adds_trade_cancelled_event` | `TestDomainEvents.test_trade_cancelled_event_contains_all_fields` |
| `TestDecline.test_decline_adds_trade_declined_event` | `TestDecline.test_trade_declined_event_contains_all_fields` |

全4例へ件数1の確認を1行ずつ追加した。移植前の主試験は最初のイベントしか調べないため、2件以上の誤発行を見逃す。**同じ名前の型を調べているというだけで発行例を削除しない。**

主試験に元からあった34個のassertは、構文木で変更なしを確認した。件数の4個を加えて38個になる。`events[0]` と、その値を代入した `event` の別名を揃えると、吸収した宣言の全assertが主試験に含まれる。ファイル全体でも、4宣言の削除・件数4行の追加・仕様説明4つの更新以外に構文木の差はない。

保持した情報:

- 出品: 型、集約ID・種別、出品者、品、金額、範囲、投影用情報、取引作成日時、基底イベントの属性存在
- 受託: 型、集約ID・種別、買い手IDと表示名、出品者、品、金額、取引作成日時、投影用情報、基底イベントの属性存在
- 取消: 型、集約ID・種別、基底イベントの属性存在
- 辞退: 型、集約ID・種別、辞退者、基底イベントの属性存在

属性存在の確認をより強い値検査へ変えることや、共通イベントの責務整理は今回に混ぜていない。

## 別に残した契約

- 公開取引と直接取引の作成・受託は入力の種類が異なる。状態と買い手の設定を守る成功例を残す
- `can_be_accepted_by` は `TradeCommandService` が操作前の問い合わせに使う。操作の例外確認とは別の公開契約
- 出品→受託の蓄積例は2イベントの順序と保持を確認し、既存イベントの置換・消失を検出する。単発イベントの主試験とは統合しない
- 消去・取得リストの複製も残す。共通基底への試験移管をこの変更に混ぜない
- 辞退者が出品者の場合と公開取引の場合は、複数のガードから同じ拒否例外が出うる。特定ガードだけを除いても同じ拒否が残ることを、弱い試験という理由にしない
- `is_active` / `is_for_player` の通常の直接呼び出しは検索では見つからなかったが、公開口を廃止する証拠は不足する。今回のイベント統合と分離する

製品の通常経路は [TradeCommandService](../../src/ai_rpg_world/application/trade/services/trade_command_service.py) の4操作から集約を呼び、取引と所持品などを保存する。[TradeEventHandler](../../src/ai_rpg_world/application/trade/handlers/trade_event_handler.py) はイベントの投影用情報から表示用モデルを作る。メモリ上とSQLiteの保存先は、共通作業単位へ未発行イベントを集める。

ハンドラとJSON試験はイベントを直接作るので、集約が正しく情報を生成することの代わりにならない。SQLiteコマンド試験は実コマンドから保存したイベントの復元・配送を担う。これらの別層の試験は変更していない。

## 実行結果

Python 3.10.22、pytest 8.4.1、固定済み依存を使用。対象作業ツリーの製品ソースを読み、通信を遮断した直列実行。基準失敗はない。

| 実行 | 合格数 | 実時間 | pytest全体 | 準備・本体・後処理の合計 |
|---|---:|---:|---:|---:|
| 基準1 | 41 | 0.4860秒 | 0.1814秒 | 0.0222秒 |
| 基準2 | 41 | 0.4065秒 | 0.1251秒 | 0.0231秒 |
| 関連・基準 | 96 | 3.0894秒 | 2.5336秒 | 1.8372秒 |
| 変更後1 | 37 | 0.4777秒 | 0.1712秒 | 0.0259秒 |
| 変更後2 | 37 | 0.4223秒 | 0.1236秒 | 0.0206秒 |
| 関連・変更後 | 96 | 2.5655秒 | 2.1498秒 | 1.7395秒 |

収集だけの時間は今回の計測器では記録できていない。pytest全体から試験時間を引いた値には他の処理も含まれるため、収集時間とは扱わない。全リポジトリの試験は手元で実行していない。

関連96件の内訳は、通常コマンド22件、SQLiteファイルへ読み込まれた元のコマンドクラス22件、SQLite版の継承試験23件、SQLite固有7件、ハンドラ12件、JSON10件。元クラスの重複収集は別の候補であり、ここでは変更していない。96件を96種類の独立契約と主張しない。

再現する範囲:

```sh
uv run --frozen pytest tests/domain/trade/test_trade_aggregate.py
uv run --frozen pytest \
  tests/application/trade/services/test_trade_command_service.py \
  tests/application/trade/services/test_trade_command_service_sqlite.py \
  tests/application/trade/handlers/test_trade_event_handler.py \
  tests/infrastructure/events/test_trade_event_json_serializer.py
ruff check tests/domain/trade/test_trade_aggregate.py
git diff --check
```

通常CIは `.github/workflows/ci.yml` のPython 3.10 / `uv sync --locked --extra export` / `uv run --frozen pytest -n auto`。対象は標準の発見規則に含まれ、登録変更は不要。

## 公開前のmain追随

最初の比較後にmainが進んだため、新しい上流 `f8224b8cc805107785524d7255a68b88e1e4b65f` を取り込み、同じ範囲を再実行した。上の基準・変更後の比較と改変試験は、元の上流を基準とした証拠のまま区別する。

- 取引の製品所有者、共通ドメイン、取引アプリケーション、主試験、関連4ファイル、`uv.lock` は新旧mainで差分なし
- 追随後の主試験: 37件合格、実時間0.5458秒
- 追随後の関連試験: 96件合格、実時間3.0894秒
- 追随後もruffと差分の空白検査は合格。新mainからの差分は試験1ファイルと文書2ファイルのみで、製品変更は0

## 保全の改変試験

4操作それぞれのイベント追加をもう1回行う、独立した4改変を試した。各改変の旧版は吸収側と主試験の2件、新版は主試験1件を実行した。

| 改変 | 旧版 | 新版 | 失敗理由 |
|---|---|---|---|
| 出品の二重発行 | 発行例が失敗、全項目例は合格 | 主試験が失敗 | `len(events)` が2 |
| 受託の二重発行 | 発行例が失敗、全項目例は合格 | 主試験が失敗 | `len(events)` が2 |
| 取消の二重発行 | 発行例が失敗、全項目例は合格 | 主試験が失敗 | `len(events)` が2 |
| 辞退の二重発行 | 発行例が失敗、全項目例は合格 | 主試験が失敗 | `len(events)` が2 |

全8実行で、意図した件数比較 `2 == 1` による失敗を確認した。新しい不具合を修理した証拠ではなく、既存の件数契約を失わず移した証拠である。各操作の後に製品を元のバイト列へ戻し、全4改変後のSHA256は `fe0c566a02ba6dc9c2dc52da3b8936425220724f26d90f851a21c7f824eef276` と一致した。

辞退改変の最初の実行だけは、製品ファイル末尾の改行なしを実験スクリプトが扱えず構文エラーになった。これは契約の検証には数えていない。元のバイト列を復元したうえで改変生成を修正し、構文解析の事前確認を追加して再実行した結果が上表である。

## 全宣言の判定

行番号は基準版。Rは保持、Cは対応する主試験へ件数確認を吸収。F/Dは0。根拠は実際のassertと入力を読んで判定した。

### TradeAggregate

tests/domain/trade/test_trade_aggregate.py

分類: {'R': 37, 'C': 4}

|行|判定|宣言|根拠|
|---|---|---|---|
|189|R|`TestTradeAggregate.TestCreateNewTrade.test_create_global_trade_success`|公開出品の構築値・ACTIVE・買い手なし・版0の既定値|
|221|R|`TestTradeAggregate.TestCreateNewTrade.test_create_direct_trade_success`|直接出品の構築値・宛先範囲・ACTIVE・買い手なし・版0。公開出品と別入力|
|253|C|`TestTradeAggregate.TestCreateNewTrade.test_create_trade_adds_trade_offered_event`|655行の全フィールド例へ件数1を移して吸収。型・ID・出品情報は既に包含|
|288|R|`TestTradeAggregate.TestIsActive.test_active_trade_returns_true`|ACTIVEの公開状態照会。通常の製品呼び出し不在だけでは削除を確定しない|
|293|R|`TestTradeAggregate.TestIsActive.test_completed_trade_returns_false`|COMPLETEDがACTIVE照会に混入しない。公開口の削除は別調査|
|298|R|`TestTradeAggregate.TestIsActive.test_cancelled_trade_returns_false`|CANCELLEDがACTIVE照会に混入しない。公開口の削除は別調査|
|306|R|`TestTradeAggregate.TestIsDirectTrade.test_global_trade_returns_false`|公開出品を直接取引と判定しない。accept_by / decline_byが利用する|
|311|R|`TestTradeAggregate.TestIsDirectTrade.test_direct_trade_returns_true`|直接出品を直接取引と判定する。accept_by / decline_byが利用する|
|319|R|`TestTradeAggregate.TestIsForPlayer.test_global_trade_always_returns_false`|公開出品を特定人向けと返さない。公開口の削除は別調査|
|326|R|`TestTradeAggregate.TestIsForPlayer.test_direct_trade_with_target_player_returns_true`|直接出品の宛先照会。公開口の削除は別調査|
|334|R|`TestTradeAggregate.TestIsForPlayer.test_direct_trade_with_other_player_returns_false`|直接出品の宛先以外を対象と返さない。公開口の削除は別調査|
|344|R|`TestTradeAggregate.TestCanBeAcceptedBy.test_inactive_trade_returns_false`|受託可否照会が完了済みを除外する。アプリが直接使う|
|349|R|`TestTradeAggregate.TestCanBeAcceptedBy.test_seller_cannot_accept_own_trade`|受託可否照会が自己出品を除外する。アプリが直接使う|
|357|R|`TestTradeAggregate.TestCanBeAcceptedBy.test_direct_trade_wrong_player_returns_false`|受託可否照会が宛先以外を除外する。アプリが直接使う|
|364|R|`TestTradeAggregate.TestCanBeAcceptedBy.test_global_trade_other_player_can_accept`|公開出品の他人には受託可を返す。拒否だけへ変わる退行の対照|
|371|R|`TestTradeAggregate.TestCanBeAcceptedBy.test_direct_trade_target_player_can_accept`|直接出品の宛先には受託可を返す。拒否だけへ変わる退行の対照|
|382|R|`TestTradeAggregate.TestAcceptBy.test_successful_acceptance_of_global_trade`|公開取引の受託で買い手とCOMPLETEDが設定される。イベントの例とは別契約|
|393|R|`TestTradeAggregate.TestAcceptBy.test_successful_acceptance_of_direct_trade`|直接取引の宛先が受託して買い手とCOMPLETEDになる|
|405|R|`TestTradeAggregate.TestAcceptBy.test_accept_inactive_trade_raises_exception`|完了済み取引を再受託できない|
|411|R|`TestTradeAggregate.TestAcceptBy.test_seller_accept_own_trade_raises_exception`|出品者の自己受託を固有例外で拒否する|
|420|R|`TestTradeAggregate.TestAcceptBy.test_wrong_player_accept_direct_trade_raises_exception`|宛先以外の受託を固有例外で拒否する|
|428|C|`TestTradeAggregate.TestAcceptBy.test_accept_adds_trade_accepted_event`|692行の全フィールド例へ件数1を移して吸収|
|441|R|`TestTradeAggregate.TestAcceptBy.test_accept_cancelled_trade_raises_exception`|取消済み取引を受託できない。完了済みとは異なる終端状態|
|450|R|`TestTradeAggregate.TestCancelBy.test_successful_cancellation`|出品者の取消でCANCELLEDになる。イベント内容とは別契約|
|461|R|`TestTradeAggregate.TestCancelBy.test_cancel_inactive_trade_raises_exception`|完了済み取引を取消できない|
|470|R|`TestTradeAggregate.TestCancelBy.test_non_seller_cancel_trade_raises_exception`|出品者以外は取消できない|
|478|C|`TestTradeAggregate.TestCancelBy.test_cancel_adds_trade_cancelled_event`|718行の全フィールド例へ件数1を移して吸収|
|493|R|`TestTradeAggregate.TestCancelBy.test_cancel_cancelled_trade_raises_exception`|取消済みへの再取消を拒否する|
|505|R|`TestTradeAggregate.TestDecline.test_decline_by_target_player_succeeds`|直接取引の宛先が辞退するとCANCELLEDで非ACTIVEになる|
|516|R|`TestTradeAggregate.TestDecline.test_decline_by_seller_raises_exception`|出品者は辞退できない。同じ例外の別ガードだけでは弱い試験としない|
|524|R|`TestTradeAggregate.TestDecline.test_decline_by_other_player_raises_exception`|宛先以外の第三者は辞退できない|
|532|R|`TestTradeAggregate.TestDecline.test_decline_global_trade_raises_exception`|公開取引は辞退できない。同じ例外の別ガードだけでは弱い試験としない|
|540|R|`TestTradeAggregate.TestDecline.test_decline_completed_trade_raises_exception`|完了済み取引を辞退できない|
|548|C|`TestTradeAggregate.TestDecline.test_decline_adds_trade_declined_event`|563行の全フィールド例へ件数1を移して吸収|
|563|R|`TestTradeAggregate.TestDecline.test_trade_declined_event_contains_all_fields`|辞退者と取引ID・型・基底情報を保つ主試験。548行から件数1を吸収|
|583|R|`TestTradeAggregate.TestDomainEvents.test_events_are_accumulated`|発行→受託が2件を順序どおり保持し、既存イベントを消さない|
|614|R|`TestTradeAggregate.TestDomainEvents.test_clear_events_removes_all_events`|未発行イベントの明示消去。共通所有者への移管をこの候補に混ぜない|
|642|R|`TestTradeAggregate.TestDomainEvents.test_get_events_returns_copy_not_reference`|イベント取得が同じリスト参照を返さない。共通所有者への移管をこの候補に混ぜない|
|655|R|`TestTradeAggregate.TestDomainEvents.test_trade_offered_event_contains_all_fields`|投影情報と取引日時を含む出品イベントの主試験。253行から件数1を吸収|
|692|R|`TestTradeAggregate.TestDomainEvents.test_trade_accepted_event_contains_all_fields`|表示名・投影・出品者・品・金額・日時を含む受託イベントの主試験。428行から件数1を吸収|
|718|R|`TestTradeAggregate.TestDomainEvents.test_trade_cancelled_event_contains_all_fields`|取引ID・型・基底情報を保つ取消イベント主試験。478行から件数1を吸収|

## 今後の所有権

同一操作・同一入力のイベントを別の宣言で繰り返す前に、既存の主試験へ確認を追加できるか確認する。発行件数と内容を同じ主試験が所有する。別層の追加には、配送・永続化・順序・復元など、その層固有の失敗を示す。状態遷移とイベントの契約を一括削除しない。
