"""Jev アダプタが、質問の束を 1 回で送り、答えを型へ写すことを保証する。

## 本物の httpx を通す

送る形が合っているかは、リクエストを組み立てるところまで通さないと分からない。
自前の偽物に差し替えると、組み立てを飛ばしたまま緑になる (design_decisions
#41)。``httpx.MockTransport`` を使い、**実際に組み立てた HTTP リクエストを
検査する**。

## 失敗を成功へ潰さない

timeout / HTTP エラー / スキーマ不一致は例外にする。既定値を返すと、判断を
得られなかったことと「判断の結果がこうだった」ことが同じになり、呼び出し側は
縮退したことに気づけない (design_decisions #5)。
"""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

import httpx
import pytest

from ai_rpg_world.application.llm.ports.typed_judgment_port import (
    ChoiceQuestion,
    JudgmentSource,
    NoulQuestion,
    ScoreQuestion,
    TypedJudgmentUnavailableException,
)
from ai_rpg_world.infrastructure.llm.jev_typed_judgment_adapter import (
    JevTypedJudgmentAdapter,
)

_ENDPOINT = "https://openrouter.ai/api/alpha/decisions"


def _adapter(
    handler: Callable[[httpx.Request], httpx.Response],
    *,
    retry_attempts: int = 0,
    sleeps: list | None = None,
) -> JevTypedJudgmentAdapter:
    return JevTypedJudgmentAdapter(
        api_key="sk-or-v1-test",
        endpoint=_ENDPOINT,
        model="typesafe/jev-1.13",
        timeout_seconds=5.0,
        rate_limit_retry_attempts=retry_attempts,
        rate_limit_retry_base_sleep=0.0,
        sleep=(sleeps.append if sleeps is not None else (lambda _seconds: None)),
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )


def _answers(body: dict) -> Callable[[httpx.Request], httpx.Response]:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=body)

    return handler


class TestTheRequestCarriesEveryQuestionAtOnce:
    """同じ state を使う質問が 1 回のリクエストにまとまることを保証する。"""

    def test_three_questions_are_sent_in_one_request(self) -> None:
        """3 問渡すと HTTP 呼び出しは 1 回で、questions に 3 件すべてが載る。"""
        sent: list[dict[str, Any]] = []

        def handler(request: httpx.Request) -> httpx.Response:
            sent.append(json.loads(request.content))
            return httpx.Response(
                200,
                json={
                    "answers": {
                        "memo_0": {"type": "noul", "noul": 0.71},
                        "memo_1": {"type": "noul", "noul": 0.07},
                        "memo_2": {"type": "noul", "noul": 0.07},
                    }
                },
            )

        _adapter(handler).judge(
            {"action": "麦を刈った"},
            {
                "memo_0": NoulQuestion(instructions="a"),
                "memo_1": NoulQuestion(instructions="b"),
                "memo_2": NoulQuestion(instructions="c"),
            },
        )

        assert len(sent) == 1
        assert set(sent[0]["questions"]) == {"memo_0", "memo_1", "memo_2"}

    def test_the_request_names_the_model_and_carries_the_state(self) -> None:
        """model と state が、渡したまま body に載る。"""
        sent: list[dict[str, Any]] = []

        def handler(request: httpx.Request) -> httpx.Response:
            sent.append(json.loads(request.content))
            return httpx.Response(200, json={"answers": {"q": {"type": "noul", "noul": 0.5}}})

        _adapter(handler).judge({"actor": "アオイ"}, {"q": NoulQuestion(instructions="a")})

        assert sent[0]["model"] == "typesafe/jev-1.13"
        assert sent[0]["state"] == {"actor": "アオイ"}

    def test_the_api_key_goes_in_the_authorization_header(self) -> None:
        """キーは Authorization ヘッダで送り、body や URL に混ぜない。"""
        seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            seen.append(request)
            return httpx.Response(200, json={"answers": {"q": {"type": "noul", "noul": 0.5}}})

        _adapter(handler).judge("x", {"q": NoulQuestion(instructions="a")})

        assert seen[0].headers["authorization"] == "Bearer sk-or-v1-test"
        assert "sk-or-v1-test" not in str(seen[0].url)
        assert b"sk-or-v1-test" not in seen[0].content


class TestEachQuestionTypeIsWrittenInTheWireForm:
    """3 種の質問が、API の受け取る形に変換されることを保証する。"""

    def _sent_question(self, question: Any) -> dict:
        sent: list[dict[str, Any]] = []

        def handler(request: httpx.Request) -> httpx.Response:
            sent.append(json.loads(request.content))
            return httpx.Response(
                200,
                json={
                    "answers": {
                        "q": {
                            "type": "noul",
                            "noul": 0.5,
                        }
                        if isinstance(question, NoulQuestion)
                        else {
                            "type": "choice",
                            "choice": "a",
                            "probabilities": {"a": 1.0},
                            "confidence": 1.0,
                        }
                        if isinstance(question, ChoiceQuestion)
                        else {
                            "type": "score",
                            "score": 0.0,
                            "legend": {"0": "低"},
                            "probabilities": {"0": 1.0},
                            "confidence": 1.0,
                        }
                    }
                },
            )

        _adapter(handler).judge("x", {"q": question})
        return sent[0]["questions"]["q"]

    def test_a_noul_carries_what_true_and_false_mean(self) -> None:
        """Noul は criteria に true / false の意味を載せる。"""
        written = self._sent_question(
            NoulQuestion(
                instructions="果たされたか",
                true_means="果たされた",
                false_means="まだ",
            )
        )

        assert written == {
            "type": "noul",
            "instructions": "果たされたか",
            "criteria": {"true": "果たされた", "false": "まだ"},
        }

    def test_a_noul_without_criteria_omits_the_key(self) -> None:
        """真偽の意味を書かなければ criteria を送らない (空の辞書を送らない)。"""
        written = self._sent_question(NoulQuestion(instructions="果たされたか"))

        assert written == {"type": "noul", "instructions": "果たされたか"}

    def test_a_choice_carries_each_option_with_its_meaning(self) -> None:
        """Choice は criteria に選択肢名 → 意味を載せる。"""
        written = self._sent_question(
            ChoiceQuestion(
                instructions="どの操作か",
                options={"reap_wheat": "麦を刈る", "none": None},
            )
        )

        assert written == {
            "type": "choice",
            "instructions": "どの操作か",
            "criteria": {"reap_wheat": "麦を刈る", "none": None},
        }

    def test_a_score_carries_its_levels_in_order(self) -> None:
        """Score は criteria に段階を低い方から並べた配列で載せる。"""
        written = self._sent_question(ScoreQuestion(instructions="切迫度", levels=["低", "中", "高"]))

        assert written == {
            "type": "score",
            "instructions": "切迫度",
            "criteria": ["低", "中", "高"],
        }


class TestTheAnswerIsMappedToTheResultType:
    """応答が JudgmentResult へ写ることを保証する。"""

    def test_a_noul_answer_has_no_confidence(self) -> None:
        """Noul の応答は確率だけなので、confidence は None になる。"""
        answers = _adapter(_answers({"answers": {"q": {"type": "noul", "noul": 0.42}}})).judge(
            "x", {"q": NoulQuestion(instructions="a")}
        )

        assert answers["q"].value == 0.42
        assert answers["q"].confidence is None
        assert answers["q"].probabilities == {}

    def test_a_choice_answer_keeps_its_distribution_and_confidence(self) -> None:
        """Choice は選んだ名前・分布・confidence をそのまま持つ。"""
        answers = _adapter(
            _answers(
                {
                    "answers": {
                        "q": {
                            "type": "choice",
                            "choice": "reap_wheat",
                            "probabilities": {"reap_wheat": 0.97, "none": 0.03},
                            "confidence": 0.96,
                        }
                    }
                }
            )
        ).judge(
            "x",
            {"q": ChoiceQuestion(instructions="a", options={"reap_wheat": None})},
        )

        assert answers["q"].value == "reap_wheat"
        assert answers["q"].probabilities == {"reap_wheat": 0.97, "none": 0.03}
        assert answers["q"].confidence == 0.96

    def test_a_score_answer_keeps_the_expected_level(self) -> None:
        """Score は段階の期待値を value に持つ。"""
        answers = _adapter(
            _answers(
                {
                    "answers": {
                        "q": {
                            "type": "score",
                            "score": 1.6,
                            "legend": {"0": "低", "1": "高"},
                            "probabilities": {"0": 0.3, "1": 0.7},
                            "confidence": 0.78,
                        }
                    }
                }
            )
        ).judge("x", {"q": ScoreQuestion(instructions="a", levels=["低", "高"])})

        assert answers["q"].value == 1.6
        assert answers["q"].confidence == 0.78

    def test_every_answer_is_labelled_as_coming_from_jev(self) -> None:
        """source が jev になり、stub の結果と trace 上で区別できる。"""
        answers = _adapter(_answers({"answers": {"q": {"type": "noul", "noul": 0.42}}})).judge(
            "x", {"q": NoulQuestion(instructions="a")}
        )

        assert answers["q"].source is JudgmentSource.JEV
        assert answers["q"].latency_ms >= 0.0


class TestFailuresAreRaisedInsteadOfDefaulted:
    """判断を得られなかったことが、判断の結果に化けないことを保証する。"""

    def test_a_missing_answer_is_a_failure(self) -> None:
        """要求した質問の答えが返らなければ例外になる (黙って欠かさない)。"""
        adapter = _adapter(_answers({"answers": {"q": {"type": "noul", "noul": 0.5}}}))

        with pytest.raises(TypedJudgmentUnavailableException):
            adapter.judge(
                "x",
                {
                    "q": NoulQuestion(instructions="a"),
                    "missing": NoulQuestion(instructions="b"),
                },
            )

    def test_an_answer_of_the_wrong_type_is_a_failure(self) -> None:
        """Choice を問って Noul が返るような食い違いは例外になる。"""
        adapter = _adapter(_answers({"answers": {"q": {"type": "noul", "noul": 0.5}}}))

        with pytest.raises(TypedJudgmentUnavailableException):
            adapter.judge("x", {"q": ChoiceQuestion(instructions="a", options={"o": None})})

    def test_an_answer_whose_label_disagrees_with_its_payload_is_a_failure(
        self,
    ) -> None:
        """型の札と中身が食い違う答えは例外になる。

        Noul を問って ``{"type": "choice", "noul": 0.5}`` が返る形。値は読める
        ので、**型の札を見ていないと通ってしまう**。札と中身が食い違うのは
        接続先の契約が変わった合図なので、黙って読み進めない。
        """
        adapter = _adapter(_answers({"answers": {"q": {"type": "choice", "noul": 0.5}}}))

        with pytest.raises(TypedJudgmentUnavailableException):
            adapter.judge("x", {"q": NoulQuestion(instructions="a")})

    def test_an_http_error_is_a_failure(self) -> None:
        """401 のような HTTP エラーは例外になる。"""
        adapter = _adapter(lambda _request: httpx.Response(401, json={"error": {"message": "no"}}))

        with pytest.raises(TypedJudgmentUnavailableException):
            adapter.judge("x", {"q": NoulQuestion(instructions="a")})

    def test_the_api_key_is_not_in_the_failure_message(self) -> None:
        """失敗の文面にキーを載せない。trace と report に残る文面なので。"""
        adapter = _adapter(lambda _request: httpx.Response(401, text="unauthorized"))

        with pytest.raises(TypedJudgmentUnavailableException) as caught:
            adapter.judge("x", {"q": NoulQuestion(instructions="a")})

        assert "sk-or-v1-test" not in str(caught.value)

    def test_a_timeout_is_a_failure(self) -> None:
        """timeout は例外になる。既定値へ落ちない。"""

        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ReadTimeout("too slow", request=request)

        with pytest.raises(TypedJudgmentUnavailableException):
            _adapter(handler).judge("x", {"q": NoulQuestion(instructions="a")})

    def test_a_body_that_is_not_json_is_a_failure(self) -> None:
        """JSON として読めない応答は例外になる。"""
        adapter = _adapter(lambda _request: httpx.Response(200, text="<html>"))

        with pytest.raises(TypedJudgmentUnavailableException):
            adapter.judge("x", {"q": NoulQuestion(instructions="a")})

    def test_no_question_means_no_request(self) -> None:
        """質問が 0 件なら呼ばない。空の問い合わせに課金しない。"""
        calls: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            calls.append(request)
            return httpx.Response(200, json={"answers": {}})

        assert _adapter(handler).judge("x", {}) == {}
        assert calls == []


class TestRateLimitsAreRetriedWithinTheGivenBudget:
    """429 / 529 を決めた回数だけ再試行し、超えたら例外になることを保証する。"""

    def test_a_rate_limit_is_retried_and_can_succeed(self) -> None:
        """429 の次に 200 が返れば、答えを返す。"""
        statuses = [429, 200]
        sleeps: list[float] = []

        def handler(_request: httpx.Request) -> httpx.Response:
            status = statuses.pop(0)
            if status == 200:
                return httpx.Response(200, json={"answers": {"q": {"type": "noul", "noul": 0.5}}})
            return httpx.Response(status, json={"error": {"message": "slow down"}})

        answers = _adapter(handler, retry_attempts=1, sleeps=sleeps).judge("x", {"q": NoulQuestion(instructions="a")})

        assert answers["q"].value == 0.5
        assert len(sleeps) == 1

    def test_running_out_of_retries_is_a_failure(self) -> None:
        """再試行の上限を使い切ったら例外になる。無限に粘らない。"""
        adapter = _adapter(lambda _request: httpx.Response(429, text="slow down"), retry_attempts=1)

        with pytest.raises(TypedJudgmentUnavailableException):
            adapter.judge("x", {"q": NoulQuestion(instructions="a")})

    def test_a_client_error_is_not_retried(self) -> None:
        """422 のような直しようのない失敗は再試行しない。"""
        calls: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            calls.append(request)
            return httpx.Response(422, text="bad question")

        with pytest.raises(TypedJudgmentUnavailableException):
            _adapter(handler, retry_attempts=3).judge("x", {"q": NoulQuestion(instructions="a")})

        assert len(calls) == 1
