"""会議中は、会議でできることだけを tool として出すことを保証する。

会議と投票 (docs/memory_system/meeting_and_voting_design.md) の PR 3。

## なぜ tool を外すのか (前提条件で弾くのではなく)

全 interaction に「会議中は不可」を書いて回ると、宣言の重複がシナリオ中に
散らばる。しかも LLM から見て「選べるのに必ず失敗する手」が並ぶことになり、
#860 で潰した「使えない候補を試し続ける」形をそのまま再生産する。

## prefix cache との関係

`design_decisions.md` #1 が禁じているのは「毎 tick 変わる動的注入」で、
フェーズ境界でだけ変わるのは対象外である (コストの判断であって正しさの
判断ではない)。そのうえで被害を抑えるため、**全フェーズ共通の tool を先に
置く**。会議で落ちるのは後ろのブロックだけになり、先頭の共通部分は
キャッシュに残る (reason-first が `assess_situation` を末尾に置いたのと
同じ技法)。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from ai_rpg_world.application.world_runtime.world_runtime import create_world_runtime
from ai_rpg_world.domain.player.value_object.player_id import PlayerId

_SCENARIO = (
    Path(__file__).resolve().parents[3] / "tests" / "fixtures" / "scenarios" / "darkened_station.json"
)

_KUZE = PlayerId(3)

#: 会議中でも使える tool。話す・聞く・待つと、手当てと、記憶系。
#:
#: tend_to_player が入っているのは #864 のマージ後レビューの結果。倒れて
#: いる相手を報告すると全員がその場所に集まるのに、手当てだけできない
#: 状態だった (test_meeting_does_not_outlive_rescue.py を参照)。
_MEETING_ALLOWED = {"speak", "listen", "wait", "tend_to_player"}

#: 会議中は出さない tool (物理的な行為)。
_FREE_ROAM_ONLY = {
    "travel_to", "set_sub_location", "explore", "interact",
    "use_item", "drop_item", "pickup_item", "give_item",
    "attack", "report_body",
}

#: 会議中は出さないが、**シナリオが宣言したときだけ**出る tool。
#:
#: このシナリオには同時行動の宣言も商人の宣言も無いので自由時間でも並ばない。
#: 売買は会議中に出さない (その場で選べない対象は並べない規約)。
#: 「自由時間には必ず出る」の集合とは分けておかないと、シナリオを
#: 差し替えたときに落ちる。分類の網羅だけがこちらを見る。
_FREE_ROAM_ONLY_WHEN_DECLARED = {
    "prepare_action",
    "buy_item",
    "sell_item",
    # 人同士の取引も、宣言した世界の自由時間にだけ出る。
    "trade_offer",
    "trade_accept",
    "trade_decline",
    # 市場も、板を宣言した世界の自由時間にだけ出る。会議中に板を触れると、
    # 議論の場から抜けて売り買いを始められてしまう。
    "market_list_item",
    "market_view",
    "market_buy",
    "market_reprice",
    "market_cancel",
    "market_bid",
    "market_sell",
}


@pytest.fixture()
def runtime():
    return create_world_runtime(_SCENARIO)


def _tool_names(runtime) -> list[str]:
    return [d.name for d in runtime.get_tool_definitions(for_every_player=True)]


class TestFreeRoamOffersEverything:
    """自由時間の tool 一覧は従来どおり。"""

    def test_movement_and_interaction_are_available(self, runtime) -> None:
        """移動や interact が出る。"""
        names = set(_tool_names(runtime))
        assert _FREE_ROAM_ONLY <= names

    def test_speaking_is_available(self, runtime) -> None:
        """話す手段も当然ある。"""
        assert _MEETING_ALLOWED <= set(_tool_names(runtime))


class TestMeetingNarrowsTheToolset:
    """会議中は物理的な行為の tool が消える。"""

    def test_movement_is_gone(self, runtime) -> None:
        """会議中に移動できない。

        前提条件で弾くのではなく、そもそも選択肢に出さない。
        """
        runtime.begin_meeting(initiator_player_id=_KUZE, trigger="emergency_button")

        assert not (_FREE_ROAM_ONLY & set(_tool_names(runtime)))

    def test_speaking_remains(self, runtime) -> None:
        """話す手段は残る (これが無いと会議が成立しない)。"""
        runtime.begin_meeting(initiator_player_id=_KUZE, trigger="emergency_button")

        assert _MEETING_ALLOWED <= set(_tool_names(runtime))

    def test_ending_the_meeting_restores_the_toolset(self, runtime) -> None:
        """会議が終われば元に戻る。"""
        runtime.begin_meeting(initiator_player_id=_KUZE, trigger="emergency_button")
        runtime.end_meeting(reason="vote_concluded")

        assert _FREE_ROAM_ONLY <= set(_tool_names(runtime))


class TestCommonToolsComeFirst:
    """共通 tool を先に置き、フェーズで落ちるぶんを後ろに寄せる。"""

    def test_meeting_toolset_is_a_prefix_of_free_roam_up_to_the_dropped_block(
        self, runtime
    ) -> None:
        """会議で落ちる tool より前の並びが、両フェーズで一致する。

        ここが崩れると、フェーズが変わるたびに **tool 定義の先頭から**
        prefix cache を捨てることになる。落ちるブロックを後ろへ寄せてある
        ので、先頭の共通部分は再利用できる。
        """
        free_roam = _tool_names(runtime)
        runtime.begin_meeting(initiator_player_id=_KUZE, trigger="emergency_button")
        meeting = _tool_names(runtime)

        first_dropped = next(
            i for i, name in enumerate(free_roam) if name in _FREE_ROAM_ONLY
        )

        assert free_roam[:first_dropped] == meeting[:first_dropped], (
            "会議で落ちる tool より前の並びが一致していない。"
            f"\n free_roam={free_roam}\n meeting={meeting}"
        )

    def test_the_shared_prefix_is_not_trivially_short(self, runtime) -> None:
        """共通の先頭が 1 個や 2 個ではない。

        並べ替えが崩れて共通部分がほぼ無くなっても、上のテストは
        「先頭 0 個が一致」で通ってしまう。実際に意味のある長さを要求する。
        """
        free_roam = _tool_names(runtime)
        first_dropped = next(
            i for i, name in enumerate(free_roam) if name in _FREE_ROAM_ONLY
        )

        assert first_dropped >= len(_MEETING_ALLOWED), (
            f"共通の先頭が短すぎる: {free_roam[:first_dropped]}"
        )


class TestPrefixIsStableWithinAPhase:
    """同じフェーズの間は tool 一覧が変わらない。

    `design_decisions.md` #1 が本当に禁じているのはこちら (毎 tick 変わる
    動的注入)。フェーズ境界での変化は許容するが、フェーズ内で揺れては
    いけない。
    """

    def test_repeated_calls_return_the_same_list(self, runtime) -> None:
        """同じフェーズで 2 回呼んでも完全に同じ並び。"""
        assert _tool_names(runtime) == _tool_names(runtime)

    def test_stable_during_a_meeting_too(self, runtime) -> None:
        """会議中も同じ。"""
        runtime.begin_meeting(initiator_player_id=_KUZE, trigger="emergency_button")

        assert _tool_names(runtime) == _tool_names(runtime)


class TestReasonFirstCombinedWithMeeting:
    """reason_first と会議を組み合わせても壊れない。

    **この組み合わせで一度バグを出している。** フェーズ分割を
    `strip_reason_first_action_subjective_schema` より前に置いたため strip の
    結果が捨てられ、未 strip の定義がそのまま返っていた。既存の contract
    テストが捕まえたが、フェーズ側のテストには無かったので回帰を固定する。
    """

    def _names(self, runtime) -> list[str]:
        return [
            d.name
            for d in runtime.get_tool_definitions(
                tool_schema_mode="reason_first",
                for_every_player=True,
            )
        ]

    def test_assessment_tool_stays_last_during_a_meeting(self, runtime) -> None:
        """会議中でも assess_situation が末尾のまま。

        action_phase は「末尾の評価 tool だけを落とす」ので、位置が動くと
        その前提が崩れる。
        """
        runtime.begin_meeting(initiator_player_id=_KUZE, trigger="emergency_button")

        assert self._names(runtime)[-1] == "assess_situation"

    def test_action_tools_are_still_stripped_during_a_meeting(self, runtime) -> None:
        """会議中に残る行動 tool からも inner_thought が外れている。

        strip を通らない経路ができると、step1 が所有するはずの
        inner_thought を step2 の行動 tool が再生成し、reason-first が
        解いたはずのループが戻る。
        """
        runtime.begin_meeting(initiator_player_id=_KUZE, trigger="emergency_button")

        speak = next(
            d
            for d in runtime.get_tool_definitions(
                tool_schema_mode="reason_first",
                for_every_player=True,
            )
            if d.name == "speak"
        )
        assert "inner_thought" not in speak.parameters["properties"]

    def test_meeting_drops_the_same_tools_in_both_modes(self, runtime) -> None:
        """落ちる tool の集合が schema mode で変わらない。

        フェーズの絞り込みは schema mode と直交している。片方だけ絞られる
        状態になると、reason_first の run でだけ会議中に移動できてしまう。
        """
        runtime.begin_meeting(initiator_player_id=_KUZE, trigger="emergency_button")

        legacy = set(_tool_names(runtime))
        reason_first = set(self._names(runtime))

        assert not (_FREE_ROAM_ONLY & legacy)
        assert not (_FREE_ROAM_ONLY & reason_first)


class TestVoteIsMeetingOnly:
    """投票 tool は会議中だけ出る。

    自由時間に並ぶと「いつでも投票できる」と読め、会議の外で試して失敗し
    続ける (#860 で潰した形)。逆に会議中に出ないと、話し合いが決着しない。
    """

    def test_absent_during_free_roam(self, runtime) -> None:
        """自由時間には出ない。"""
        assert "vote" not in _tool_names(runtime)

    def test_present_during_a_meeting(self, runtime) -> None:
        """会議中には出る。"""
        runtime.begin_meeting(initiator_player_id=_KUZE, trigger="emergency_button")

        assert "vote" in _tool_names(runtime)

    def test_gone_again_after_the_meeting(self, runtime) -> None:
        """会議が終われば消える。"""
        runtime.begin_meeting(initiator_player_id=_KUZE, trigger="emergency_button")
        runtime.end_meeting(reason="vote_concluded")

        assert "vote" not in _tool_names(runtime)


class TestEveryToolIsExplicitlyClassified:
    """すべての spot tool が、3 分類のどれかに明示的に入っている。

    実装の free_roam_only は「共通でも会議専用でもないもの全部」という
    引き算で決まる。放っておくと、**今後追加される tool は自動的に会議中は
    非露出になる**。安全側ではあるが、「会議でも使えるべき tool」を足した
    人が気づけない。分類の宣言を強制して、足した人が必ず判断するようにする
    (#859 と同じ形)。
    """

    def test_no_tool_is_left_unclassified(self) -> None:
        """3 分類のどれにも入っていない tool は無い。

        落ちたら、増やした tool を _MEETING_ALLOWED か _FREE_ROAM_ONLY の
        どちらかに書き足す。**どちらでもよいから片方に書く**のではなく、
        会議中にその手を使わせるべきかを決めてから書く。
        """
        from ai_rpg_world.application.llm.services.tool_catalog.spot_graph import (
            get_spot_graph_specs,
        )

        exposed = {defn.name for defn, _ in get_spot_graph_specs()}
        classified = (
            _MEETING_ALLOWED
            | _FREE_ROAM_ONLY
            | _FREE_ROAM_ONLY_WHEN_DECLARED
            | {"vote"}
        )

        assert not (exposed - classified)

    def test_the_classification_does_not_name_tools_that_vanished(self) -> None:
        """消えた tool 名が分類に残り続けない。

        残っていると、分類表を読んだ人が「会議中も使える」と誤解する。
        """
        from ai_rpg_world.application.llm.services.tool_catalog.spot_graph import (
            get_spot_graph_specs,
        )

        exposed = {defn.name for defn, _ in get_spot_graph_specs()}
        classified = (
            _MEETING_ALLOWED
            | _FREE_ROAM_ONLY
            | _FREE_ROAM_ONLY_WHEN_DECLARED
            | {"vote"}
        )

        assert not (classified - exposed)
