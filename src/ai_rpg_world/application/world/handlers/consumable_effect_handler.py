"""
ConsumableUsedEvent を受けて、消費可能アイテムの効果（HP/MP回復など）を PlayerStatusAggregate に適用する同期ハンドラ。

効果の種類に応じた適用はアプリケーション層（本ハンドラ）で行う。
ItemEffect は値オブジェクトとしてデータのみを保持し、ドメイン境界を超えた依存を持たない。
"""

import logging

from ai_rpg_world.application.common.exceptions import ApplicationException, SystemErrorException
from ai_rpg_world.application.world.exceptions.consumable_effect_exception import (
    ItemSpecNotFoundForConsumableEffectException,
    PlayerNotFoundForConsumableEffectException,
    ConsumeEffectMissingException,
)
from ai_rpg_world.domain.common.event_handler import EventHandler
from ai_rpg_world.domain.common.exception import DomainException
from ai_rpg_world.domain.item.event.item_event import ConsumableUsedEvent
from ai_rpg_world.domain.item.repository.item_spec_repository import ItemSpecRepository
from ai_rpg_world.domain.item.value_object.item_effect import (
    HealEffect,
    RecoverMpEffect,
    GoldEffect,
    ExpEffect,
    CompositeItemEffect,
    ItemEffect,
)
from ai_rpg_world.domain.player.repository.player_status_repository import PlayerStatusRepository


class ConsumableEffectHandler(EventHandler[ConsumableUsedEvent]):
    """消費可能アイテムの効果をプレイヤーステータスに適用するハンドラ"""

    def __init__(
        self,
        item_spec_repository: ItemSpecRepository,
        player_status_repository: PlayerStatusRepository,
    ):
        self._item_spec_repository = item_spec_repository
        self._player_status_repository = player_status_repository
        self._logger = logging.getLogger(self.__class__.__name__)

    def handle(self, event: ConsumableUsedEvent) -> None:
        try:
            self._handle_impl(event)
        except (ApplicationException, DomainException, SystemErrorException):
            raise
        except Exception as e:
            self._logger.exception("Unexpected error in ConsumableEffectHandler: %s", e)
            raise SystemErrorException(
                f"Consumable effect handling failed: {e}",
                original_exception=e,
            ) from e

    def _handle_impl(self, event: ConsumableUsedEvent) -> None:
        player_id = event.aggregate_id
        spec_rm = self._item_spec_repository.find_by_id(event.item_spec_id)
        if spec_rm is None:
            raise ItemSpecNotFoundForConsumableEffectException(event.item_spec_id.value)

        item_spec = spec_rm.to_item_spec()
        if item_spec.consume_effect is None:
            raise ConsumeEffectMissingException(event.item_spec_id.value)

        player_status = self._player_status_repository.find_by_id(player_id)
        if player_status is None:
            raise PlayerNotFoundForConsumableEffectException(player_id.value)

        self._apply_effect_to_status(item_spec.consume_effect, player_status)
        self._player_status_repository.save(player_status)
        self._logger.debug(
            "Applied consume effect for player_id=%s item_spec_id=%s",
            player_id,
            event.item_spec_id,
        )

    def _apply_effect_to_status(self, effect: ItemEffect, player_status) -> None:
        """効果データを PlayerStatusAggregate に反映する。効果の種類ごとに適切なメソッドを呼ぶ。"""
        if isinstance(effect, HealEffect):
            player_status.heal_hp(effect.amount)
        elif isinstance(effect, RecoverMpEffect):
            player_status.heal_mp(effect.amount)
        elif isinstance(effect, GoldEffect):
            player_status.earn_gold(effect.amount)
        elif isinstance(effect, ExpEffect):
            player_status.gain_exp(effect.amount)
        elif isinstance(effect, CompositeItemEffect):
            for sub in effect.effects:
                self._apply_effect_to_status(sub, player_status)
        else:
            raise SystemErrorException(
                f"Unknown consumable effect type: {type(effect).__name__}. "
                "Register a handler for this effect type in ConsumableEffectHandler.",
                original_exception=None,
            )
