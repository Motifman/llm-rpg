"""run_situation_belief_recall が、ゲームの観測と行動結果を観測の契約に変換して状況の項目を組み、信念を引いて【関連する学び】と trace に出す挙動を保証する。"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from tests.trace_helpers import RecordingTraceRecorder

from ai_rpg_world.application.being.recall.belief_recall import SituationBeliefRecall
from ai_rpg_world.application.llm.contracts.dtos import ActionResultEntry
from ai_rpg_world.application.llm.services.in_memory_semantic_memory_store import (
    InMemorySemanticMemoryStore,
)
from ai_rpg_world.application.llm.services.prompt_sections.situation_recall import (
    SKIPPED_CONTRACT_VIOLATION,
    SituationRecallSources,
    run_situation_belief_recall,
)
from ai_rpg_world.application.llm.services.text_candidate_narrowing import (
    CharBigramBm25Narrower,
)
from ai_rpg_world.application.observation.contracts.dtos import (
    ObservationEntry,
    ObservationOutput,
)
from ai_rpg_world.application.trace import TraceEventKind
from ai_rpg_world.domain.being.value_object.being_id import BeingId
from ai_rpg_world.domain.memory.expectation.aggregate.expectation import Expectation
from ai_rpg_world.domain.memory.expectation.value_object.expectation_id import (
    ExpectationId,
)
from ai_rpg_world.domain.memory.expectation.value_object.expectation_origin import (
    ExpectationOrigin,
)
from ai_rpg_world.domain.memory.expectation.value_object.likelihood import Likelihood
from ai_rpg_world.domain.memory.semantic.value_object.semantic_memory_entry import (
    SemanticMemoryEntry,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.infrastructure.repository.in_memory_expectation_repository import (
    InMemoryExpectationRepository,
)

BEING = BeingId("being_w1_p1")
PLAYER = PlayerId.create(1)
T0 = datetime(2026, 10, 4, 9, 0, tzinfo=timezone.utc)
LABEL = "一日目の朝 9:00"


class _Builder:
    """run_situation_belief_recall が読む prompt builder の属性だけを持つ。"""

    def __init__(self, recorder: Any, *, top_k: int = 3) -> None:
        self._semantic_passive_top_k = top_k
        self._current_tick_provider = lambda: 7
        self._logger = logging.getLogger("test_situation_recall")
        self._recorder = recorder

    def _resolve_trace_recorder(self) -> Any:
        return self._recorder


class _Env:
    def __init__(
        self,
        *beliefs: tuple[str, str],
        goal: str | None = None,
        hearsay_only: frozenset[str] = frozenset(),
    ) -> None:
        self.recorder = RecordingTraceRecorder()
        self.store = InMemorySemanticMemoryStore()
        for entry_id, text in beliefs:
            heard = entry_id in hearsay_only
            self.store.add_by_being(
                BEING,
                SemanticMemoryEntry(
                    entry_id=entry_id,
                    player_id=1,
                    being_id=BEING,
                    text=text,
                    evidence_episode_ids=("ep-1",),
                    confidence=0.6,
                    created_at=T0,
                    support_evidence_ids=("e1",) if heard else (),
                    hearsay_support_count=1 if heard else 0,
                ),
            )
        self.expectations = InMemoryExpectationRepository()
        self.goal = goal
        self.sources = SituationRecallSources(
            recall=SituationBeliefRecall(self.store, CharBigramBm25Narrower()),
            expectations=self.expectations,
            goal_text=lambda _pid: self.goal,
        )

    def expect(self, content: str) -> None:
        self.expectations.save(
            Expectation(
                expectation_id=ExpectationId(f"{BEING.value}:t0:{content}"),
                holder=BEING,
                content=content,
                origin=ExpectationOrigin.WITH_ACTION,
                likelihood=Likelihood.PROBABLY,
                formed_at_turn=0,
                expires_at_turn=10,
            ),
            [],
        )

    def run(
        self,
        observations: list[ObservationEntry] = [],  # noqa: B006
        action_results: list[ActionResultEntry] = [],  # noqa: B006
        *,
        builder: Any = None,
    ) -> tuple[str, tuple[str, ...]]:
        return run_situation_belief_recall(
            builder or _Builder(self.recorder),
            self.sources,
            player_id=PLAYER,
            being_id=BEING,
            player_name="アリス",
            place_name="干潟",
            observations=observations,
            action_results=action_results,
        )

    def trace(self) -> dict[str, Any]:
        (payload,) = self.recorder.payloads(TraceEventKind.SITUATION_BELIEF_RECALL)
        return payload


def _seen(prose: str, minutes: int, **structured: Any) -> ObservationEntry:
    return ObservationEntry(
        occurred_at=T0 + timedelta(minutes=minutes),
        output=ObservationOutput(
            prose=prose, structured=structured, observation_category="social"
        ),
        game_time_label=LABEL,
    )


def _acted(result: str, minutes: int, *, inner_thought: str | None = None) -> ActionResultEntry:
    return ActionResultEntry(
        occurred_at=T0 + timedelta(minutes=minutes),
        action_summary="流木を拾う",
        result_summary=result,
        game_time_label=LABEL,
        inner_thought=inner_thought,
    )


class TestSituationFromGame:
    """ゲームの観測と行動結果、エージェントの持ち物から項目が組まれることを保証する。"""

    def test_observations_and_action_results_are_merged_newest_first(self) -> None:
        """観測と行動結果は時刻の新しい順に混ぜて、いま起きたことの項目に並ぶ。"""
        env = _Env()

        env.run(
            [_seen("潮が満ちてきた", 1), _seen("鳥が鳴いた", 3)],
            [_acted("流木を拾えた", 2)],
        )

        assert env.trace()["situation"]["いま起きたこと"] == [
            "鳥が鳴いた",
            "流木を拾えた",
            "潮が満ちてきた",
        ]

    def test_place_comes_from_the_current_place_through_the_contract(self) -> None:
        """自分の行動の結果は、いまいる場所の名前を場所の項目に運ぶ。"""
        env = _Env()

        env.run([], [_acted("流木を拾えた", 1)])

        assert env.trace()["situation"]["場所"] == ["干潟"]

    def test_unrepresentable_observations_are_skipped_and_counted_by_reason(self) -> None:
        """契約に写せない観測は項目に入れず、飛ばした理由ごとの件数を、種類が分かれば種類を添えて trace に残す。"""
        env = _Env()
        loop_warning = _seen("同じ手を繰り返している", 1, loop_guard=True)
        untimed = ObservationEntry(
            occurred_at=T0, output=ObservationOutput(prose="風が吹いた", structured={})
        )

        env.run([loop_warning, untimed, _seen("鳥が鳴いた", 2)])

        payload = env.trace()
        assert payload["situation"]["いま起きたこと"] == ["鳥が鳴いた"]
        assert payload["skipped_observations"] == {
            "being_inner_record: loop_guard": 1,
            "missing_time_label": 1,
        }

    def test_memo_tool_results_stay_out_of_what_happened(self) -> None:
        """メモ機能の結果は、いま起きたことに入れず、Being 自身の記録として道具の名前を添えて飛ばした件数に数える。"""
        env = _Env()
        memo = ActionResultEntry(
            occurred_at=T0 + timedelta(minutes=2),
            action_summary="memo_add()",
            result_summary="メモを追加しました（ID: ccd325…）。",
            tool_name="memo_add",
            game_time_label=LABEL,
        )

        env.run([_seen("潮が満ちてきた", 1)], [memo])

        payload = env.trace()
        assert payload["situation"]["いま起きたこと"] == ["潮が満ちてきた"]
        assert payload["skipped_observations"] == {"being_inner_record: memo_add": 1}

    def test_goal_inner_thought_and_open_expectations_fill_intent_and_unresolved(self) -> None:
        """目的と直前の内心はやろうとしていることに、清算待ちの予期は未解決のことに入る。"""
        env = _Env(goal="島から出る")
        env.expect("トムが麦束を焼いてくれる")

        env.run([], [_acted("流木を拾えた", 2, inner_thought="火を起こしたい"), _acted("石を拾えた", 1)])

        situation = env.trace()["situation"]
        assert situation["やろうとしていること"] == ["島から出る", "火を起こしたい"]
        assert situation["未解決のこと"] == ["トムが麦束を焼いてくれる"]


class TestRecallOutput:
    """引いた信念が【関連する学び】と台帳への ID になり、問い合わせ文と結果が trace に残ることを保証する。"""

    def test_returns_chosen_beliefs_as_text_and_ids(self) -> None:
        """頭に載せた信念を「- 文」の行と、その ID の並びで返す。"""
        env = _Env(("b-crab", "潮が満ちると干潟は渡れない"))

        text, ids = env.run([_seen("潮が満ちてきた", 1)])

        assert text == "- 潮が満ちると干潟は渡れない"
        assert ids == ("b-crab",)

    def test_shown_beliefs_are_ordered_by_id_regardless_of_rank(self) -> None:
        """複数の信念が載るとき、本文と返す ID は選ばれた順位ではなく信念の ID の順に並ぶ。同じ組なら同じ文字列にする。"""
        env = _Env(
            ("b-2", "潮が満ちてきたら高台へ行く"),
            ("b-1", "満ちてきた水は冷たい"),
        )

        text, ids = env.run([_seen("潮が満ちてきた", 1)])

        assert env.trace()["chosen"][0] == "b-2"
        assert ids == ("b-1", "b-2")
        assert text == "- 満ちてきた水は冷たい\n- 潮が満ちてきたら高台へ行く"

    def test_belief_supported_only_by_hearsay_is_marked_as_heard(self) -> None:
        """支持がすべて伝聞の信念は、言い切りの文でも「(人から聞いた話)」付きで載る (#1602)。"""
        env = _Env(("b-crab", "潮が満ちると干潟は渡れない"), hearsay_only=frozenset({"b-crab"}))

        text, ids = env.run([_seen("潮が満ちてきた", 1)])

        assert text == "- 潮が満ちると干潟は渡れない (人から聞いた話)"
        assert ids == ("b-crab",)

    def test_trace_has_the_whole_query_and_what_was_found(self) -> None:
        """trace には、全部の項目をつないだ問い合わせ文、候補の数、引けた信念、載せた信念が残る。"""
        env = _Env(("b-crab", "潮が満ちると干潟は渡れない"))

        env.run([_seen("潮が満ちてきた", 1)])

        payload = env.trace()
        assert payload["query"] == "干潟\n潮が満ちてきた"
        assert payload["candidate_count"] == 1
        assert [hit["entry_id"] for hit in payload["hits"]] == ["b-crab"]
        assert payload["chosen"] == ["b-crab"]
        assert payload["failed"] is None
        assert payload["being_id"] == BEING.value
        assert payload["top_k"] == 3

    def test_without_recorder_the_beliefs_are_returned_without_warning(self, caplog: Any) -> None:
        """trace の記録先が無ければ、記録の失敗として扱わずに、引いた信念を返す。"""
        env = _Env(("b-crab", "潮が満ちると干潟は渡れない"))

        with caplog.at_level(logging.WARNING):
            _, ids = env.run([_seen("潮が満ちてきた", 1)], builder=_Builder(None))

        assert ids == ("b-crab",)
        assert not any(r.levelno >= logging.WARNING for r in caplog.records)

    def test_trace_failure_does_not_discard_the_recalled_beliefs(self, caplog: Any) -> None:
        """trace の記録が例外を投げても、引いた信念は捨てずに返し、WARNING を残す。"""
        env = _Env(("b-crab", "潮が満ちると干潟は渡れない"))

        class _Broken:
            def record(self, *_args: Any, **_kwargs: Any) -> None:
                raise OSError("disk full")

        with caplog.at_level(logging.WARNING):
            _, ids = env.run([_seen("潮が満ちてきた", 1)], builder=_Builder(_Broken()))

        assert ids == ("b-crab",)
        assert any(r.levelno == logging.WARNING for r in caplog.records)

    def test_observation_violating_the_contract_is_skipped_and_counted(
        self, monkeypatch: Any
    ) -> None:
        """契約の検査に通らない観測は 1 件だけ飛ばして数え、ほかの観測で項目を組む。"""
        import ai_rpg_world.application.llm.services.prompt_sections.situation_recall as module
        from ai_rpg_world.being.contract import ContractViolation

        original = module.observation_from_game

        def _strict(output: Any, **kwargs: Any) -> Any:
            if output.prose == "壊れた観測":
                raise ContractViolation("place must not be empty")
            return original(output, **kwargs)

        monkeypatch.setattr(module, "observation_from_game", _strict)
        env = _Env()

        env.run([_seen("壊れた観測", 1), _seen("鳥が鳴いた", 2)])

        payload = env.trace()
        assert payload["failed"] is None
        assert payload["situation"]["いま起きたこと"] == ["鳥が鳴いた"]
        assert payload["skipped_observations"] == {SKIPPED_CONTRACT_VIOLATION: 1}

    def test_failure_returns_nothing_and_is_traced_as_failed(self, caplog: Any) -> None:
        """引く途中で例外が出たら何も載せず、ERROR で記録し、trace に失敗として残す。"""
        env = _Env()
        builder = _Builder(env.recorder, top_k=0)

        with caplog.at_level(logging.ERROR):
            result = env.run([_seen("潮が満ちてきた", 1)], builder=builder)

        assert result == ("", ())
        assert "ValueError" in env.trace()["failed"]
        assert any(r.levelno == logging.ERROR for r in caplog.records)

    def test_failure_trace_names_the_chosen_narrower(self) -> None:
        """引く途中で失敗しても、trace に選んだ手法の名前が残る。手法ごとに失敗を数えられる。"""
        env = _Env()
        builder = _Builder(env.recorder, top_k=0)

        env.run([_seen("潮が満ちてきた", 1)], builder=builder)

        assert env.trace()["requested_narrower"] == "char_bigram_bm25"


class TestSources:
    """SituationRecallSources が、配線の取り違えを作る時点で拒むことを保証する。"""

    def test_rejects_wrong_types(self) -> None:
        """引く部品、予期の保存先、目的の取り出し方のどれかが違う型なら TypeError を投げる。"""
        import pytest

        env = _Env()
        good = {
            "recall": env.sources.recall,
            "expectations": env.expectations,
            "goal_text": env.sources.goal_text,
        }
        for name, bad in (
            ("recall", object()),
            ("expectations", object()),
            ("goal_text", "目的"),
        ):
            with pytest.raises(TypeError, match=name):
                SituationRecallSources(**{**good, name: bad})
