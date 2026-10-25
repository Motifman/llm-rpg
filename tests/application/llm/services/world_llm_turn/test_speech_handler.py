"""``handle_speech`` が、世界の規則で断られた発話を例外ではなく失敗の結果として本人に返すことを保証する。"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from ai_rpg_world.application.llm.services.llm_client_stub import StubLlmClient
from ai_rpg_world.application.llm.services.world_llm_turn.speech_handler import (
    handle_speech,
)
from ai_rpg_world.application.speech.exceptions import PlayerNotFoundException
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.presentation.spot_graph_game.runtime_manager import (
    GameRuntimeManager,
)
from ai_rpg_world.presentation.spot_graph_game.schemas import (
    CharacterCreateRequest,
    SessionCreateRequest,
)

_SCENARIO_DIR = Path(__file__).resolve().parents[5] / "tests" / "fixtures" / "scenarios"


def _session_with_shout(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    monkeypatch.setenv("SPOT_GRAPH_TICK_LOOP_ENABLED", "false")
    mgr = GameRuntimeManager(
        scenarios_dir=_SCENARIO_DIR,
        characters_path=tmp_path / "characters.json",
    )
    char = mgr.create_character(CharacterCreateRequest(name="倒れた話し手"))
    summary = mgr.create_session(SessionCreateRequest(world_id="control_panel_toggle", character_ids=[char.id]))
    state = mgr._sessions[summary.session_id]
    state.llm_wiring.llm_client = StubLlmClient(
        tool_call_to_return={
            "name": "speak",
            "arguments": {"channel": "shout", "content": "誰か来てくれ"},
        }
    )
    return state


def _knock_down(state, player_id: PlayerId) -> None:
    repo = state.runtime._player_status_repo
    status = repo.find_by_id(player_id)
    status.apply_damage(status.hp.max_hp)
    status.clear_events()
    repo.save(status)


class TestDownedSpeakerIsRefusedAsWorldFailure:
    """手番を選ばれたあと同じ tick のうちに倒された本人の speak を、世界の中の失敗として返す観点。"""

    def test_downed_speaker_gets_speaker_down_failure_with_remediation(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """倒れている本人が shout すると、例外を投げずに error_code=SPEAKER_DOWN と対処の文を持つ失敗を返す。"""
        state = _session_with_shout(monkeypatch, tmp_path)
        player_id = state.runtime.get_player_ids()[0]
        _knock_down(state, player_id)

        result = state.llm_wiring.run_turn(player_id)

        assert result.success is False
        assert result.error_code == "SPEAKER_DOWN"
        assert "倒れて" in result.message
        assert result.remediation
        assert "player_id" not in result.message

    def test_refusal_other_than_downed_is_reraised(self) -> None:
        """PLAYER.DOWNED 以外の SpeechCommandException は失敗の結果にせず、そのまま投げ直す。"""

        def _raise_not_found(*_args, **_kwargs):
            raise PlayerNotFoundException(1)

        wiring = SimpleNamespace(runtime=SimpleNamespace(do_speech=_raise_not_found))

        with pytest.raises(PlayerNotFoundException):
            handle_speech(wiring, PlayerId(1), {"channel": "shout", "content": "誰か来てくれ"}, None)
