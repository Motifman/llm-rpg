"""文のベクトルを持ち、候補の中から近い順に引く索引の仕様 (#1454)。

索引は差し替える。既定は手元のメモリで全件を行列積で比べる実装。件数が増えたら
近似検索の索引 (sqlite-vec、faiss など) に替えても、絞り込みの部品は変えない。
"""

from __future__ import annotations

import logging
import warnings

import numpy as np
import pytest

from ai_rpg_world.application.llm.services.vector_index import (
    InMemoryExactVectorIndex,
    IVectorIndex,
    VectorDimensionMismatchError,
)


def _unit(*values: float) -> np.ndarray:
    v = np.asarray(values, dtype=np.float32)
    return v / np.linalg.norm(v)


def _index(**kwargs) -> InMemoryExactVectorIndex:
    index = InMemoryExactVectorIndex(**kwargs)
    index.add(
        ["food", "road", "wood", "cave"],
        np.vstack([_unit(0.9, 0.1, 0.0), _unit(0.1, 1.0, 0.0), _unit(0.3, 0.3, 0.9), _unit(-1.0, 0.0, 0.0)]),
    )
    return index


class TestSearchAmongCandidates:
    """渡した候補の中だけから、問い合わせのベクトルと向きの近い順に返すことを保証する。"""

    def test_hits_are_positions_in_the_candidates_ordered_by_score(self) -> None:
        """返すのは候補の並びの中の位置と点で、点の降順に並ぶ。"""
        hits = _index().search(_unit(1.0, 0.0, 0.0), ["road", "wood", "food"], top_k=3)

        assert [position for position, _ in hits] == [2, 1, 0]
        assert hits[0][1] > hits[1][1] > hits[2][1]

    def test_texts_outside_the_candidates_are_not_returned(self) -> None:
        """索引に入っていても、候補に無い文は返さない。"""
        hits = _index().search(_unit(1.0, 0.0, 0.0), ["road"], top_k=3)

        assert [position for position, _ in hits] == [0]

    def test_at_most_top_k_hits(self) -> None:
        """top_k=1 なら 1 件だけ返す。"""
        hits = _index().search(_unit(1.0, 0.0, 0.0), ["road", "food"], top_k=1)

        assert [position for position, _ in hits] == [1]

    def test_non_positive_scores_are_not_returned(self) -> None:
        """向きが逆 (点が 0 以下) の候補は返さない。"""
        hits = _index().search(_unit(1.0, 0.0, 0.0), ["cave", "food"], top_k=3)

        assert [position for position, _ in hits] == [1]

    def test_equal_scores_keep_the_candidate_order(self) -> None:
        """同じ文が候補に 2 回あれば、同じ点のまま渡した順に返す。"""
        hits = _index().search(_unit(1.0, 0.0, 0.0), ["food", "food"], top_k=2)

        assert [position for position, _ in hits] == [0, 1]

    def test_an_orthogonal_candidate_scores_zero_and_is_not_returned(self) -> None:
        """向きが直交する (点がちょうど 0) 候補も、近いとは言えないので返さない。"""
        index = InMemoryExactVectorIndex()
        index.add(["side", "food"], np.vstack([_unit(0.0, 1.0, 0.0), _unit(1.0, 0.0, 0.0)]))

        hits = index.search(_unit(1.0, 0.0, 0.0), ["side", "food"], top_k=3)

        assert [position for position, _ in hits] == [1]

    def test_many_equal_scores_keep_the_candidate_order(self) -> None:
        """同じ点の候補が 20 件あっても、渡した順のまま返す。"""
        index = InMemoryExactVectorIndex()
        texts = [f"t{i}" for i in range(20)]
        index.add(texts, np.vstack([_unit(1.0, 0.0, 0.0)] * 20))

        hits = index.search(_unit(1.0, 0.0, 0.0), list(reversed(texts)), top_k=20)

        assert [position for position, _ in hits] == list(range(20))

    def test_a_candidate_not_in_the_index_is_rejected(self) -> None:
        """入れていない文を候補に渡すと KeyError になる。点の無い候補を黙って落とさない。"""
        with pytest.raises(KeyError):
            _index().search(_unit(1.0, 0.0, 0.0), ["unknown"], top_k=1)


class TestStoredVectors:
    """入れたベクトルを覚え、まだ無い文を答え、持てる数を超えたら古いものから捨てることを保証する。"""

    def test_missing_lists_texts_not_yet_stored_once_each(self) -> None:
        """まだ入れていない文を、重ねずに、渡した順で返す。"""
        assert _index().missing(["food", "new", "new", "other"]) == ["new", "other"]

    def test_the_least_recently_searched_vector_is_dropped_after_a_search(self) -> None:
        """持てる数を超えると、検索のあとで、いちばん長く使っていない文から捨てる。"""
        index = _index(max_vectors=2)

        index.search(_unit(1.0, 0.0, 0.0), ["road", "food"], top_k=1)

        assert index.missing(["food", "road", "wood", "cave"]) == ["wood", "cave"]

    def test_candidates_beyond_the_capacity_are_all_searched(self) -> None:
        """1 回の候補が持てる数より多くても、その検索では全部の候補を比べる。"""
        index = _index(max_vectors=1)

        hits = index.search(_unit(1.0, 0.0, 0.0), ["road", "wood", "food"], top_k=3)

        assert len(hits) == 3

    def test_a_dimension_mismatch_is_rejected(self) -> None:
        """入れたベクトルと次元の違う問い合わせは ValueError になる。"""
        with pytest.raises(ValueError, match="dimension"):
            _index().search(_unit(1.0, 0.0), ["food"], top_k=1)

    def test_stored_vectors_of_mixed_dimensions_are_a_dimension_mismatch(self) -> None:
        """候補に、入れたときの次元が違うベクトルが混ざっていれば VectorDimensionMismatchError になる。"""
        index = InMemoryExactVectorIndex()
        index.add(["a"], np.vstack([_unit(1.0, 0.0, 0.0)]))
        index.add(["b"], np.vstack([_unit(1.0, 0.0)]))

        with pytest.raises(VectorDimensionMismatchError):
            index.search(_unit(1.0, 0.0, 0.0), ["a", "b"], top_k=2)

    def test_non_finite_scores_are_rejected(self) -> None:
        """入れたベクトルに NaN があり点が有限でなければ FloatingPointError になる。NaN のまま並べない。"""
        index = InMemoryExactVectorIndex()
        index.add(["a"], np.asarray([[float("nan"), 0.0, 0.0]], dtype=np.float32))

        with pytest.raises(FloatingPointError):
            index.search(_unit(1.0, 0.0, 0.0), ["a"], top_k=1)

    def test_candidates_beyond_the_capacity_are_warned(self, caplog: pytest.LogCaptureFixture) -> None:
        """1 回の候補が持てる数を超えると、毎回ベクトルを作り直すことになるので警告を残す。"""
        index = _index(max_vectors=2)

        with caplog.at_level(logging.WARNING):
            index.search(_unit(1.0, 0.0, 0.0), ["road", "wood", "food"], top_k=1)

        assert any("max_vectors" in r.getMessage() for r in caplog.records)

    def test_vectors_and_texts_must_have_the_same_count(self) -> None:
        """文の数とベクトルの数が違えば ValueError になる。"""
        with pytest.raises(ValueError, match="count"):
            InMemoryExactVectorIndex().add(["a", "b"], np.vstack([_unit(1.0, 0.0)]))

    def test_capacity_below_one_is_rejected(self) -> None:
        """持てる数に 0 を渡すと ValueError になる。"""
        with pytest.raises(ValueError, match="max_vectors"):
            InMemoryExactVectorIndex(max_vectors=0)

    def test_it_is_a_vector_index(self) -> None:
        """差し替えの型 IVectorIndex の実装である。"""
        assert isinstance(InMemoryExactVectorIndex(), IVectorIndex)


class TestNoSpuriousWarnings:
    """正しい値が出る比較で、numpy の誤った浮動小数点の警告を run のログに出さないことを保証する。"""

    def test_a_search_over_many_dimensions_raises_no_runtime_warning(self) -> None:
        """4096 次元・300 件の比較でも RuntimeWarning を出さない (macOS の Accelerate では行列積が値は正しいまま警告を出す)。"""
        rng = np.random.default_rng(0)
        matrix = rng.standard_normal((300, 4096)).astype(np.float32)
        matrix /= np.linalg.norm(matrix, axis=1, keepdims=True)
        texts = [f"t{i}" for i in range(300)]
        index = InMemoryExactVectorIndex()
        index.add(texts, matrix)

        with warnings.catch_warnings():
            warnings.simplefilter("error")
            hits = index.search(matrix[7], texts, top_k=1)

        assert hits[0][0] == 7
