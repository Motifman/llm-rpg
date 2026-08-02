"""ツールを出すかどうかの判断が 1 か所に集まっていることを保証する。

## 集めた理由

判断が 3 か所に散っていた。

- ツール定義を組む場所 (`get_tool_definitions` に 3 つのインライン分岐)
- 同席者行に組み込みツールを並べる場所
- 同席者行の見出しで `give_item` を案内する文

**後ろの 2 つが最初の 1 つを見ていなかった。** シナリオが
`disabled_tools` で無効化しても、行動候補として宣伝され続ける。
エージェントはそれを選び、呼んだ先にツールは無い。無効化しないより悪い。

## 今後ツールを足す人へ

ツール名を出す判断はこのファイルだけを見れば済む。逆に、ここを見ずに
ツール名をプロンプトへ書くと、`tests/demos/test_disabled_tools_vanish_
from_the_prompt.py` の総当たりで落ちる。
"""

from __future__ import annotations

import pytest

from ai_rpg_world.application.llm.tool_exposure import (
    PHASE_COMMON_TOOLS,
    ToolExposure,
)


def _spot_tool_names() -> list:
    """spot graph ツールの実名。カタログから取るので足し忘れが起きない。"""
    from ai_rpg_world.application.llm.services.tool_catalog.spot_graph import (
        get_spot_graph_specs,
    )

    return [defn.name for defn, _ in get_spot_graph_specs()]


class _Scenario:
    def __init__(self, *, disabled=(), synchronized=()) -> None:
        self.disabled_tools = disabled
        self.synchronized_action_groups = synchronized


class TestWhatTheWorldHas:
    """この世界に在るかどうか。"""

    def test_an_ordinary_tool_is_exposed(self) -> None:
        """何も宣言しなければ、そのまま出る。"""
        exposure = ToolExposure.from_scenario(_Scenario(), meeting_declared=False)

        assert exposure.is_exposed("travel_to") is True

    def test_a_tool_the_scenario_disabled_is_not(self) -> None:
        """シナリオが無効化したツールは出ない。"""
        exposure = ToolExposure.from_scenario(
            _Scenario(disabled=("attack",)), meeting_declared=False
        )

        assert exposure.is_exposed("attack") is False

    @pytest.mark.parametrize("tool_name", ["vote", "report_body"])
    def test_meeting_tools_need_the_declaration(self, tool_name) -> None:
        """会議を宣言しない世界に、会議系は出ない。

        会議を開けない世界に「報告する」「投票する」が並ぶと、選べるのに
        必ず失敗する手が増える (#860)。
        """
        without = ToolExposure.from_scenario(_Scenario(), meeting_declared=False)
        with_meeting = ToolExposure.from_scenario(_Scenario(), meeting_declared=True)

        assert without.is_exposed(tool_name) is False
        assert with_meeting.is_exposed(tool_name) is True

    def test_prepare_action_needs_synchronized_groups(self) -> None:
        """同時行動を宣言しない世界に prepare_action は出ない。"""
        without = ToolExposure.from_scenario(_Scenario(), meeting_declared=False)
        with_groups = ToolExposure.from_scenario(
            _Scenario(synchronized=("dig",)), meeting_declared=False
        )

        assert without.is_exposed("prepare_action") is False
        assert with_groups.is_exposed("prepare_action") is True

    def test_the_scenario_declaration_beats_everything(self) -> None:
        """無効化の宣言は、他の条件を満たしていても勝つ。

        「会議を宣言しているが投票はさせない」のような世界を書けるように
        する。**engine が「会議があるなら投票もある」と決めない。**
        """
        exposure = ToolExposure.from_scenario(
            _Scenario(disabled=("vote",)), meeting_declared=True
        )

        assert exposure.is_exposed("vote") is False

    def test_a_malformed_declaration_disables_nothing(self) -> None:
        """宣言が想定外の型なら、何も落とさない。

        loader が必ず tuple を渡すので、ここに来るのはテスト用の代役だけ。
        落とす側に倒すと、無関係なテストが黙って壊れる。
        """
        scenario = _Scenario()
        scenario.disabled_tools = "attack"  # 文字列 = 書き方の誤り

        exposure = ToolExposure.from_scenario(scenario, meeting_declared=False)

        assert exposure.is_exposed("attack") is True


class TestWhichBlockATooolGoesIn:
    """フェーズごとに、どのブロックへ置くか。"""

    @pytest.mark.parametrize("tool_name", sorted(PHASE_COMMON_TOOLS))
    def test_common_tools_are_not_in_the_phase_block(self, tool_name) -> None:
        """共通ブロックのツールは、フェーズ固有ブロックに入らない。

        両方に入ると **同じツールが 2 回並ぶ**。
        """
        assert ToolExposure.is_phase_common(tool_name) is True
        for in_meeting in (True, False):
            assert (
                ToolExposure.is_available_in_phase(tool_name, in_meeting=in_meeting)
                is False
            )

    def test_voting_only_appears_during_a_meeting(self) -> None:
        """投票は会議中だけ。

        自由時間に並ぶと「いつでも投票できる」と読め、会議の外で試して
        失敗し続ける。
        """
        assert ToolExposure.is_available_in_phase("vote", in_meeting=True) is True
        assert ToolExposure.is_available_in_phase("vote", in_meeting=False) is False

    def test_ordinary_tools_disappear_during_a_meeting(self) -> None:
        """物理的な行為は会議中に出ない。

        前提条件で弾く形にすると、全 interaction に「会議中は不可」を書いて
        回ることになる。
        """
        assert ToolExposure.is_available_in_phase("travel_to", in_meeting=False) is True
        assert ToolExposure.is_available_in_phase("travel_to", in_meeting=True) is False

    def test_no_tool_is_ever_in_two_blocks(self) -> None:
        """どのツールも、2 つのブロックに同時に入らない。

        入ると **同じツールが 2 回並ぶ**。

        「ちょうど 1 つ」では縛れない。**どちらのフェーズにも意図的に
        落とすツールがある**。自由時間は vote を落とし、会議中は物理的な
        行為を落とす。0 個は正しい状態になりうる。
        """
        for name in _spot_tool_names():
            for in_meeting in (True, False):
                blocks = [
                    ToolExposure.is_phase_common(name),
                    ToolExposure.is_available_in_phase(
                        name, in_meeting=in_meeting
                    ),
                ]
                assert sum(blocks) <= 1, (name, in_meeting, blocks)

    @pytest.mark.parametrize(
        ("in_meeting", "expected"),
        [
            pytest.param(False, ("travel_to", "interact", "speak"), id="free_roam"),
            pytest.param(True, ("speak", "vote"), id="meeting"),
        ],
    )
    def test_each_phase_keeps_what_it_needs(self, in_meeting, expected) -> None:
        """各フェーズに、そのフェーズが成立するツールが残る。

        重複だけを見ていると、**全部消えても通ってしまう**。会議中に話す
        手段が無ければ会議は成立せず、自由時間に動く手段が無ければ世界が
        止まる。
        """
        surviving = {
            name
            for name in _spot_tool_names()
            if ToolExposure.is_phase_common(name)
            or ToolExposure.is_available_in_phase(name, in_meeting=in_meeting)
        }

        for name in expected:
            assert name in surviving, name
