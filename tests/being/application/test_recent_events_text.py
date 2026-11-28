"""Being の短期記憶から、毎ターンのプロンプトの【直近の出来事】の本文を作る規則を保証する (#1824、design_decisions D1824-10、#2345)。"""

from __future__ import annotations

from ai_rpg_world.being.application.recent_events_text import NO_RECENT_EVENTS, recent_events_text
from ai_rpg_world.being.contract import (
    UNKNOWN,
    ActionTaken,
    AgentMove,
    Observation,
    ObservedTime,
    OccurrenceOrder,
    OwnAction,
    SeenOrHeard,
)
from ai_rpg_world.being.domain.being_id import BeingId
from ai_rpg_world.being.domain.old_world_preformatted_line import OldWorldPreformattedLine
from ai_rpg_world.being.domain.short_term_memory import AttemptTaken, ShortTermMemory

ADA = BeingId("being_p1")
_MORNING = ObservedTime(display="1日目 朝")
_VILLAGE = "廃坑の山村"


def _observation(
    body: str, *, display: str = "1日目 朝", route: object = SeenOrHeard(), order: OccurrenceOrder | None = None
) -> Observation:
    return Observation(
        body=body,
        route=route,
        time=ObservedTime(display=display),
        subject_is_self=isinstance(route, OwnAction),
        subject_name=UNKNOWN,
        source=UNKNOWN,
        place=UNKNOWN,
        addressed_to_self=UNKNOWN,
        order=order,
    )


def _move(call_id: str, *, inner_thought: str | None = None) -> AgentMove:
    return AgentMove(call_id=call_id, tool_name="interact", arguments={}, inner_thought=inner_thought)


def _at(value: float) -> OccurrenceOrder:
    return OccurrenceOrder(environment=_VILLAGE, value=value)


def _take(
    memory: ShortTermMemory,
    call_id: str,
    summary: str | None,
    *,
    turn: int,
    accepted: bool = True,
    noticed: str | None = None,
    order: OccurrenceOrder | None = None,
    inner_thought: str | None = None,
    call_text: str | None = None,
    memo_rejections: tuple[str, ...] = (),
) -> None:
    memory.act(
        _move(call_id, inner_thought=inner_thought),
        current_turn=turn,
        call_text=call_text,
        memo_rejections=memo_rejections,
    )
    memory.receive_response(
        AttemptTaken(
            ActionTaken(call_id=call_id, action_summary=summary, accepted=accepted, time=_MORNING, order=order)
        ),
        current_turn=turn,
    )
    if noticed is not None:
        memory.perceive(_observation(noticed, route=OwnAction(), order=order), current_turn=turn)


class TestRecentEventsText:
    """recent_events_text が、自分の行動を「[行動] 要約」の行で、ほかは観測の 1 行で出すことを保証する。"""

    def test_empty_memory_shows_the_placeholder(self) -> None:
        """出来事が 1 つも無ければ、今のプロンプトと同じ「（直近の出来事はありません）」になる。"""
        assert recent_events_text(ShortTermMemory.empty(ADA)) == NO_RECENT_EVENTS == "（直近の出来事はありません）"

    def test_perception_is_a_line_with_its_time(self) -> None:
        """見聞きしたことは「- [時刻] 本文」の 1 行になる。"""
        memory = ShortTermMemory.empty(ADA)
        memory.perceive(_observation("ミオが坑道から戻ってきた"), current_turn=0)

        assert recent_events_text(memory) == "- [1日目 朝] ミオが坑道から戻ってきた"

    def test_speaking_shows_only_the_action_line_when_nothing_is_noticed(self) -> None:
        """話す 1 手に、本人が知った観測が無ければ、「[行動] 要約」と呼び出しの行だけが出て、[結果] は出ない。"""
        memory = ShortTermMemory.empty(ADA)

        _take(
            memory,
            "call-1",
            "あなたは言った: 「ふむ」",
            turn=1,
            call_text='speak(reach="ふつうの声で話す", content=本文)',
        )

        assert recent_events_text(memory) == (
            '- [1日目 朝] [行動] あなたは言った: 「ふむ」\n  呼び出し: speak(reach="ふつうの声で話す", content=本文)'
        )

    def test_accepted_move_lists_call_thought_and_memos_then_what_was_noticed(self) -> None:
        """通った 1 手は「[行動] 要約」の行に、呼び出し・心の声・メモの順で続き行が付き、本人が知った観測が同じ時刻の次の行に出る。"""
        memory = ShortTermMemory.empty(ADA)

        _take(
            memory,
            "call-1",
            "「事務机」で引き出しを探る",
            turn=1,
            noticed="引き出しの奥に、黄ばんだ紙切れが挟まっていた。",
            order=_at(2.0),
            inner_thought="番号の手がかりを探す",
            call_text='interact(target="事務机", how="引き出しを探る")',
            memo_rejections=("「m_3f2a7b を消す」は書けなかった（理由: そのメモはない）",),
        )

        assert recent_events_text(memory) == (
            "- [1日目 朝] [行動] 「事務机」で引き出しを探る\n"
            '  呼び出し: interact(target="事務机", how="引き出しを探る")\n'
            "  心の声: 番号の手がかりを探す\n"
            "  メモ: 「m_3f2a7b を消す」は書けなかった（理由: そのメモはない）\n"
            "- [1日目 朝] 引き出しの奥に、黄ばんだ紙切れが挟まっていた。"
        )

    def test_refused_move_has_no_call_line_and_the_refusal_follows_as_an_observation(self) -> None:
        """断られた 1 手は呼び出しの行が付かず、断られたことが観測として行動のすぐ後に出る。[失敗] は出ない。"""
        memory = ShortTermMemory.empty(ADA)

        _take(
            memory,
            "call-1",
            "「金庫」で番号を合わせて金庫を開ける",
            turn=1,
            accepted=False,
            noticed="ダイヤルを合わせて把手を引いたが、扉はびくともしない。",
            order=_at(1.0),
            call_text='interact(target="金庫", how="番号を合わせて金庫を開ける", details=本文)',
        )

        assert recent_events_text(memory) == (
            "- [1日目 朝] [行動] 「金庫」で番号を合わせて金庫を開ける\n"
            "- [1日目 朝] ダイヤルを合わせて把手を引いたが、扉はびくともしない。"
        )

    def test_move_without_a_summary_shows_only_the_action_marker(self) -> None:
        """環境が要約を組み立てられなかった 1 手は「[行動]」だけの行に、呼び出しと心の声の続き行が付く。"""
        memory = ShortTermMemory.empty(ADA)

        _take(memory, "call-1", None, turn=1, inner_thought="渡す", call_text='give_item(item="鍵")')

        assert recent_events_text(memory) == '- [1日目 朝] [行動]\n  呼び出し: give_item(item="鍵")\n  心の声: 渡す'

    def test_arrival_is_a_single_observation_without_a_call_line(self) -> None:
        """移動先に着いたこと (経路 OwnAction の観測) は 1 行の観測で出て、「呼び出し: travel_to()」は出ない。"""
        memory = ShortTermMemory.empty(ADA)

        memory.perceive(_observation("「鉱山会社の事務所」に着いた。", route=OwnAction()), current_turn=1)

        assert recent_events_text(memory) == "- [1日目 朝] 「鉱山会社の事務所」に着いた。"

    def test_old_world_line_keeps_its_preformatted_body_and_the_inner_thought(self) -> None:
        """古い世界が組み終えた行は、本文をそのまま行にし、心の声とメモの続き行が付く。古い世界のプロンプトは変わらない。"""
        memory = ShortTermMemory.empty(ADA)
        memory.act(
            _move("call-1", inner_thought="灯りをつける"),
            current_turn=1,
            memo_rejections=("「m_3f2a7b を消す」は書けなかった（理由: そのメモはない）",),
        )
        memory.receive_response(
            OldWorldPreformattedLine(
                call_id="call-1", body="[行動] 灯した → [結果] カンテラに火を入れた。", time=_MORNING
            ),
            current_turn=1,
        )

        assert recent_events_text(memory) == (
            "- [1日目 朝] [行動] 灯した → [結果] カンテラに火を入れた。\n  心の声: 灯りをつける\n"
            "  メモ: 「m_3f2a7b を消す」は書けなかった（理由: そのメモはない）"
        )

    def test_lapse_is_a_line_without_inner_thought(self) -> None:
        """1 手を出せなかったことは「- [時刻] 本文」の 1 行になる。"""
        memory = ShortTermMemory.empty(ADA)
        memory.lapse(
            body="[行動] 迷い → [失敗] | 決められなかった", time=ObservedTime(display="1日目 夜"), current_turn=1
        )

        assert recent_events_text(memory) == "- [1日目 夜] [行動] 迷い → [失敗] | 決められなかった"

    def test_attempt_without_response_is_not_shown(self) -> None:
        """返事の無い試みは行にしない。今のプロンプトには、返事の無い 1 手の行が無いため。"""
        memory = ShortTermMemory.empty(ADA)
        memory.act(_move("call-1"), current_turn=1)
        memory.perceive(_observation("鐘が鳴った"), current_turn=1)
        memory.act(_move("call-2"), current_turn=2)

        assert recent_events_text(memory) == "- [1日目 朝] 鐘が鳴った"

    def test_only_unanswered_attempts_show_the_placeholder(self) -> None:
        """出来事が返事の無い試みだけなら、行が無いので「（直近の出来事はありません）」になる。"""
        memory = ShortTermMemory.empty(ADA)
        memory.act(_move("call-1"), current_turn=1)
        memory.act(_move("call-2"), current_turn=2)

        assert recent_events_text(memory) == NO_RECENT_EVENTS

    def test_others_and_own_observations_follow_the_occurrence_order(self) -> None:
        """同じ環境で先に起きた他人の行動は自分の行動より前に、後に起きた他人の行動は本人が知った観測より後に並ぶ。"""
        memory = ShortTermMemory.empty(ADA)
        memory.perceive(_observation("ゲンが周囲を探索している", order=_at(10.0)), current_turn=4)
        _take(memory, "call-1", "「扉」を蹴った", turn=5, noticed="扉は開かなかった。", order=_at(20.0))
        memory.perceive(_observation("サヨが「大丈夫？」と言った", order=_at(30.0)), current_turn=5)

        assert recent_events_text(memory) == (
            "- [1日目 朝] ゲンが周囲を探索している\n"
            "- [1日目 朝] [行動] 「扉」を蹴った\n"
            "- [1日目 朝] 扉は開かなかった。\n"
            "- [1日目 朝] サヨが「大丈夫？」と言った"
        )
