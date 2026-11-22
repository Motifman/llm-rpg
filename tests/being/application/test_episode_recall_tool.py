from __future__ import annotations

from ai_rpg_world.being.application.episode_recall_tool import recall_call_text


class TestRecallCallText:
    """recall_call_text が、古い run と同じく、呼び名の配列だけを JSON のまま引用した呼び出しの文を作ることを保証する。"""

    def test_handles_are_quoted_as_compact_json(self) -> None:
        """呼び名の配列は、区切りに空白を入れない JSON で引用し、ほかの引数は出さない。"""
        call = recall_call_text("episode_recall", {"handles": ["ep_1", "ep_2"], "inner_thought": "思い出す"})

        assert call == 'episode_recall(handles=["ep_1","ep_2"])'

    def test_missing_handles_give_an_empty_call(self) -> None:
        """呼び名が無ければ、引数の無い呼び出しの文になる。"""
        assert recall_call_text("episode_recall", {}) == "episode_recall()"
