"""TypeSafe の Jev を呼ぶ型付き判断アダプタ (#1319)。

## LiteLLM は通らない

Jev の入口は chat/completions ではなく Decisions endpoint で、body は
``{model, state, questions}`` である。chat/completions へ投げると 400 で
明示的に断られる。

    typesafe/jev-1.13 is a decisions model and cannot be used with the
    chat/completions endpoint. Use the /api/alpha/decisions endpoint instead.

そのため ``LiteLLMClient`` の経路には乗せられない。timeout と再試行はこの
アダプタ側に持つ。

## 接続先

TypeSafe 直叩き (``https://api.typesafe.ai/v1/systemone``) と OpenRouter
(``https://openrouter.ai/api/alpha/decisions``) のどちらでも同じ body が通る。
endpoint と model とキーは profile から渡す (design_decisions #28)。

## 失敗を既定値へ落とさない

timeout / HTTP エラー / スキーマ不一致は ``TypedJudgmentUnavailableException``。
既定値を返すと「判断を得られなかった」ことと「判断の結果がこうだった」ことが
同じになり、呼び出し側は縮退したことに気づけない (design_decisions #5)。

429 (レート制限) と 529 (過負荷) だけは決めた回数だけ再試行する。それ以外の
4xx は投げ方の問題なので再試行しない。
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable, Mapping, Sequence
from typing import Any, Union

import httpx

from ai_rpg_world.application.llm.contracts.aux_llm_call import (
    AuxLlmCall,
    AuxLlmCallSink,
    AuxLlmComponent,
)
from ai_rpg_world.application.llm.ports.typed_judgment_port import (
    ChoiceQuestion,
    ITypedJudgmentPort,
    JudgmentResult,
    JudgmentSource,
    NoulQuestion,
    Question,
    ScoreQuestion,
    TypedJudgmentUnavailableException,
)

logger = logging.getLogger(__name__)

#: 再試行してよい HTTP status。429 はレート制限、529 は過負荷。
_RETRYABLE_STATUSES = frozenset({429, 529})

#: 質問の型 → 応答の ``type`` 値。食い違いを検出するために対で持つ。
_EXPECTED_ANSWER_TYPE = {
    NoulQuestion: "noul",
    ChoiceQuestion: "choice",
    ScoreQuestion: "score",
}


class JevTypedJudgmentAdapter(ITypedJudgmentPort):
    """Decisions endpoint へ質問の束を 1 回で送る。"""

    def __init__(
        self,
        *,
        api_key: str,
        endpoint: str,
        model: str,
        timeout_seconds: float,
        rate_limit_retry_attempts: int = 2,
        rate_limit_retry_base_sleep: float = 0.5,
        sleep: Callable[[float], Any] = time.sleep,
        client: httpx.Client | None = None,
        aux_call_sink: AuxLlmCallSink | None = None,
    ) -> None:
        if not isinstance(api_key, str) or not api_key.strip():
            raise ValueError("api_key must be a non-empty string")
        if not isinstance(endpoint, str) or not endpoint.strip():
            raise ValueError("endpoint must be a non-empty string")
        if not isinstance(model, str) or not model.strip():
            raise ValueError("model must be a non-empty string")
        if not isinstance(timeout_seconds, (int, float)) or timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be a positive number")
        if rate_limit_retry_attempts < 0:
            raise ValueError("rate_limit_retry_attempts must be >= 0")
        self._api_key = api_key.strip()
        self._endpoint = endpoint.strip()
        self._model = model.strip()
        self._timeout_seconds = float(timeout_seconds)
        self._retry_attempts = int(rate_limit_retry_attempts)
        self._retry_base_sleep = float(rate_limit_retry_base_sleep)
        self._sleep = sleep
        self._client = client or httpx.Client()
        self._aux_call_sink = aux_call_sink

    def judge(
        self,
        state: str | Mapping[str, Any] | Sequence[Any],
        questions: Mapping[str, Question],
    ) -> Mapping[str, JudgmentResult]:
        if not questions:
            # 空の問い合わせに課金しない。呼び出し側が「未完了 memo が 0 件」の
            # ような形で空を渡すのは正常な経路である。
            return {}
        body = {
            "model": self._model,
            "state": state,
            "questions": {
                name: _as_wire_question(question)
                for name, question in questions.items()
            },
        }
        started = time.perf_counter()
        payload: dict[str, Any] | None = None
        try:
            payload = self._post_with_retry(body)
            latency_ms = (time.perf_counter() - started) * 1000
            results = _as_results(payload, questions, latency_ms)
        except TypedJudgmentUnavailableException as exc:
            self._record_call(questions, payload, started, error_code=exc.error_code)
            raise
        self._record_call(questions, payload, started, error_code=None)
        return results

    def _record_call(
        self,
        questions: Mapping[str, Question],
        payload: Mapping[str, Any] | None,
        started: float,
        *,
        error_code: str | None,
    ) -> None:
        if self._aux_call_sink is None:
            return
        try:
            # #1429 の時点で Decisions endpoint は usage を返さない。返すように
            # なったら拾い、返さない間は None のまま「取れない」と残す。
            usage = (payload or {}).get("usage")
            usage = usage if isinstance(usage, dict) else {}
            self._aux_call_sink.record(
                AuxLlmCall(
                    component=AuxLlmComponent.TYPED_JUDGMENT,
                    model=self._model,
                    wall_latency_ms=int((time.perf_counter() - started) * 1000),
                    success=error_code is None,
                    prompt_tokens=_optional_int(usage.get("prompt_tokens")),
                    completion_tokens=_optional_int(usage.get("completion_tokens")),
                    cost_usd=_optional_float(usage.get("cost")),
                    error_code=error_code,
                    question_names=tuple(questions),
                )
            )
        except Exception:
            logger.exception("aux_call_sink.record failed for typed judgment")

    def _post_with_retry(self, body: dict[str, Any]) -> dict[str, Any]:
        attempt = 0
        while True:
            try:
                response = self._client.post(
                    self._endpoint,
                    headers={
                        "Authorization": f"Bearer {self._api_key}",
                        "Content-Type": "application/json",
                    },
                    json=body,
                    timeout=self._timeout_seconds,
                )
            except httpx.HTTPError as exc:
                # 例外本文に URL は載るがキーは載らない (キーはヘッダにしか
                # 入れていない)。
                raise TypedJudgmentUnavailableException(
                    f"typed judgment transport failed: {type(exc).__name__}",
                    error_code="TYPED_JUDGMENT_TRANSPORT_FAILED",
                    cause=exc,
                ) from exc

            if response.status_code in _RETRYABLE_STATUSES:
                if attempt >= self._retry_attempts:
                    raise TypedJudgmentUnavailableException(
                        f"typed judgment rate limited: HTTP {response.status_code}",
                        error_code="TYPED_JUDGMENT_RATE_LIMITED",
                    )
                self._sleep(self._retry_base_sleep * (2**attempt))
                attempt += 1
                continue

            if response.status_code != 200:
                # 応答本文は載せない。provider の文面に何が混ざるかを保証でき
                # ないので、trace と report に残る文面は status だけにする。
                raise TypedJudgmentUnavailableException(
                    f"typed judgment call failed: HTTP {response.status_code}",
                    error_code="TYPED_JUDGMENT_HTTP_ERROR",
                )

            try:
                payload = response.json()
            except ValueError as exc:  # json.JSONDecodeError を含む
                raise TypedJudgmentUnavailableException(
                    "typed judgment response was not JSON",
                    error_code="TYPED_JUDGMENT_SCHEMA_MISMATCH",
                    cause=exc,
                ) from exc
            if not isinstance(payload, dict):
                raise TypedJudgmentUnavailableException(
                    "typed judgment response was not an object",
                    error_code="TYPED_JUDGMENT_SCHEMA_MISMATCH",
                )
            return payload


def _optional_int(value: Any) -> int | None:
    return int(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def _optional_float(value: Any) -> float | None:
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def _as_wire_question(question: Question) -> dict[str, Any]:
    if isinstance(question, NoulQuestion):
        written: dict[str, Any] = {
            "type": "noul",
            "instructions": question.instructions,
        }
        criteria = {
            key: value
            for key, value in (
                ("true", question.true_means),
                ("false", question.false_means),
            )
            if value is not None
        }
        if criteria:
            written["criteria"] = criteria
        return written
    if isinstance(question, ChoiceQuestion):
        return {
            "type": "choice",
            "instructions": question.instructions,
            "criteria": dict(question.options),
        }
    if isinstance(question, ScoreQuestion):
        return {
            "type": "score",
            "instructions": question.instructions,
            "criteria": list(question.levels),
        }
    raise TypeError(f"unsupported question type: {type(question)!r}")


def _as_results(
    payload: Mapping[str, Any],
    questions: Mapping[str, Question],
    latency_ms: float,
) -> Mapping[str, JudgmentResult]:
    answers = payload.get("answers")
    if not isinstance(answers, dict):
        raise TypedJudgmentUnavailableException(
            "typed judgment response had no answers object",
            error_code="TYPED_JUDGMENT_SCHEMA_MISMATCH",
        )
    out: dict[str, JudgmentResult] = {}
    for name, question in questions.items():
        answer = answers.get(name)
        if not isinstance(answer, dict):
            # 問った質問の答えが無いまま進むと、呼び出し側は「判断が無かった」
            # ことに気づかないまま既定値で分岐する。
            raise TypedJudgmentUnavailableException(
                f"typed judgment answer missing for question {name!r}",
                error_code="TYPED_JUDGMENT_ANSWER_MISSING",
            )
        expected = _EXPECTED_ANSWER_TYPE[type(question)]
        if answer.get("type") != expected:
            raise TypedJudgmentUnavailableException(
                f"typed judgment answer for {name!r} was {answer.get('type')!r}, "
                f"expected {expected!r}",
                error_code="TYPED_JUDGMENT_SCHEMA_MISMATCH",
            )
        out[name] = _as_result(name, expected, answer, latency_ms)
    return out


def _as_result(
    name: str, expected: str, answer: Mapping[str, Any], latency_ms: float
) -> JudgmentResult:
    probabilities = answer.get("probabilities") or {}
    if not isinstance(probabilities, dict):
        raise TypedJudgmentUnavailableException(
            f"typed judgment probabilities for {name!r} was not an object",
            error_code="TYPED_JUDGMENT_SCHEMA_MISMATCH",
        )
    value_key = {"noul": "noul", "choice": "choice", "score": "score"}[expected]
    if value_key not in answer:
        raise TypedJudgmentUnavailableException(
            f"typed judgment answer for {name!r} had no {value_key!r}",
            error_code="TYPED_JUDGMENT_SCHEMA_MISMATCH",
        )
    confidence = answer.get("confidence")
    if confidence is not None and not isinstance(confidence, (int, float)):
        raise TypedJudgmentUnavailableException(
            f"typed judgment confidence for {name!r} was not a number",
            error_code="TYPED_JUDGMENT_SCHEMA_MISMATCH",
        )
    return JudgmentResult(
        value=answer[value_key],
        probabilities={str(k): float(v) for k, v in probabilities.items()},
        # Noul の応答は confidence を持たない。持たないことを 0.0 に潰すと、
        # 「確信が無い」と読めてしまう。
        confidence=None if confidence is None else float(confidence),
        source=JudgmentSource.JEV,
        latency_ms=latency_ms,
    )


__all__ = ["JevTypedJudgmentAdapter"]
