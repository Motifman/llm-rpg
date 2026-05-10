"""モンスターの「性格」プリセットを `MonsterTemplate` に適用する。

Phase 4b PR (d): `TemperamentEnum` で性格をひとことで宣言できるようにし、
個別パラメータ (reaction_to_attack / flee_grace_ticks / chase_max_distance
/ chase_max_ticks / chase_search_ticks / flee_threshold) の組み合わせを
プリセット化する。

使い方:

    base = MonsterTemplate(
        template_id=MonsterTemplateId.create(1),
        name="Wolf",
        ...,
        # 反応系パラメータは temperament でまとめて設定するので未指定
    )
    final = apply_temperament(base, TemperamentEnum.AGGRESSIVE)

`apply_temperament` は dataclasses.replace で 6 フィールドを上書きする。
既に明示的に設定された値も上書きされる点に注意。微調整したい場合は
apply 後にさらに `dataclasses.replace(final, ...)` で書き換える。
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from ai_rpg_world.domain.monster.enum.monster_enum import (
    ReactionPolicyEnum,
    TemperamentEnum,
)
from ai_rpg_world.domain.monster.value_object.monster_template import MonsterTemplate


@dataclass(frozen=True)
class _TemperamentPreset:
    """1 つの temperament が指定するパラメータ束。"""

    reaction_to_attack: ReactionPolicyEnum
    flee_grace_ticks: int
    flee_threshold: float
    chase_max_distance: int
    chase_max_ticks: int
    chase_search_ticks: int


# 各 temperament のプリセット値。数値の根拠は docstring 参照。
_PRESETS: dict[TemperamentEnum, _TemperamentPreset] = {
    # 攻撃しない平和な動物。被弾しても無反応で立ち尽くす。
    # 注: chase_max_* / chase_search_ticks は reaction=PASSIVE で `_continue_chase`
    # に入らないため値は参照されない (デッドフィールド)。`0` が入っているが、
    # これは BERSERKER の `0=無制限` と意味が異なる。仮に reaction を後から
    # ALWAYS_RETALIATE に上書きすると CHASE 系挙動が「無制限執念深い」に
    # 化けるので注意 (apply 後の `replace` で reaction を変えるなら chase
    # 系も同時に上書きすること)。
    TemperamentEnum.PASSIVE_BEAST: _TemperamentPreset(
        reaction_to_attack=ReactionPolicyEnum.PASSIVE,
        flee_grace_ticks=0,
        flee_threshold=0.0,
        chase_max_distance=0,
        chase_max_ticks=0,
        chase_search_ticks=0,
    ),
    # 弱気な動物。被弾即逃走、追跡しない。
    # 注: chase_* は ALWAYS_FLEE 経路では参照されないデッドフィールド
    # (PASSIVE_BEAST と同じ注意事項が適用される)。
    TemperamentEnum.COWARD: _TemperamentPreset(
        reaction_to_attack=ReactionPolicyEnum.ALWAYS_FLEE,
        flee_grace_ticks=5,
        flee_threshold=0.0,
        chase_max_distance=0,
        chase_max_ticks=0,
        chase_search_ticks=0,
    ),
    # 警戒型。HP 比 30% 未満で逃走、それ以外は反撃。短距離追跡。
    TemperamentEnum.WARY: _TemperamentPreset(
        reaction_to_attack=ReactionPolicyEnum.FLEE_WHEN_LOW_HP,
        flee_grace_ticks=3,
        flee_threshold=0.3,
        chase_max_distance=2,
        chase_max_ticks=10,
        chase_search_ticks=2,
    ),
    # 普通の敵。被弾したら反撃、中距離追跡。
    TemperamentEnum.AGGRESSIVE: _TemperamentPreset(
        reaction_to_attack=ReactionPolicyEnum.ALWAYS_RETALIATE,
        flee_grace_ticks=5,
        flee_threshold=0.0,
        chase_max_distance=5,
        chase_max_ticks=20,
        chase_search_ticks=3,
    ),
    # 執念深い敵。長距離追跡 + 長時間探索。
    TemperamentEnum.FEROCIOUS: _TemperamentPreset(
        reaction_to_attack=ReactionPolicyEnum.ALWAYS_RETALIATE,
        flee_grace_ticks=10,
        flee_threshold=0.0,
        chase_max_distance=15,
        chase_max_ticks=60,
        chase_search_ticks=8,
    ),
    # 狂戦士。距離 / tick 無制限 (0 = 無制限)、執念は最大級。
    TemperamentEnum.BERSERKER: _TemperamentPreset(
        reaction_to_attack=ReactionPolicyEnum.ALWAYS_RETALIATE,
        flee_grace_ticks=20,
        flee_threshold=0.0,
        chase_max_distance=0,  # 無制限
        chase_max_ticks=0,     # 無制限
        chase_search_ticks=15,
    ),
}


def _validate_preset_coverage() -> None:
    """モジュールロード時に `_PRESETS` が `TemperamentEnum` の全値を網羅
    していることを assert する。enum 追加時にプリセット追加を忘れた場合、
    import 時点で AssertionError として失敗する (フェイルファスト)。

    PASSIVE_BEAST / COWARD のように chase 系フィールドが「reaction が
    chase に入らないため意味を持たない」temperament でも、デッドフィールド
    として 0 を入れている (BERSERKER の `0=無制限` と同じ値だが、reaction
    が PASSIVE / ALWAYS_FLEE のため `_continue_chase` には入らないので
    実害なし)。
    """
    missing = [t for t in TemperamentEnum if t not in _PRESETS]
    if missing:
        raise AssertionError(
            f"_PRESETS に未登録の TemperamentEnum: {missing}"
        )


_validate_preset_coverage()


def apply_temperament(
    base: MonsterTemplate,
    temperament: TemperamentEnum,
) -> MonsterTemplate:
    """`base` template に `temperament` プリセットを適用した新しい template を返す。

    上書きされるフィールド:
    - reaction_to_attack
    - flee_grace_ticks
    - flee_threshold
    - chase_max_distance
    - chase_max_ticks
    - chase_search_ticks

    その他のフィールド (HP / 攻撃力 / race / faction 等) は base のまま維持。

    `dataclasses.replace` 経由のため `MonsterTemplate.__post_init__` の
    バリデーションが再実行される。preset 値はバリデーションを通過する
    前提で定義されている (テストで全 temperament を呼び出して確認済み)。
    """
    preset = _PRESETS[temperament]
    return replace(
        base,
        reaction_to_attack=preset.reaction_to_attack,
        flee_grace_ticks=preset.flee_grace_ticks,
        flee_threshold=preset.flee_threshold,
        chase_max_distance=preset.chase_max_distance,
        chase_max_ticks=preset.chase_max_ticks,
        chase_search_ticks=preset.chase_search_ticks,
    )
