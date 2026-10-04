"""形態素解析で中身のある語だけを取り出し、BM25 の語にする仕様 (#1498)。

2 字組の BM25 は語尾も語と同じに数え、1 文字の語を比べられない。語に分ける手法は、
品詞で助詞・助動詞・記号・数を外し、動詞と形容詞を原形にそろえる。辞書に無い名前は
解析器が名詞として切り出すので残る。
"""

from __future__ import annotations

import pytest

from ai_rpg_world.application.llm.services.morpheme_analysis import (
    JanomeAnalyzer,
    MorphemeAnalyzer,
    SudachiAnalyzer,
)
from ai_rpg_world.application.llm.services.text_candidate_narrowing import (
    CHAR_BIGRAM_BM25,
    JANOME_BM25,
    SUDACHI_BM25,
    TextCandidate,
    create_text_candidate_narrower,
)

ANALYZERS = [
    pytest.param(JanomeAnalyzer(), id="janome"),
    pytest.param(SudachiAnalyzer(), id="sudachi"),
]
MORPHEME_NARROWERS = [JANOME_BM25, SUDACHI_BM25]


@pytest.mark.parametrize("analyzer", ANALYZERS)
class TestContentWordsKeepOnlyWordsWithContent:
    """助詞・助動詞・記号・数を外し、中身のある語を原形で残すことを保証する。"""

    def test_particles_and_auxiliaries_are_dropped(self, analyzer: MorphemeAnalyzer) -> None:
        """「ノアは廃屋にいた」から「は」「に」「た」は残らず、「ノア」と「廃屋」は残る。"""
        words = analyzer.content_words("ノアは廃屋にいた")

        assert {"ノア", "廃屋"} <= set(words)
        assert not {"は", "に", "た"} & set(words)

    def test_inflected_verbs_become_the_same_word(self, analyzer: MorphemeAnalyzer) -> None:
        """「焼いた」も「焼く」も、原形の「焼く」1 語になる。"""
        assert analyzer.content_words("焼いた") == analyzer.content_words("焼く") == ["焼く"]

    def test_numbers_are_dropped(self, analyzer: MorphemeAnalyzer) -> None:
        """「空腹82」の 82 は語に残らない。体の値は場面ごとに変わり、信念の文と当てる意味が無い。"""
        assert analyzer.content_words("空腹82") == ["空腹"]

    def test_a_word_after_symbols_keeps_its_part_of_speech(self, analyzer: MorphemeAnalyzer) -> None:
        """記号の並び「）。」のすぐ後の「水」も、前後の「空腹」「飲む」と並んで語として残る。区切らずに解析すると Janome は「水」を接尾辞と読んで落とした。"""
        words = analyzer.content_words("空腹82/100（危険域）。水を飲んだ")

        assert {"空腹", "水", "飲む"} <= set(words)

    def test_an_invented_name_is_kept(self, analyzer: MorphemeAnalyzer) -> None:
        """辞書に無い作った人名「ザルクート」は 1 語のまま残る。"""
        assert "ザルクート" in analyzer.content_words("ザルクートが来た")

    def test_width_and_case_do_not_change_the_words(self, analyzer: MorphemeAnalyzer) -> None:
        """全角と大文字だけが違う文は、同じ語になり、「HP」も語として残る。"""
        words = analyzer.content_words("ＨＰが減った")

        assert words == analyzer.content_words("hpが減った")
        assert {w.lower() for w in words} >= {"hp"}


@pytest.mark.parametrize("name", MORPHEME_NARROWERS)
class TestMorphemeBm25Narrowing:
    """語に分けた BM25 が、2 字組で比べられなかった語で候補を当てることを保証する。"""

    def test_a_single_character_word_finds_its_belief(self, name: str) -> None:
        """「水を飲んだ」で、「水」を含む信念が引ける。2 字組では「水」だけを共有する文は当たらない。"""
        candidates = [
            TextCandidate("water", "水は湧き水の口で汲める"),
            TextCandidate("other", "浜辺では流木が手に入る"),
        ]

        ranked = create_text_candidate_narrower(name).narrow("水を飲んだ", candidates, top_k=2)

        assert [r.key for r in ranked] == ["water"]

    def test_shared_word_endings_alone_do_not_match(self, name: str) -> None:
        """「海で貝を拾っていた」で引くと、語尾「ていた」と助詞しか重ならない「畑で芋を耕していた」は返らない。"""
        candidates = [
            TextCandidate("ending-only", "畑で芋を耕していた"),
            TextCandidate("content", "浜辺で貝を拾っていた"),
        ]

        ranked = create_text_candidate_narrower(name).narrow("海で貝を拾っていた", candidates, top_k=2)

        assert [r.key for r in ranked] == ["content"]

    def test_a_query_without_content_words_returns_nothing(self, name: str) -> None:
        """問い合わせ文に中身のある語が無ければ、候補があっても空を返す。"""
        candidates = [TextCandidate("x", "ノアは嘘をつかない")]

        assert create_text_candidate_narrower(name).narrow("、。", candidates, top_k=1) == ()

    def test_top_k_below_one_is_rejected(self, name: str) -> None:
        """top_k に 0 を渡すと ValueError になる。"""
        with pytest.raises(ValueError, match="top_k"):
            create_text_candidate_narrower(name).narrow("水", [TextCandidate("x", "水")], top_k=0)

    def test_the_narrower_reports_its_profile_name(self, name: str) -> None:
        """profile の名前で組んだ実装は、同じ名前を返す。trace の narrower に残る名前になる。"""
        assert create_text_candidate_narrower(name).name == name


def test_an_analyzer_that_cannot_load_fails_when_it_is_built(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """解析器や辞書を読めないと、手法を組んだ時点で RuntimeError になる。最初の想起まで遅れない。"""
    from ai_rpg_world.application.llm.services import morpheme_analysis

    def broken() -> None:
        raise ImportError("no dictionary")

    monkeypatch.setattr(morpheme_analysis, "_sudachi", broken)

    with pytest.raises(RuntimeError, match="SudachiPy"):
        create_text_candidate_narrower(SUDACHI_BM25)


def test_the_bigram_narrower_misses_a_single_character_word() -> None:
    """2 字組の BM25 は、「水」だけを共有する文を当てない。語に分ける手法との違いの対照。"""
    candidates = [TextCandidate("water", "水は湧き水の口で汲める")]

    ranked = create_text_candidate_narrower(CHAR_BIGRAM_BM25).narrow("水を飲んだ", candidates, top_k=1)

    assert ranked == ()
