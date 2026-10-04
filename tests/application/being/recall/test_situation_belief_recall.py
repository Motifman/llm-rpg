"""SituationBeliefRecall が、いまの状況の全部の項目をつなげた 1 本の問い合わせ文で、有効な信念の上位を引く挙動を保証する。"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime, timezone

import pytest

from ai_rpg_world.application.being.recall.belief_recall import SituationBeliefRecall
from ai_rpg_world.application.being.recall.situation import Situation
from ai_rpg_world.application.llm.services.embedding_narrowing import (
    EmbeddingNarrower,
    EmbeddingUnavailableError,
    FallbackNarrower,
    ITextEmbedder,
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
SITUATION = Situation(place=("干潟",), happening=("カニに挟まれた",))
QUERY = "干潟\nカニに挟まれた"


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
    """問い合わせ文ごとに決めた順位を返す。受け取った問い合わせ文を残す。"""

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


class TestOneQuery:
    """全部の項目をつなげた 1 本の問い合わせ文で引くことを保証する。"""

    def test_the_whole_situation_is_asked_once(self) -> None:
        """手法には、全部の項目をつなげた問い合わせ文を 1 回だけ渡し、上位から順に返す。"""
        store = _store(*((key, key) for key in ("a", "b", "c", "d")))
        narrower = _FixedRankNarrower({QUERY: ["c", "a", "d", "b"]})

        result = SituationBeliefRecall(store, narrower).retrieve(BEING, SITUATION, top_k=3)

        assert narrower.calls == [(QUERY, 3)]
        assert _ids(result.chosen) == ["c", "a", "d"]

    def test_beliefs_matching_any_field_are_found(self) -> None:
        """場所に一致する信念も、いま起きたことに一致する信念も、同じ 1 本の問い合わせで引ける。"""
        store = _store(
            ("b-place", "干潟は潮が満ちると渡れない"),
            ("b-crab", "カニに挟まれたら手を離して待つ"),
            ("b-other", "森の奥には泉がある"),
        )

        result = _bm25(store).retrieve(BEING, SITUATION, top_k=3)

        assert set(_ids(result.chosen)) == {"b-place", "b-crab"}

    def test_inactive_beliefs_are_not_recalled(self) -> None:
        """同じ文の信念でも、active のものだけを引き、active でないものは引かない。"""
        store = _store(
            ("b-new", "カニに挟まれたら叫ぶ"),
            ("b-old", "カニに挟まれたら叫ぶ", "superseded"),
        )

        result = _bm25(store).retrieve(BEING, SITUATION, top_k=3)

        assert _ids(result.chosen) == ["b-new"]
        assert result.candidate_count == 1

    def test_beliefs_of_another_being_are_not_recalled(self) -> None:
        """別の Being の信念は、同じ文でも引かない。"""
        store = _store(("b-mine", "カニに挟まれたら叫ぶ"))
        _add(store, ("b-theirs", "カニに挟まれたら叫ぶ"), being_id=OTHER_BEING)

        result = _bm25(store).retrieve(BEING, SITUATION, top_k=3)

        assert _ids(result.chosen) == ["b-mine"]

    def test_empty_situation_is_not_searched(self) -> None:
        """どの項目も値を持たない状況は手法に渡さず、何も返さない。"""
        narrower = _FixedRankNarrower({"": ["a"]})

        result = SituationBeliefRecall(_store(("a", "a")), narrower).retrieve(
            BEING, Situation(), top_k=3
        )

        assert narrower.calls == []
        assert result.chosen == ()

    def test_returns_nothing_when_no_belief_matches(self) -> None:
        """状況に一致しない信念は、新しさや重要度だけで選ばれない。"""
        result = _bm25(_store(("b-other", "森の奥には泉がある"))).retrieve(
            BEING, SITUATION, top_k=3
        )

        assert result.chosen == ()
        assert result.candidate_count == 1

    def test_unknown_key_from_narrower_raises_with_its_name(self) -> None:
        """手法が候補に無い信念を返したら、手法の名前と信念を添えて ValueError を投げる。"""

        class _Broken(_FixedRankNarrower):
            def narrow(self, query, candidates, *, top_k):  # type: ignore[no-untyped-def]
                return (RankedCandidate("ghost", "幽霊", 1.0),)

        with pytest.raises(ValueError, match="fixed_rank.*ghost"):
            SituationBeliefRecall(_store(("a", "a")), _Broken({})).retrieve(
                BEING, SITUATION, top_k=3
            )

    @pytest.mark.parametrize("top_k", [0, -1])
    def test_rejects_top_k_below_one(self, top_k: int) -> None:
        """top_k に 1 未満を渡すと、手法が検査するかによらず ValueError を投げ、手法を呼ばない。"""
        narrower = _FixedRankNarrower({QUERY: ["a"]})

        with pytest.raises(ValueError):
            SituationBeliefRecall(_store(("a", "a")), narrower).retrieve(
                BEING, SITUATION, top_k=top_k
            )
        assert narrower.calls == []


class TestTracePayload:
    """何を問い合わせて何が引けたかを trace で読めることを保証する。"""

    def test_payload_has_query_hits_and_candidate_count(self) -> None:
        """trace には、手法、問い合わせ文、候補の数、引けた信念の本文と点、載せた信念が載る。"""
        store = _store(("b-crab", "カニに挟まれたら手を離して待つ"))
        narrower = CharBigramBm25Narrower()

        payload = (
            SituationBeliefRecall(store, narrower).retrieve(BEING, SITUATION, top_k=3).to_trace_payload()
        )

        assert payload["narrower"] == narrower.name
        assert payload["query"] == QUERY
        assert payload["candidate_count"] == 1
        assert [hit["entry_id"] for hit in payload["hits"]] == ["b-crab"]
        assert payload["hits"][0]["text"] == "カニに挟まれたら手を離して待つ"
        assert isinstance(payload["hits"][0]["score"], float)
        assert payload["chosen"] == ["b-crab"]

    def test_payload_without_fallback_names_the_chosen_narrower(self) -> None:
        """縮退しなければ、選んだ手法と使った手法は同じ名前で、縮退の理由は None。"""
        store = _store(("b-crab", "カニに挟まれたら手を離して待つ"))

        payload = _bm25(store).retrieve(BEING, SITUATION, top_k=3).to_trace_payload()

        assert payload["requested_narrower"] == "char_bigram_bm25"
        assert payload["narrower"] == "char_bigram_bm25"
        assert payload["fallback_reason"] is None

    def test_payload_after_fallback_names_the_used_narrower_and_the_reason(self) -> None:
        """埋め込みを得られず 2 字組で引き直したら、選んだ手法、実際に使った手法、縮退の理由が残る。"""
        store = _store(("b-crab", "カニに挟まれたら手を離して待つ"))
        narrower = FallbackNarrower(
            primary=EmbeddingNarrower(
                name="qwen3_embedding_8b_openrouter",
                embedder=_UnavailableEmbedder(),
            ),
            fallback=CharBigramBm25Narrower(),
        )

        result = SituationBeliefRecall(store, narrower).retrieve(BEING, SITUATION, top_k=3)
        payload = result.to_trace_payload()

        assert payload["requested_narrower"] == "qwen3_embedding_8b_openrouter"
        assert payload["narrower"] == "char_bigram_bm25"
        assert "HTTP 503" in payload["fallback_reason"]
        assert payload["chosen"] == ["b-crab"]


class _UnavailableEmbedder(ITextEmbedder):
    @property
    def name(self) -> str:
        return "unavailable"

    def embed_queries(self, texts: Sequence[str]):
        raise EmbeddingUnavailableError("HTTP 503")

    def embed_documents(self, texts: Sequence[str]):
        raise EmbeddingUnavailableError("HTTP 503")
