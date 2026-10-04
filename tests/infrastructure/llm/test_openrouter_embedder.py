"""OpenRouter の埋め込み API で文をベクトルにする部品の仕様 (#1454)。

通信は ``httpx.MockTransport`` で置き換え、実 API は呼ばない。失敗はすべて
``EmbeddingUnavailableError`` にそろえ、呼び出し側が 2 字組へ縮退できるようにする。
"""

from __future__ import annotations

import json

import httpx
import pytest

from ai_rpg_world.application.llm.services.embedding_narrowing import (
    EmbeddingUnavailableError,
)
from ai_rpg_world.infrastructure.llm.openrouter_embedder import OpenRouterEmbedder


def _ok(vectors: list[list[float]], *, cost: float = 1e-07, tokens: int = 10) -> dict:
    return {
        "object": "list",
        "data": [{"object": "embedding", "index": i, "embedding": v} for i, v in enumerate(vectors)],
        "usage": {"prompt_tokens": tokens, "total_tokens": tokens, "cost": cost},
    }


def _embedder(handler, **kwargs) -> OpenRouterEmbedder:
    client = httpx.Client(transport=httpx.MockTransport(handler))
    return OpenRouterEmbedder(api_key="sk-test", client=client, **kwargs)


class TestRequestShape:
    """問い合わせ文と検索される文を、モデルの決まりどおりに送ることを保証する。"""

    def test_queries_are_sent_with_the_instruction_and_documents_without(self) -> None:
        """問い合わせ文には「Instruct: …\\nQuery:」の指示文を付け、検索される文はそのまま送る (Qwen3-Embedding の決まり)。"""
        sent: list[dict] = []

        def handler(request: httpx.Request) -> httpx.Response:
            sent.append(json.loads(request.content))
            return httpx.Response(200, json=_ok([[1.0, 0.0]]))

        embedder = _embedder(handler, query_instruction="find beliefs")
        embedder.embed_queries(["空腹で動けない"])
        embedder.embed_documents(["空腹なら食べる"])

        assert sent[0]["input"] == ["Instruct: find beliefs\nQuery:空腹で動けない"]
        assert sent[1]["input"] == ["空腹なら食べる"]
        assert sent[0]["model"] == "qwen/qwen3-embedding-8b"

    def test_the_key_is_sent_as_a_bearer_token_to_the_embeddings_endpoint(self) -> None:
        """キーは Authorization ヘッダで送り、宛先は OpenRouter の /embeddings。"""
        seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            seen.append(request)
            return httpx.Response(200, json=_ok([[1.0]]))

        _embedder(handler).embed_documents(["a"])

        assert seen[0].headers["authorization"] == "Bearer sk-test"
        assert str(seen[0].url) == "https://openrouter.ai/api/v1/embeddings"

    def test_vectors_are_returned_in_the_order_of_the_texts(self) -> None:
        """応答の data が index の順に並んでいなくても、渡した文の順にベクトルを返す。"""

        def handler(request: httpx.Request) -> httpx.Response:
            body = _ok([[1.0, 0.0], [0.0, 1.0]])
            body["data"].reverse()
            return httpx.Response(200, json=body)

        vectors = _embedder(handler).embed_documents(["a", "b"])

        assert vectors.tolist() == [[1.0, 0.0], [0.0, 1.0]]

    def test_no_texts_sends_nothing(self) -> None:
        """文が 0 件なら API を呼ばずに空を返す。"""

        def handler(request: httpx.Request) -> httpx.Response:
            raise AssertionError("must not be called")

        assert len(_embedder(handler).embed_documents([])) == 0


class TestUsageIsCounted:
    """比べる run の費用を出せるよう、使ったトークンと課金を積むことを保証する。"""

    def test_tokens_and_cost_accumulate_across_calls(self) -> None:
        """2 回呼ぶと、応答の usage のトークン数と cost を足し合わせて持つ。"""

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json=_ok([[1.0]], cost=2e-07, tokens=20))

        embedder = _embedder(handler)
        embedder.embed_documents(["a"])
        embedder.embed_queries(["b"])

        assert embedder.usage.requests == 2
        assert embedder.usage.prompt_tokens == 40
        assert embedder.usage.cost == pytest.approx(4e-07)

    def test_a_broken_usage_does_not_discard_valid_vectors(self) -> None:
        """usage の値が数として読めなくても、ベクトルが正しければそのまま返し、使用量には足さない。"""

        def handler(request: httpx.Request) -> httpx.Response:
            body = _ok([[1.0, 0.0]])
            body["usage"] = {"prompt_tokens": "many", "cost": "?"}
            return httpx.Response(200, json=body)

        embedder = _embedder(handler)

        assert embedder.embed_documents(["a"]).tolist() == [[1.0, 0.0]]
        assert embedder.usage.prompt_tokens == 0

    def test_failed_requests_are_counted(self) -> None:
        """失敗した呼び出しも requests と failures に数える。縮退した試算の使用量を少なく見せない。"""

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(503, json={"error": {"message": "overloaded"}})

        embedder = _embedder(handler)
        with pytest.raises(EmbeddingUnavailableError):
            embedder.embed_documents(["a"])

        assert embedder.usage.requests == 1
        assert embedder.usage.failures == 1


class TestFailuresBecomeUnavailable:
    """通信と応答の失敗を、縮退できる EmbeddingUnavailableError にそろえることを保証する。"""

    def test_an_error_status_is_unavailable_with_the_status(self) -> None:
        """HTTP 503 が返ると、状態コードを添えた EmbeddingUnavailableError になる。"""

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(503, json={"error": {"message": "overloaded"}})

        with pytest.raises(EmbeddingUnavailableError, match="503"):
            _embedder(handler).embed_documents(["a"])

    def test_an_error_status_with_data_is_still_unavailable(self) -> None:
        """4xx や 5xx なら、本文に data があっても採らずに EmbeddingUnavailableError にする。"""

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(500, json=_ok([[1.0]]))

        with pytest.raises(EmbeddingUnavailableError, match="500"):
            _embedder(handler).embed_documents(["a"])

    @pytest.mark.parametrize(
        ("label", "data"),
        [
            ("index の重複", [{"index": 0, "embedding": [1.0]}, {"index": 0, "embedding": [0.0]}]),
            ("index が範囲外", [{"index": 0, "embedding": [1.0]}, {"index": 5, "embedding": [0.0]}]),
            ("embedding の欠け", [{"index": 0, "embedding": [1.0]}, {"index": 1}]),
        ],
    )
    def test_malformed_items_are_unavailable(self, label: str, data: list[dict]) -> None:
        """2 文に対する data の項目が、index の重複・範囲外・embedding の欠けなら EmbeddingUnavailableError になる。"""

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"data": data})

        with pytest.raises(EmbeddingUnavailableError):
            _embedder(handler).embed_documents(["a", "b"])

    def test_a_timeout_is_unavailable(self) -> None:
        """時間切れは EmbeddingUnavailableError になる。"""

        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ReadTimeout("slow", request=request)

        with pytest.raises(EmbeddingUnavailableError, match="ReadTimeout"):
            _embedder(handler).embed_documents(["a"])

    def test_an_error_body_with_status_200_is_unavailable(self) -> None:
        """200 でも本文が error だけなら EmbeddingUnavailableError になる (OpenRouter は 200 で error を返すことがある)。"""

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"error": {"message": "No endpoints found"}})

        with pytest.raises(EmbeddingUnavailableError, match="No endpoints found"):
            _embedder(handler).embed_documents(["a"])

    def test_a_wrong_number_of_vectors_is_unavailable(self) -> None:
        """2 文を送って 1 本しか返らなければ EmbeddingUnavailableError になる。"""

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json=_ok([[1.0]]))

        with pytest.raises(EmbeddingUnavailableError, match="1 vectors for 2 texts"):
            _embedder(handler).embed_documents(["a", "b"])

    def test_a_non_numeric_vector_is_unavailable(self) -> None:
        """ベクトルに数でない値が混ざれば EmbeddingUnavailableError になる。"""

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json=_ok([[1.0, "x"]]))

        with pytest.raises(EmbeddingUnavailableError):
            _embedder(handler).embed_documents(["a"])

    def test_a_body_that_is_not_json_is_unavailable(self) -> None:
        """本文が JSON でなければ EmbeddingUnavailableError になる。"""

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, content=b"<html>gateway</html>")

        with pytest.raises(EmbeddingUnavailableError):
            _embedder(handler).embed_documents(["a"])

    def test_the_key_never_appears_in_the_error(self) -> None:
        """失敗の文面にキーを出さない。trace とログに残るため。"""

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(401, json={"error": {"message": "bad key"}})

        with pytest.raises(EmbeddingUnavailableError) as info:
            _embedder(handler).embed_documents(["a"])

        assert "sk-test" not in str(info.value)


class TestConstruction:
    """組めない設定を、最初の想起まで待たずに組む時点で落とすことを保証する。"""

    def test_an_empty_key_is_rejected(self) -> None:
        """キーが空なら ValueError になる。"""
        with pytest.raises(ValueError, match="api_key"):
            OpenRouterEmbedder(api_key="")
