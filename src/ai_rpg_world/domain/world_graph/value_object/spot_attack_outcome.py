"""スポットグラフ世界の攻撃結果を表す統一値オブジェクト。

`SpotMonsterAttackService` (モンスター → プレイヤー) と
`SpotPlayerAttackService` (プレイヤー → モンスター) の両方が同じ型を返す
ことで、上位レイヤー (orchestrator / tick service / tool executor) が
attacker / target の組み合わせに依存せずに結果を扱えるようにする。

`target_incapacitated` の意味:
- プレイヤーが対象 (モンスター → プレイヤー攻撃) なら **PlayerDowned** 状態
- モンスターが対象 (プレイヤー → モンスター攻撃) なら **MonsterDead** 状態

どちらも「行動不能」の意味で、event 構築側 (orchestrator) で event の
`target_downed` / `target_killed` フィールドにそれぞれ翻訳する。

`reason` は `executed=False` 時の短い英語コード。現状想定する値:
- `"ok"`: 成立
- `"not_hostile"`: モンスター faction が ENEMY 以外（モンスター → プレイヤー）
- `"cannot_attack"`: cooldown 中 / DEAD（モンスター → プレイヤー）
- `"not_visible"`: 暗闇 + dark_vision なし（モンスター → プレイヤー）
- `"target_down"`: 対象プレイヤーが既にダウン（モンスター → プレイヤー）
- `"attacker_down"`: 攻撃者プレイヤーがダウン（プレイヤー → モンスター）
- `"target_dead"`: 対象モンスターが ALIVE でない（プレイヤー → モンスター）
- `"zero_damage"`: damage=0（両方向）
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AttackOutcome:
    """攻撃の結果。攻撃者・対象の種類によらず統一フォーマット。"""

    executed: bool
    reason: str
    damage: int = 0
    target_incapacitated: bool = False
