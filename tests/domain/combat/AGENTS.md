# 戦闘ドメインの試験

- 損傷の数値規則は `CombatLogicService.calculate_damage`、任意の能力補正は `BaseStats.apply_modifiers` が第一所有者。期限付き効果の数値規則は `tests/domain/common/service/test_effective_stats_domain_service.py` で守る
- 期待値は独立した固定値にする。実装の計算や助け関数で期待値を作らない。数値の説明が実装と似ていることだけを削除理由にしない
- 量の整数型は値の等価比較とは別に検査する。割合上限の試験で整数型の回帰を代用しない。半端な入力を選ぶときは、切捨てとPythonの偶数丸めを区別できる値か確認する
- 試験内で計算と反映を手組みした経路を、本番ハンドラの接続証明と呼ばない。公開の生成口・既定値は、本番呼出がないだけでは廃止しない

判断と保存範囲は `docs/test_audits/combat_calculation_contracts.md` に記録している。
