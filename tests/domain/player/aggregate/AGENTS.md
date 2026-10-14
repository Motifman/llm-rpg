# 所持品集約の試験を変更するとき

- PlayerInventoryAggregate の探索・列挙契約は test_player_inventory_iter_slots.py に集める。同じ予約設定を別ファイルへ複製しない
- 探索では枠と品の対応を検査する。AvailableSlotLookup は found、slot_id、item_instance_id、blocked_by_reservation を確認し、未所持と予約による不一致を区別する
- 復元データの検証は restore_from_data を通す。私有検証メソッドの直接再演は増やさず、疎な有効データと容量ちょうどの境界を残す
- 不整合な保存状態は restore_from_data で作り、集約の私有辞書を直接書き換えない
- 移動・装備・整理の設定では、対象品が実際に元枠にあることと、操作後に元枠から消えることを確認する
- getter、既定値、空/満杯、イベント順序の独立した契約を、短いという理由で削除しない
- executor の私有辞書依存を避ける既存の設計検査は、動作試験と役割が異なる。代替の根拠なく削除しない
