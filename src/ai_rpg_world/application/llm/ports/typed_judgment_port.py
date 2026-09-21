"""型付きの判断を 1 回でまとめて問うポート (#1319)。

ルールでは意味を見られず、LLM に任せると 1 回 3〜4 秒かかる判断がある。
起床の是非、発明された行動名の行き先、memo の完了。いまはハードコードの
閾値や文字の重なりで代用している。

このポートは「state と型付きの質問を渡し、較正済みの確率を受け取る」形だけを
決める。テキストは生成しない。

## 1 回に複数の質問を渡す

``judge`` は名前つきの質問の辞書を受ける。**同じ state を使う質問は 1 回に
まとめる。** 質問ごとにリクエストを割ると state を送り直すので、Noul 3 問で
input tokens が 2.3 倍になる (実測: 630 → 1,476)。質問は並列に評価されるため、
まとめても遅くならない。

質問は単純に保つ。複数の要素に依存する判断は個別の質問へ分解し、重み付けは
コード側で組み立てる。算術 (tick 差、件数) と日付の比較はこのポートに問わず、
コードに残す。苦手だと公表されている。

## 閾値は持たない

確率を採用するかどうかは呼び出し側が config から受けた閾値で決める。ポートは
閾値を知らない。同じ確率を別の用途が別の閾値で使うため。

## 失敗は例外

timeout / HTTP / スキーマ不一致は ``TypedJudgmentUnavailableException``。
呼び出し側は既存のルールへ縮退し、trace に残す。**成功扱いにしない**
(design_decisions #5)。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import Enum
from typing import Any, Union

from ai_rpg_world.application.llm.exceptions import LlmApplicationException


class JudgmentSource(Enum):
    """判断をどこから得たか。trace に残して run の比較に使う。"""

    #: TypeSafe の Jev (System One モデル)
    JEV = "jev"
    #: 決定論 stub。実 API を呼ばずに配線を確かめる
    STUB = "stub"
    #: 小型 LLM に同じ形を返させるアダプタ。精度の対照用 (未実装)
    LLM = "llm"


@dataclass(frozen=True)
class NoulQuestion:
    """命題が成り立つかを 0〜1 で問う。

    ``criteria`` は真と偽が何を意味するかを言葉で書く。省略すると、モデルは
    命題の言い回しだけから両側を推測することになる。
    """

    instructions: str
    true_means: str | None = None
    false_means: str | None = None


@dataclass(frozen=True)
class ChoiceQuestion:
    """選択肢から 1 つを選ばせる。

    ``options`` は選択肢名 → その意味。名前だけを並べると、裸の識別子から
    意味を推測させることになる (design_decisions #38 が `take` 誤読で踏んだ形)。

    **「どれにも当たらない」を選択肢に入れるかは呼び出し側が決める。** 入れ
    ないと、必ずどれかに寄る。
    """

    instructions: str
    options: Mapping[str, str | None]


@dataclass(frozen=True)
class ScoreQuestion:
    """順序のある段階で評価させる。``levels`` は低い方から並べる。"""

    instructions: str
    levels: Sequence[str]


#: ``judge`` に渡せる質問。
Question = Union[NoulQuestion, ChoiceQuestion, ScoreQuestion]


@dataclass(frozen=True)
class JudgmentResult:
    """質問 1 件の答え。

    Attributes:
        value: Noul なら 0〜1 の float、Choice なら選んだ選択肢名、Score なら
            段階の期待値 (float)
        probabilities: 選択肢または段階ごとの確率。Noul は空
        confidence: Choice と Score だけが持つ。**Noul は None。**
            Jev の Noul 応答は ``{"type": "noul", "noul": 0.42}`` だけで、
            confidence を返さない
        source: どこから得たか
        latency_ms: 呼び出しにかかった時間
    """

    value: Any
    probabilities: Mapping[str, float]
    confidence: float | None
    source: JudgmentSource
    latency_ms: float


class TypedJudgmentUnavailableException(LlmApplicationException):
    """型付き判断を得られなかった。

    呼び出し側は既存のルールへ縮退し、縮退したことを trace に残す。**判断が
    無かったことを、判断の結果と同じ扱いにしない。**
    """

    def __init__(
        self,
        message: str,
        error_code: str = "TYPED_JUDGMENT_UNAVAILABLE",
        cause: Exception | None = None,
        **context: Any,
    ) -> None:
        super().__init__(message, cause=cause, error_code=error_code, **context)
        self.cause = cause


class ITypedJudgmentPort(ABC):
    """state と名前つきの質問を受け、質問ごとの答えを返す。"""

    @abstractmethod
    def judge(
        self,
        state: str | Mapping[str, Any] | Sequence[Any],
        questions: Mapping[str, Question],
    ) -> Mapping[str, JudgmentResult]:
        """``questions`` のすべてを同じ ``state`` に対して 1 回で問う。

        Args:
            state: 判断の材料。名前だけを入れ、整数 ID を入れない (設計原則 1)
            questions: 名前 → 質問。名前は trace と呼び出し側の分岐に使う

        Returns:
            ``questions`` と同じ名前をキーに持つ答え。

        Raises:
            TypedJudgmentUnavailableException: timeout / HTTP / スキーマ不一致。
                呼び出し側は既存のルールへ縮退する
        """
        raise NotImplementedError


__all__ = [
    "ChoiceQuestion",
    "ITypedJudgmentPort",
    "JudgmentResult",
    "JudgmentSource",
    "NoulQuestion",
    "Question",
    "ScoreQuestion",
    "TypedJudgmentUnavailableException",
]
