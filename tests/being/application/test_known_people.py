from __future__ import annotations

from ai_rpg_world.being.application.known_people import render_known_people
from ai_rpg_world.being.domain.acquaintance import Acquaintance


def _introduced(name: str, note: str | None = None, *, env: str = "山村") -> Acquaintance:
    return Acquaintance.introduced(environment_name=env, name=name, turn=0, relation_note=note)


class TestRenderKnownPeople:
    """render_known_people が、いまの環境で知っている相手を、知った順に名前と関係の注記で描くことを保証する。"""

    def test_people_are_listed_in_known_order_with_notes(self) -> None:
        """知った順に 1 行ずつ「- 名前」で並べ、関係の注記がある相手だけ「（注記）」を付ける。"""
        text = render_known_people(
            [_introduced("ノア", "あなたと同じ側"), _introduced("カイ")],
            environment_name="山村",
        )

        assert text == "- ノア（あなたと同じ側）\n- カイ"

    def test_people_of_other_environments_are_not_listed(self) -> None:
        """別の環境で知った相手は、いまの環境の一覧に出さない。"""
        text = render_known_people(
            [_introduced("ノア", env="島"), _introduced("カイ")],
            environment_name="山村",
        )

        assert text == "- カイ"

    def test_meeting_counts_do_not_change_the_text(self) -> None:
        """会った回数や会ったターンが変わっても描いた文は変わらない。会うたびに節が書き換わると、そこから後ろのキャッシュが切れる。"""
        known = _introduced("ノア")

        before = render_known_people([known], environment_name="山村")
        after = render_known_people([known.met_at(turn=3).met_at(turn=9)], environment_name="山村")

        assert before == after

    def test_nobody_known_renders_empty(self) -> None:
        """いまの環境で誰も知らなければ空文字を返す。"""
        assert render_known_people([], environment_name="山村") == ""

    def test_people_whose_names_are_unknown_are_not_listed(self) -> None:
        """名前を知らずに会った相手は【知っている人】に並べず、名前を知ったあとは知った順の末尾に名前で並べる (#1581)。"""
        stranger = Acquaintance.first_meeting(environment_name="山村", name="ノア", turn=1, knows_name=False)

        before = render_known_people([_introduced("カイ"), stranger], environment_name="山村")
        after = render_known_people([_introduced("カイ"), stranger.learned_name(turn=2)], environment_name="山村")

        assert (before, after) == ("- カイ", "- カイ\n- ノア")
