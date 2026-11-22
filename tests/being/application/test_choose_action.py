from __future__ import annotations

import pytest

from ai_rpg_world.being.application.choose_action import (
    ActionChoosingReply,
    ActionChosen,
    ActionNotChosen,
    ChooseAction,
    ChooseActionCommand,
    ToolCallReply,
    TurnSpentRecalling,
)
from ai_rpg_world.being.application.current_working_memory import CurrentWorkingMemory
from ai_rpg_world.being.application.receive_action_result import ReceiveActionResult, ReceiveActionResultCommand
from ai_rpg_world.being.contract import (
    UNKNOWN,
    ActionChoice,
    ActionChoices,
    ArgumentOutline,
    Candidate,
    Description,
    FreeText,
    Observation,
    ObservedTime,
    OfferedBeingTools,
    Orientation,
    OwnActionResult,
    PersonInText,
    PickOne,
    Scene,
)
from ai_rpg_world.being.domain.being import Being
from ai_rpg_world.being.domain.being_attachment import BeingAttachment
from ai_rpg_world.being.domain.being_id import BeingId
from ai_rpg_world.being.domain.episode import Episode, EpisodeIndex, EpisodeRepository
from ai_rpg_world.being.domain.memo_book import MemoBook, MemoBookRepository, MemoKind
from ai_rpg_world.being.domain.persona import Persona
from ai_rpg_world.being.domain.short_term_memory import (
    Attempt,
    MemoryOperationOutcome,
    ObservedOutcome,
    ShortTermMemory,
    ShortTermMemoryRepository,
)
from ai_rpg_world.being.domain.working_memory import Closing
from ai_rpg_world.being.infrastructure.in_memory_acquaintance_repository import InMemoryAcquaintanceRepository
from ai_rpg_world.being.infrastructure.in_memory_episode_repository import InMemoryEpisodeRepository
from ai_rpg_world.being.infrastructure.in_memory_memo_book_repository import InMemoryMemoBookRepository
from ai_rpg_world.being.infrastructure.in_memory_memory_turn_clock import InMemoryMemoryTurnClock
from ai_rpg_world.being.infrastructure.in_memory_short_term_memory_repository import (
    InMemoryShortTermMemoryRepository,
)
from ai_rpg_world.being.infrastructure.scripted_action_choosing import ScriptedActionChoosing
from tests.event_handoff_helpers import discard_events

GEN = BeingId("being_gen")
SAYO = PersonInText(handle=2, appearance="綿入れを着込んだ若い娘", visible_name="サヨ")
NOW = ObservedTime(display="1日目 9:00")
WITH_MEMORY = OfferedBeingTools(
    inner_thought="inner_thought", memo="memo", episode_recall="episode_recall", episode_index_shown=True
)


class _Beings:
    def find_by_id(self, being_id: BeingId) -> Being | None:
        attachment = BeingAttachment(environment_id="mine_village_v2#1", environment_name="廃坑の山村")
        return Being(being_id=GEN, persona=Persona(name="ゲン"), attachment=attachment)


def _choices() -> ActionChoices:
    code = FreeText(name="code", label="番号")
    content = FreeText(name="content", label="中身")
    safe = Candidate(
        label="金庫",
        values=(
            PickOne(name="how", label="操作", candidates=(Candidate(label="番号を合わせて開ける", values=(code,)),)),
        ),
    )
    whisper = PickOne(name="to", label="相手", candidates=(Candidate(label=SAYO, values=(content,)),))
    return ActionChoices(
        (
            ActionChoice(
                name="interact",
                label="操作する",
                outline=(
                    ArgumentOutline(name="target", label="相手", required=True),
                    ArgumentOutline(name="how", label="操作"),
                ),
                takes_details=True,
                values=(PickOne(name="target", label="相手", candidates=(safe,)),),
            ),
            ActionChoice(
                name="speak",
                label="話す",
                outline=(
                    ArgumentOutline(name="reach", label="届け方", required=True),
                    ArgumentOutline(name="to", label="相手"),
                    ArgumentOutline(name="content", label="中身"),
                ),
                values=(
                    PickOne(name="reach", label="届け方", candidates=(Candidate(label="ささやく", values=(whisper,)),)),
                ),
            ),
            ActionChoice(
                name="pickup_item",
                label="拾う",
                outline=(ArgumentOutline(name="item", label="品物", required=True),),
                values=(PickOne(name="item", label="品物", candidates=()),),
            ),
        )
    )


def _command(being_tools: OfferedBeingTools) -> ChooseActionCommand:
    return ChooseActionCommand(
        being_id=GEN,
        orientation=Orientation([Description(heading="ペルソナ", text="あなたはゲン。")]),
        being_tools=being_tools,
        imposed_goal="金庫の中を確かめる",
        scene=Scene([Description(heading="現在地と周囲", text="事務所")]),
        closing=Closing(instruction="行動を 1 つ選んでください。"),
        choices=_choices(),
        now=NOW,
    )


def _reply(name: str, arguments: dict[str, object], *, call_id: str = "call_1") -> ActionChoosingReply:
    return ActionChoosingReply(tool_call=ToolCallReply(tool_name=name, arguments=arguments, call_id=call_id))


CUT_OFF = ActionChoosingReply(tool_call=None, cut_off_while_reasoning=True)


class _FailingToSaveMemo(InMemoryMemoBookRepository):
    def save(self, book: MemoBook) -> None:
        raise OSError("disk is full")


class _FailingToSave(InMemoryShortTermMemoryRepository):
    def save(self, memory: ShortTermMemory) -> None:
        raise OSError("disk is full")


def _choose(
    *replies: ActionChoosingReply,
    memories: ShortTermMemoryRepository | None = None,
    clock: InMemoryMemoryTurnClock | None = None,
    being_tools: OfferedBeingTools = OfferedBeingTools(inner_thought="inner_thought"),
    episodes: EpisodeRepository | None = None,
    memo_books: MemoBookRepository | None = None,
) -> tuple[ActionChosen | ActionNotChosen | TurnSpentRecalling, ScriptedActionChoosing]:
    short_term_memories = memories or InMemoryShortTermMemoryRepository()
    clock = clock or InMemoryMemoryTurnClock()
    episodes = episodes or InMemoryEpisodeRepository(handoff=discard_events)
    memo_books = memo_books or InMemoryMemoBookRepository(handoff=discard_events)
    completion = ScriptedActionChoosing(replies)
    working_memory = CurrentWorkingMemory(
        beings=_Beings(),
        short_term_memories=short_term_memories,
        acquaintances=InMemoryAcquaintanceRepository(),
        episodes=episodes,
        memo_books=memo_books,
        episode_index_limit=5,
    )
    choose = ChooseAction(
        working_memory=working_memory,
        completion=completion,
        short_term_memories=short_term_memories,
        turn_clock=clock,
        beings=_Beings(),
        memo_books=memo_books,
        episodes=episodes,
        recall_limit=2,
    )
    return choose.execute(_command(being_tools)), completion


def _episodes_with_the_safe_story() -> tuple[EpisodeRepository, str]:
    episodes = InMemoryEpisodeRepository(handoff=discard_events)
    episode = Episode.write(
        being_id=GEN,
        episode_id="3f2a7b00-0000-4000-8000-00000000abcd",
        environment_name="廃坑の山村",
        written_turn=1,
        index=EpisodeIndex(summary="親方が金庫の番号を口にした", recall_when="金庫の話が出たとき"),
        body="親方は酔って、金庫は 1907 で開くと言った。",
    )
    episodes.add(episode)
    return episodes, episode.handle


class TestChooseAction:
    """ChooseAction が、作業記憶と行動の選択肢から LLM に行動を選ばせ、選んだ行動を返して試みとして残すことを保証する。"""

    def test_opening_the_safe_with_1907_returns_the_move(self) -> None:
        """スタブの LLM が「金庫 / 番号を合わせて開ける / 1907」を選ぶと、details を外して平らにした AgentMove が返る。"""
        outcome, _ = _choose(
            _reply(
                "interact",
                {
                    "target": "金庫",
                    "how": "番号を合わせて開ける",
                    "details": {"code": "1907"},
                    "inner_thought": "あの番号を試す",
                },
            )
        )

        assert isinstance(outcome, ActionChosen)
        assert outcome.move.tool_name == "interact"
        assert dict(outcome.move.arguments) == {"target": "金庫", "how": "番号を合わせて開ける", "code": "1907"}
        assert outcome.move.inner_thought == "あの番号を試す"

    def test_llm_sees_the_tools_and_the_candidate_table(self) -> None:
        """LLM には、行動の種類ごとのツールと、場面の後ろに【行動の候補】を置いたメッセージが渡る。"""
        _, completion = _choose(_reply("interact", {"target": "金庫", "how": "番号を合わせて開ける"}))

        [call] = completion.calls
        assert [t["function"]["name"] for t in call.tools] == ["interact", "speak", "pickup_item"]
        assert "【行動の候補】" in call.messages[1]["content"]
        assert call.messages[0]["role"] == "system" and not call.reasoning_off

    def test_whisper_to_sayo_returns_her_mark_not_her_name(self) -> None:
        """サヨへのささやきは、呼び方「サヨ」ではなく人の印 {"person": 2} で返り、中身の文字はそのまま返る。"""
        outcome, _ = _choose(_reply("speak", {"reach": "ささやく", "to": "サヨ", "content": "サヨ、番号を知ってる？"}))

        assert isinstance(outcome, ActionChosen)
        assert dict(outcome.move.arguments) == {
            "reach": "ささやく",
            "to": {"person": 2},
            "content": "サヨ、番号を知ってる？",
        }

    def test_chosen_move_is_kept_as_an_attempt_awaiting_its_result(self) -> None:
        """選んだ行動は、結果を待つ試みとして短期記憶に残る。"""
        memories = InMemoryShortTermMemoryRepository()

        outcome, _ = _choose(_reply("interact", {"target": "金庫", "how": "番号を合わせて開ける"}), memories=memories)

        [attempt] = memories.get(GEN).unsummarized()
        assert isinstance(attempt, Attempt) and isinstance(outcome, ActionChosen)
        assert attempt.move == outcome.move and not attempt.is_answered()

    def test_choosing_a_move_advances_the_memory_turn(self) -> None:
        """行動を選ぶと記憶のターンが 1 進み、ツールを呼ばなかったときは進まない。"""
        clock = InMemoryMemoryTurnClock()

        _choose(_reply("interact", {"target": "金庫", "how": "番号を合わせて開ける"}), clock=clock)
        _choose(ActionChoosingReply(tool_call=None), clock=clock)

        assert clock.current_turn(GEN) == 1

    def test_memory_turn_does_not_advance_when_saving_the_attempt_fails(self) -> None:
        """試みを短期記憶に保存できなければ、記憶のターンは進まない。"""
        clock = InMemoryMemoryTurnClock()

        with pytest.raises(OSError):
            _choose(
                _reply("interact", {"target": "金庫", "how": "番号を合わせて開ける"}),
                memories=_FailingToSave(),
                clock=clock,
            )

        assert clock.current_turn(GEN) == 0

    def test_cut_off_reply_is_asked_again_once_with_reasoning_off(self) -> None:
        """考えが出力の上限で切れて行動が返らなければ、考えを止めて同じメッセージで 1 回だけ呼び直す。"""
        outcome, completion = _choose(CUT_OFF, _reply("interact", {"target": "金庫", "how": "番号を合わせて開ける"}))

        assert isinstance(outcome, ActionChosen)
        assert [c.reasoning_off for c in completion.calls] == [False, True]
        assert completion.calls[0].messages == completion.calls[1].messages

    def test_second_cut_off_is_not_asked_again(self) -> None:
        """呼び直しも切れたら、3 回目は呼ばず、ツールを呼ばなかったこととして選べなかったを返す。"""
        outcome, completion = _choose(CUT_OFF, CUT_OFF)

        assert len(completion.calls) == 2
        assert outcome == ActionNotChosen(requested_tool=None, suggestion=None, exchange=outcome.exchange)

    def test_reply_without_tool_that_was_not_cut_off_is_not_asked_again(self) -> None:
        """出力の上限で切れたのでなければ、ツールを呼ばなくても呼び直さない。"""
        outcome, completion = _choose(ActionChoosingReply(tool_call=None))

        assert isinstance(outcome, ActionNotChosen) and len(completion.calls) == 1

    def test_unknown_tool_is_not_sent_and_suggests_a_close_name(self) -> None:
        """出していないツール名 (pickup) には、出したツールのうち近い名前 (pickup_item) を添えて、選べなかったを返す。"""
        outcome, _ = _choose(_reply("pickup", {"item": "ランプ"}))

        assert isinstance(outcome, ActionNotChosen)
        assert (outcome.requested_tool, outcome.suggestion) == ("pickup", "pickup_item")

    def test_unknown_tool_is_remembered_as_a_failed_attempt(self) -> None:
        """出していないツール名の呼び出しは、試みと、近い名前と使えるツールの一覧を添えた失敗の結果として短期記憶に残る。"""
        memories = InMemoryShortTermMemoryRepository()

        _choose(_reply("pickup", {"item": "ランプ"}, call_id="call_9"), memories=memories)

        [attempt] = memories.get(GEN).unsummarized()
        assert isinstance(attempt, Attempt) and isinstance(attempt.result, ObservedOutcome)
        assert attempt.move.tool_name == "pickup" and attempt.is_answered()
        assert attempt.result.observation.body == (
            "'pickup' というツールは無い。もしかして 'pickup_item' ですか? "
            "いま使えるツール: [interact, speak, pickup_item]"
        )
        assert attempt.result.observation.time == NOW

    def test_unknown_tool_without_a_close_name_is_remembered_without_suggestion(self) -> None:
        """近い名前が無い (gather) ときは、提案を添えず、使えるツールの一覧だけを添えて残す。"""
        memories = InMemoryShortTermMemoryRepository()

        outcome, _ = _choose(_reply("gather", {}), memories=memories)

        [attempt] = memories.get(GEN).unsummarized()
        assert isinstance(outcome, ActionNotChosen) and outcome.suggestion is None
        assert isinstance(attempt, Attempt) and isinstance(attempt.result, ObservedOutcome)
        assert (
            attempt.result.observation.body
            == "'gather' というツールは無い。いま使えるツール: [interact, speak, pickup_item]"
        )


class TestWritingMemoWithTheMove:
    """ChooseAction が、行動と一緒に書かれたメモを、行動を選んだその場でメモ帳に書くことを保証する。"""

    def test_memo_written_with_the_move_goes_into_the_memo_book(self) -> None:
        """「行く」に添えたやることは、今いる環境の名前でメモ帳に入り、世界に渡す行動には残らない。"""
        memo_books = InMemoryMemoBookRepository(handoff=discard_events)
        todo = {"do": "add", "kind": "todo", "text": "事務所で鍵を取る"}

        outcome, _ = _choose(
            _reply("speak", {"reach": "ささやく", "to": "サヨ", "content": "鍵は?", "memo": [todo]}),
            being_tools=WITH_MEMORY,
            memo_books=memo_books,
        )

        [memo] = memo_books.get(GEN).memos
        assert (memo.kind, memo.text, memo.environment_name) == (MemoKind.TODO, "事務所で鍵を取る", "廃坑の山村")
        assert isinstance(outcome, ActionChosen) and "memo" not in outcome.move.arguments

    def test_memo_is_left_alone_when_the_memo_argument_is_not_offered(self) -> None:
        """メモの引数を出していなければ、memo と書かれていてもメモ帳には書かない。"""
        memo_books = InMemoryMemoBookRepository(handoff=discard_events)

        _choose(
            _reply("interact", {"target": "金庫", "memo": [{"do": "add", "kind": "todo", "text": "開ける"}]}),
            memo_books=memo_books,
        )

        assert memo_books.get(GEN).memos == ()

    def test_memo_is_not_written_for_a_tool_that_was_not_offered(self) -> None:
        """出していないツールの呼び出しに添えたメモは書かない。"""
        memo_books = InMemoryMemoBookRepository(handoff=discard_events)

        _choose(
            _reply("pickup", {"memo": [{"do": "add", "kind": "todo", "text": "拾う"}]}),
            being_tools=WITH_MEMORY,
            memo_books=memo_books,
        )

        assert memo_books.get(GEN).memos == ()

    def test_failing_to_write_the_memo_leaves_no_attempt_and_keeps_the_turn(self) -> None:
        """メモ帳に保存できなければ例外が上がり、試みは短期記憶に残らず、記憶のターンも進まない。"""
        memories = InMemoryShortTermMemoryRepository()
        clock = InMemoryMemoryTurnClock()

        with pytest.raises(OSError):
            _choose(
                _reply("interact", {"target": "金庫", "memo": [{"do": "add", "kind": "todo", "text": "開ける"}]}),
                being_tools=WITH_MEMORY,
                memo_books=_FailingToSaveMemo(),
                memories=memories,
                clock=clock,
            )

        assert memories.get(GEN).unsummarized() == () and clock.current_turn(GEN) == 0


class TestHowTheBeingReadsItsOwnMove:
    """ChooseAction が、自分の 1 手を読む見出しと、書けなかったメモの理由を試みに添えることを保証する。"""

    def test_chosen_move_carries_its_heading(self) -> None:
        """金庫を番号で開けると、試みに「操作する: 金庫 / 番号を合わせて開ける (番号: 1907)」の見出しが付く。"""
        memories = InMemoryShortTermMemoryRepository()

        _choose(
            _reply("interact", {"target": "金庫", "how": "番号を合わせて開ける", "details": {"code": "1907"}}),
            memories=memories,
        )

        [attempt] = memories.get(GEN).unsummarized()
        assert isinstance(attempt, Attempt)
        assert attempt.action_heading == "操作する: 金庫 / 番号を合わせて開ける (番号: 1907)"

    def test_memo_operations_that_could_not_be_written_stay_with_the_attempt(self) -> None:
        """書けたメモはメモ帳に入り、書けなかった操作の理由は、配列の位置を添えて試みに残る。"""
        memories = InMemoryShortTermMemoryRepository()
        memo_books = InMemoryMemoBookRepository(handoff=discard_events)
        memo = [{"do": "add", "kind": "todo", "text": "鍵を取る"}, {"do": "remove", "id": "m_3f2a7b"}, {"do": "fly"}]

        _choose(
            _reply("interact", {"target": "金庫", "memo": memo}),
            being_tools=WITH_MEMORY,
            memories=memories,
            memo_books=memo_books,
        )

        [attempt] = memories.get(GEN).unsummarized()
        assert [m.text for m in memo_books.get(GEN).memos] == ["鍵を取る"]
        assert isinstance(attempt, Attempt) and attempt.memo_rejections == (
            "2 件目: m_3f2a7b というメモはありません。",
            "3 件目: do は add / edit / remove のどれかです。",
        )

    def test_recall_reads_as_recalling_the_handles(self) -> None:
        """思い出すツールの試みは「思い出す: 呼び名」の見出しになる。"""
        memories = InMemoryShortTermMemoryRepository()

        _choose(_reply("episode_recall", {"handles": ["ep_ffffff"]}), being_tools=WITH_MEMORY, memories=memories)

        [attempt] = memories.get(GEN).unsummarized()
        assert isinstance(attempt, Attempt) and attempt.action_heading == "思い出す: ep_ffffff"

    def test_unknown_tool_reads_as_its_name(self) -> None:
        """出していないツールの試みは、呼んだツールの名前が見出しになる。"""
        memories = InMemoryShortTermMemoryRepository()

        _choose(_reply("pickup", {"item": "ランプ"}), memories=memories)

        [attempt] = memories.get(GEN).unsummarized()
        assert isinstance(attempt, Attempt) and attempt.action_heading == "pickup"


class TestRecallingEpisodes:
    """ChooseAction が、思い出すツールを選ばれたら世界に行為を渡さず、思い出した本文を自分の 1 手の結果として残すことを保証する。"""

    def test_recalling_spends_the_turn_and_keeps_the_body_as_the_result(self) -> None:
        """金庫の話の呼び名を思い出すと、TurnSpentRecalling が返り、目次と本文が試みの結果として短期記憶に残る。"""
        episodes, handle = _episodes_with_the_safe_story()
        memories = InMemoryShortTermMemoryRepository()

        outcome, _ = _choose(
            _reply("episode_recall", {"handles": [handle]}, call_id="call_r"),
            being_tools=WITH_MEMORY,
            episodes=episodes,
            memories=memories,
        )

        [attempt] = memories.get(GEN).unsummarized()
        assert isinstance(outcome, TurnSpentRecalling) and outcome.move.tool_name == "episode_recall"
        assert isinstance(attempt, Attempt) and isinstance(attempt.result, MemoryOperationOutcome)
        assert (
            attempt.result.body
            == f"[{handle}] 親方が金庫の番号を口にした\n  親方は酔って、金庫は 1907 で開くと言った。"
        )
        assert (attempt.result.call_id, attempt.result.time) == ("call_r", NOW)

    def test_recalling_counts_the_recall_at_the_new_turn(self) -> None:
        """思い出すと、そのエピソードの思い出した回数が 1 増え、記憶のターンが 1 進む。"""
        episodes, handle = _episodes_with_the_safe_story()
        clock = InMemoryMemoryTurnClock()

        _choose(
            _reply("episode_recall", {"handles": [handle]}), being_tools=WITH_MEMORY, episodes=episodes, clock=clock
        )

        recalled = episodes.find_by_handle(GEN, handle)
        assert recalled is not None and (recalled.recall_count, recalled.last_recalled_turn) == (1, 1)
        assert clock.current_turn(GEN) == 1

    def test_unknown_handle_is_answered_as_not_remembered(self) -> None:
        """目次に無い呼び名は、思い出せないと結果に残る。"""
        memories = InMemoryShortTermMemoryRepository()

        _choose(_reply("episode_recall", {"handles": ["ep_ffffff"]}), being_tools=WITH_MEMORY, memories=memories)

        [attempt] = memories.get(GEN).unsummarized()
        assert isinstance(attempt, Attempt) and isinstance(attempt.result, MemoryOperationOutcome)
        assert attempt.result.body == "[ep_ffffff] そのような記憶は思い出せない。"

    def test_more_handles_than_the_limit_recall_nothing(self) -> None:
        """一度に思い出せる件数 (2) を超えて渡すと、どれも思い出さず、件数を減らすよう結果に残る。"""
        episodes, handle = _episodes_with_the_safe_story()
        memories = InMemoryShortTermMemoryRepository()

        _choose(
            _reply("episode_recall", {"handles": [handle, "ep_a", "ep_b"]}),
            being_tools=WITH_MEMORY,
            episodes=episodes,
            memories=memories,
        )

        [attempt] = memories.get(GEN).unsummarized()
        recalled = episodes.find_by_handle(GEN, handle)
        assert isinstance(attempt, Attempt) and isinstance(attempt.result, MemoryOperationOutcome)
        assert attempt.result.body == "一度に思い出せるのは 2 件までです。呼び名を減らしてください。"
        assert recalled is not None and recalled.recall_count == 0

    def test_handles_not_written_as_a_list_are_answered_with_how_to_write_them(self) -> None:
        """呼び名を配列で渡さなければ、書き方を結果に残す。"""
        memories = InMemoryShortTermMemoryRepository()

        _choose(_reply("episode_recall", {"handles": "ep_1"}), being_tools=WITH_MEMORY, memories=memories)

        [attempt] = memories.get(GEN).unsummarized()
        assert isinstance(attempt, Attempt) and isinstance(attempt.result, MemoryOperationOutcome)
        assert attempt.result.body.startswith("handles には、【思い出せる出来事】に並ぶ")

    def test_recall_tool_not_offered_is_an_unknown_tool(self) -> None:
        """思い出すツールを出していなければ、episode_recall は無いツールとして選べなかったを返す。"""
        outcome, _ = _choose(_reply("episode_recall", {"handles": ["ep_1"]}))

        assert isinstance(outcome, ActionNotChosen) and outcome.requested_tool == "episode_recall"


class TestReceiveActionResult:
    """ReceiveActionResult が、世界の返した結果を、結果を待っている試みに結び付けて短期記憶に残すことを保証する。"""

    def test_result_answers_the_awaiting_attempt(self) -> None:
        """選んだ行動の呼び出しの ID を持つ結果を渡すと、その試みが結果つきになる。"""
        memories = InMemoryShortTermMemoryRepository()
        clock = InMemoryMemoryTurnClock()
        _choose(
            _reply("interact", {"target": "金庫", "how": "番号を合わせて開ける"}, call_id="call_3"),
            memories=memories,
            clock=clock,
        )
        result = Observation(
            body="金庫の扉が開いた。",
            route=OwnActionResult(call_id="call_3", succeeded=True),
            time=NOW,
            subject_is_self=True,
            subject_name=UNKNOWN,
            source=UNKNOWN,
            place=UNKNOWN,
            addressed_to_self=True,
        )

        ReceiveActionResult(memories, clock).execute(ReceiveActionResultCommand(GEN, result))

        [attempt] = memories.get(GEN).unsummarized()
        assert isinstance(attempt, Attempt) and attempt.is_answered()
        assert isinstance(attempt.result, ObservedOutcome) and attempt.result.observation.body == "金庫の扉が開いた。"
