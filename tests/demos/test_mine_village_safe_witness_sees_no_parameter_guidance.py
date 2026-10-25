"""廃坑の山村で、他の人が引数を渡し忘れて金庫を開けられなかったとき、同席者の観測に引数の案内が出ないことを保証する (#1607)。

ハルが `open_safe` を `"code"` 無しで呼ぶと、ハル本人には「parameters の "code" で
指定してください」が返る (design_decisions D1591)。これは道具の呼び方の案内で、
世界では何も起きていない。同じ部屋のミオの観測にこの文が混ざると、ミオは引数名を
世界の出来事として読む。
"""

from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

import pytest

from ai_rpg_world.application.llm.services.world_llm_turn.types import LlmPhaseAResult
from ai_rpg_world.application.llm.tool_constants import TOOL_NAME_SPOT_GRAPH_INTERACT
from ai_rpg_world.application.llm.wiring.resolved_runtime_config import (
    ResolvedLlmRuntimeConfig,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world_graph.value_object.entity_id import EntityId
from ai_rpg_world.presentation.spot_graph_game.runtime_manager import GameRuntimeManager
from ai_rpg_world.presentation.spot_graph_game.schemas import (
    CharacterCreateRequest,
    SessionCreateRequest,
)

_SCENARIO = Path(__file__).resolve().parents[2] / "data" / "scenarios" / "mine_village_v1.json"
_HAL = PlayerId(1)
_MIO = PlayerId(2)


@pytest.fixture(autouse=True)
def _without_developer_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("OPENROUTER_API_KEY", "OPENAI_API_KEY"):
        monkeypatch.delenv(name, raising=False)


def _session_with_hal_and_mio_in_the_office(tmp: str):
    manager = GameRuntimeManager(
        scenarios_dir=_SCENARIO.parent,
        characters_path=Path(tmp) / "characters.json",
        runtime_config=ResolvedLlmRuntimeConfig.for_tests(typed_judgment_provider="stub"),
    )
    character = manager.create_character(CharacterCreateRequest(name="probe"))
    summary = manager.create_session(SessionCreateRequest(world_id=_SCENARIO.stem, character_ids=[character.id]))
    wiring = manager._sessions[summary.session_id].llm_wiring
    runtime = wiring.runtime
    office = SpotId.create(runtime.id_mapper.get_int("spot", "company_office"))
    graph = runtime._spot_graph_repo.find_graph()
    for player in (_HAL, _MIO):
        entity = EntityId.create(int(player))
        graph.unplace_entity(entity)
        graph.place_entity(entity, office)
    runtime._spot_graph_repo.save(graph)
    return wiring


def _hal_tries_the_safe(wiring, arguments: dict[str, Any]):
    return wiring.run_phase_b(
        LlmPhaseAResult(
            player_id=_HAL,
            prompt=wiring.runtime.build_full_prompt(_HAL),
            tools_payload=[],
            tool_call={
                "name": TOOL_NAME_SPOT_GRAPH_INTERACT,
                "arguments": {
                    "target_label": "金庫",
                    "action_name": "open_safe",
                    "inner_thought": "開けてみる。",
                    **arguments,
                },
            },
            exception=None,
        )
    )


def _what_mio_saw(wiring) -> list[str]:
    return [entry.output.prose for entry in wiring.runtime._obs_buffer.get_observations(_MIO)]


def _the_safe_attempts(proses: list[str]) -> list[str]:
    return [p for p in proses if p.startswith("ハルが金庫")]


class TestWitnessOfAFailedSafe:
    """金庫の失敗を同じ部屋で見たミオの観測に、何が届き何が届かないかを保証する。"""

    @pytest.mark.parametrize(
        "arguments",
        [
            pytest.param({}, id="no_parameters"),
            pytest.param({"parameters": {"text": "1907"}}, id="wrong_key"),
        ],
    )
    def test_missing_code_reaches_mio_without_parameter_guidance(self, arguments: dict[str, Any]) -> None:
        """ハルが "code" を渡さずに金庫を開けようとすると、ハル本人には "code" の案内が返り、ミオの観測には金庫を試した失敗の文が 1 件も出ない。"""
        with TemporaryDirectory() as tmp:
            wiring = _session_with_hal_and_mio_in_the_office(tmp)

            result = _hal_tries_the_safe(wiring, arguments)

            assert result.success is False
            assert '"code"' in result.message
            seen = _what_mio_saw(wiring)
            assert _the_safe_attempts(seen) == []
            assert not any("parameters" in p or "指定してください" in p for p in seen)

    def test_wrong_code_still_reaches_mio_as_a_failed_attempt(self) -> None:
        """ハルが "code" に違う番号を入れて金庫を開けられなかったときは、これまでどおりミオに金庫を試して失敗した文が届く。"""
        with TemporaryDirectory() as tmp:
            wiring = _session_with_hal_and_mio_in_the_office(tmp)

            _hal_tries_the_safe(wiring, {"parameters": {"code": "0000"}})

            attempts = _the_safe_attempts(_what_mio_saw(wiring))
            assert len(attempts) == 1
            assert "parameters" not in attempts[0]
