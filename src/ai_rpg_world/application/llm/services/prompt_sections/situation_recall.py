"""【関連する学び】を状況の欄から引く (#1414)。profile で有効にしたときだけ使う。

ゲームの観測と行動結果は、観測の契約 (design_decisions D1463) に変換してから欄に
組み立てる。契約に写せない観測 (ループ警告、目的の振り返り、時刻の無い観測など) は
飛ばし、飛ばした理由を trace に数で残す。

どの欄を残すかは、直前のターンの終わりの清算で Jev が選んだもの (design_decisions
D1414-3) を使う。選択が無い、古い、清算を切っている run では、理由をつけて全部の欄で引く。
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Any

from ai_rpg_world.application.being.recall.belief_recall import SituationBeliefRecall
from ai_rpg_world.application.being.recall.selection_store import (
    DEGRADED_NO_SELECTION,
    DEGRADED_SETTLEMENT_DISABLED,
    NextTurnFieldSelections,
)
from ai_rpg_world.application.being.recall.situation import FieldSelection, SituationField
from ai_rpg_world.application.being.recall.situation_assembly import (
    AgentHoldings,
    assemble_situation,
)
from ai_rpg_world.application.llm.contracts.dtos import ActionResultEntry
from ai_rpg_world.application.observation.being_contract import (
    ObservationNotRepresentable,
    Observer,
    observation_from_action_result,
    observation_from_game,
)
from ai_rpg_world.application.observation.contracts.dtos import ObservationEntry
from ai_rpg_world.application.trace import TraceEventKind
from ai_rpg_world.being.contract import ContractViolation, Observation
from ai_rpg_world.domain.being.value_object.being_id import BeingId
from ai_rpg_world.domain.memory.expectation.repository.expectation_repository import (
    ExpectationRepository,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId

if TYPE_CHECKING:
    from ai_rpg_world.application.llm.services.prompt_builder import DefaultPromptBuilder

#: 契約の欄の検査に通らなかった観測。1 件のためにそのターンの想起全体を落とさない。
SKIPPED_CONTRACT_VIOLATION = "contract_violation"


@dataclass(frozen=True)
class SituationRecallSources:
    """状況の欄から引くときに要るもの。``goal_text`` は読み取りだけで、目的を書き込まない。

    ``selections`` が None なのは、清算を切っていて欄が選ばれない run。
    """

    recall: SituationBeliefRecall
    expectations: ExpectationRepository
    goal_text: Callable[[PlayerId], str | None]
    selections: NextTurnFieldSelections | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.recall, SituationBeliefRecall):
            raise TypeError("recall must be SituationBeliefRecall")
        if not isinstance(self.expectations, ExpectationRepository):
            raise TypeError("expectations must be ExpectationRepository")
        if not callable(self.goal_text):
            raise TypeError("goal_text must be callable")
        if self.selections is not None and not isinstance(
            self.selections, NextTurnFieldSelections
        ):
            raise TypeError("selections must be NextTurnFieldSelections or None")

    def selection_for(self, being_id: BeingId) -> FieldSelection:
        if self.selections is None:
            return FieldSelection.degraded(
                DEGRADED_SETTLEMENT_DISABLED, "expectation settlement is disabled in this run"
            )
        return self.selections.for_prompt(
            being_id, current_turn=self.expectations.current_turn(being_id)
        )


def run_situation_belief_recall(
    builder: DefaultPromptBuilder,
    sources: SituationRecallSources,
    *,
    player_id: PlayerId,
    being_id: BeingId,
    player_name: str,
    place_name: str | None,
    observations: Sequence[ObservationEntry],
    action_results: Sequence[ActionResultEntry],
) -> tuple[str, tuple[str, ...]]:
    """戻り値は既存の受動想起と同じ (整形した本文, 頭に載せた信念の ID)。

    失敗してもプロンプトの組み立ては止めず、何も載せない。ERROR で記録し、trace にも
    失敗として残す。何も引けなかった結果と見分けられるようにする。trace の記録が失敗
    しても、引けた信念は捨てない。
    """
    try:
        payload, text, belief_ids = _recall(
            builder,
            sources,
            player_id=player_id,
            being_id=being_id,
            player_name=player_name,
            place_name=place_name,
            observations=observations,
            action_results=action_results,
        )
    except Exception as exc:
        builder._logger.error(
            "Situation belief recall failed for player_id=%s", player_id.value, exc_info=True
        )
        payload, text, belief_ids = {"failed": f"{type(exc).__name__}: {exc}"}, "", ()
    _record(builder, player_id=player_id, being_id=being_id, payload=payload)
    return text, belief_ids


def _recall(
    builder: DefaultPromptBuilder,
    sources: SituationRecallSources,
    *,
    player_id: PlayerId,
    being_id: BeingId,
    player_name: str,
    place_name: str | None,
    observations: Sequence[ObservationEntry],
    action_results: Sequence[ActionResultEntry],
) -> tuple[dict[str, Any], str, tuple[str, ...]]:
    observer = Observer(
        player_id=player_id, name=player_name, place_name=place_name, seconds_per_tick=None
    )
    contract_observations, skipped = _to_contract(observations, action_results, observer)
    holdings = AgentHoldings(
        goal=sources.goal_text(player_id),
        inner_thought=action_results[0].inner_thought if action_results else None,
        open_expectations=tuple(
            e.content for e in sources.expectations.list_open_by_being(being_id)
        ),
    )
    situation = assemble_situation(contract_observations, holdings)
    selection = sources.selection_for(being_id)
    result = sources.recall.retrieve(
        being_id, situation, selection, top_k=builder._semantic_passive_top_k
    )
    payload = {
        "situation": {f.value: list(situation.texts(f)) for f in SituationField},
        "skipped_observations": dict(skipped),
        "top_k": builder._semantic_passive_top_k,
        "failed": None,
        **result.to_trace_payload(),
    }
    # 表示は ID の順に固定する。同じ信念の組なら同じ文字列にして、プロンプトの並びの
    # 揺れでキャッシュを壊さない (format_semantic_recall_section と同じ扱い)。
    shown = sorted(
        (e for e in result.chosen if e.text.strip()), key=lambda e: e.entry_id
    )
    text = "\n".join(f"- {e.text.strip()}" for e in shown)
    return payload, text, tuple(e.entry_id for e in shown)


def _record(
    builder: DefaultPromptBuilder,
    *,
    player_id: PlayerId,
    being_id: BeingId,
    payload: dict[str, Any],
) -> None:
    try:
        recorder = builder._resolve_trace_recorder()
        if recorder is None:
            return
        recorder.record(
            TraceEventKind.SITUATION_BELIEF_RECALL,
            tick=_current_tick(builder),
            player_id=int(player_id.value),
            being_id=being_id.value,
            **payload,
        )
    except Exception:
        builder._logger.warning(
            "SITUATION_BELIEF_RECALL trace record failed for player_id=%s",
            player_id.value,
            exc_info=True,
        )


def _to_contract(
    observations: Sequence[ObservationEntry],
    action_results: Sequence[ActionResultEntry],
    observer: Observer,
) -> tuple[list[Observation], Counter[str]]:
    dated: list[tuple[datetime, Observation]] = []
    skipped: Counter[str] = Counter()
    for entry in observations:
        try:
            dated.append(
                (
                    entry.occurred_at,
                    observation_from_game(
                        entry.output,
                        tick=None,
                        game_time_label=entry.game_time_label,
                        observer=observer,
                    ),
                )
            )
        except ObservationNotRepresentable as exc:
            skipped[exc.reason.value] += 1
        except ContractViolation:
            skipped[SKIPPED_CONTRACT_VIOLATION] += 1
    for result in action_results:
        # 呼び出しの ID は欄に入らない。契約の型が空を拒むので、行動の時刻から作る。
        call_id = result.prediction_context_id or f"action@{result.occurred_at.isoformat()}"
        try:
            dated.append(
                (
                    result.occurred_at,
                    observation_from_action_result(result, call_id=call_id, observer=observer),
                )
            )
        except ObservationNotRepresentable as exc:
            skipped[exc.reason.value] += 1
        except ContractViolation:
            skipped[SKIPPED_CONTRACT_VIOLATION] += 1
    # timestamp で比べる。タイムゾーンの有無が混ざった datetime どうしは比べられない。
    dated.sort(key=lambda pair: pair[0].timestamp(), reverse=True)
    return [observation for _, observation in dated], skipped


def _current_tick(builder: DefaultPromptBuilder) -> int | None:
    if builder._current_tick_provider is None:
        return None
    return builder._current_tick_provider()


__all__ = [
    "DEGRADED_NO_SELECTION",
    "SKIPPED_CONTRACT_VIOLATION",
    "SituationRecallSources",
    "run_situation_belief_recall",
]
