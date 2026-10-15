# 配置・移動試験の責任分担

- 配置と移動の主担当は `test_spot_graph_aggregate.py`、`aggregate/test_spot_graph_monster_presence.py`、`aggregate/test_spot_graph_move_monster.py`。値の在席規則は `test_spot_presence.py`、識別子の入力と固有例外は `test_world_graph_ids.py` に残す
- モンスター移動の通知対は、退出→出現の順序・件数・各IDと場所を実イベントで調べる。型名の集合や包含だけで、重複を見逃す判定に戻さない
- 同じ入力と同じ通知を再実行する試験を統合するときは、既定値も含む全判定を先に保持先へ移し、元試験が残る状態で成功を確かめる。状態照会と通知、事前通行queryと実移動は別の契約なので、似た準備だけを根拠に削除しない
- 保存用APIや復元入力の試験は、現在の呼出数だけで削除しない。導入履歴の公開契約と実際の保存経路を区別する。world snapshotの既知制限をSQLite保存の証明として扱わない
