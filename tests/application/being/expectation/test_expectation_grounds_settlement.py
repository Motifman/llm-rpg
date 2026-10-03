"""予期を書いたターンの清算の呼び出しで、頭にあった信念とエピソードごとに予期の根拠かを問い、確定した当否を根拠にだけ返す挙動を保証する (#1484)。"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from tests.application.being.expectation.support import (
    RecordingTraceRecorder,
    ScriptedJudgmentPort,
)

from ai_rpg_world.application.being.expectation.belief_material import (
    ExpectationBeliefMaterialReceiver,
)
from ai_rpg_world.application.being.expectation.event_delivery import (
    ExpectationEventDispatcher,
)
from ai_rpg_world.application.being.expectation.grounds import InMindTextReader
from ai_rpg_world.application.being.expectation.recall_credit import (
    ExpectationRecallCreditReceiver,
)
from ai_rpg_world.application.being.expectation.settlement import (
    ExpectationSettlementService,
    TurnMaterial,
)
from ai_rpg_world.application.llm.ports.typed_judgment_port import (
    NoulQuestion,
    TypedJudgmentUnavailableException,
)
from ai_rpg_world.application.llm.services.episodic_recall_success_store import (
    InMemoryEpisodicRecallSuccessStore,
)
from ai_rpg_world.application.llm.services.in_memory_belief_evidence_buffer_store import (
    InMemoryBeliefEvidenceBufferStore,
)
from ai_rpg_world.application.llm.services.in_memory_episodic_reinterpretation_stores import (
    InMemoryEpisodicRecallBufferStore,
)
from ai_rpg_world.application.trace import TraceEventKind
from ai_rpg_world.domain.being.value_object.being_id import BeingId
from ai_rpg_world.domain.memory.episodic.value_object.episodic_recall_observation import (
    EpisodicRecallObservation,
)
from ai_rpg_world.domain.memory.expectation.aggregate.expectation import (
    Expectation,
)
from ai_rpg_world.domain.memory.expectation.value_object.expectation_grounds import (
    ExpectationGrounds,
)
from ai_rpg_world.domain.memory.expectation.value_object.expectation_id import (
    ExpectationId,
)
from ai_rpg_world.domain.memory.expectation.value_object.expectation_origin import (
    ExpectationOrigin,
)
from ai_rpg_world.domain.memory.expectation.value_object.likelihood import (
    Likelihood,
)
from ai_rpg_world.infrastructure.repository.in_memory_expectation_repository import (
    InMemoryExpectationRepository,
)

RIO = BeingId("being-rio")
QUIET = TurnMaterial()
BELIEFS = {
    "belief-flat": "干潟は大型カニがいて危険だ",
    "belief-tom": "トムは頼めば麦束を焼いてくれる",
}
EPISODES = {
    "ep-crab": "干潟でカニに挟まれた",
    "ep-bread": "トムが焼いた麦束を分けてくれた",
}
SETTLEABLE_HIT_HIT = ({"check_0": "hit"}, {"check_0": "hit"})
SETTLEABLE_MISS_MISS = ({"check_0": "miss"}, {"check_0": "miss"})


class _Texts(InMindTextReader):
    def __init__(
        self,
        beliefs: dict[str, str] | None = None,
        episodes: dict[str, str] | None = None,
        broken: bool = False,
    ) -> None:
        self._beliefs = BELIEFS if beliefs is None else beliefs
        self._episodes = EPISODES if episodes is None else episodes
        self._broken = broken

    def belief_text(self, being_id: BeingId, belief_id: str) -> str | None:
        if self._broken:
            raise RuntimeError("semantic store is down")
        return self._beliefs.get(belief_id)

    def episode_text(self, being_id: BeingId, episode_id: str) -> str | None:
        return self._episodes.get(episode_id)


class _Harness:
    """清算の service に、信念の材料と想起の受け取る側を実物の store でつないだもの。"""

    def __init__(
        self,
        port: ScriptedJudgmentPort,
        *,
        texts: InMindTextReader | None = None,
        max_grounds_questions: int = 8,
    ) -> None:
        self.repository = InMemoryExpectationRepository()
        self.recorder = RecordingTraceRecorder()
        self.port = port
        self.evidence = InMemoryBeliefEvidenceBufferStore()
        self.success = InMemoryEpisodicRecallSuccessStore()
        self.recalls = InMemoryEpisodicRecallBufferStore()
        trace = lambda: self.recorder  # noqa: E731
        self.service = ExpectationSettlementService(
            self.repository,
            judgment_port=port,
            dispatcher=ExpectationEventDispatcher(
                self.repository,
                receivers=(
                    ExpectationBeliefMaterialReceiver(
                        self.evidence,
                        now_provider=lambda: datetime(2026, 10, 4, tzinfo=timezone.utc),
                        trace_recorder_provider=trace,
                    ),
                    ExpectationRecallCreditReceiver(
                        success_store=self.success,
                        recall_buffer_store=self.recalls,
                        trace_recorder_provider=trace,
                    ),
                ),
                max_attempts=3,
                trace_recorder_provider=trace,
            ),
            max_open=8,
            timeline_turns=3,
            grounds_reader=texts or _Texts(),
            max_grounds_questions=max_grounds_questions,
            grounds_min_probability=0.5,
            trace_recorder_provider=trace,
        )

    def form(self, expectation_id: str = "exp-1", content: str = "トムが麦束を焼いてくれる") -> None:
        """次のターンに進め、頭に信念 2 件とエピソード 2 件を載せた予期を作る。"""
        self.repository.advance_turn(RIO)
        turn = self.repository.current_turn(RIO)
        self.repository.save(
            Expectation(
                expectation_id=ExpectationId(expectation_id),
                holder=RIO,
                content=content,
                origin=ExpectationOrigin.WITH_ACTION,
                likelihood=Likelihood.PROBABLY,
                formed_at_turn=turn,
                expires_at_turn=turn + 10,
                beliefs_in_mind=tuple(BELIEFS),
                episodes_in_mind=tuple(EPISODES),
            ),
            [],
        )

    def settle_formed_turn(self) -> None:
        self.service.settle_turn(RIO, self_name="リオ", material=QUIET)

    def turn(self) -> None:
        self.repository.advance_turn(RIO)
        self.service.settle_turn(RIO, self_name="リオ", material=QUIET)

    def grounds(self, expectation_id: str = "exp-1") -> ExpectationGrounds | None:
        (expectation,) = [
            e
            for e in self.repository.list_all_by_being(RIO)
            if e.expectation_id == ExpectationId(expectation_id)
        ]
        return expectation.snapshot().grounds

    def grounds_trace(self, index: int = 0) -> list[dict[str, Any]]:
        settlements = self.recorder.payloads(TraceEventKind.EXPECTATION_SETTLEMENT)
        grounds: list[dict[str, Any]] = settlements[index]["grounds"]
        return grounds


def _ground_questions(port: ScriptedJudgmentPort, call: int = 0) -> dict[str, Any]:
    _, questions = port.calls[call]
    return {name: q for name, q in questions.items() if name.startswith("ground_")}


def _recall(recall_id: str, episode_id: str) -> EpisodicRecallObservation:
    return EpisodicRecallObservation(
        recall_id=recall_id,
        player_id=1,
        episode_id=episode_id,
        recalled_at=datetime(2026, 10, 4, tzinfo=timezone.utc),
        source_axes=("temporal",),
        current_state_snapshot="浜",
        recent_events_snapshot="トムがいる",
        persona_snapshot="リオ",
        situation_cues=(),
        turn_index=1,
    )


class TestAskedWithShape:
    """予期を書いたターンに、根拠の問いを形の問いと同じ呼び出しで問う挙動を保証する。"""

    def test_each_belief_and_episode_in_mind_is_asked_in_the_shape_call(self) -> None:
        """頭にあった信念 2 件とエピソード 2 件それぞれについて、予期と本文を並べた Noul を、形の問いと同じ 1 回の呼び出しで問う。"""
        harness = _Harness(ScriptedJudgmentPort({}))
        harness.form()

        harness.settle_formed_turn()

        assert len(harness.port.calls) == 1
        _, questions = harness.port.calls[0]
        assert "shape_0" in questions
        grounds = _ground_questions(harness.port)
        assert sorted(grounds) == [
            "ground_belief_0",
            "ground_belief_1",
            "ground_episode_0",
            "ground_episode_1",
        ]
        assert all(isinstance(q, NoulQuestion) for q in grounds.values())
        instructions = [q.instructions for q in grounds.values()]
        assert all("トムが麦束を焼いてくれる" in text for text in instructions)
        for text in (*BELIEFS.values(), *EPISODES.values()):
            assert sum(text in i for i in instructions) == 1

    def test_question_names_and_texts_carry_no_ids(self) -> None:
        """根拠の問いの名前と文には、信念やエピソードの ID を入れない。"""
        harness = _Harness(ScriptedJudgmentPort({}))
        harness.form()

        harness.settle_formed_turn()

        _, questions = harness.port.calls[0]
        dumped = repr(questions)
        assert not any(i in dumped for i in (*BELIEFS, *EPISODES))

    def test_pending_expectation_is_not_asked_for_grounds_again(self) -> None:
        """形を判定済みの清算待ちの予期には、次のターンに根拠を問い直さない。"""
        harness = _Harness(ScriptedJudgmentPort({}, {}))
        harness.form()
        harness.settle_formed_turn()

        harness.turn()

        assert _ground_questions(harness.port, call=1) == {}


class TestChoosingGrounds:
    """確率が閾値を超えたものだけを根拠として予期に記録する挙動を保証する。"""

    def test_only_probabilities_above_threshold_become_grounds(self) -> None:
        """確率が閾値を超えた信念 1 件とエピソード 1 件だけが根拠になり、閾値ちょうどと下回るものは根拠にならない。"""
        harness = _Harness(
            ScriptedJudgmentPort(
                {
                    "ground_belief_0": 0.2,
                    "ground_belief_1": 0.9,
                    "ground_episode_0": 0.5,
                    "ground_episode_1": 0.8,
                }
            )
        )
        harness.form()

        harness.settle_formed_turn()

        assert harness.grounds() == ExpectationGrounds(
            beliefs=("belief-tom",), episodes=("ep-bread",)
        )

    def test_undecided_answers_choose_nothing(self) -> None:
        """どの問いにも迷った答え (0.5) が返ると、根拠は空になり、頭にあったものすべてには倒れない。"""
        harness = _Harness(ScriptedJudgmentPort({}))
        harness.form()

        harness.settle_formed_turn()

        assert harness.grounds() == ExpectationGrounds()

    def test_trace_lists_in_mind_asked_probabilities_and_chosen(self) -> None:
        """trace に、予期ごとの頭にあったもの、問うたものと確率、選ばれた根拠が残る。"""
        harness = _Harness(
            ScriptedJudgmentPort({"ground_belief_1": 0.9, "ground_episode_0": 0.1})
        )
        harness.form()

        harness.settle_formed_turn()

        (entry,) = harness.grounds_trace()
        assert entry["expectation_id"] == "exp-1"
        assert entry["beliefs_in_mind"] == list(BELIEFS)
        assert entry["episodes_in_mind"] == list(EPISODES)
        assert [(a["kind"], a["id"], a["probability"]) for a in entry["asked"]] == [
            ("belief", "belief-flat", 0.5),
            ("belief", "belief-tom", 0.9),
            ("episode", "ep-crab", 0.1),
            ("episode", "ep-bread", 0.5),
        ]
        assert entry["omitted"] == []
        assert (entry["judged"], entry["beliefs"], entry["episodes"]) == (
            True,
            ["belief-tom"],
            [],
        )


class TestOutcomeReachesOnlyGrounds:
    """確定した当否が、根拠と判断された信念とエピソードにだけ返る挙動を保証する。"""

    def test_hit_supports_only_grounding_belief(self) -> None:
        """当たりの材料は 1 件だけ積まれ、指す信念は根拠と判断した信念だけで、いつも頭にあった信念を含まない。"""
        harness = _Harness(
            ScriptedJudgmentPort({"ground_belief_1": 0.9}, *SETTLEABLE_HIT_HIT)
        )
        harness.form()
        harness.settle_formed_turn()

        harness.turn()
        harness.turn()

        (material,) = harness.evidence.list_all_by_being(RIO)
        assert material.in_context_belief_ids == ("belief-tom",)

    def test_hit_credits_only_grounding_episode(self) -> None:
        """当たりで役に立った回数が増えるのは、根拠と判断したエピソードだけ。"""
        harness = _Harness(
            ScriptedJudgmentPort({"ground_episode_1": 0.9}, *SETTLEABLE_HIT_HIT)
        )
        harness.form()
        harness.settle_formed_turn()

        harness.turn()
        harness.turn()

        assert harness.success.list_all_by_being(RIO) == {"ep-bread": 1}

    def test_miss_stamps_only_recalls_of_grounding_episode(self) -> None:
        """外れのずれは根拠のエピソードの想起にだけ書き添え、頭にあった他のエピソードの想起には書かない。"""
        harness = _Harness(
            ScriptedJudgmentPort({"ground_episode_1": 0.9}, *SETTLEABLE_MISS_MISS)
        )
        harness.recalls.append_by_being(RIO, _recall("r-crab", "ep-crab"))
        harness.recalls.append_by_being(RIO, _recall("r-bread", "ep-bread"))
        harness.form()
        harness.settle_formed_turn()

        harness.turn()
        harness.turn()

        stamps = {
            o.recall_id: o.prediction_outcome_error
            for o in harness.recalls.list_pending_by_being(RIO)
        }
        assert stamps["r-crab"] is None
        assert stamps["r-bread"] is not None

    def test_hit_without_any_grounds_reaches_no_belief_and_no_episode(self) -> None:
        """根拠が 1 件も無い予期が当たっても、信念の材料も役に立った回数も増えない。"""
        harness = _Harness(ScriptedJudgmentPort({}, *SETTLEABLE_HIT_HIT))
        harness.form()
        harness.settle_formed_turn()

        harness.turn()
        harness.turn()

        assert harness.evidence.list_all_by_being(RIO) == []
        assert harness.success.list_all_by_being(RIO) == {}

    def test_miss_without_any_grounds_is_still_material_pointing_nowhere(self) -> None:
        """根拠が 1 件も無い予期の外れは、新しく学ぶ材料として積まれ、指す信念は空になる。"""
        harness = _Harness(ScriptedJudgmentPort({}, *SETTLEABLE_MISS_MISS))
        harness.form()
        harness.settle_formed_turn()

        harness.turn()
        harness.turn()

        (material,) = harness.evidence.list_all_by_being(RIO)
        assert material.in_context_belief_ids == ()


class TestJudgmentUnavailable:
    """判断が得られないとき、根拠を頭にあったものに倒さず、理由を trace に残す挙動を保証する。"""

    def test_unavailable_judgment_leaves_grounds_empty_and_traced(self) -> None:
        """判断が得られないターンは根拠を記録せず、trace に予期ごとの空の根拠と縮退の理由が残る。"""
        harness = _Harness(
            ScriptedJudgmentPort(TypedJudgmentUnavailableException("timeout"))
        )
        harness.form()

        harness.settle_formed_turn()

        assert harness.grounds() is None
        (entry,) = harness.grounds_trace()
        assert (entry["judged"], entry["beliefs"], entry["episodes"]) == (False, [], [])
        assert all(a["probability"] is None for a in entry["asked"])
        settlement = harness.recorder.payloads(TraceEventKind.EXPECTATION_SETTLEMENT)[0]
        assert "timeout" in settlement["unavailable_reason"]

    def test_unusable_ground_answer_degrades_whole_turn(self) -> None:
        """根拠の問いの答えが 0〜1 の数でなければ、そのターンはどの予期にも形も根拠も渡さない。"""
        harness = _Harness(ScriptedJudgmentPort({"ground_belief_0": 1.5}))
        harness.form()

        harness.settle_formed_turn()

        assert harness.grounds() is None
        settlement = harness.recorder.payloads(TraceEventKind.EXPECTATION_SETTLEMENT)[0]
        assert settlement["skipped_reason"] == "judgment_unavailable"
        assert "ground_belief_0" in settlement["unavailable_reason"]

    def test_grounds_are_asked_again_with_shape_on_next_turn(self) -> None:
        """判断が得られなかった予期は、次のターンに形と一緒に根拠をもう一度問われ、そこで根拠が決まる。"""
        harness = _Harness(
            ScriptedJudgmentPort(
                TypedJudgmentUnavailableException("timeout"), {"ground_belief_1": 0.9}
            )
        )
        harness.form()
        harness.settle_formed_turn()

        harness.turn()

        assert len(_ground_questions(harness.port, call=1)) == 4
        assert harness.grounds() == ExpectationGrounds(beliefs=("belief-tom",))


class TestQuestionLimit:
    """1 回の呼び出しに並べる根拠の問いの数に上限を置き、外したものを trace に残す挙動を保証する。"""

    def test_questions_over_limit_are_omitted_and_traced(self) -> None:
        """上限 3 で 4 件の問いがあるとき、3 件だけを並べ、外した 1 件を理由つきで trace に残し、根拠にもしない。"""
        harness = _Harness(
            ScriptedJudgmentPort(
                {f"ground_{k}_{i}": 0.9 for k in ("belief", "episode") for i in (0, 1)}
            ),
            max_grounds_questions=3,
        )
        harness.form()

        harness.settle_formed_turn()

        assert len(_ground_questions(harness.port)) == 3
        (entry,) = harness.grounds_trace()
        assert entry["omitted"] == [
            {"kind": "episode", "id": "ep-bread", "reason": "over_limit"}
        ]
        grounds = harness.grounds()
        assert grounds is not None
        assert "ep-bread" not in grounds.episodes

    def test_limit_counts_questions_across_expectations_of_the_turn(self) -> None:
        """同じターンに 2 件の予期があるとき、上限は 2 件の予期の問いを合わせて数え、後の予期の問いから外す。"""
        harness = _Harness(ScriptedJudgmentPort({}), max_grounds_questions=5)
        harness.form()
        harness.repository.save(
            Expectation(
                expectation_id=ExpectationId("exp-2"),
                holder=RIO,
                content="干潟でカニに出会う",
                origin=ExpectationOrigin.WITH_ACTION,
                likelihood=Likelihood.PROBABLY,
                formed_at_turn=1,
                expires_at_turn=11,
                beliefs_in_mind=tuple(BELIEFS),
                episodes_in_mind=tuple(EPISODES),
            ),
            [],
        )

        harness.settle_formed_turn()

        first, second = harness.grounds_trace()
        assert (len(first["asked"]), len(first["omitted"])) == (4, 0)
        assert (len(second["asked"]), len(second["omitted"])) == (1, 3)


class TestUnreadableText:
    """本文を引けない信念やエピソードを問わず、理由を trace に残す挙動を保証する。"""

    def test_missing_text_is_not_asked_and_traced(self) -> None:
        """本文の見つからない信念は問わず、text_not_found として trace に残し、根拠にもしない。"""
        harness = _Harness(
            ScriptedJudgmentPort({}),
            texts=_Texts(beliefs={"belief-tom": BELIEFS["belief-tom"]}),
        )
        harness.form()

        harness.settle_formed_turn()

        (entry,) = harness.grounds_trace()
        assert entry["omitted"] == [
            {"kind": "belief", "id": "belief-flat", "reason": "text_not_found"}
        ]
        assert len(_ground_questions(harness.port)) == 3

    def test_text_read_failure_omits_item_but_shape_is_still_judged(self) -> None:
        """本文を引く口が例外を投げても、その信念を外して trace に残し、形の判定は続ける。"""
        harness = _Harness(ScriptedJudgmentPort({}), texts=_Texts(broken=True))
        harness.form()

        harness.settle_formed_turn()

        (entry,) = harness.grounds_trace()
        assert {o["reason"] for o in entry["omitted"]} == {
            "text_read_failed: RuntimeError: semantic store is down"
        }
        assert harness.grounds() == ExpectationGrounds()
