"""``target=TARGET_PLAYER`` の GIVE_ITEM / REMOVE_ITEM が、行為者ではなく
対象プレイヤーのバケットに積まれることを保証する。

奪う (take) は「対象から REMOVE_ITEM、行為者に GIVE_ITEM」の 2 効果で書く。
両方が同じバケットに積まれると、自分から取り上げて自分に渡す no-op になり、
しかも成功として返る (静かな失敗)。効果の宛先はバケットで分ける。

宛先が無いのに ``TARGET_PLAYER`` が指定された場合は、行為者バケットへ
フォールバックさせない。フォールバックすると「奪ったつもりで自分の持ち物が
消える」という、成功に見える誤動作になる。
"""

from __future__ import annotations

import pytest

from ai_rpg_world.domain.player.aggregate.player_status_aggregate import (
    PlayerStatusAggregate,
)
from ai_rpg_world.domain.player.value_object.base_stats import BaseStats
from ai_rpg_world.domain.player.value_object.exp_table import ExpTable
from ai_rpg_world.domain.player.value_object.gold import Gold
from ai_rpg_world.domain.player.value_object.growth import Growth
from ai_rpg_world.domain.player.value_object.hp import Hp
from ai_rpg_world.domain.player.value_object.mp import Mp
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.player.value_object.stamina import Stamina
from ai_rpg_world.domain.player.value_object.stat_growth_factor import StatGrowthFactor
from ai_rpg_world.domain.world_graph.entity.spot_interior import SpotInterior
from ai_rpg_world.domain.world_graph.enum.effect_target import EffectTarget
from ai_rpg_world.domain.world_graph.enum.interaction_effect_type import (
    InteractionEffectTypeEnum,
)
from ai_rpg_world.domain.world_graph.exception.spot_graph_exception import (
    InteractionEffectValidationException,
)
from ai_rpg_world.domain.world_graph.service.world_graph_effect_service import (
    WorldGraphEffectService,
)
from ai_rpg_world.domain.world_graph.value_object.interaction_effect import (
    InteractionEffect,
)


def _player_status(player_id: int = 2) -> PlayerStatusAggregate:
    exp_table = ExpTable(100, 1.5)
    return PlayerStatusAggregate(
        player_id=PlayerId(player_id),
        base_stats=BaseStats(100, 50, 10, 10, 10, 0.05, 0.05),
        stat_growth_factor=StatGrowthFactor(1.0, 1.0, 1.0, 1.0, 1.0, 0.0, 0.0),
        exp_table=exp_table,
        growth=Growth(1, 0, exp_table),
        gold=Gold(0),
        hp=Hp(value=100, max_hp=100),
        mp=Mp(value=50, max_mp=50),
        stamina=Stamina(value=100, max_stamina=100),
    )


def _empty_interior() -> SpotInterior:
    return SpotInterior((), (), (), ())


def _item_effect(effect_type, spec_id: int, target: EffectTarget) -> InteractionEffect:
    return InteractionEffect(
        effect_type=effect_type,
        parameters={"item_spec_id": spec_id},
        target=target,
    )


def _apply(*effects: InteractionEffect, target_player=None):
    return WorldGraphEffectService().apply_effects(
        interior=_empty_interior(),
        acting_object=None,
        effects=list(effects),
        world_flags=frozenset(),
        target_player_status=target_player,
    )


class TestTargetPlayerItemBuckets:
    """GIVE_ITEM / REMOVE_ITEM の宛先が ``target`` で振り分けられる。"""

    @pytest.mark.parametrize(
        ("effects", "expected"),
        [
            (((InteractionEffectTypeEnum.REMOVE_ITEM, 7, EffectTarget.TARGET_PLAYER),), ((), (), (), (7,))),
            (((InteractionEffectTypeEnum.GIVE_ITEM, 7, EffectTarget.ACTOR),), ((7,), (), (), ())),
            ((
                (InteractionEffectTypeEnum.REMOVE_ITEM, 7, EffectTarget.TARGET_PLAYER),
                (InteractionEffectTypeEnum.GIVE_ITEM, 7, EffectTarget.ACTOR),
            ), ((7,), (), (), (7,))),
            ((
                (InteractionEffectTypeEnum.REMOVE_ITEM, 8, EffectTarget.ACTOR),
                (InteractionEffectTypeEnum.GIVE_ITEM, 9, EffectTarget.TARGET_PLAYER),
            ), ((), (8,), (9,), ())),
        ],
    )
    def test_transfers_keep_actor_and_target_buckets_separate(self, effects, expected) -> None:
        """単独・複合の授受は宣言した行為者/対象者と付与/削除の4列へ分離される。"""
        result = _apply(*(_item_effect(*effect) for effect in effects), target_player=_player_status())
        actual = (
            result.item_spec_ids_to_grant, result.item_spec_ids_to_remove,
            result.target_item_spec_ids_to_grant, result.target_item_spec_ids_to_remove,
        )
        assert tuple(tuple(spec.value for spec in bucket) for bucket in actual) == expected


class TestTargetPlayerMissing:
    """対象プレイヤーが渡されていないのに ``TARGET_PLAYER`` が指定された場合。"""

    @pytest.mark.parametrize("effect_type", [InteractionEffectTypeEnum.REMOVE_ITEM, InteractionEffectTypeEnum.GIVE_ITEM])
    def test_raises_instead_of_falling_back_to_actor(self, effect_type) -> None:
        """行為者バケットへフォールバックせず、例外で止まる。

        フォールバックすると「奪ったつもりが自分の持ち物を失う」という、
        成功として返る誤動作になる。
        """
        with pytest.raises(InteractionEffectValidationException):
            _apply(
                _item_effect(
                    effect_type,
                    7,
                    EffectTarget.TARGET_PLAYER,
                ),
                target_player=None,
            )
