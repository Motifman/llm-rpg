"""_build_observation_stack のテスト（正常・境界・統合）"""

from unittest.mock import MagicMock

import pytest

from ai_rpg_world.application.llm.contracts.interfaces import ILlmTurnTrigger
from ai_rpg_world.application.observation.contracts.interfaces import (
    IObservationContextBuffer,
    IObservationFormatter,
)
from ai_rpg_world.application.observation.services.observation_context_buffer import (
    DefaultObservationContextBuffer,
)
from ai_rpg_world.domain.common.unit_of_work_factory import UnitOfWorkFactory
from ai_rpg_world.infrastructure.events.observation_event_handler_registry import (
    ObservationEventHandlerRegistry,
)
from ai_rpg_world.application.llm.wiring import _build_observation_stack


def _minimal_observation_stack_deps(llm_turn_trigger: ILlmTurnTrigger):
    """_build_observation_stack に渡す最小限の依存を返す。"""
    uow = MagicMock(spec=UnitOfWorkFactory)
    uow.create.return_value = MagicMock()
    uow.create.return_value.__enter__ = MagicMock(return_value=MagicMock())
    uow.create.return_value.__exit__ = MagicMock(return_value=False)
    return {
        "player_status_repository": MagicMock(),
        "physical_map_repository": MagicMock(),
        "player_profile_repository": MagicMock(),
        "quest_repository": None,
        "guild_repository": None,
        "shop_repository": None,
        "trade_repository": None,
        "monster_repository": None,
        "hit_box_repository": None,
        "skill_loadout_repository": None,
        "skill_deck_progress_repository": None,
        "sns_user_repository": None,
        "buffer": DefaultObservationContextBuffer(),
        "unit_of_work_factory": uow,
        "llm_turn_trigger": llm_turn_trigger,
        "llm_player_resolver": MagicMock(),
        "movement_service": MagicMock(),
        "game_time_provider": None,
        "world_time_config_service": None,
        "observation_formatter": None,
        "spot_repository": None,
        "item_spec_repository": None,
        "item_repository": None,
        "skill_spec_repository": None,
    }


class TestBuildObservationStackReturnType:
    """_build_observation_stack の戻り値（正常）"""

    def test_returns_observation_registry(self):
        """返り値は ObservationEventHandlerRegistry である"""
        trigger = MagicMock(spec=ILlmTurnTrigger)
        trigger.schedule_turn = MagicMock()
        trigger.run_scheduled_turns = MagicMock()
        deps = _minimal_observation_stack_deps(trigger)
        result = _build_observation_stack(**deps)
        assert isinstance(result, ObservationEventHandlerRegistry)

    def test_registry_has_register_handlers(self):
        """返された Registry は register_handlers メソッドを持つ"""
        trigger = MagicMock(spec=ILlmTurnTrigger)
        trigger.schedule_turn = MagicMock()
        trigger.run_scheduled_turns = MagicMock()
        deps = _minimal_observation_stack_deps(trigger)
        result = _build_observation_stack(**deps)
        assert hasattr(result, "register_handlers")
        assert callable(result.register_handlers)

    def test_accepts_optional_observation_formatter(self):
        """observation_formatter を渡した場合はそれが使われる"""
        trigger = MagicMock(spec=ILlmTurnTrigger)
        trigger.schedule_turn = MagicMock()
        trigger.run_scheduled_turns = MagicMock()
        custom_formatter = MagicMock(spec=IObservationFormatter)
        deps = _minimal_observation_stack_deps(trigger)
        deps["observation_formatter"] = custom_formatter
        result = _build_observation_stack(**deps)
        assert result._handler._formatter is custom_formatter

    def test_accepts_optional_observation_buffer(self):
        """buffer を渡した場合はそれが handler に渡される"""
        trigger = MagicMock(spec=ILlmTurnTrigger)
        trigger.schedule_turn = MagicMock()
        trigger.run_scheduled_turns = MagicMock()
        custom_buffer = MagicMock(spec=IObservationContextBuffer)
        deps = _minimal_observation_stack_deps(trigger)
        deps["buffer"] = custom_buffer
        result = _build_observation_stack(**deps)
        assert result._handler._buffer is custom_buffer


def _minimal_wiring_deps():
    """create_llm_agent_wiring に渡す最小限のモック依存を返す。"""
    from ai_rpg_world.domain.common.unit_of_work_factory import UnitOfWorkFactory
    from ai_rpg_world.application.world.services.world_query_service import (
        WorldQueryService,
    )
    from ai_rpg_world.application.world.services.movement_service import (
        MovementApplicationService,
    )
    from ai_rpg_world.domain.player.repository.player_profile_repository import (
        PlayerProfileRepository,
    )
    from ai_rpg_world.domain.player.repository.player_status_repository import (
        PlayerStatusRepository,
    )
    from ai_rpg_world.domain.world.repository.physical_map_repository import (
        PhysicalMapRepository,
    )

    uow = MagicMock(spec=UnitOfWorkFactory)
    uow.create.return_value = MagicMock()
    uow.create.return_value.__enter__ = MagicMock(return_value=MagicMock())
    uow.create.return_value.__exit__ = MagicMock(return_value=False)
    wq = MagicMock(spec=WorldQueryService)
    wq.get_player_current_state = MagicMock(return_value=None)
    mov = MagicMock(spec=MovementApplicationService)
    mov.move_to_destination = MagicMock()
    mov.cancel_movement = MagicMock()
    return {
        "player_status_repository": MagicMock(spec=PlayerStatusRepository),
        "physical_map_repository": MagicMock(spec=PhysicalMapRepository),
        "world_query_service": wq,
        "movement_service": mov,
        "player_profile_repository": MagicMock(spec=PlayerProfileRepository),
        "unit_of_work_factory": uow,
    }


class TestBuildObservationStackIntegration:
    """create_llm_agent_wiring 経由での統合確認"""

    def test_wiring_uses_observation_stack_from_build(self):
        """create_llm_agent_wiring で _build_observation_stack 経由の registry が使われる"""
        from ai_rpg_world.application.llm.wiring import create_llm_agent_wiring

        deps = _minimal_wiring_deps()
        result = create_llm_agent_wiring(**deps)
        assert isinstance(result.observation_registry, ObservationEventHandlerRegistry)
        assert hasattr(result.observation_registry, "register_handlers")
