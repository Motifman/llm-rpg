"""SituationBeliefRecall が、マスクごとに信念を引いて別々の一覧で持ち、重複を後の一覧から除いて、頭に載せる枠を一覧から順番に埋める挙動を保証する。"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime, timezone

import pytest

from ai_rpg_world.application.being.recall.belief_recall import SituationBeliefRecall
from ai_rpg_world.application.being.recall.situation import (
    FieldSelection,
    Situation,
    SituationField,
)
from ai_rpg_world.application.llm.services.in_memory_semantic_memory_store import (
    InMemorySemanticMemoryStore,
)
from ai_rpg_world.application.llm.services.text_candidate_narrowing import (
    CharBigramBm25Narrower,
    ITextCandidateNarrower,
    RankedCandidate,
    TextCandidate,
)
from ai_rpg_world.domain.being.value_object.being_id import BeingId
from ai_rpg_world.domain.memory.semantic.value_object.semantic_memory_entry import (
    SemanticMemoryEntry,
)

BEING = BeingId("being_w1_p1")
OTHER_BEING = BeingId("being_w1_p2")
HAPPENING_ONLY = FieldSelection(kept=frozenset({SituationField.HAPPENING}))
SITUATION = Situation(place=("干潟",), happening=("カニに挟まれた",))
WITH_PLACE_QUERY = "干潟\nカニに挟まれた"
WITHOUT_PLACE_QUERY = "カニに挟まれた"


def _store(
    *beliefs: tuple[str, str] | tuple[str, str, str], being_id: BeingId = BEING
) -> InMemorySemanticMemoryStore:
    store = InMemorySemanticMemoryStore()
    _add(store, *beliefs, being_id=being_id)
    return store


def _add(
    store: InMemorySemanticMemoryStore,
    *beliefs: tuple[str, str] | tuple[str, str, str],
    being_id: BeingId = BEING,
) -> None:
    for belief in beliefs:
        entry_id, text = belief[0], belief[1]
        status = belief[2] if len(belief) == 3 else "active"
        store.add_by_being(
            being_id,
            SemanticMemoryEntry(
                entry_id=entry_id,
                player_id=1,
                being_id=being_id,
                text=text,
                evidence_episode_ids=("ep-1",),
                confidence=0.6,
                created_at=datetime(2026, 6, 1, tzinfo=timezone.utc),
                status=status,
            ),
        )


class _FixedRankNarrower(ITextCandidateNarrower):
    """問い合わせ文ごとに決めた順位を返す。BM25 の点に頼らずに、引いたあとの扱いを試験する。"""

    def __init__(self, ranks: Mapping[str, Sequence[str]]) -> None:
        self._ranks = ranks
        self.calls: list[tuple[str, int]] = []

    @property
    def name(self) -> str:
        return "fixed_rank"

    def narrow(
        self, query: str, candidates: Sequence[TextCandidate], *, top_k: int
    ) -> tuple[RankedCandidate, ...]:
        self.calls.append((query, top_k))
        texts = {c.key: c.text for c in candidates}
        keys = [key for key in self._ranks.get(query, ()) if key in texts]
        return tuple(
            RankedCandidate(key, texts[key], float(len(keys) - i))
            for i, key in enumerate(keys[:top_k])
        )


def _bm25(store: InMemorySemanticMemoryStore) -> SituationBeliefRecall:
    return SituationBeliefRecall(store, CharBigramBm25Narrower())


def _ids(entries) -> list[str]:  # type: ignore[no-untyped-def]
    return [e.entry_id for e in entries]


class TestSeparateListsPerMask:
    """マスクごとの結果を混ぜずに持つことを保証する。"""

    def test_place_kept_search_finds_place_knowledge_and_dropped_search_does_not(self) -> None:
        """場所だけに一致する信念は、場所を残した一覧に入り、場所を捨てた一覧には入らない。"""
        store = _store(("b-place", "干潟は潮が満ちると渡れない"))

        result = _bm25(store).retrieve(BEING, SITUATION, HAPPENING_ONLY, top_k=3)

        with_place, without_place = result.lists
        assert _ids(with_place.entries) == ["b-place"]
        assert without_place.entries == ()

    def test_belief_found_by_both_masks_stays_only_in_the_first_list(self) -> None:
        """両方のマスクで引けた信念は、場所を残した一覧にだけ残し、後の一覧では重複として記録する。"""
        store = _store(("b-crab", "カニに挟まれたら手を離して待つ"))

        result = _bm25(store).retrieve(BEING, SITUATION, HAPPENING_ONLY, top_k=3)

        with_place, without_place = result.lists
        assert _ids(with_place.entries) == ["b-crab"]
        assert without_place.entries == ()
        assert without_place.duplicates == ("b-crab",)

    def test_later_list_is_filled_beyond_the_overlap(self) -> None:
        """後の一覧は先の一覧と重なった分を除いたうえで top_k 件まで埋まり、重なりで空にならない。"""
        store = _store(*((key, key) for key in ("a", "b", "c", "d", "e")))
        narrower = _FixedRankNarrower(
            {WITH_PLACE_QUERY: ["a", "b", "c"], WITHOUT_PLACE_QUERY: ["a", "b", "c", "d", "e"]}
        )

        result = SituationBeliefRecall(store, narrower).retrieve(
            BEING, SITUATION, HAPPENING_ONLY, top_k=3
        )

        _, without_place = result.lists
        assert _ids(without_place.entries) == ["d", "e"]
        assert without_place.duplicates == ("a", "b", "c")
        assert narrower.calls[1] == (WITHOUT_PLACE_QUERY, 6)

    def test_later_list_is_cut_at_top_k_when_extra_results_do_not_overlap(self) -> None:
        """重なりの分として余分に引いた信念が先の一覧と重ならなければ、後の一覧は top_k 件で切られる。"""
        store = _store(*((key, key) for key in ("a", "b", "c", "d", "e")))
        narrower = _FixedRankNarrower(
            {WITH_PLACE_QUERY: ["a"], WITHOUT_PLACE_QUERY: ["b", "c", "d", "e"]}
        )

        result = SituationBeliefRecall(store, narrower).retrieve(
            BEING, SITUATION, HAPPENING_ONLY, top_k=3
        )

        _, without_place = result.lists
        assert _ids(without_place.entries) == ["b", "c", "d"]
        assert [hit.key for hit in without_place.hits] == ["b", "c", "d"]

    def test_inactive_beliefs_are_not_recalled(self) -> None:
        """同じ文の信念でも、active のものだけを引き、active でないものは引かない。"""
        store = _store(
            ("b-new", "カニに挟まれたら叫ぶ"),
            ("b-old", "カニに挟まれたら叫ぶ", "superseded"),
        )

        result = _bm25(store).retrieve(BEING, SITUATION, HAPPENING_ONLY, top_k=3)

        assert _ids(result.chosen) == ["b-new"]
        assert result.candidate_count == 1

    def test_beliefs_of_another_being_are_not_recalled(self) -> None:
        """別の Being の信念は、同じ文でも引かない。"""
        store = _store(("b-mine", "カニに挟まれたら叫ぶ"))
        _add(store, ("b-theirs", "カニに挟まれたら叫ぶ"), being_id=OTHER_BEING)

        result = _bm25(store).retrieve(BEING, SITUATION, HAPPENING_ONLY, top_k=3)

        assert _ids(result.chosen) == ["b-mine"]

    def test_mask_with_empty_query_is_not_searched(self) -> None:
        """残した欄に値が無いマスクは手法に渡さず、空の問い合わせとして空の一覧を持つ。"""
        store = _store(("b-crab", "カニに挟まれたら手を離して待つ"))
        narrower = _FixedRankNarrower({"干潟": ["b-crab"]})
        selection = FieldSelection(kept=frozenset({SituationField.COUNTERPART}))

        result = SituationBeliefRecall(store, narrower).retrieve(
            BEING, SITUATION, selection, top_k=3
        )

        _, without_place = result.lists
        assert [query for query, _ in narrower.calls] == ["干潟"]
        assert without_place.query == ""
        assert without_place.entries == ()

    def test_dropping_every_field_searches_by_place_only(self) -> None:
        """場所以外の欄をすべて捨てると、場所だけの検索で引き、場所を捨てた検索は空の問い合わせになる。"""
        store = _store(("b-place", "干潟は潮が満ちると渡れない"))

        result = _bm25(store).retrieve(
            BEING, SITUATION, FieldSelection(kept=frozenset()), top_k=3
        )

        with_place, without_place = result.lists
        assert with_place.query == "干潟"
        assert _ids(result.chosen) == ["b-place"]
        assert without_place.query == ""

    def test_unknown_key_from_narrower_raises_with_its_name(self) -> None:
        """手法が候補に無い信念を返したら、手法の名前と信念を添えて ValueError を投げる。"""

        class _Broken(_FixedRankNarrower):
            def narrow(self, query, candidates, *, top_k):  # type: ignore[no-untyped-def]
                return (RankedCandidate("ghost", "幽霊", 1.0),)

        with pytest.raises(ValueError, match="fixed_rank.*ghost"):
            SituationBeliefRecall(_store(("a", "a")), _Broken({})).retrieve(
                BEING, SITUATION, HAPPENING_ONLY, top_k=3
            )


class TestChosenSlots:
    """頭に載せる枠を、一覧から順番に 1 件ずつ取って埋めることを保証する。"""

    def test_alternates_between_lists_starting_with_place_kept(self) -> None:
        """枠は場所を残した一覧の 1 位、捨てた一覧の 1 位、場所を残した一覧の 2 位、の順に埋まる。"""
        store = _store(*((key, key) for key in ("p1", "p2", "h1", "h2")))
        narrower = _FixedRankNarrower(
            {WITH_PLACE_QUERY: ["p1", "p2", "h1"], WITHOUT_PLACE_QUERY: ["h1", "h2"]}
        )

        result = SituationBeliefRecall(store, narrower).retrieve(
            BEING, SITUATION, HAPPENING_ONLY, top_k=3
        )

        assert _ids(result.chosen) == ["p1", "h2", "p2"]

    def test_returns_nothing_when_no_belief_matches(self) -> None:
        """どのマスクにも一致しない信念は、新しさや重要度だけで選ばれない。"""
        store = _store(("b-other", "森の奥には泉がある"))

        result = _bm25(store).retrieve(BEING, SITUATION, HAPPENING_ONLY, top_k=3)

        assert result.chosen == ()
        assert result.candidate_count == 1

    @pytest.mark.parametrize("top_k", [0, -1])
    def test_rejects_top_k_below_one(self, top_k: int) -> None:
        """top_k に 1 未満を渡すと ValueError を投げる。止めるかは呼び出し側が決める。"""
        with pytest.raises(ValueError):
            _bm25(_store()).retrieve(BEING, SITUATION, HAPPENING_ONLY, top_k=top_k)

    def test_top_k_one_takes_only_the_first_of_the_place_kept_list(self) -> None:
        """top_k が 1 なら、場所を残した一覧の 1 位だけが載る。"""
        store = _store(*((key, key) for key in ("p1", "h1")))
        narrower = _FixedRankNarrower({WITH_PLACE_QUERY: ["p1"], WITHOUT_PLACE_QUERY: ["h1"]})

        result = SituationBeliefRecall(store, narrower).retrieve(
            BEING, SITUATION, HAPPENING_ONLY, top_k=1
        )

        assert _ids(result.chosen) == ["p1"]


class TestTracePayload:
    """失敗したときに、どの欄を残してどのマスクで何が引けたかを trace で読めることを保証する。"""

    def test_payload_of_degraded_selection_has_reason_and_per_mask_results(self) -> None:
        """縮退した選び方の trace には、残した欄、縮退の理由、手法、候補数、マスクごとの欄と問い合わせ文と引けた信念と重複が載る。"""
        store = _store(("b-crab", "カニに挟まれたら手を離して待つ"))
        narrower = CharBigramBm25Narrower()
        selection = FieldSelection.degraded("judgment_unavailable", "TIMEOUT: 遅い")

        payload = (
            SituationBeliefRecall(store, narrower)
            .retrieve(BEING, SITUATION, selection, top_k=3)
            .to_trace_payload()
        )

        assert payload["kept_fields"] == [
            "相手", "自分の状態", "やろうとしていること", "いま起きたこと", "未解決のこと"
        ]
        assert payload["degraded_reason"] == "judgment_unavailable"
        assert payload["degraded_detail"] == "TIMEOUT: 遅い"
        assert payload["narrower"] == narrower.name
        assert payload["candidate_count"] == 1
        first, second = payload["masks"]
        assert first["fields"][0] == "場所"
        assert first["query"] == WITH_PLACE_QUERY
        assert [hit["entry_id"] for hit in first["hits"]] == ["b-crab"]
        assert first["hits"][0]["text"] == "カニに挟まれたら手を離して待つ"
        assert isinstance(first["hits"][0]["score"], float)
        assert second["hits"] == []
        assert second["duplicates"] == ["b-crab"]
        assert payload["chosen"] == ["b-crab"]

    def test_payload_of_judged_selection_has_no_reason_and_only_kept_fields(self) -> None:
        """縮退していない選び方の trace は、縮退の理由が None で、残した欄は選ばれた欄だけになる。"""
        payload = (
            _bm25(_store())
            .retrieve(BEING, SITUATION, HAPPENING_ONLY, top_k=3)
            .to_trace_payload()
        )

        assert payload["kept_fields"] == ["いま起きたこと"]
        assert payload["degraded_reason"] is None
        assert payload["candidate_count"] == 0
