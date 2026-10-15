# アイテムのスタック判定を試験する場所

- `ItemInstance.can_stack_with` の条件は `entity/test_item_instance.py` が所有する
- 集約が実体の判定を返す接続は、実集約を使う `service/test_item_domain_service.py` の `test_calculate_max_stack_quantity_with_non_stackable_items` で守る。この検査は肯定・否定の候補と実際の採用ID・合計数量を照合する。集約側で全条件を再演しない
- 耐久品は最大スタック1なので、数量1の拒否だけでは耐久禁止を検査できない。有効な数量0の入力で満杯条件を外し、耐久度実体がある場合と仕様だけの場合を確認する
- 仕様の同一性は `ItemSpecId` による。仕様ID相違の検査には、名前・種別が同じ対照を含める
- 個別状態による拒否と状態解除後の再許可は `test_item_instance_state.py` に残す。使用・破損・修理のイベントは集約の別契約として保持する
