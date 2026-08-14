"""動的な在室数表示が未配線のまま成功扱いにならないことを保証する。"""

from types import SimpleNamespace

import pytest

from ai_rpg_world.application.common.exceptions import ApplicationException
from ai_rpg_world.application.world_graph.spot_interaction_application_service import (
    SpotInteractionApplicationService,
)


def test_declared_occupancy_effect_without_provider_fails_loudly() -> None:
    """表示要求に provider が無ければ、空の成功文へ縮退せず明示的に失敗する。"""
    service = object.__new__(SpotInteractionApplicationService)
    service._room_occupancy_message_provider = None
    result = SimpleNamespace(room_occupancy_display_specs=(object(),))

    with pytest.raises(ApplicationException, match="在室数の配線がありません"):
        service._room_occupancy_messages(result)
