# ショップ・ドメインテストの整理と拒否時保証

## 要点

所有する4ファイル・48宣言を確認し、重複8宣言の検証を既存の主担当へ移した。非所有者による出品・取り下げの2宣言には、拒否後も出品と未発行イベントが変化しない保証を追加した。本番コードは変更していない。

reprの弱いORは、どの表示規約を守るべきか独立した根拠がないため保留。単純な値保存・変換・正数境界・等価性・hashは、公開契約として残した。

## 変更規模と入力の保存

| 項目 | 変更前 | 変更後 |
|---|---:|---:|
| テストファイル | 4 | 4 |
| テスト宣言 | 48 | 40 |
| pytestの収集ケース | 48 | 45 |
| テスト4ファイルの行数 | 667 | 574 |
| パッケージ初期化込み | 669 | 576 |
| 本番変更行数 | 0 | 0 |

変更したのはテスト3ファイル、82行追加・175行削除、純減93行。宣言が8件減っても入力を8件捨てたわけではない。IDの1/999999と価格の1/50/100を入力表で保持し、非所有者拒否には空イベント/既存イベントありの2行を各1宣言へ追加した。この入力表への展開で、40宣言から45ケースが収集される。

作成時の非空名「店」・非空説明「説明文」の状態確認はそのまま残した。既定値の空文字を確認するイベント試験も別入力として残している。出品ID値オブジェクトの試験ファイルとrepr試験は未変更。

## 根拠

固定点は上流`0b51eb28d4692635a932dcf4063ab9b231768bf0`。元の全宣言を読み、集約・値オブジェクト・イベント受信側・コマンドサービス・SQLite保存復元との責務を照合した。

- [購入イベント導入の履歴](https://github.com/Motifman/llm-rpg/commit/92edfa2fc4d0f9d00eccbc2142a9908910358c54)は読取モデル更新のために購入イベントの内容を保証している。単なる属性コピーとして削らない
- [投影情報拡張の履歴](https://github.com/Motifman/llm-rpg/commit/669d5bb38d9e9fe78b4f9238cf94ab8c77c28eee)は受信時の再読込を減らしている。イベントの投影情報・位置・当事者を保持する
- 在庫・所持金・商品移動はアプリケーション側の責務。集約の購入イベント試験を取引全体の試験とは呼ばず、関連層も変更前後に実行した
- 非所有者拒否の修理は、集約の「所有者だけが出品・取り下げを変更できる」契約に基づく。現在の実装が壊れていたという主張ではなく、将来の壊れ方を見逃していた検証の修理

## 検証結果

| 対象 | 変更前 | 変更後 |
|---|---|---|
| 全shopドメイン | 48成功×2（0.16秒、0.11秒） | 45成功×2（0.17秒、0.10秒） |
| application/shopとショップ関連リポジトリ | 71成功（0.96秒） | 71成功（0.76秒） |
| 変更領域のruff | 編集前の基準は未実行 | 成功 |
| git diff --check | 成功 | 成功 |
| 本番ソースとの差分 | 0 | 0 |

時間はpytestの表示値。プロセス起動を含む実時間は主試験の変更前0.525/0.385秒、変更後0.459/0.376秒。安い試験で測定回数も少なく、速度改善は主張しない。

Python3.10.22・pytest8.4.1でsrcを優先して実行し、外部通信を遮断、認証環境変数を除去した。外部LLM・実APIは呼ばない。関連71件の内訳は`tests/application/shop`、SQLiteのショップ集約・読取モデルリポジトリ、InMemoryの出品/概要読取モデルリポジトリ。リポジトリ全体の試験やGitHub CIを実行したとは主張しない。

基準測定後の初回候補も45成功。測定日は2026-10-13。通常のローカル再現コマンドは次のとおり。外部APIへ接続する試験は選ばない。

```bash
uv run --frozen pytest tests/domain/shop -q
uv run --frozen pytest tests/application/shop \
  tests/infrastructure/repository/test_sqlite_shop_repository.py \
  tests/infrastructure/repository/test_sqlite_shop_read_model_repositories.py \
  tests/infrastructure/repository/test_in_memory_shop_listing_read_model_repository.py \
  tests/infrastructure/repository/test_in_memory_shop_summary_read_model_repository.py -q
uv run --frozen ruff check tests/domain/shop
git diff --check
```

変異は下表の変更を本番所有箇所へ1件ずつ一時適用し、表の対応領域を旧・新の試験それぞれで実行した。直列に実行し、各変更を復元してから次に進めた。

## 変異による検出力の確認

拒否時の壊れ方8件を本番ソースへ一時的に入れ、旧テストは成功する一方、修理後は対応する状態またはイベントの一致検証で失敗することを確認した。別に、統合した契約7件は旧・新の双方で失敗することを確認した。

すべて収集エラーや準備の例外ではなく、対象の検証失敗である。各変異の終了時に本番3ファイルを基準のバイト列へ復元し、SHA256を記録。最後にGitの基準内容とも一致を確認し、通常の全shop試験を2回成功させた。

| 変異 | 旧テスト | 新テスト | 狙った契約 |
|---|---|---|---|
| list-insert-before-denial | 成功（見逃し） | 失敗（検出） | 非所有者の出品を保存してから拒否 |
| list-erase-existing | 成功（見逃し） | 失敗（検出） | 拒否時に既存の別出品を消去 |
| unlist-delete-before-denial | 成功（見逃し） | 失敗（検出） | 拒否対象の出品を消してから拒否 |
| unlist-erase-unrelated | 成功（見逃し） | 失敗（検出） | 拒否時に対象以外の出品だけを消去 |
| list-forged-event | 成功（見逃し） | 失敗（検出） | 拒否される出品イベントを誤発行 |
| unlist-forged-event | 成功（見逃し） | 失敗（検出） | 拒否される取り下げイベントを誤発行 |
| list-drop-events | 成功（見逃し） | 失敗（検出） | 出品拒否時に既存の保留イベントを消去 |
| unlist-drop-events | 成功（見逃し） | 失敗（検出） | 取り下げ拒否時に既存の保留イベントを消去 |
| create-drop-type | 失敗（検出） | 失敗（検出） | 移管した開設イベントの集約型名が欠落 |
| listed-drop-projection | 失敗（検出） | 失敗（検出） | 移管した出品イベントの投影情報が欠落 |
| unlisted-drop-location | 失敗（検出） | 失敗（検出） | 移管した取り下げイベントの位置情報が欠落 |
| purchase-double-event | 失敗（検出） | 失敗（検出） | 移管した購入イベントの件数保証に対する二重発行 |
| listing-id-mismatch | 失敗（検出） | 失敗（検出） | 移管した取得結果の出品IDが辞書キーと不一致 |
| large-id-truncated | 失敗（検出） | 失敗（検出） | 保存した入力999999だけを誤変換 |
| price-50-corrupted | 失敗（検出） | 失敗（検出） | 保存した入力50だけを誤変換 |

保留イベント消去の2変異では、空イベント行は成功し、既存イベントあり行だけが失敗した。非空条件を追加した意味も実測できている。失敗ケースと本番復元値は以下に記録する。


### 変異の失敗箇所と復元証拠

表のケース名は所属する`tests/domain/shop`内のテスト名。拒否修理の8件は旧集約テスト21件が全て成功し、新集約テスト17ケースのうち記載したケースだけが失敗した。後半7件は旧・新とも検出した。全30実行で収集・準備エラーは0。

| 変異 | 新試験で失敗したケース |
|---|---|
| list-insert-before-denial | `test_list_item_non_owner_raises[empty_events]`, `test_list_item_non_owner_raises[pending_events]` |
| list-erase-existing | `test_list_item_non_owner_raises[empty_events]`, `test_list_item_non_owner_raises[pending_events]` |
| unlist-delete-before-denial | `test_unlist_item_non_owner_raises[empty_events]`, `test_unlist_item_non_owner_raises[pending_events]` |
| unlist-erase-unrelated | `test_unlist_item_non_owner_raises[empty_events]`, `test_unlist_item_non_owner_raises[pending_events]` |
| list-forged-event | `test_list_item_non_owner_raises[empty_events]`, `test_list_item_non_owner_raises[pending_events]` |
| unlist-forged-event | `test_unlist_item_non_owner_raises[empty_events]`, `test_unlist_item_non_owner_raises[pending_events]` |
| list-drop-events | `test_list_item_non_owner_raises[pending_events]` |
| unlist-drop-events | `test_unlist_item_non_owner_raises[pending_events]` |
| create-drop-type | `test_create_adds_shop_created_event` |
| listed-drop-projection | `test_list_item_success` |
| unlisted-drop-location | `test_unlist_item_success` |
| purchase-double-event | `test_record_purchase_adds_event_with_all_fields` |
| listing-id-mismatch | `test_list_item_success` |
| large-id-truncated | `test_create_positive_int_id[999999]` |
| price-50-corrupted | `test_create_positive_value[50]` |

本番ファイルは各変異終了時と最終試験前に元のバイト列へ復元した。最終内容は基準Gitツリーと一致し、SHA256は次のとおり。テストの変更前・変更後で本番コードは同一。

| 本番ファイル | 復元後SHA256 |
|---|---|
| src/ai_rpg_world/domain/shop/aggregate/shop_aggregate.py | `1db07650ee3b4801221065777c786b17f07c553348b7b2540a3156bdeba2c233` |
| src/ai_rpg_world/domain/shop/value_object/shop_id.py | `37096c933092a274ac01fdd64167316bb9cad55d7e95fdb7d6c2eb42ae6d1e60` |
| src/ai_rpg_world/domain/shop/value_object/shop_listing_price.py | `7745100cb8726b89c4aa882eaa69cb22b5ea0500c92650807ee870ba87a1fabd` |

## 統合8宣言の全assert移管確認

元の各assertをASTで抽出し、eventとevents[0]の同一参照、入力表の999999/50だけを正規化して残存先に含まれることを検査した。単なる件数比較ではない。元assertは合計39個あり、すべて残存先に対応した。

| 元宣言 | 残す宣言 | 移管した検証数 |
|---|---|---:|
| TestShopAggregate::TestCreate::test_create_event_contains_all_fields | TestShopAggregate::TestCreate::test_create_adds_shop_created_event | 11 |
| TestShopAggregate::TestIsOwner::test_owner_returns_true | TestShopAggregate::TestCreate::test_create_success | 1 |
| TestShopAggregate::TestListItem::test_list_item_event_contains_all_fields | TestShopAggregate::TestListItem::test_list_item_success | 10 |
| TestShopAggregate::TestUnlistItem::test_unlist_item_event_contains_all_fields | TestShopAggregate::TestUnlistItem::test_unlist_item_success | 9 |
| TestShopAggregate::TestRecordPurchase::test_record_purchase_success | TestShopAggregate::TestRecordPurchase::test_record_purchase_adds_event_with_all_fields | 2 |
| TestShopAggregate::TestGetListing::test_get_listing_returns_listing | TestShopAggregate::TestListItem::test_list_item_success | 3 |
| TestShopId::test_create_large_positive_int_id | TestShopId::test_create_positive_int_id | 1 |
| TestShopListingPrice::test_of_factory_method | TestShopListingPrice::test_create_positive_value | 2 |

元入力も維持した。createの既定値、出品/取下げの商品100・価格50・所有者1・投影、購入数2/総額100は同じ操作へ移管。get_listingのlisting.listing_id確認は出品成功へ移した。999999と50は専用の誤変換変異でも検出できた。

## 元の全48宣言と最終的な残存先

R=維持、C=検証と入力を主担当へ移して統合、F=検証修理候補。F3件のうち非所有者拒否2件を修理し、repr1件は保留。D=0。元の行番号は固定SHAへのリンク、残存先行番号はこの変更後のファイルを指す。

### tests/domain/shop/test_shop_aggregate.py

| 元宣言 | 判断 | 残存先 | 守る契約・根拠 |
|---|---|---|---|
| [TestShopAggregate::TestCreate::test_create_success](https://github.com/Motifman/llm-rpg/blob/0b51eb28d4692635a932dcf4063ab9b231768bf0/tests/domain/shop/test_shop_aggregate.py#L74-L96) | R: 維持 | TestShopAggregate::TestCreate::test_create_success L74-L96 | 指定された識別子・位置・名前・説明と所有者で空の店を作る。名前や説明を無視する、初期出品が混入する変更を検出。非空入力を維持 |
| [TestShopAggregate::TestCreate::test_create_adds_shop_created_event](https://github.com/Motifman/llm-rpg/blob/0b51eb28d4692635a932dcf4063ab9b231768bf0/tests/domain/shop/test_shop_aggregate.py#L98-L121) | R: 維持 | TestShopAggregate::TestCreate::test_create_adds_shop_created_event L98-L124 | 省略した名前・説明の既定値と所有者を含む開設イベントを正確に1件出す。未発行・二重発行・既定値変更を検出。開設イベントの残存先 |
| [TestShopAggregate::TestCreate::test_create_event_contains_all_fields](https://github.com/Motifman/llm-rpg/blob/0b51eb28d4692635a932dcf4063ab9b231768bf0/tests/domain/shop/test_shop_aggregate.py#L123-L149) | C: 統合済み | TestShopAggregate::TestCreate::test_create_adds_shop_created_event L98-L124 | 直前の既定値イベント試験と同じ入力。aggregate_type、occurred_at/event_idの存在確認をtest_create_adds_shop_created_eventへ移した |
| [TestShopAggregate::TestIsOwner::test_owner_returns_true](https://github.com/Motifman/llm-rpg/blob/0b51eb28d4692635a932dcf4063ab9b231768bf0/tests/domain/shop/test_shop_aggregate.py#L154-L156) | C: 統合済み | TestShopAggregate::TestCreate::test_create_success L74-L96 | 初期所有者を受け入れる同一assertはtest_create_successに既存。その他の入力・準備・副作用はない |
| [TestShopAggregate::TestIsOwner::test_non_owner_returns_false](https://github.com/Motifman/llm-rpg/blob/0b51eb28d4692635a932dcf4063ab9b231768bf0/tests/domain/shop/test_shop_aggregate.py#L158-L162) | R: 維持 | TestShopAggregate::TestIsOwner::test_non_owner_returns_false L129-L133 | 別プレイヤーを所有者扱いしない。所有者判定の常時True化を検出 |
| [TestShopAggregate::TestListItem::test_list_item_success](https://github.com/Motifman/llm-rpg/blob/0b51eb28d4692635a932dcf4063ab9b231768bf0/tests/domain/shop/test_shop_aggregate.py#L167-L192) | R: 維持 | TestShopAggregate::TestListItem::test_list_item_success L138-L175 | 公開取得で出品・商品・価格・出品者と1件の出品イベントを検証。保存忘れ・誤保存・二重発行を検出。出品状態とイベントの残存先 |
| [TestShopAggregate::TestListItem::test_list_item_non_owner_raises](https://github.com/Motifman/llm-rpg/blob/0b51eb28d4692635a932dcf4063ab9b231768bf0/tests/domain/shop/test_shop_aggregate.py#L194-L210) | F: 修理済み | TestShopAggregate::TestListItem::test_list_item_non_owner_raises L178-L209 | 非所有者拒否の例外契約は有用。ただし変更後に例外を出しても成功する。既存出品とイベントの不変を追加済み |
| [TestShopAggregate::TestListItem::test_list_item_event_contains_all_fields](https://github.com/Motifman/llm-rpg/blob/0b51eb28d4692635a932dcf4063ab9b231768bf0/tests/domain/shop/test_shop_aggregate.py#L212-L240) | C: 統合済み | TestShopAggregate::TestListItem::test_list_item_success L138-L175 | 同じ出品操作のイベント項目をtest_list_item_successへ移した。listing_projectionは2026-03の履歴で裏付けられた非同期投影契約 |
| [TestShopAggregate::TestUnlistItem::test_unlist_item_success](https://github.com/Motifman/llm-rpg/blob/0b51eb28d4692635a932dcf4063ab9b231768bf0/tests/domain/shop/test_shop_aggregate.py#L245-L265) | R: 維持 | TestShopAggregate::TestUnlistItem::test_unlist_item_success L214-L244 | 所有者が取り下げると対象が消え、取り下げイベントだけが1件出る。削除漏れ・二重発行を検出。取り下げ状態とイベントの残存先 |
| [TestShopAggregate::TestUnlistItem::test_unlist_item_non_owner_raises](https://github.com/Motifman/llm-rpg/blob/0b51eb28d4692635a932dcf4063ab9b231768bf0/tests/domain/shop/test_shop_aggregate.py#L267-L283) | F: 修理済み | TestShopAggregate::TestUnlistItem::test_unlist_item_non_owner_raises L247-L274 | 非所有者拒否の例外契約は有用。ただし対象を消してから例外でも成功する。対象・他出品・保留イベントの不変を追加済み |
| [TestShopAggregate::TestUnlistItem::test_unlist_nonexistent_listing_raises](https://github.com/Motifman/llm-rpg/blob/0b51eb28d4692635a932dcf4063ab9b231768bf0/tests/domain/shop/test_shop_aggregate.py#L285-L292) | R: 維持 | TestShopAggregate::TestUnlistItem::test_unlist_nonexistent_listing_raises L276-L283 | 所有者でも存在しない出品はListingNotFoundException。黙認や別例外を検出 |
| [TestShopAggregate::TestUnlistItem::test_unlist_item_event_contains_all_fields](https://github.com/Motifman/llm-rpg/blob/0b51eb28d4692635a932dcf4063ab9b231768bf0/tests/domain/shop/test_shop_aggregate.py#L294-L320) | C: 統合済み | TestShopAggregate::TestUnlistItem::test_unlist_item_success L214-L244 | 同じ取り下げ操作の位置・出品ID・操作主等をtest_unlist_item_successへ移した |
| [TestShopAggregate::TestRecordPurchase::test_record_purchase_success](https://github.com/Motifman/llm-rpg/blob/0b51eb28d4692635a932dcf4063ab9b231768bf0/tests/domain/shop/test_shop_aggregate.py#L325-L350) | C: 統合済み | TestShopAggregate::TestRecordPurchase::test_record_purchase_adds_event_with_all_fields L288-L325 | 同じ出品ID=1、商品=100、価格=50、数量=2、総額=100で同じ購入記録。len(events)==1をtest_record_purchase_adds_event_with_all_fieldsへ移した |
| [TestShopAggregate::TestRecordPurchase::test_record_purchase_adds_event_with_all_fields](https://github.com/Motifman/llm-rpg/blob/0b51eb28d4692635a932dcf4063ab9b231768bf0/tests/domain/shop/test_shop_aggregate.py#L352-L388) | R: 維持 | TestShopAggregate::TestRecordPurchase::test_record_purchase_adds_event_with_all_fields L288-L325 | 購入記録の出品・商品・買い手・数量・総額・売り手を確認。受信者に誤った情報を送る変更を検出。購入イベントの残存先 |
| [TestShopAggregate::TestRecordPurchase::test_record_purchase_listing_not_found_raises](https://github.com/Motifman/llm-rpg/blob/0b51eb28d4692635a932dcf4063ab9b231768bf0/tests/domain/shop/test_shop_aggregate.py#L390-L402) | R: 維持 | TestShopAggregate::TestRecordPurchase::test_record_purchase_listing_not_found_raises L327-L339 | 存在しない出品の購入記録を拒否。欠損出品のイベント生成や別例外を検出 |
| [TestShopAggregate::TestRemoveListing::test_remove_listing_success](https://github.com/Motifman/llm-rpg/blob/0b51eb28d4692635a932dcf4063ab9b231768bf0/tests/domain/shop/test_shop_aggregate.py#L407-L422) | R: 維持 | TestShopAggregate::TestRemoveListing::test_remove_listing_success L344-L359 | 売り切れ用の公開操作で対象出品が消える。取り下げとは別の呼び出し元を持ち、削除漏れを検出 |
| [TestShopAggregate::TestRemoveListing::test_remove_listing_nonexistent_raises](https://github.com/Motifman/llm-rpg/blob/0b51eb28d4692635a932dcf4063ab9b231768bf0/tests/domain/shop/test_shop_aggregate.py#L424-L427) | R: 維持 | TestShopAggregate::TestRemoveListing::test_remove_listing_nonexistent_raises L361-L364 | 売り切れ用操作の存在しないIDをドメイン例外にする。無言の成功やKeyErrorへの退行を検出 |
| [TestShopAggregate::TestGetListing::test_get_listing_returns_listing](https://github.com/Motifman/llm-rpg/blob/0b51eb28d4692635a932dcf4063ab9b231768bf0/tests/domain/shop/test_shop_aggregate.py#L432-L450) | C: 統合済み | TestShopAggregate::TestListItem::test_list_item_success L138-L175 | 出品後の取得はtest_list_item_successで既に実行。唯一追加のlisting.listing_id一致assertをそちらへ移管 |
| [TestShopAggregate::TestGetListing::test_get_listing_nonexistent_returns_none](https://github.com/Motifman/llm-rpg/blob/0b51eb28d4692635a932dcf4063ab9b231768bf0/tests/domain/shop/test_shop_aggregate.py#L452-L454) | R: 維持 | TestShopAggregate::TestGetListing::test_get_listing_nonexistent_returns_none L369-L371 | 存在しないIDの公開照会はNone。例外化やダミー出品を返す変更を検出 |
| [TestShopAggregate::TestAddOwnerRemoveOwner::test_add_owner_then_is_owner](https://github.com/Motifman/llm-rpg/blob/0b51eb28d4692635a932dcf4063ab9b231768bf0/tests/domain/shop/test_shop_aggregate.py#L459-L467) | R: 維持 | TestShopAggregate::TestAddOwnerRemoveOwner::test_add_owner_then_is_owner L376-L384 | 後から追加した所有者が公開判定で有効になる。追加を無視する変更を検出。現時点で本番の直接呼び出し未確認だが公開複数所有者契約なので保持 |
| [TestShopAggregate::TestAddOwnerRemoveOwner::test_remove_owner_then_is_owner_false](https://github.com/Motifman/llm-rpg/blob/0b51eb28d4692635a932dcf4063ab9b231768bf0/tests/domain/shop/test_shop_aggregate.py#L469-L476) | R: 維持 | TestShopAggregate::TestAddOwnerRemoveOwner::test_remove_owner_then_is_owner_false L386-L393 | 所有者を削除すると公開判定で拒否される。削除を無視する変更を検出。最後の所有者削除を禁止する仕様への変更は別判断 |

### tests/domain/shop/value_object/test_shop_id.py

| 元宣言 | 判断 | 残存先 | 守る契約・根拠 |
|---|---|---|---|
| [TestShopId::test_create_positive_int_id](https://github.com/Motifman/llm-rpg/blob/0b51eb28d4692635a932dcf4063ab9b231768bf0/tests/domain/shop/value_object/test_shop_id.py#L11-L14) | R: 維持 | TestShopId::test_create_positive_int_id L12-L15 | 正整数の最小境界1をそのまま保持する公開構築契約。1を拒否する境界変更を検出。999999の入力も保持する残存先 |
| [TestShopId::test_create_large_positive_int_id](https://github.com/Motifman/llm-rpg/blob/0b51eb28d4692635a932dcf4063ab9b231768bf0/tests/domain/shop/value_object/test_shop_id.py#L16-L19) | C: 統合済み | TestShopId::test_create_positive_int_id L12-L15 | 999999を切り詰めない契約をtest_create_positive_int_idの入力表へ移した。単純さを理由に入力を削除しない |
| [TestShopId::test_create_from_int_create_method](https://github.com/Motifman/llm-rpg/blob/0b51eb28d4692635a932dcf4063ab9b231768bf0/tests/domain/shop/value_object/test_shop_id.py#L21-L25) | R: 維持 | TestShopId::test_create_from_int_create_method L17-L21 | 公開createの整数123を正しい型・値として返す。factoryが値や型を変える変更を検出。直接構築とは別入口 |
| [TestShopId::test_create_from_str_create_method](https://github.com/Motifman/llm-rpg/blob/0b51eb28d4692635a932dcf4063ab9b231768bf0/tests/domain/shop/value_object/test_shop_id.py#L27-L31) | R: 維持 | TestShopId::test_create_from_str_create_method L23-L27 | 文字列456を整数456へ変換してShopIdを返す。変換漏れ・型違いを検出 |
| [TestShopId::test_create_zero_id_raises_error](https://github.com/Motifman/llm-rpg/blob/0b51eb28d4692635a932dcf4063ab9b231768bf0/tests/domain/shop/value_object/test_shop_id.py#L33-L36) | R: 維持 | TestShopId::test_create_zero_id_raises_error L29-L32 | 境界0をShopIdValidationExceptionで拒否。<=を<に変える変更を検出 |
| [TestShopId::test_create_negative_id_raises_error](https://github.com/Motifman/llm-rpg/blob/0b51eb28d4692635a932dcf4063ab9b231768bf0/tests/domain/shop/value_object/test_shop_id.py#L38-L43) | R: 維持 | TestShopId::test_create_negative_id_raises_error L34-L39 | -1と-100を拒否。絶対値化や非正値の受け入れを検出 |
| [TestShopId::test_create_from_negative_str_raises_error](https://github.com/Motifman/llm-rpg/blob/0b51eb28d4692635a932dcf4063ab9b231768bf0/tests/domain/shop/value_object/test_shop_id.py#L45-L48) | R: 維持 | TestShopId::test_create_from_negative_str_raises_error L41-L44 | 文字列-5を変換後にも検証する。factoryの検証迂回を検出 |
| [TestShopId::test_create_from_zero_str_raises_error](https://github.com/Motifman/llm-rpg/blob/0b51eb28d4692635a932dcf4063ab9b231768bf0/tests/domain/shop/value_object/test_shop_id.py#L50-L53) | R: 維持 | TestShopId::test_create_from_zero_str_raises_error L46-L49 | 文字列0を変換後にも境界拒否する。整数構築と文字列入口双方の契約 |
| [TestShopId::test_create_from_invalid_str_raises_error](https://github.com/Motifman/llm-rpg/blob/0b51eb28d4692635a932dcf4063ab9b231768bf0/tests/domain/shop/value_object/test_shop_id.py#L55-L62) | R: 維持 | TestShopId::test_create_from_invalid_str_raises_error L51-L58 | abc、12.5、空文字をドメイン例外にする。数値以外の許容・組込みValueError漏出を検出 |
| [TestShopId::test_str_conversion](https://github.com/Motifman/llm-rpg/blob/0b51eb28d4692635a932dcf4063ab9b231768bf0/tests/domain/shop/value_object/test_shop_id.py#L64-L67) | R: 維持 | TestShopId::test_str_conversion L60-L63 | 文字列変換で789を返す公開値表現。識別子のログ表現で値を落とす変更を検出 |
| [TestShopId::test_int_conversion](https://github.com/Motifman/llm-rpg/blob/0b51eb28d4692635a932dcf4063ab9b231768bf0/tests/domain/shop/value_object/test_shop_id.py#L69-L72) | R: 維持 | TestShopId::test_int_conversion L65-L68 | int変換で101を返す。SQLiteやread model境界で整数変換が壊れる変更を検出 |
| [TestShopId::test_equality](https://github.com/Motifman/llm-rpg/blob/0b51eb28d4692635a932dcf4063ab9b231768bf0/tests/domain/shop/value_object/test_shop_id.py#L74-L82) | R: 維持 | TestShopId::test_equality L70-L78 | 同値・異値・異型を区別。IDを生整数や文字列と同一扱いする変更を検出 |
| [TestShopId::test_hash](https://github.com/Motifman/llm-rpg/blob/0b51eb28d4692635a932dcf4063ab9b231768bf0/tests/domain/shop/value_object/test_shop_id.py#L84-L90) | R: 維持 | TestShopId::test_hash L80-L86 | 同値IDは同じhashで集合の1要素になる。辞書/集合キーの整合性破壊を検出 |

### tests/domain/shop/value_object/test_shop_listing_id.py

| 元宣言 | 判断 | 残存先 | 守る契約・根拠 |
|---|---|---|---|
| [TestShopListingId::test_create_positive_int_id](https://github.com/Motifman/llm-rpg/blob/0b51eb28d4692635a932dcf4063ab9b231768bf0/tests/domain/shop/value_object/test_shop_listing_id.py#L11-L14) | R: 維持 | TestShopListingId::test_create_positive_int_id L11-L14 | 出品IDの最小値1を保持。境界1拒否を検出。ShopIdとは別の公開型 |
| [TestShopListingId::test_create_from_int_create_method](https://github.com/Motifman/llm-rpg/blob/0b51eb28d4692635a932dcf4063ab9b231768bf0/tests/domain/shop/value_object/test_shop_listing_id.py#L16-L20) | R: 維持 | TestShopListingId::test_create_from_int_create_method L16-L20 | 公開createで123を型付きIDとして保持。factory値・型破壊を検出 |
| [TestShopListingId::test_create_from_str_create_method](https://github.com/Motifman/llm-rpg/blob/0b51eb28d4692635a932dcf4063ab9b231768bf0/tests/domain/shop/value_object/test_shop_listing_id.py#L22-L25) | R: 維持 | TestShopListingId::test_create_from_str_create_method L22-L25 | 文字列456から整数456に変換。文字列入口の変換漏れを検出 |
| [TestShopListingId::test_create_zero_id_raises_error](https://github.com/Motifman/llm-rpg/blob/0b51eb28d4692635a932dcf4063ab9b231768bf0/tests/domain/shop/value_object/test_shop_listing_id.py#L27-L30) | R: 維持 | TestShopListingId::test_create_zero_id_raises_error L27-L30 | 出品IDの0拒否。ショップIDの試験ではこの型の検証削除を検出できない |
| [TestShopListingId::test_create_negative_id_raises_error](https://github.com/Motifman/llm-rpg/blob/0b51eb28d4692635a932dcf4063ab9b231768bf0/tests/domain/shop/value_object/test_shop_listing_id.py#L32-L35) | R: 維持 | TestShopListingId::test_create_negative_id_raises_error L32-L35 | 出品IDの-1拒否。正整数制約の削除を検出 |
| [TestShopListingId::test_create_from_invalid_str_raises_error](https://github.com/Motifman/llm-rpg/blob/0b51eb28d4692635a932dcf4063ab9b231768bf0/tests/domain/shop/value_object/test_shop_listing_id.py#L37-L40) | R: 維持 | TestShopListingId::test_create_from_invalid_str_raises_error L37-L40 | abcをShopListingIdValidationExceptionで拒否。組込み例外漏出を検出 |
| [TestShopListingId::test_equality_and_hash](https://github.com/Motifman/llm-rpg/blob/0b51eb28d4692635a932dcf4063ab9b231768bf0/tests/domain/shop/value_object/test_shop_listing_id.py#L42-L49) | R: 維持 | TestShopListingId::test_equality_and_hash L42-L49 | 同値・異値とhashの一致。集約の出品辞書で別インスタンスの同じIDを引けなくなる変更を検出 |

### tests/domain/shop/value_object/test_shop_listing_price.py

| 元宣言 | 判断 | 残存先 | 守る契約・根拠 |
|---|---|---|---|
| [TestShopListingPrice::test_create_positive_value](https://github.com/Motifman/llm-rpg/blob/0b51eb28d4692635a932dcf4063ab9b231768bf0/tests/domain/shop/value_object/test_shop_listing_price.py#L11-L16) | R: 維持 | TestShopListingPrice::test_create_positive_value L12-L16 | 価格1と100を保持。最小の有料価格を拒否・丸め・切詰めする変更を検出。factory50の型確認も保持する残存先 |
| [TestShopListingPrice::test_of_factory_method](https://github.com/Motifman/llm-rpg/blob/0b51eb28d4692635a932dcf4063ab9b231768bf0/tests/domain/shop/value_object/test_shop_listing_price.py#L18-L22) | C: 統合済み | TestShopListingPrice::test_create_positive_value L12-L16 | 同じof入口を価格50で再実行。50とisinstance確認をtest_create_positive_valueの入力表へ移管 |
| [TestShopListingPrice::test_zero_raises_error](https://github.com/Motifman/llm-rpg/blob/0b51eb28d4692635a932dcf4063ab9b231768bf0/tests/domain/shop/value_object/test_shop_listing_price.py#L24-L27) | R: 維持 | TestShopListingPrice::test_zero_raises_error L18-L21 | 無料価格0をドメイン例外で拒否。<=を<に変える変更を検出 |
| [TestShopListingPrice::test_negative_raises_error](https://github.com/Motifman/llm-rpg/blob/0b51eb28d4692635a932dcf4063ab9b231768bf0/tests/domain/shop/value_object/test_shop_listing_price.py#L29-L32) | R: 維持 | TestShopListingPrice::test_negative_raises_error L23-L26 | 価格-1をドメイン例外で拒否。負数での取引価格作成を許す変更を検出 |
| [TestShopListingPrice::test_str_repr](https://github.com/Motifman/llm-rpg/blob/0b51eb28d4692635a932dcf4063ab9b231768bf0/tests/domain/shop/value_object/test_shop_listing_price.py#L34-L38) | F: 保留・未変更 | TestShopListingPrice::test_str_repr L28-L32 | strに99が含まれることは保持。reprは型名または99の片方だけで通る弱いassert。ただし両方必須という独立仕様が未確認のため修理保留。現実装を新仕様にしない |
| [TestShopListingPrice::test_int_conversion](https://github.com/Motifman/llm-rpg/blob/0b51eb28d4692635a932dcf4063ab9b231768bf0/tests/domain/shop/value_object/test_shop_listing_price.py#L40-L43) | R: 維持 | TestShopListingPrice::test_int_conversion L34-L37 | int変換で42を返す。SQLiteの価格保存で変換が壊れる変更を検出 |
| [TestShopListingPrice::test_equality_and_hash](https://github.com/Motifman/llm-rpg/blob/0b51eb28d4692635a932dcf4063ab9b231768bf0/tests/domain/shop/value_object/test_shop_listing_price.py#L45-L52) | R: 維持 | TestShopListingPrice::test_equality_and_hash L39-L46 | 同価格の等価性とhash一致、異価格の不等価。値オブジェクトとしての比較崩れを検出 |

## 残したもの・今後の判断

- 全4ファイルを残した。イベント発行側と受信側は異なる契約なので、受信側試験があることを理由に集約の保証を削っていない
- reprの型名/値の両方を要求する新仕様は導入していない。独立した表示契約が得られるまで保留
- 開設イベントの非空名前/説明、出品イベントの位置、closeの集約単体ガード等、もともと試験が薄い点は別判断の候補として記録した。この整理で新たに保証したとは言わない
- テスト専用の本番引数やラッパーの削除はなく、本番簡略化は0行。目的外の機能変更を混ぜない
- 削除前後の検証・入力移管と15変異の失敗理由は、変更担当者とは別の読取でも照合した
