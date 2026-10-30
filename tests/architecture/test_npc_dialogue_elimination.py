"""NPC会話の木を消し、本番の発言とクエストの他の経路を残す。"""

from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2] / "src/ai_rpg_world"


@pytest.mark.parametrize(
    "relative_path",
    [
        "application/conversation",
        "domain/conversation",
        "infrastructure/repository/in_memory_dialogue_tree_repository.py",
        "infrastructure/repository/sqlite_dialogue_tree_repository.py",
        "infrastructure/repository/sqlite_dialogue_tree_state_codec.py",
        "application/observation/services/formatters/conversation_formatter.py",
        "application/observation/services/recipient_strategies/conversation_recipient_strategy.py",
    ],
)
def test_npc_dialogue_implementation_is_removed(relative_path: str) -> None:
    """NPC会話の本体・保存先・観測の実装は、ディレクトリも含め存在しない。"""
    assert not (_ROOT / relative_path).exists()


def test_npc_dialogue_strategy_is_not_registered() -> None:
    """NPC会話の戦略は登録されず、本番の発言は引き続き観測の登録に残る。"""
    from ai_rpg_world.application.observation.services.observed_event_registry import (
        ObservedEventRegistry,
    )
    from ai_rpg_world.domain.player.event.conversation_events import PlayerSpokeEvent

    registry = ObservedEventRegistry()
    assert PlayerSpokeEvent in registry.get_event_types_for_strategy("speech")
    assert registry.get_event_types_for_strategy("conversation") == ()
