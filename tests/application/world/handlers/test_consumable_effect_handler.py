"""ConsumableEffectHandler の網羅的テスト"""

import pytest
from unittest.mock import MagicMock

from ai_rpg_world.application.common.exceptions import SystemErrorException
from ai_rpg_world.application.world.exceptions.consumable_effect_exception import (
    ItemSpecNotFoundForConsumableEffectException,
    PlayerNotFoundForConsumableEffectException,
    ConsumeEffectMissingException,
)
from ai_rpg_world.application.world.handlers.consumable_effect_handler import (
    ConsumableEffectHandler,
)
from ai_rpg_world.domain.item.event.item_event import ConsumableUsedEvent
from ai_rpg_world.domain.item.value_object.item_spec_id import ItemSpecId
from ai_rpg_world.domain.item.value_object.item_effect import (
    HealEffect,
    RecoverMpEffect,
    GoldEffect,
    ExpEffect,
    CompositeItemEffect,
    ItemEffect,
)
from ai_rpg_world.domain.item.value_object.item_spec import ItemSpec
from ai_rpg_world.domain.item.value_object.max_stack_size import MaxStackSize
from ai_rpg_world.domain.item.read_model.item_spec_read_model import ItemSpecReadModel
from ai_rpg_world.domain.item.enum.item_enum import ItemType, Rarity
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.player.aggregate.player_status_aggregate import PlayerStatusAggregate
from ai_rpg_world.domain.player.value_object.base_stats import BaseStats
from ai_rpg_world.domain.player.value_object.stat_growth_factor import StatGrowthFactor
from ai_rpg_world.domain.player.value_object.exp_table import ExpTable
from ai_rpg_world.domain.player.value_object.growth import Growth
from ai_rpg_world.domain.player.value_object.gold import Gold
from ai_rpg_world.domain.player.value_object.hp import Hp
from ai_rpg_world.domain.player.value_object.mp import Mp
from ai_rpg_world.domain.player.value_object.stamina import Stamina
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world.value_object.coordinate import Coordinate


class _FakeItemEffect(ItemEffect):
    """テスト用の未知の効果タイプ"""

    def __repr__(self) -> str:
        return "FakeEffect()"


def _create_handler_with_mocks():
    item_spec_repo = MagicMock()
    player_status_repo = MagicMock()
    return ConsumableEffectHandler(
        item_spec_repository=item_spec_repo,
        player_status_repository=player_status_repo,
    ), item_spec_repo, player_status_repo


def _create_player_status(
    player_id: int = 1,
    hp_current: int = 50,
    hp_max: int = 100,
    mp_current: int = 50,
    mp_max: int = 50,
):
    exp_table = ExpTable(100, 1.5)
    return PlayerStatusAggregate(
        player_id=PlayerId(player_id),
        base_stats=BaseStats(10, 10, 10, 10, 10, 0.05, 0.05),
        stat_growth_factor=StatGrowthFactor(1.1, 1.1, 1.1, 1.1, 1.1, 0.01, 0.01),
        exp_table=exp_table,
        growth=Growth(1, 0, exp_table),
        gold=Gold(1000),
        hp=Hp.create(hp_current, hp_max),
        mp=Mp.create(mp_current, mp_max),
        stamina=Stamina.create(100, 100),
        current_spot_id=SpotId(1),
        current_coordinate=Coordinate(0, 0, 0),
    )


class TestConsumableEffectHandler:
    """ConsumableEffectHandler のテスト"""

    def test_apply_heal_effect(self):
        """HealEffect が正しく適用される"""
        handler, item_spec_repo, player_status_repo = _create_handler_with_mocks()
        player_id = PlayerId(1)
        item_spec_id = ItemSpecId(900)
        spec = ItemSpec(
            item_spec_id=item_spec_id,
            name="回復ポーション",
            item_type=ItemType.CONSUMABLE,
            rarity=Rarity.COMMON,
            description="HP回復",
            max_stack_size=MaxStackSize(10),
            consume_effect=HealEffect(amount=30),
        )
        spec_rm = ItemSpecReadModel(
            item_spec_id=spec.item_spec_id,
            name=spec.name,
            item_type=spec.item_type,
            rarity=spec.rarity,
            description=spec.description,
            max_stack_size=spec.max_stack_size,
            consume_effect=spec.consume_effect,
        )
        spec_rm.consume_effect = spec.consume_effect
        item_spec_repo.find_by_id.return_value = spec_rm
        player_status = _create_player_status(1, hp_current=50, hp_max=100)
        player_status_repo.find_by_id.return_value = player_status

        event = ConsumableUsedEvent.create(
            aggregate_id=player_id,
            aggregate_type="PlayerStatusAggregate",
            item_spec_id=item_spec_id,
        )
        handler.handle(event)

        assert player_status.hp.value == 80
        player_status_repo.save.assert_called_once_with(player_status)

    def test_apply_recover_mp_effect(self):
        """RecoverMpEffect が正しく適用される"""
        handler, item_spec_repo, player_status_repo = _create_handler_with_mocks()
        player_id = PlayerId(1)
        item_spec_id = ItemSpecId(901)
        spec_rm = ItemSpecReadModel(
            item_spec_id=item_spec_id,
            name="MPポーション",
            item_type=ItemType.CONSUMABLE,
            rarity=Rarity.COMMON,
            description="MP回復",
            max_stack_size=MaxStackSize(10),
            consume_effect=RecoverMpEffect(amount=20),
        )
        item_spec_repo.find_by_id.return_value = spec_rm
        player_status = _create_player_status(mp_current=30, mp_max=50)
        player_status_repo.find_by_id.return_value = player_status
        initial_mp = player_status.mp.value

        event = ConsumableUsedEvent.create(
            aggregate_id=player_id,
            aggregate_type="PlayerStatusAggregate",
            item_spec_id=item_spec_id,
        )
        handler.handle(event)

        assert player_status.mp.value == initial_mp + 20
        player_status_repo.save.assert_called_once()

    def test_apply_gold_effect(self):
        """GoldEffect が正しく適用される"""
        handler, item_spec_repo, player_status_repo = _create_handler_with_mocks()
        player_id = PlayerId(1)
        item_spec_id = ItemSpecId(902)
        spec_rm = ItemSpecReadModel(
            item_spec_id=item_spec_id,
            name="金袋",
            item_type=ItemType.CONSUMABLE,
            rarity=Rarity.COMMON,
            description="金増加",
            max_stack_size=MaxStackSize(10),
            consume_effect=GoldEffect(amount=500),
        )
        item_spec_repo.find_by_id.return_value = spec_rm
        player_status = _create_player_status()
        player_status_repo.find_by_id.return_value = player_status
        initial_gold = player_status.gold.value

        event = ConsumableUsedEvent.create(
            aggregate_id=player_id,
            aggregate_type="PlayerStatusAggregate",
            item_spec_id=item_spec_id,
        )
        handler.handle(event)

        assert player_status.gold.value == initial_gold + 500
        player_status_repo.save.assert_called_once()

    def test_apply_exp_effect(self):
        """ExpEffect が正しく適用される"""
        handler, item_spec_repo, player_status_repo = _create_handler_with_mocks()
        player_id = PlayerId(1)
        item_spec_id = ItemSpecId(903)
        spec_rm = ItemSpecReadModel(
            item_spec_id=item_spec_id,
            name="経験値の書",
            item_type=ItemType.CONSUMABLE,
            rarity=Rarity.COMMON,
            description="経験値増加",
            max_stack_size=MaxStackSize(10),
            consume_effect=ExpEffect(amount=100),
        )
        item_spec_repo.find_by_id.return_value = spec_rm
        player_status = _create_player_status()
        player_status_repo.find_by_id.return_value = player_status

        event = ConsumableUsedEvent.create(
            aggregate_id=player_id,
            aggregate_type="PlayerStatusAggregate",
            item_spec_id=item_spec_id,
        )
        handler.handle(event)

        player_status_repo.save.assert_called_once()

    def test_apply_composite_effect(self):
        """CompositeItemEffect が再帰的に適用される"""
        handler, item_spec_repo, player_status_repo = _create_handler_with_mocks()
        player_id = PlayerId(1)
        item_spec_id = ItemSpecId(904)
        composite = CompositeItemEffect(
            effects=(HealEffect(amount=10), GoldEffect(amount=50))
        )
        spec_rm = ItemSpecReadModel(
            item_spec_id=item_spec_id,
            name="複合ポーション",
            item_type=ItemType.CONSUMABLE,
            rarity=Rarity.COMMON,
            description="HP+金",
            max_stack_size=MaxStackSize(10),
            consume_effect=composite,
        )
        item_spec_repo.find_by_id.return_value = spec_rm
        player_status = _create_player_status(1, hp_current=50, hp_max=100)
        player_status_repo.find_by_id.return_value = player_status
        initial_gold = player_status.gold.value

        event = ConsumableUsedEvent.create(
            aggregate_id=player_id,
            aggregate_type="PlayerStatusAggregate",
            item_spec_id=item_spec_id,
        )
        handler.handle(event)

        assert player_status.hp.value == 60
        assert player_status.gold.value == initial_gold + 50
        player_status_repo.save.assert_called_once()

    def test_item_spec_not_found_raises(self):
        """ItemSpec が見つからない場合は ItemSpecNotFoundForConsumableEffectException"""
        handler, item_spec_repo, player_status_repo = _create_handler_with_mocks()
        item_spec_repo.find_by_id.return_value = None

        event = ConsumableUsedEvent.create(
            aggregate_id=PlayerId(1),
            aggregate_type="PlayerStatusAggregate",
            item_spec_id=ItemSpecId(999),
        )
        with pytest.raises(ItemSpecNotFoundForConsumableEffectException, match="999"):
            handler.handle(event)

    def test_no_consume_effect_raises(self):
        """consume_effect が None の場合は ConsumeEffectMissingException"""
        handler, item_spec_repo, player_status_repo = _create_handler_with_mocks()
        spec_rm = ItemSpecReadModel(
            item_spec_id=ItemSpecId(905),
            name="効果なし",
            item_type=ItemType.CONSUMABLE,
            rarity=Rarity.COMMON,
            description="効果なし",
            max_stack_size=MaxStackSize(10),
            consume_effect=None,
        )
        item_spec_repo.find_by_id.return_value = spec_rm

        event = ConsumableUsedEvent.create(
            aggregate_id=PlayerId(1),
            aggregate_type="PlayerStatusAggregate",
            item_spec_id=ItemSpecId(905),
        )
        with pytest.raises(ConsumeEffectMissingException, match="905"):
            handler.handle(event)

    def test_player_status_not_found_raises(self):
        """PlayerStatus が見つからない場合は PlayerNotFoundForConsumableEffectException"""
        handler, item_spec_repo, player_status_repo = _create_handler_with_mocks()
        spec_rm = ItemSpecReadModel(
            item_spec_id=ItemSpecId(906),
            name="回復ポーション",
            item_type=ItemType.CONSUMABLE,
            rarity=Rarity.COMMON,
            description="HP回復",
            max_stack_size=MaxStackSize(10),
            consume_effect=HealEffect(amount=50),
        )
        item_spec_repo.find_by_id.return_value = spec_rm
        player_status_repo.find_by_id.return_value = None

        event = ConsumableUsedEvent.create(
            aggregate_id=PlayerId(999),
            aggregate_type="PlayerStatusAggregate",
            item_spec_id=ItemSpecId(906),
        )
        with pytest.raises(PlayerNotFoundForConsumableEffectException, match="999"):
            handler.handle(event)

    def test_unknown_effect_type_raises_system_error(self):
        """未知の効果タイプの場合は SystemErrorException"""
        handler, item_spec_repo, player_status_repo = _create_handler_with_mocks()
        spec_rm = ItemSpecReadModel(
            item_spec_id=ItemSpecId(907),
            name="謎のアイテム",
            item_type=ItemType.CONSUMABLE,
            rarity=Rarity.COMMON,
            description="未知の効果",
            max_stack_size=MaxStackSize(10),
            consume_effect=_FakeItemEffect(),
        )
        item_spec_repo.find_by_id.return_value = spec_rm
        player_status = _create_player_status()
        player_status_repo.find_by_id.return_value = player_status

        event = ConsumableUsedEvent.create(
            aggregate_id=PlayerId(1),
            aggregate_type="PlayerStatusAggregate",
            item_spec_id=ItemSpecId(907),
        )
        with pytest.raises(SystemErrorException, match="Unknown consumable effect type"):
            handler.handle(event)
