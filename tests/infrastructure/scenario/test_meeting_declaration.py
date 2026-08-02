"""会議機構がシナリオの宣言で on / off されることを保証する。

## なぜ宣言制にするか

#874 で `report_body` を tool として出したとき、**会議と無関係なシナリオの
tool 一覧にも並んだ** (survival_island_v4_coop で 16 → 17)。会議を開けない
世界に「倒れている人を見つけたと知らせる」が並ぶのは、選べるのに必ず失敗
する手が増えるのと同じで、#860 で潰した形の再生産にあたる。

それ以上に困るのが**比較実験の土台が黙って動くこと**。プロンプトが変われば
過去 run との比較可能性が切れる。しかも「tool が 1 つ増えた」は trace を
眺めていて気付ける類の変化ではない。

同時行動 (prepare_action) が宣言のあるシナリオにだけ出るのと同じ形にする。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from ai_rpg_world.application.world_runtime.world_runtime import create_world_runtime

_SCENARIOS = Path(__file__).resolve().parents[3] / "data" / "scenarios"
_FIXTURE_SCENARIOS = (
    Path(__file__).resolve().parents[3] / "tests" / "fixtures" / "scenarios"
)

#: 会議機構を宣言していないシナリオ。
_WITHOUT_MEETING = _SCENARIOS / "survival_island_v4_coop.json"

#: 会議機構を宣言しているシナリオ。
_WITH_MEETING = _FIXTURE_SCENARIOS / "darkened_station.json"

#: 宣言があるときだけ出る tool。
_MEETING_TOOLS = {"report_body", "vote"}


def _tool_names(scenario: Path, *, as_meeting_phase: bool | None = None) -> set[str]:
    runtime = create_world_runtime(scenario)
    if as_meeting_phase is None:
        return {d.name for d in runtime.get_tool_definitions(for_every_player=True)}
    return {
        d.name
        for d in runtime.get_tool_definitions(
            as_meeting_phase=as_meeting_phase,
            for_every_player=True,
        )
    }


class TestScenariosWithoutTheDeclaration:
    """宣言の無いシナリオには会議が一切出ない。"""

    def test_no_meeting_tool_is_exposed(self) -> None:
        """自由時間の tool 一覧に会議系が出ない。

        ここが本 PR の主眼。#874 前のプロンプトに戻す。
        """
        assert not (_MEETING_TOOLS & _tool_names(_WITHOUT_MEETING))

    def test_not_even_when_asked_as_the_meeting_phase(self) -> None:
        """会議フェーズとして訊いても出ない。

        起動時の dispatch 整合検査がこの口を使う。ここで出てしまうと、
        会議を持たないシナリオでも handler の有無を問われることになる。
        """
        assert not (
            _MEETING_TOOLS & _tool_names(_WITHOUT_MEETING, as_meeting_phase=True)
        )

    def test_the_toolset_matches_what_it_was_before_the_meeting_work(self) -> None:
        """会議の実装が入る前と同じ tool 一覧に戻っている。

        「会議系が出ない」だけだと、別の理由で増減していても気付けない。
        比較実験の土台なので、集合そのものを固定する。
        """
        expected = {
            "travel_to", "set_sub_location", "explore", "interact",
            "use_item", "drop_item", "pickup_item", "give_item",
            "attack", "listen", "wait", "tend_to_player", "speak",
            "memo_add", "memo_list", "memo_done",
        }

        assert _tool_names(_WITHOUT_MEETING) == expected


class TestScenariosWithTheDeclaration:
    """宣言のあるシナリオでは従来どおり会議が使える。"""

    def test_reporting_is_available(self) -> None:
        """自由時間に report_body が出る。"""
        assert "report_body" in _tool_names(_WITH_MEETING)

    def test_voting_is_available_during_a_meeting(self) -> None:
        """会議フェーズでは vote が出る。"""
        assert "vote" in _tool_names(_WITH_MEETING, as_meeting_phase=True)


class TestTheRuntimeRefusesWhenNotDeclared:
    """露出を絞るだけに頼らない。"""

    @pytest.fixture()
    def runtime(self):
        return create_world_runtime(_WITHOUT_MEETING)

    def test_calling_an_emergency_meeting_is_refused(self, runtime) -> None:
        """宣言の無い世界で緊急招集を呼んでも始まらない。

        tool から外すのは露出の制御であって防御ではない (設計 doc H-6)。
        ここが素通りすると、会議を想定していない世界で全員が 1 箇所に
        テレポートさせられる。
        """
        from ai_rpg_world.domain.player.value_object.player_id import PlayerId

        result = runtime.call_emergency_meeting(PlayerId(1))

        assert result.success is False
        assert result.error_code == "MEETING_NOT_AVAILABLE"

    def test_reporting_a_body_is_refused(self, runtime) -> None:
        """死体の報告も同じく弾かれる。

        **理由まで見る。** 「相手が倒れていない」でも success=False になる
        ので、成否だけ見ると宣言のガードを外しても通ってしまう。
        """
        from ai_rpg_world.domain.player.value_object.player_id import PlayerId

        result = runtime.report_body(PlayerId(1), PlayerId(2))

        assert result.error_code == "MEETING_NOT_AVAILABLE"

    def test_voting_is_refused(self, runtime) -> None:
        """投票も弾かれる。

        こちらも「会議中でない」で弾かれるため、理由まで確かめないと
        ガードの有無を区別できない。
        """
        from ai_rpg_world.domain.player.value_object.player_id import PlayerId

        result = runtime.cast_vote(PlayerId(1), PlayerId(2))

        assert result.error_code == "MEETING_NOT_AVAILABLE"
