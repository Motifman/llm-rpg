"""手元の Ruri v3 で文をベクトルにする部品の仕様 (#1454)。

sentence-transformers は任意の依存 (``embedding-local``) で、CI には入れない。
接頭辞の付け方は差し替えたモデルで確かめ、実モデルのテストは入っているときだけ回す。
"""

from __future__ import annotations

import builtins
import importlib.util
from collections.abc import Sequence

import pytest

from ai_rpg_world.infrastructure.llm.ruri_embedder import RuriEmbedder


class _RecordingModel:
    def __init__(self) -> None:
        self.calls: list[list[str]] = []

    def encode(self, sentences: Sequence[str], **kwargs):
        self.calls.append(list(sentences))
        return [[float(len(s)), 1.0] for s in sentences]


class TestPrefixes:
    """Ruri v3 の決まりどおり、役割ごとの接頭辞を付けてからベクトルにすることを保証する。"""

    def test_queries_get_the_query_prefix(self) -> None:
        """問い合わせ文には「検索クエリ: 」を付ける。"""
        model = _RecordingModel()

        RuriEmbedder(model_name="cl-nagoya/ruri-v3-30m", model=model).embed_queries(["空腹で動けない"])

        assert model.calls == [["検索クエリ: 空腹で動けない"]]

    def test_documents_get_the_document_prefix(self) -> None:
        """検索される文には「検索文書: 」を付ける。"""
        model = _RecordingModel()

        RuriEmbedder(model_name="cl-nagoya/ruri-v3-30m", model=model).embed_documents(["空腹なら食べる"])

        assert model.calls == [["検索文書: 空腹なら食べる"]]

    def test_vectors_are_returned_as_a_float32_matrix(self) -> None:
        """モデルの返す配列を、文の数 × 次元の float32 の行列にして返す (差し替えたモデルは接頭辞込みの文字数を返す)。"""
        vectors = RuriEmbedder(model_name="m", model=_RecordingModel()).embed_documents(["ab"])

        assert vectors.tolist() == [[8.0, 1.0]]

    def test_no_texts_does_not_call_the_model(self) -> None:
        """文が 0 件ならモデルを呼ばない。"""
        model = _RecordingModel()

        assert len(RuriEmbedder(model_name="m", model=model).embed_queries([])) == 0
        assert model.calls == []

    def test_name_is_the_model_name(self) -> None:
        """name はモデルの名前。"""
        assert RuriEmbedder(model_name="cl-nagoya/ruri-v3-30m", model=_RecordingModel()).name == (
            "cl-nagoya/ruri-v3-30m"
        )


class TestMissingDependency:
    """依存が入っていないとき、最初の想起まで待たずに、入れ方を添えて組む時点で落とすことを保証する。"""

    def test_missing_sentence_transformers_names_the_extra(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """sentence-transformers が import できなければ、embedding-local の入れ方を添えた RuntimeError になる。"""
        real_import = builtins.__import__

        def fake_import(name, *args, **kwargs):
            if name.startswith("sentence_transformers"):
                raise ImportError("No module named 'sentence_transformers'")
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", fake_import)

        with pytest.raises(RuntimeError, match="embedding-local"):
            RuriEmbedder(model_name="cl-nagoya/ruri-v3-30m")


@pytest.mark.skipif(
    importlib.util.find_spec("sentence_transformers") is None,
    reason="sentence-transformers is an optional dependency (uv sync --extra embedding-local)",
)
@pytest.mark.slow
class TestRealRuriModel:
    """実モデル (ruri-v3-30m) で、語の重なりの少ない言い換えでも意味の近い信念が上に来ることを確かめる。"""

    def test_a_hunger_situation_ranks_the_food_belief_first(self) -> None:
        """「腹が減って力が出ない」に対し、2 字組の重なりの無い「空腹が危険域なら食料を口にする」が、人や道の信念より近い。"""
        from ai_rpg_world.application.llm.services.embedding_narrowing import EmbeddingNarrower
        from ai_rpg_world.application.llm.services.text_candidate_narrowing import TextCandidate

        try:
            embedder = RuriEmbedder(model_name="cl-nagoya/ruri-v3-30m")
        except OSError as exc:
            pytest.skip(f"the model could not be fetched: {exc}")
        narrower = EmbeddingNarrower(name="ruri_v3_30m", embedder=embedder)
        candidates = [
            TextCandidate("road", "ノアは川沿いルートを推した"),
            TextCandidate("food", "空腹が危険域なら食料を口にする"),
            TextCandidate("tool", "カイは火起こし道具一式を持っている"),
        ]

        ranked = narrower.narrow("腹が減って力が出ない", candidates, top_k=3)

        assert ranked[0].key == "food"
