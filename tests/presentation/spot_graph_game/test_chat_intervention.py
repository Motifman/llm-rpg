from ai_rpg_world.application.observation.services.observation_context_buffer import (
    DefaultObservationContextBuffer,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.presentation.spot_graph_game.runtime_manager import (
    GameRuntimeManager,
    _SessionState,
)
from ai_rpg_world.presentation.spot_graph_game.schemas import ChatSendRequest


class _FakeIdMapper:
    def get_int(self, namespace: str, string_id: str) -> int:
        if namespace == "player" and string_id == "gate_girl":
            return 1
        raise KeyError(string_id)


class _FakeRuntime:
    def __init__(self) -> None:
        self.id_mapper = _FakeIdMapper()
        self._obs_buffer = DefaultObservationContextBuffer()

    def current_tick(self) -> int:
        return 0


def test_send_chat_message_appends_user_speech_observation() -> None:
    manager = GameRuntimeManager()
    runtime = _FakeRuntime()
    manager._sessions["session-1"] = _SessionState(
        session_id="session-1",
        world_id="abandoned_hospital",
        world_title="廃病院",
        character_ids=["gate_girl"],
        status="running",
        created_at="now",
        runtime=runtime,
    )

    response = manager.send_chat_message(
        ChatSendRequest(
            session_id="session-1",
            target_character_id="gate_girl",
            message="大丈夫？",
        )
    )

    observations = runtime._obs_buffer.get_observations(PlayerId(1))
    assert response.message == "大丈夫？"
    assert len(observations) == 1
    assert observations[0].output.structured["type"] == "user_directed_speech"
    assert observations[0].output.structured["content"] == "大丈夫？"
    assert "大丈夫？" in observations[0].output.prose
    assert 1 in manager._sessions["session-1"].pending_llm_turns


def test_send_chat_message_requires_existing_session() -> None:
    manager = GameRuntimeManager()

    try:
        manager.send_chat_message(
            ChatSendRequest(
                session_id="missing",
                target_character_id="gate_girl",
                message="聞こえる？",
            )
        )
    except ValueError as exc:
        assert "Session not found" in str(exc)
    else:
        raise AssertionError("ValueError was not raised")
