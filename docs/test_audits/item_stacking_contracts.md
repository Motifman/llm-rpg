# スタック判定の条件と集約の接続を別々に守る

## 対象と目的

基準は `8bd969c2aeeb4ee540f7d1046e3bca266ef62310`。対象はアイテムのスタック判定8宣言だけで、前段の読み取り調査で確認した96宣言の残り88宣言は保留した。アイテム全域の監査完了を意味しない。

耐久品を拒否する旧試験は数量1・上限1を使っており、耐久禁止を取り除いても満杯条件だけで通っていた。この検査を直し、集約と実体で同じ条件を繰り返す試験を所有側へまとめた。製品コード、計画API、Recipeの契約は変更していない。

8宣言を4宣言へ整理したが、元の入力と独立した対照を表の行として残したため、アイテム全体の実行件数は332件から333件になった。削減件数や速度ではなく、拒否理由を独立に検査することが目的である。

## 判定の所有者と8宣言の台帳

`ItemInstance.can_stack_with` が条件を判定し、`ItemAggregate.can_stack_with` は実体へ中継する。条件の所有先は `tests/domain/item/entity/test_item_instance.py`、集約の接続は実集約を使うサービス試験に置く。

Aは `tests/domain/item/aggregate/test_item_aggregate.py` の `TestItemAggregate`、Eは `tests/domain/item/entity/test_item_instance.py` の `TestItemInstance`。Rは保持、Fは契約を保持して検査を修復、Cは既存の保存先へ統合する判定。

| 旧宣言 | 判定 | 保存先と理由 |
|---|---|---|
| A.test_can_stack_with_same_spec_different_instances | C | E.test_can_stack_with_same_itemへ。数量5/3の両方向肯定も表に移した |
| A.test_can_stack_with_different_specs | C | 仕様ID相違はE.test_cannot_stack_different_spec_ids、耐久禁止はE.test_cannot_stack_durable_itemsへ。旧入力は仕様IDと耐久仕様の両方が違い、拒否理由を分離できなかった |
| A.test_can_stack_with_same_spec_different_durability | C | 修復したE.test_cannot_stack_durable_itemsへ。集約固有のイベントや状態変更は検査していなかった |
| E.test_can_stack_with_same_item | R | 元の数量1/1と移管した5/3で、両方向に許可されることを確認 |
| E.test_cannot_stack_different_name | R・改名 | 実際の契約に合わせtest_cannot_stack_different_spec_idsへ改名。名前が違う元の負入力を残した |
| E.test_cannot_stack_different_type | C | 同じ名前で種別が違う元の負入力を上記の表へ統合。仕様IDだけ違う対照も加えた |
| E.test_cannot_stack_at_max_quantity | R | 同仕様・耐久度なしの数量2/上限2による満杯拒否を保持 |
| E.test_cannot_stack_durable_items | F | 元の数量1の拒否を残し、数量0について耐久度実体あり・なしの2行を加えた |

仕様の同一性は `ItemSpec.__eq__` が `ItemSpecId` で判定する。名前や種別も変わる入力だけでは、仕様ID比較を名前比較へ誤変更したときに見逃す可能性がある。IDだけ違う対照を追加し、元の異名・異種別の入力も保持した。

数量0は不正な状態ではない。`ItemInstance._validate` は負数を拒否するが0を許す。耐久品でも公開操作 `remove_quantity(1)` により数量1から0へ到達する。最大スタック1・仕様と一致する耐久度の最大値を維持し、私有属性の書き換えは使わない。

## 集約の接続を保持する試験

保存先は `tests/domain/item/service/test_item_domain_service.py` の `TestItemStackingDomainServiceStacking.test_calculate_max_stack_quantity_with_non_stackable_items`。模擬集約ではなく実際の `ItemAggregate` を使い、基準10、採用候補20、非互換な耐久品1、採用候補15から、合計45と採用ID105/107を照合する。

この試験は集約から実体への接続を検査する。一方、耐久禁止そのものは数量0を使う実体試験で検査する。非互換な候補には仕様IDの違いもあるので、サービス試験だけを耐久条件の証明とはしない。

計画サービスの現行の非テスト呼出元は見つからないが、外部から組み立てるライブラリの方針があり、未接続だけで公開APIを廃止しない。この検査を実ゲーム全体の統合試験と呼ぶこともしない。

## 保持した別契約

- `test_item_instance_state.py` の片側・両側の状態付き拒否と、状態解除後の再許可
- 集約の使用・破損・修理イベントの内容、順序、発行抑制
- 最後の1個を使用すると数量0になること、および数量0での使用失敗
- 実体の構築検証と、SQLiteで実体を直接再構築する入口
- 計画値、計画サービス、Recipeの契約。未接続を理由に削除していない

`ItemInstance` の最後の1個の消費は [be01406](https://github.com/Motifman/llm-rpg/commit/be014066df0c9a485040784bf3f9777779a521eb)、個別状態のスタック禁止は [a1125a1](https://github.com/Motifman/llm-rpg/commit/a1125a10dfd08d988f7e2cd606ebbb3777fa036e) の具体的な変更を守るため、今回の重複整理に含めなかった。対象の旧スタック試験は [e1255c6](https://github.com/Motifman/llm-rpg/commit/e1255c613bff7c0890fa1614df8b6f0c97a03310) の一括追加に由来する。

## 試験結果

2026-10-13、Python3.10.22で直列に実行した。正式実行は環境変数から認証情報とプロキシ設定を除き、モデル価格表・関連キャッシュをローカルに固定した共通実行器を使った。ネットワーク接続を試験収集前に禁止し、自分の作業ツリーの `src/ai_rpg_world/__init__.py` を読み込んだことを各実行のJSONへ記録した。

最初に通常のuv入口で得た332件・44件の結果は補助記録として保管したが、この共通実行器を通していないため、正式な基準・比較時間からは除外した。その後、保存していた旧試験の内容を戻して正式基準を2回実行し、候補を復元して検証した。

| 実行 | 結果 | 実時間 | 利用者CPU時間 | システムCPU時間 |
|---|---:|---:|---:|---:|
| 基準1・tests/domain/item | 332合格 | 0.714秒 | 0.655秒 | 0.057秒 |
| 基準2・tests/domain/item | 332合格 | 0.788秒 | 0.724秒 | 0.063秒 |
| 最終1・tests/domain/item | 333合格 | 0.960秒 | 0.911秒 | 0.047秒 |
| 最終2・tests/domain/item | 333合格 | 0.736秒 | 0.683秒 | 0.052秒 |
| 関連・基準 | 44合格 | 1.350秒 | 1.291秒 | 0.057秒 |
| 関連・最終 | 44合格 | 1.200秒 | 1.172秒 | 0.027秒 |

関連は次の3ファイル。アイテム全体を回帰範囲に使ったが、内容を整理した範囲は上記8宣言だけである。

- `tests/application/shop/services/test_shop_command_service.py`
- `tests/application/world/services/test_use_item_service.py`
- `tests/infrastructure/repository/test_sqlite_item_write_repository.py`

最終の独立収集も333件。時間は1秒前後の小さな単体試験の測定で変動もあるため、速度改善率は示さない。

### 意図的な破壊による検出力の確認

すべて同じ共通実行器で実行し、例外による収集失敗ではなく、狙った断言で失敗することを確認した。

| 一時的な破壊 | 実際の結果 |
|---|---|
| 実体の耐久拒否2節を除去、旧スタック8宣言を実行 | 8件とも合格。旧試験の見逃しを確認 |
| 同じ破壊、修復した耐久拒否試験を実行 | 数量0の2行が失敗、元の数量1の行は合格 |
| 仕様のdurability_max拒否だけを除去 | 耐久度実体なし・数量0の行だけ失敗 |
| 集約の応答を固定Trueへ変更 | サービス保存先が `46 == 45` で失敗 |
| 集約の応答を固定Falseへ変更 | サービス保存先が `10 == 45` で失敗 |
| 実体の仕様比較を省略 | 仕様ID相違の3行が失敗 |
| 仕様比較を名前比較へ変更 | 同名の異種別とIDのみ相違の2行が失敗 |
| 実体の満杯条件を省略 | 最大数量での拒否試験が失敗 |

各変更の後に製品ソースを元の内容へ戻し、全変異の終了後に保存済み内容との完全一致とSHA-256一致を確認してから最終2回を実行した。製品コードの差分はない。

- `item_instance.py`: `8f0f69431158d43447cd75e3c222ac1b2646d5fe0e4bebcd02665f90d18b8de0`
- `item_aggregate.py`: `086391c66f71c19b2fa280e6cce1d383d5c617ddd6aaeb8d68a12945b689045c`

対象2ファイルのruffと `git diff --check` は成功。最終テスト差分は50行追加・98行削除の差引48行削減。所有規約と本書は別に追加した。リポジトリ全件の実行やCI成功を、この局所検証の結果から推定しない。

## 公開先mainへの追従

正式な変更前基準は上記の `8bd969c2aeeb4ee540f7d1046e3bca266ef62310` のままとし、公開先は `37bae48104b50ec2f0f73d1fd6cf493ffffdb1f1` へ追従した。後者は別作業のLLM強制指示の実装・試験削除と文書変更の3ファイルで、この監査のアイテム製品・試験・保存先・`uv.lock`・CI設定には変更がなかった。

追従は履歴を書き換えずマージで取り込み、その後も同じ共通実行器で `tests/domain/item` の333件と関連44件が合格した。各実行で自分の作業ツリーのソースを読み込んだことを確認している。

公開先mainとの差分は試験2ファイル、所有規約1ファイル、本監査文書1ファイルの計4ファイル。製品コードの差分は0である。追従前に行った意図的破壊の保存先も変わっていない。
