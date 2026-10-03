"""予期の根拠を、頭にあった信念とエピソードから Jev に選ばせる問い (#1484)。

## 頭にあったものすべてを根拠にしない

頭に載る信念とエピソードは、予期と関係が無くても載る。すべてに当否を返すと、
いつも載るものに支持と役に立った回数が積まれ、さらに載りやすくなる。予期を
書いたターンに 1 件ずつ「この予期の材料になったか」を問い、選ばれたものだけを
根拠にする。判断が得られなかったものは根拠にしない。

## 本文は清算のときに記憶から引く

予期は頭にあったものを ID でしか持たない。問いには本文が要るので、形を問う
ターンに記憶の保存先から引く。プロンプトに載せた時点から再解釈で書き換わって
いれば、書き換わったあとの本文で問う。
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from ai_rpg_world.application.llm.ports.typed_judgment_port import (
    JudgmentResult,
    NoulQuestion,
)
from ai_rpg_world.domain.being.value_object.being_id import BeingId
from ai_rpg_world.domain.memory.episodic.repository.episodic_episode_repository import (
    EpisodicEpisodeRepository,
)
from ai_rpg_world.domain.memory.episodic.repository.episodic_reinterpretation_journal_repository import (
    EpisodicReinterpretationJournalRepository,
)
from ai_rpg_world.domain.memory.expectation.aggregate.expectation import (
    Expectation,
)
from ai_rpg_world.domain.memory.expectation.value_object.expectation_grounds import (
    ExpectationGrounds,
)
from ai_rpg_world.domain.memory.semantic.repository.semantic_memory_repository import (
    SemanticMemoryRepository,
)

logger = logging.getLogger(__name__)

BELIEF = "belief"
EPISODE = "episode"
OMITTED_OVER_LIMIT = "over_limit"
OMITTED_TEXT_NOT_FOUND = "text_not_found"


class InMindTextReader(ABC):
    """頭にあった信念とエピソードの本文を引く口。見つからなければ None。"""

    @abstractmethod
    def belief_text(self, being_id: BeingId, belief_id: str) -> str | None:
        raise NotImplementedError

    @abstractmethod
    def episode_text(self, being_id: BeingId, episode_id: str) -> str | None:
        raise NotImplementedError


class MemoryStoreInMindTextReader(InMindTextReader):
    """記憶の保存先から本文を引く。保存先が無い記憶は本文が無いものとして扱う。

    エピソードは、プロンプトの想起と同じく、有効な再解釈があればその文を使う。
    """

    def __init__(
        self,
        *,
        semantic_store: SemanticMemoryRepository | None,
        episode_store: EpisodicEpisodeRepository | None,
        journal_store: EpisodicReinterpretationJournalRepository | None,
    ) -> None:
        self._semantic_store = semantic_store
        self._episode_store = episode_store
        self._journal_store = journal_store

    def belief_text(self, being_id: BeingId, belief_id: str) -> str | None:
        if self._semantic_store is None:
            return None
        for entry in self._semantic_store.list_for_being(being_id):
            if entry.entry_id == belief_id:
                return _text_or_none(entry.text)
        return None

    def episode_text(self, being_id: BeingId, episode_id: str) -> str | None:
        if self._episode_store is None:
            return None
        episode = self._episode_store.get_by_being(being_id, episode_id)
        if episode is None:
            return None
        if self._journal_store is not None:
            active = self._journal_store.get_active_by_being(being_id, episode_id)
            if active is not None and _text_or_none(active.current_recall_text):
                return _text_or_none(active.current_recall_text)
        return _text_or_none(episode.recall_text) or _text_or_none(episode.what)


def _text_or_none(value: object) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


@dataclass(frozen=True)
class GroundQuestion:
    """根拠の問い 1 件。どの予期の、頭にあったどれを問うたか。"""

    expectation: Expectation
    kind: str
    ground_id: str
    text: str


@dataclass
class GroundsPlan:
    """1 ターンに問う根拠の問いと、問わずに外したもの。予期ごとに trace へ並べる。"""

    questions: dict[str, GroundQuestion] = field(default_factory=dict)
    omitted: dict[str, list[dict[str, str]]] = field(default_factory=dict)
    expectations: list[Expectation] = field(default_factory=list)

    def grounds_for(
        self, expectation: Expectation, answers: Mapping[str, float], min_probability: float
    ) -> ExpectationGrounds:
        """確率が閾値を超えたものだけを、頭にあった順で根拠にする。

        閾値ちょうどは採らない。迷った答え (0.5) を根拠にすると、判断が無いのと
        同じ答えで頭にあったものすべてが根拠になりうる。
        """
        chosen = [
            q
            for name, q in self.questions.items()
            if q.expectation is expectation and answers[name] > min_probability
        ]
        return ExpectationGrounds(
            beliefs=tuple(q.ground_id for q in chosen if q.kind == BELIEF),
            episodes=tuple(q.ground_id for q in chosen if q.kind == EPISODE),
        )

    def trace(
        self,
        *,
        answers: Mapping[str, JudgmentResult] | None,
        judged: Mapping[str, ExpectationGrounds] | None,
    ) -> list[dict[str, Any]]:
        """予期ごとに、頭にあったもの・問うたものと確率・外したもの・選んだ根拠を並べる。

        判断が得られなかったターンは ``judged`` が None で、確率も根拠も空で残す。
        """
        entries: list[dict[str, Any]] = []
        for expectation in self.expectations:
            key = expectation.expectation_id.value
            grounds = None if judged is None else judged.get(key)
            entries.append(
                {
                    "expectation_id": key,
                    "content": expectation.content,
                    "beliefs_in_mind": list(expectation.beliefs_in_mind),
                    "episodes_in_mind": list(expectation.episodes_in_mind),
                    "asked": [
                        {
                            "question": name,
                            "kind": q.kind,
                            "id": q.ground_id,
                            "text": q.text,
                            "probability": (
                                None
                                if answers is None or name not in answers
                                else answers[name].value
                            ),
                        }
                        for name, q in self.questions.items()
                        if q.expectation is expectation
                    ],
                    "omitted": list(self.omitted.get(key, [])),
                    "judged": grounds is not None,
                    "beliefs": [] if grounds is None else list(grounds.beliefs),
                    "episodes": [] if grounds is None else list(grounds.episodes),
                }
            )
        return entries


def plan_ground_questions(
    being_id: BeingId,
    new: Sequence[Expectation],
    *,
    reader: InMindTextReader,
    limit: int,
) -> GroundsPlan:
    """形を問う予期ごとに、頭にあった信念、エピソードの順で問いを並べる。

    上限は 1 回の呼び出し全体で数え、先に書いた予期から埋める。上限を超えた
    もの、本文を引けないものは問わずに外し、根拠にもしない。
    """
    plan = GroundsPlan(expectations=list(new))
    counters = {BELIEF: 0, EPISODE: 0}
    for expectation in new:
        omitted = plan.omitted.setdefault(expectation.expectation_id.value, [])
        items = [(BELIEF, b) for b in expectation.beliefs_in_mind] + [
            (EPISODE, e) for e in expectation.episodes_in_mind
        ]
        for kind, ground_id in items:
            if len(plan.questions) >= limit:
                omitted.append({"kind": kind, "id": ground_id, "reason": OMITTED_OVER_LIMIT})
                continue
            text, reason = _read(reader, being_id, kind, ground_id)
            if text is None:
                omitted.append({"kind": kind, "id": ground_id, "reason": reason})
                continue
            name = f"ground_{kind}_{counters[kind]}"
            counters[kind] += 1
            plan.questions[name] = GroundQuestion(expectation, kind, ground_id, text)
    return plan


def _read(
    reader: InMindTextReader, being_id: BeingId, kind: str, ground_id: str
) -> tuple[str | None, str]:
    # 本文を引けない 1 件のために形の判定まで止めない。外したことは trace に残る。
    try:
        text = (
            reader.belief_text(being_id, ground_id)
            if kind == BELIEF
            else reader.episode_text(being_id, ground_id)
        )
    except Exception as exc:
        logger.warning(
            "reading %s text failed for being=%s id=%s", kind, being_id.value, ground_id,
            exc_info=True,
        )
        return None, f"text_read_failed: {type(exc).__name__}: {exc}"
    return text, OMITTED_TEXT_NOT_FOUND


def ground_question(self_name: str, question: GroundQuestion) -> NoulQuestion:
    expectation = question.expectation
    written = (
        f"{self_name}がターン{expectation.formed_at_turn}に書いた予期"
        f"「{expectation.content}」"
    )
    if question.kind == BELIEF:
        return NoulQuestion(
            instructions=(
                f"{written}は、{self_name}がそのとき持っていた信念"
                f"「{question.text}」から出てきたものか。"
            ),
            true_means=(
                "この信念が予期の理由や前提になっている。この信念が無ければ、"
                "この予期は持たなかった"
            ),
            false_means=(
                "この信念は予期と関係が無い、または関係が薄い。この信念が無くても"
                "同じ予期を持った"
            ),
        )
    return NoulQuestion(
        instructions=(
            f"{written}は、{self_name}がそのとき思い出していた出来事"
            f"「{question.text}」を材料にしたものか。"
        ),
        true_means="この出来事で見聞きしたことが、予期の理由や手がかりになっている",
        false_means=(
            "この出来事は予期と関係が無い、または関係が薄い。思い出していなくても"
            "同じ予期を持った"
        ),
    )


__all__ = [
    "GroundQuestion",
    "GroundsPlan",
    "InMindTextReader",
    "MemoryStoreInMindTextReader",
    "ground_question",
    "plan_ground_questions",
]
