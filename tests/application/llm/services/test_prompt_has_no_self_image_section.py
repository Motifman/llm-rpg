"""1 ターンのプロンプトに【自己像と世界観】が出ないことを保証する (#1824)。長い期間の流れはエピソードの目次が受け持つ。"""

from __future__ import annotations

from ai_rpg_world.being.domain.short_term_memory import Backstory, ShortTermMemory
from ai_rpg_world.domain.player.value_object.player_id import PlayerId


class TestThePromptHasNoSelfImageSection:
    """1 ターンのプロンプトに【自己像と世界観】が出ないことを保証する。"""

    def test_prompt_after_overflow_shows_recent_flow_but_not_self_image(self) -> None:
        """Being の短期記憶にいきさつが 3 世代たまったあとのプロンプトに、【ここまでのいきさつ】は出て【自己像と世界観】は出ない。"""
        import tests.demos.test_disabled_memory_parts_vanish_from_the_prompt as capture

        scenario, mapping = capture._profile_mapping("smoke_stub")
        runtime = capture.create_world_runtime(
            scenario,
            config=capture.ResolvedLlmRuntimeConfig.from_mapping({**mapping, **capture._OFFLINE}),
        )
        player_id = PlayerId(1)
        being_id = runtime._acting_being_for(player_id).being_id
        runtime._being_short_term_memory_store.replace_all_by_being(
            ShortTermMemory(
                being_id,
                backstories=tuple(
                    Backstory(flow=f"{n} 回目の流れ", mood="", written_turn=n * 10 + 10, until_turn=n * 10)
                    for n in (1, 2, 3)
                ),
                recent_from=31,
            )
        )
        client = capture._PromptCaptureClient()

        capture._WorldLlmWiring(
            runtime=runtime,
            observation_buffer=runtime._obs_buffer,
            llm_client=client,
            typed_judgment_port=capture.ScriptedJudgmentPort(),
        ).run_phase_a(player_id)

        prompt = "\n".join(str(message["content"]) for message in client.messages)
        assert "【ここまでのいきさつ】" in prompt
        assert "【自己像と世界観】" not in prompt
