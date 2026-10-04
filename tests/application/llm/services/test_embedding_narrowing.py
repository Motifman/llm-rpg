"""文の埋め込みで候補を絞る仕様と、埋め込みを得られないときの縮退の仕様 (#1454)。

埋め込みを作る部品 (``ITextEmbedder``) は差し替える。ここでは手で決めたベクトルを
返す部品で、並べ方・ベクトルの使い回し・縮退だけを確かめる。
"""

from __future__ import annotations

import logging
from collections.abc import Sequence

import pytest

from ai_rpg_world.application.llm.services.embedding_narrowing import (
    EmbeddingNarrower,
    EmbeddingUnavailableError,
    FallbackNarrower,
    ITextEmbedder,
)
from ai_rpg_world.application.llm.services.text_candidate_narrowing import (
    CHAR_BIGRAM_BM25,
    QWEN3_EMBEDDING_8B_OPENROUTER,
    SUPPORTED_TEXT_CANDIDATE_NARROWERS,
    CharBigramBm25Narrower,
    ITextCandidateNarrower,
    NarrowingOutcome,
    RankedCandidate,
    TextCandidate,
    create_text_candidate_narrower,
)
from ai_rpg_world.application.llm.services.vector_index import InMemoryExactVectorIndex


class _TableEmbedder(ITextEmbedder):
    """文ごとに決めたベクトルを返し、呼ばれた文を役割ごとに記録する。"""

    def __init__(self, table: dict[str, tuple[float, ...]]) -> None:
        self._table = table
        self.queries: list[str] = []
        self.documents: list[str] = []

    @property
    def name(self) -> str:
        return "table"

    def embed_queries(self, texts: Sequence[str]) -> list[tuple[float, ...]]:
        self.queries.extend(texts)
        return [self._table[t] for t in texts]

    def embed_documents(self, texts: Sequence[str]) -> list[tuple[float, ...]]:
        self.documents.extend(texts)
        return [self._table[t] for t in texts]


class _BrokenEmbedder(ITextEmbedder):
    def __init__(self, error: Exception) -> None:
        self._error = error

    @property
    def name(self) -> str:
        return "broken"

    def embed_queries(self, texts: Sequence[str]) -> list[tuple[float, ...]]:
        raise self._error

    def embed_documents(self, texts: Sequence[str]) -> list[tuple[float, ...]]:
        raise self._error


_TABLE = {
    "腹が減って動けない": (1.0, 0.0, 0.0),
    "空腹が危険域なら食料を口にする": (0.9, 0.1, 0.0),
    "ノアは川沿いルートを推した": (0.1, 1.0, 0.0),
    "浜辺では流木が手に入る": (0.3, 0.3, 0.9),
    "北の洞窟は危険だ": (-1.0, 0.0, 0.0),
}


def _candidates(*texts: str) -> list[TextCandidate]:
    return [TextCandidate(f"k{i}", t) for i, t in enumerate(texts)]


def _narrower(embedder: ITextEmbedder, **kwargs) -> EmbeddingNarrower:
    return EmbeddingNarrower(name="table_embedding", embedder=embedder, **kwargs)


class TestEmbeddingNarrowerOrdersByMeaning:
    """問い合わせ文のベクトルと向きの近い候補から並べることを保証する。"""

    def test_candidates_are_ordered_by_cosine_similarity(self) -> None:
        """問い合わせ「腹が減って動けない」に対し、向きの近い順 (空腹の信念 → 流木 → ノア) に並び、score は降順になる。"""
        candidates = _candidates(
            "ノアは川沿いルートを推した", "浜辺では流木が手に入る", "空腹が危険域なら食料を口にする"
        )

        ranked = _narrower(_TableEmbedder(_TABLE)).narrow("腹が減って動けない", candidates, top_k=3)

        assert [r.text for r in ranked] == [
            "空腹が危険域なら食料を口にする",
            "浜辺では流木が手に入る",
            "ノアは川沿いルートを推した",
        ]
        assert ranked[0].score > ranked[1].score > ranked[2].score

    def test_at_most_top_k_candidates_are_returned(self) -> None:
        """top_k=1 なら、いちばん近い 1 件だけを返す。"""
        candidates = _candidates("ノアは川沿いルートを推した", "空腹が危険域なら食料を口にする")

        ranked = _narrower(_TableEmbedder(_TABLE)).narrow("腹が減って動けない", candidates, top_k=1)

        assert [r.text for r in ranked] == ["空腹が危険域なら食料を口にする"]

    def test_candidates_pointing_away_from_the_query_are_not_returned(self) -> None:
        """向きが逆 (cosine が 0 以下) の候補は、枠が余っていても近いとは言えないので返さない。"""
        candidates = _candidates("北の洞窟は危険だ", "空腹が危険域なら食料を口にする")

        ranked = _narrower(_TableEmbedder(_TABLE)).narrow("腹が減って動けない", candidates, top_k=3)

        assert [r.text for r in ranked] == ["空腹が危険域なら食料を口にする"]

    def test_equal_scores_keep_the_candidate_order(self) -> None:
        """同じ文の候補が 2 件あれば、同じ点のまま、渡した順に両方を返す。"""
        candidates = [
            TextCandidate("first", "空腹が危険域なら食料を口にする"),
            TextCandidate("second", "空腹が危険域なら食料を口にする"),
        ]

        ranked = _narrower(_TableEmbedder(_TABLE)).narrow("腹が減って動けない", candidates, top_k=2)

        assert [r.key for r in ranked] == ["first", "second"]
        assert ranked[0].score == pytest.approx(ranked[1].score)

    def test_no_candidates_returns_empty_without_embedding(self) -> None:
        """候補が無ければ、問い合わせ文もベクトルにせずに空を返す。API の費用をかけない。"""
        embedder = _TableEmbedder(_TABLE)

        ranked = _narrower(embedder).narrow("腹が減って動けない", [], top_k=3)

        assert ranked == ()
        assert embedder.queries == []

    def test_top_k_below_one_is_rejected(self) -> None:
        """top_k に 0 を渡すと ValueError になる。"""
        with pytest.raises(ValueError, match="top_k"):
            _narrower(_TableEmbedder(_TABLE)).narrow("腹が減って動けない", [], top_k=0)

    def test_query_and_candidates_are_embedded_in_their_own_roles(self) -> None:
        """問い合わせ文は問い合わせとして、候補の文は検索される文として、別々にベクトルにする。"""
        embedder = _TableEmbedder(_TABLE)

        _narrower(embedder).narrow(
            "腹が減って動けない", _candidates("空腹が危険域なら食料を口にする"), top_k=1
        )

        assert embedder.queries == ["腹が減って動けない"]
        assert embedder.documents == ["空腹が危険域なら食料を口にする"]

    def test_name_is_the_one_given_for_the_profile(self) -> None:
        """name は profile で選ぶ名前で、埋め込みの部品の名前ではない。"""
        assert _narrower(_TableEmbedder(_TABLE)).name == "table_embedding"


class TestCandidateVectorsAreReused:
    """検索される側のベクトルを、想起のたびに作り直さないことを保証する。"""

    def test_a_candidate_text_is_embedded_only_once_across_calls(self) -> None:
        """2 回目の絞り込みでは、前に見た候補の文はベクトルにせず、新しく増えた文だけをベクトルにする。"""
        embedder = _TableEmbedder(_TABLE)
        narrower = _narrower(embedder)
        narrower.narrow("腹が減って動けない", _candidates("空腹が危険域なら食料を口にする"), top_k=3)

        narrower.narrow(
            "腹が減って動けない",
            _candidates("空腹が危険域なら食料を口にする", "浜辺では流木が手に入る"),
            top_k=3,
        )

        assert embedder.documents == ["空腹が危険域なら食料を口にする", "浜辺では流木が手に入る"]

    def test_vectors_dropped_by_the_index_are_embedded_again(self) -> None:
        """索引が持てる数を超えて捨てた文は、次に候補に出たときにベクトルにし直す。"""
        embedder = _TableEmbedder(_TABLE)
        narrower = _narrower(embedder, index=InMemoryExactVectorIndex(max_vectors=1))
        narrower.narrow("腹が減って動けない", _candidates("空腹が危険域なら食料を口にする"), top_k=1)
        narrower.narrow("腹が減って動けない", _candidates("浜辺では流木が手に入る"), top_k=1)

        narrower.narrow("腹が減って動けない", _candidates("空腹が危険域なら食料を口にする"), top_k=1)

        assert embedder.documents == [
            "空腹が危険域なら食料を口にする",
            "浜辺では流木が手に入る",
            "空腹が危険域なら食料を口にする",
        ]

    def test_candidates_beyond_the_index_capacity_are_all_ranked(self) -> None:
        """1 回の候補が索引の持てる数より多く、前に見た文と新しい文が混ざっていても、全部の候補を並べる。"""
        embedder = _TableEmbedder(_TABLE)
        narrower = _narrower(embedder, index=InMemoryExactVectorIndex(max_vectors=1))
        narrower.narrow("腹が減って動けない", _candidates("空腹が危険域なら食料を口にする"), top_k=1)

        ranked = narrower.narrow(
            "腹が減って動けない",
            _candidates(
                "浜辺では流木が手に入る", "ノアは川沿いルートを推した", "空腹が危険域なら食料を口にする"
            ),
            top_k=3,
        )

        assert len(ranked) == 3


class TestEmbedderContractViolations:
    """埋め込みの部品が数や次元の合わないベクトルを返したら、黙って並べずに埋め込みを得られなかった扱いにすることを保証する。"""

    def test_wrong_number_of_vectors_is_unavailable(self) -> None:
        """候補 2 件に対してベクトルが 1 本しか返らなければ EmbeddingUnavailableError になる。"""

        class _Short(_TableEmbedder):
            def embed_documents(self, texts: Sequence[str]) -> list[tuple[float, ...]]:
                return super().embed_documents(texts)[:1]

        with pytest.raises(EmbeddingUnavailableError, match="vectors"):
            _narrower(_Short(_TABLE)).narrow(
                "腹が減って動けない",
                _candidates("空腹が危険域なら食料を口にする", "浜辺では流木が手に入る"),
                top_k=3,
            )

    def test_mismatched_dimensions_are_unavailable(self) -> None:
        """問い合わせと候補でベクトルの次元が違えば EmbeddingUnavailableError になる。"""
        table = {**_TABLE, "浜辺では流木が手に入る": (0.3, 0.3)}

        with pytest.raises(EmbeddingUnavailableError, match="dimension"):
            _narrower(_TableEmbedder(table)).narrow(
                "腹が減って動けない", _candidates("浜辺では流木が手に入る"), top_k=3
            )

    @pytest.mark.parametrize(
        ("label", "vectors"),
        [
            ("NaN を含む", [[float("nan"), 1.0, 0.0]]),
            ("1 次元", [1.0, 0.0, 0.0]),
            ("列が 0 本", [[]]),
            ("数でない", [["a", "b", "c"]]),
        ],
    )
    def test_malformed_document_vectors_are_unavailable(self, label: str, vectors: object) -> None:
        """部品が検索される文に形や値の誤ったベクトル (NaN、1 次元、列 0 本、数でない) を返したら EmbeddingUnavailableError になる。手元のモデルは応答の検証を通らないので、ここが最後の確かめになる。"""

        class _Bad(_TableEmbedder):
            def embed_documents(self, texts: Sequence[str]):
                return vectors

        with pytest.raises(EmbeddingUnavailableError):
            _narrower(_Bad(_TABLE)).narrow(
                "腹が減って動けない", _candidates("空腹が危険域なら食料を口にする"), top_k=1
            )

    def test_a_zero_length_query_vector_is_unavailable(self) -> None:
        """問い合わせ文のベクトルが長さ 0 なら、どの候補とも比べられないので EmbeddingUnavailableError になる。何も返さずに黙らない。"""
        table = {**_TABLE, "腹が減って動けない": (0.0, 0.0, 0.0)}

        with pytest.raises(EmbeddingUnavailableError, match="zero"):
            _narrower(_TableEmbedder(table)).narrow(
                "腹が減って動けない", _candidates("空腹が危険域なら食料を口にする"), top_k=1
            )

    def test_a_zero_length_candidate_vector_is_not_returned(self) -> None:
        """候補の文のベクトルが長さ 0 なら、その候補は点 0 になり返さない。ほかの候補は並べる。"""
        table = {**_TABLE, "北の洞窟は危険だ": (0.0, 0.0, 0.0)}

        ranked = _narrower(_TableEmbedder(table)).narrow(
            "腹が減って動けない", _candidates("北の洞窟は危険だ", "空腹が危険域なら食料を口にする"), top_k=3
        )

        assert [r.text for r in ranked] == ["空腹が危険域なら食料を口にする"]

    def test_vectors_of_another_dimension_are_not_stored(self) -> None:
        """次元の合わない候補のベクトルは索引に入れない。次の想起でも同じ文をベクトルにし直し、汚れた索引で失敗し続けない。"""
        table = {**_TABLE, "浜辺では流木が手に入る": (0.3, 0.3)}
        embedder = _TableEmbedder(table)
        narrower = _narrower(embedder)
        for _ in range(2):
            with pytest.raises(EmbeddingUnavailableError, match="dimension"):
                narrower.narrow("腹が減って動けない", _candidates("浜辺では流木が手に入る"), top_k=1)

        assert embedder.documents == ["浜辺では流木が手に入る", "浜辺では流木が手に入る"]


class TestConcurrentRecalls:
    """1 ターンの中で並列に走る想起が同じ索引を使っても、候補が欠けないことを保証する。"""

    def test_a_vector_evicted_while_embedding_is_embedded_again(self) -> None:
        """この想起が新しい文をベクトルにしている間に、別の想起が前に見た文を索引から捨てても、捨てられた文をベクトルにし直して全部の候補を並べる。"""
        index = InMemoryExactVectorIndex(max_vectors=1)

        class _Interleaving(_TableEmbedder):
            other: EmbeddingNarrower | None = None

            def embed_documents(self, texts: Sequence[str]):
                if self.other is not None and texts == ["浜辺では流木が手に入る"]:
                    other, self.other = self.other, None
                    # 別の想起がこの間に走り、持てる数 1 を超えて「空腹の信念」を捨てる。
                    other.narrow("腹が減って動けない", _candidates("ノアは川沿いルートを推した"), top_k=1)
                return super().embed_documents(texts)

        embedder = _Interleaving(_TABLE)
        narrower = _narrower(embedder, index=index)
        narrower.narrow("腹が減って動けない", _candidates("空腹が危険域なら食料を口にする"), top_k=1)
        embedder.other = _narrower(_TableEmbedder(_TABLE), index=index)

        ranked = narrower.narrow(
            "腹が減って動けない",
            _candidates("空腹が危険域なら食料を口にする", "浜辺では流木が手に入る"),
            top_k=3,
        )

        assert {r.text for r in ranked} == {"空腹が危険域なら食料を口にする", "浜辺では流木が手に入る"}


class _FixedNarrower(ITextCandidateNarrower):
    def __init__(self, name: str, hits: tuple[RankedCandidate, ...]) -> None:
        self._name = name
        self._hits = hits

    @property
    def name(self) -> str:
        return self._name

    def narrow(self, query, candidates, *, top_k):
        return self._hits[:top_k]


class TestFallbackWhenEmbeddingIsUnavailable:
    """埋め込みを得られないとき、2 字組で絞り直し、縮退したことと理由を返すことを保証する。"""

    def test_the_fallback_narrows_when_the_embedder_fails(self) -> None:
        """API が失敗したら、2 字組の BM25 で同じ候補を絞った結果を返す。cue の完全一致には落とさない。"""
        primary = _narrower(_BrokenEmbedder(EmbeddingUnavailableError("HTTP 503")))
        narrower = FallbackNarrower(primary=primary, fallback=CharBigramBm25Narrower())
        candidates = _candidates("ノアは川沿いルートを推した", "空腹が危険域なら食料を口にする")

        outcome = narrower.narrow_with_outcome("空腹で動けない", candidates, top_k=3)

        assert [h.text for h in outcome.hits] == ["空腹が危険域なら食料を口にする"]
        assert outcome.narrower == CHAR_BIGRAM_BM25
        assert outcome.fallback_reason is not None and "HTTP 503" in outcome.fallback_reason

    def test_the_fallback_is_logged_as_a_warning(self, caplog: pytest.LogCaptureFixture) -> None:
        """縮退したことは警告のログにも残す。"""
        primary = _narrower(_BrokenEmbedder(EmbeddingUnavailableError("timeout")))
        narrower = FallbackNarrower(primary=primary, fallback=CharBigramBm25Narrower())

        with caplog.at_level(logging.WARNING):
            narrower.narrow("空腹", _candidates("空腹が危険域なら食料を口にする"), top_k=1)

        assert any("timeout" in r.getMessage() for r in caplog.records)

    def test_a_working_embedder_reports_no_fallback(self) -> None:
        """埋め込みが得られたら、使った手法は埋め込みの名前で、縮退の理由は None。"""
        narrower = FallbackNarrower(
            primary=_narrower(_TableEmbedder(_TABLE)), fallback=CharBigramBm25Narrower()
        )

        outcome = narrower.narrow_with_outcome(
            "腹が減って動けない", _candidates("空腹が危険域なら食料を口にする"), top_k=1
        )

        assert outcome == NarrowingOutcome(
            hits=outcome.hits, narrower="table_embedding", fallback_reason=None
        )
        assert len(outcome.hits) == 1

    def test_name_is_the_primary_name(self) -> None:
        """profile で選んだ名前 (埋め込みの側) を name として持つ。"""
        narrower = FallbackNarrower(
            primary=_narrower(_TableEmbedder(_TABLE)), fallback=CharBigramBm25Narrower()
        )

        assert narrower.name == "table_embedding"

    def test_a_long_reason_is_cut_before_the_trace(self) -> None:
        """provider が長いエラーページを返しても、縮退の理由は 300 字までに切って trace を膨らませない。"""
        primary = _narrower(_BrokenEmbedder(EmbeddingUnavailableError("x" * 5000)))
        narrower = FallbackNarrower(primary=primary, fallback=CharBigramBm25Narrower())

        outcome = narrower.narrow_with_outcome("空腹", _candidates("空腹が危険域なら食料を口にする"), top_k=1)

        assert outcome.fallback_reason is not None
        assert len(outcome.fallback_reason) <= 300

    def test_programming_errors_are_not_swallowed(self) -> None:
        """埋め込みを得られない以外の例外 (実装の誤り) は縮退せずにそのまま上げる。"""
        primary = _narrower(_BrokenEmbedder(KeyError("bug")))
        narrower = FallbackNarrower(primary=primary, fallback=CharBigramBm25Narrower())

        with pytest.raises(KeyError):
            narrower.narrow("空腹", _candidates("空腹が危険域なら食料を口にする"), top_k=1)


class TestPlainNarrowersReportTheirOwnName:
    """縮退の無い手法は、使った手法として自分の名前を返し、縮退の理由は None であることを保証する。"""

    def test_char_bigram_outcome_has_no_fallback(self) -> None:
        """2 字組の結果は、narrow と同じ候補を、自分の名前と縮退なしで返す。"""
        narrower = CharBigramBm25Narrower()
        candidates = _candidates("空腹が危険域なら食料を口にする")

        outcome = narrower.narrow_with_outcome("空腹", candidates, top_k=1)

        assert outcome == NarrowingOutcome(
            hits=narrower.narrow("空腹", candidates, top_k=1),
            narrower=CHAR_BIGRAM_BM25,
            fallback_reason=None,
        )

    def test_fixed_narrower_outcome_uses_its_name(self) -> None:
        """どの実装でも、既定の narrow_with_outcome は自分の name を使った手法として返す。"""
        hit = RankedCandidate("k", "t", 1.0)

        outcome = _FixedNarrower("fixed", (hit,)).narrow_with_outcome("q", [], top_k=1)

        assert outcome.narrower == "fixed"
        assert outcome.hits == (hit,)


class TestEmbeddingNarrowersAreChosenByName:
    """埋め込みの手法を profile の名前から組み、組めないときは最初の想起を待たずに落とすことを保証する。"""

    def test_all_embedding_names_are_supported(self) -> None:
        """API の Qwen3 と、Ruri v3 の 4 つの大きさを、profile に書ける名前として持つ。"""
        assert {
            QWEN3_EMBEDDING_8B_OPENROUTER,
            "ruri_v3_30m",
            "ruri_v3_70m",
            "ruri_v3_130m",
            "ruri_v3_310m",
        } <= SUPPORTED_TEXT_CANDIDATE_NARROWERS

    def test_qwen3_reads_the_openrouter_key_and_falls_back_to_bigrams(self) -> None:
        """OPENROUTER_API_KEY があれば、その名前を持ち、失敗時に 2 字組へ縮退する包みとして組む。"""
        narrower = create_text_candidate_narrower(
            QWEN3_EMBEDDING_8B_OPENROUTER, env={"OPENROUTER_API_KEY": "sk-or-test"}
        )

        assert isinstance(narrower, FallbackNarrower)
        assert narrower.name == QWEN3_EMBEDDING_8B_OPENROUTER

    def test_qwen3_uses_openai_api_key_with_a_warning(self, caplog: pytest.LogCaptureFixture) -> None:
        """OPENROUTER_API_KEY が無く、OPENAI_API_KEY が OpenRouter のキー (sk-or-) なら、それを使い、そのことを警告に残す。"""
        with caplog.at_level(logging.WARNING):
            narrower = create_text_candidate_narrower(
                QWEN3_EMBEDDING_8B_OPENROUTER, env={"OPENAI_API_KEY": "sk-or-v1-test"}
            )

        assert narrower.name == QWEN3_EMBEDDING_8B_OPENROUTER
        assert any("OPENAI_API_KEY" in r.getMessage() for r in caplog.records)

    def test_a_real_openai_key_is_never_sent_to_openrouter(self) -> None:
        """OPENAI_API_KEY が OpenRouter のキー (sk-or- で始まる) でなければ使わずに ValueError で止まる。OpenAI のキーを第三者のホストに送らない。"""
        with pytest.raises(ValueError, match="OPENROUTER_API_KEY"):
            create_text_candidate_narrower(
                QWEN3_EMBEDDING_8B_OPENROUTER, env={"OPENAI_API_KEY": "sk-proj-real-openai"}
            )

    @pytest.mark.parametrize("env", [{}, {"OPENROUTER_API_KEY": "EMPTY", "OPENAI_API_KEY": " "}])
    def test_qwen3_without_a_usable_key_is_rejected(self, env: dict[str, str]) -> None:
        """使えるキーが無い (空、または置き値の EMPTY) と ValueError になる。run の途中で毎回縮退し続けない。"""
        with pytest.raises(ValueError, match="OPENROUTER_API_KEY"):
            create_text_candidate_narrower(QWEN3_EMBEDDING_8B_OPENROUTER, env=env)


class TestTheChosenKeyAndModelReachTheEmbedder:
    """profile の名前から組んだとき、選んだキーとモデルが実際に埋め込みの部品に渡ることを保証する。"""

    @pytest.fixture
    def built(self, monkeypatch: pytest.MonkeyPatch) -> list[dict]:
        import ai_rpg_world.infrastructure.llm.openrouter_embedder as openrouter
        import ai_rpg_world.infrastructure.llm.ruri_embedder as ruri

        calls: list[dict] = []

        class _Recorder(ITextEmbedder):
            def __init__(self, **kwargs) -> None:
                calls.append(kwargs)

            @property
            def name(self) -> str:
                return "recorder"

            def embed_queries(self, texts):
                raise NotImplementedError

            def embed_documents(self, texts):
                raise NotImplementedError

        monkeypatch.setattr(openrouter, "OpenRouterEmbedder", _Recorder)
        monkeypatch.setattr(ruri, "RuriEmbedder", _Recorder)
        return calls

    def test_the_openrouter_key_wins_over_the_fallback_without_warning(
        self, built: list[dict], caplog: pytest.LogCaptureFixture
    ) -> None:
        """両方の変数にキーがあれば OPENROUTER_API_KEY を部品に渡し、警告は出さない。"""
        with caplog.at_level(logging.WARNING):
            create_text_candidate_narrower(
                QWEN3_EMBEDDING_8B_OPENROUTER,
                env={"OPENROUTER_API_KEY": "sk-or-named", "OPENAI_API_KEY": "sk-or-fallback"},
            )

        assert built == [{"api_key": "sk-or-named"}]
        assert not caplog.records

    def test_a_placeholder_openrouter_key_gives_way_to_the_fallback(self, built: list[dict]) -> None:
        """OPENROUTER_API_KEY が置き値の EMPTY なら、OPENAI_API_KEY の OpenRouter のキーを部品に渡す。"""
        create_text_candidate_narrower(
            QWEN3_EMBEDDING_8B_OPENROUTER,
            env={"OPENROUTER_API_KEY": "EMPTY", "OPENAI_API_KEY": "sk-or-fallback"},
        )

        assert built == [{"api_key": "sk-or-fallback"}]

    @pytest.mark.parametrize(
        ("name", "model"),
        [
            ("ruri_v3_30m", "cl-nagoya/ruri-v3-30m"),
            ("ruri_v3_70m", "cl-nagoya/ruri-v3-70m"),
            ("ruri_v3_130m", "cl-nagoya/ruri-v3-130m"),
            ("ruri_v3_310m", "cl-nagoya/ruri-v3-310m"),
        ],
    )
    def test_each_ruri_name_loads_its_model(self, built: list[dict], name: str, model: str) -> None:
        """Ruri v3 の名前ごとに、その大きさのモデル名を部品に渡し、手法の名前は profile の名前になる。名前の誤りで run の最初に読めなくなるのを防ぐ。"""
        narrower = create_text_candidate_narrower(name)

        assert built == [{"model_name": model}]
        assert narrower.name == name
