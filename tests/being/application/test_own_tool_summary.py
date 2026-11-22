from __future__ import annotations

from ai_rpg_world.being.application.own_tool_summary import own_tool_summary


class TestOwnToolSummary:
    """own_tool_summary が、古い run の表に無いツールの要約と同じ文を作ることを保証する。"""

    def test_arguments_are_written_as_json(self) -> None:
        """引数は JSON のまま、ツールの名前のあとに括弧で書く。"""
        summary = own_tool_summary("episode_recall", {"handles": ["ep_3f2a7b"]}, hidden=())

        assert summary == 'episode_recall({"handles": ["ep_3f2a7b"]}) を実行しました。'

    def test_hidden_arguments_are_left_out(self) -> None:
        """独白とメモは別の行や欄に出るので、要約に書かない。"""
        summary = own_tool_summary(
            "pickup", {"item": "鍵", "inner_thought": "拾おう", "memo": []}, hidden=("inner_thought", "memo")
        )

        assert summary == 'pickup({"item": "鍵"}) を実行しました。'

    def test_tool_without_visible_arguments_is_its_name(self) -> None:
        """書く引数が無ければ、ツールの名前だけの文になる。"""
        assert (
            own_tool_summary("gather", {"inner_thought": "…"}, hidden=("inner_thought",)) == "gather を実行しました。"
        )
