"""新しい文に近い候補を上位 K 件に絞る仕様 (#1453)。

絞り込みは文だけを見る。tags や cue、ゲームの ID は受け取らない。手法は
``ITextCandidateNarrower`` の実装として差し替える。最初の実装は文字の 2 字組の
BM25 で、形態素解析も辞書も外部 API も要らない。
"""

from __future__ import annotations

import pytest

from ai_rpg_world.application.llm.services.text_candidate_narrowing import (
    CHAR_BIGRAM_BM25,
    CharBigramBm25Narrower,
    ITextCandidateNarrower,
    TextCandidate,
    create_text_candidate_narrower,
)


def _keys(ranked) -> list[str]:
    return [r.key for r in ranked]


class TestCharBigramBm25FindsRephrasedSentences:
    """言い回しだけ違う同じ内容の文を、無関係な文より上に並べることを保証する。"""

    def test_a_rephrased_sentence_is_within_the_top_k(self) -> None:
        """「腐った貝を食べると毒に当たる」に対し、「腐った貝は食べると毒になる」が
        結論の違う同じ主題の文や無関係な信念に埋もれず上位 2 件に入る。"""
        candidates = [
            TextCandidate("a", "北の洞窟は危険だ"),
            TextCandidate("same-topic", "新鮮な貝を食べると元気になる"),
            TextCandidate("b", "エイダは枯れ葉の入手に協力的だ"),
            TextCandidate("c", "浜辺では流木が手に入る"),
            TextCandidate("target", "腐った貝は食べると毒になる"),
            TextCandidate("d", "雨の日は焚き火が消えやすい"),
            TextCandidate("e", "ノアは嘘をつかない"),
        ]

        ranked = CharBigramBm25Narrower().narrow(
            "腐った貝を食べると毒に当たる", candidates, top_k=2
        )

        assert "target" in _keys(ranked)

    def test_candidates_are_ordered_from_closest(self) -> None:
        """共有する 2 字組が多い候補ほど上に来て、score は降順に並ぶ。"""
        candidates = [
            TextCandidate("far", "腐った木は燃えにくい"),
            TextCandidate("near", "腐った貝を食べると毒に当たる"),
        ]

        ranked = CharBigramBm25Narrower().narrow(
            "腐った貝を食べると毒に当たる", candidates, top_k=5
        )

        assert _keys(ranked) == ["near", "far"]
        assert ranked[0].score > ranked[1].score

    def test_punctuation_spaces_and_width_do_not_change_the_score(self) -> None:
        """句読点・空白・全角半角の違いだけの文は、違いの無い文と同じ score になる。"""
        candidates = [
            TextCandidate("x", "洞窟はinteractで調べられない"),
            TextCandidate("y", "浜辺は安全だ"),
        ]
        plain = CharBigramBm25Narrower().narrow(
            "洞窟はinteractで調べられない", candidates, top_k=2
        )
        noisy = CharBigramBm25Narrower().narrow(
            "洞窟は　ｉｎｔｅｒａｃｔ で、調べられない。", candidates, top_k=2
        )

        assert plain[0].score == pytest.approx(noisy[0].score)


class TestCharBigramBm25LimitsTheCandidates:
    """返す件数と、返さない候補を保証する。"""

    def test_never_returns_more_than_top_k(self) -> None:
        """近い候補が K 件を超えてあっても、K 件で切る。"""
        candidates = [TextCandidate(str(i), f"洞窟は危険だ{i}") for i in range(10)]

        ranked = CharBigramBm25Narrower().narrow("洞窟は危険だ", candidates, top_k=3)

        assert len(ranked) == 3

    def test_a_candidate_sharing_no_bigram_is_not_returned(self) -> None:
        """2 字組を 1 つも共有しない候補は、K 件に満たなくても並べない。"""
        candidates = [
            TextCandidate("near", "洞窟は危険だ"),
            TextCandidate("unrelated", "ノアは嘘をつかない"),
        ]

        ranked = CharBigramBm25Narrower().narrow("北の洞窟は危険だ", candidates, top_k=5)

        assert _keys(ranked) == ["near"]

    def test_ties_keep_the_input_order(self) -> None:
        """同じ score の候補は、渡した順に並ぶ。"""
        candidates = [
            TextCandidate("first", "洞窟は危険だ"),
            TextCandidate("second", "洞窟は危険だ"),
        ]

        ranked = CharBigramBm25Narrower().narrow("洞窟は危険だ", candidates, top_k=5)

        assert _keys(ranked) == ["first", "second"]

    def test_no_candidates_returns_empty(self) -> None:
        """候補が無ければ空を返す。"""
        assert CharBigramBm25Narrower().narrow("洞窟は危険だ", [], top_k=3) == ()

    def test_a_query_of_only_punctuation_returns_empty(self) -> None:
        """記号だけの文は比べる文字が無いので、候補があっても空を返す。"""
        assert CharBigramBm25Narrower().narrow(
            "。、！", [TextCandidate("x", "洞窟")], top_k=3
        ) == ()

    def test_a_one_character_query_is_compared_by_the_character(self) -> None:
        """1 文字の文は 2 字組を作れないので、その 1 文字で比べる。"""
        ranked = CharBigramBm25Narrower().narrow(
            "毒", [TextCandidate("x", "毒"), TextCandidate("y", "薬")], top_k=5
        )

        assert _keys(ranked) == ["x"]

    def test_top_k_below_one_is_rejected(self) -> None:
        """K が 1 未満なら ValueError。0 件の絞り込みを黙って返さない。"""
        with pytest.raises(ValueError):
            CharBigramBm25Narrower().narrow("洞窟", [TextCandidate("x", "洞窟")], top_k=0)


class TestTheNarrowerIsChosenByName:
    """手法を config の名前から選べることを保証する。"""

    def test_the_bm25_narrower_is_created_by_its_name(self) -> None:
        """``char_bigram_bm25`` を渡すと BM25 の実装が返り、その名前を持つ。"""
        narrower = create_text_candidate_narrower(CHAR_BIGRAM_BM25)

        assert isinstance(narrower, ITextCandidateNarrower)
        assert narrower.name == CHAR_BIGRAM_BM25

    def test_an_unknown_name_is_rejected(self) -> None:
        """知らない名前は ValueError。BM25 へ黙って縮退しない。"""
        with pytest.raises(ValueError):
            create_text_candidate_narrower("embedding_typo")
