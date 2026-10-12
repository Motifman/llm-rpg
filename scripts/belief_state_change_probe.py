"""状態の信念と食い違う出来事を、信念を固める LLM が変わり方の信念にするかを読む (#1452)。

過去 run の snapshot にあった状態の信念と予測の外れの文を真似て、観測のターン数を
付けた場面を作る。場面ごとに信念を固める処理を 1 回動かし、選ばれた操作と、
作られた信念を並べる。run は回さない。

場面:

- ``returned_leaves`` / ``returned_shellfish``: 採り尽くされていたものが、後のターンで
  戻っていた。変わり方の信念 (explain_change) を作ってほしい
- ``still_depleted``: 後のターンでもやはり無かった。変わり方の信念は作ってほしくない
- ``overlooked``: 前に見落としていただけ。状態は変わっていないので、改める・否定するが
  正しい。変わり方の信念は作ってほしくない

使い方:
    uv run python scripts/belief_state_change_probe.py --profile station_drill --reps 5 --out /tmp/probe.json
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT / "src"))
sys.path.insert(0, str(_REPO_ROOT))

from scripts.run_scenario_experiment import (  # noqa: E402
    _runtime_config_mapping_from_source,
)

from ai_rpg_world.application.llm.services.belief_consolidation_coordinator import (  # noqa: E402
    BeliefConsolidationCoordinator,
)
from ai_rpg_world.application.llm.services.in_memory_belief_evidence_buffer_store import (  # noqa: E402
    InMemoryBeliefEvidenceBufferStore,
)
from ai_rpg_world.application.llm.services.in_memory_semantic_memory_store import (  # noqa: E402
    InMemorySemanticMemoryStore,
)
from ai_rpg_world.application.llm.wiring._llm_client_factory import (  # noqa: E402
    create_llm_client_from_config,
)
from ai_rpg_world.application.llm.wiring.resolved_runtime_config import (  # noqa: E402
    ResolvedLlmRuntimeConfig,
)
from ai_rpg_world.application.trace import NullTraceRecorder, TraceEventKind  # noqa: E402
from ai_rpg_world.being.infrastructure.in_memory_memory_turn_clock import (  # noqa: E402
    InMemoryMemoryTurnClock,
)
from ai_rpg_world.domain.being.value_object.being_id import BeingId  # noqa: E402
from ai_rpg_world.domain.memory.semantic.value_object.belief_evidence import (  # noqa: E402
    BELIEF_EVIDENCE_SALIENCE_LOW,
    BeliefEvidence,
)
from ai_rpg_world.domain.memory.semantic.value_object.belief_evidence_source_kind import (  # noqa: E402
    BeliefEvidenceSourceKind,
)
from ai_rpg_world.domain.memory.semantic.value_object.semantic_memory_entry import (  # noqa: E402
    SEMANTIC_MEMORY_STATUS_ACTIVE,
    SemanticMemoryEntry,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId  # noqa: E402
from ai_rpg_world.infrastructure.llm.litellm_client import LiteLLMClient  # noqa: E402

_BEING = BeingId("being_w1_p1")
_PLAYER = PlayerId(1)
_NOW = datetime(2026, 10, 3, tzinfo=timezone.utc)

# 過去 run の snapshot にあった信念。どの場面でも候補に並べる。
_BACKGROUND_BELIEFS = (
    ("sem-signal", "狼煙には流木・枯れ葉・火打ち石が必要だ", ("狼煙", "救助"), 4, 20),
    ("sem-crab", "貝が採れる浜辺には大型カニが現れることがある", ("hazard", "beach", "interact"), 2, 18),
)


@dataclass(frozen=True)
class Scene:
    name: str
    expect_change: bool
    belief_text: str
    belief_tags: tuple[str, ...]
    belief_support: int
    belief_turn: int
    evidence_text: str
    evidence_cue: str
    evidence_turn: int


SCENES = (
    Scene(
        name="returned_leaves",
        expect_change=True,
        belief_text="浜の流木と枯れ葉は既に採取尽くされ尽きている。",
        belief_tags=("浜", "流木", "枯れ葉", "資源枯渇", "interact"),
        belief_support=3,
        belief_turn=12,
        evidence_text=(
            "浜の枯れ葉はもう採り尽くされていて何も拾えないと思っていたが、"
            "浜辺に枯れ葉が落ちていて 2 枚拾えた。"
        ),
        evidence_cue="tool:interact|spot:浜辺",
        evidence_turn=40,
    ),
    Scene(
        name="returned_shellfish",
        expect_change=True,
        belief_text="干潟の貝は採り尽くされている",
        belief_tags=("location", "resource", "explore", "interact"),
        belief_support=2,
        belief_turn=8,
        evidence_text=(
            "干潟の貝は採り尽くされていると思っていたが、岩棚に貝が付いていて 3 つ採れた。"
        ),
        evidence_cue="tool:interact|spot:干潟",
        evidence_turn=35,
    ),
    Scene(
        name="still_depleted",
        expect_change=False,
        belief_text="浜の流木と枯れ葉は既に採取尽くされ尽きている。",
        belief_tags=("浜", "流木", "枯れ葉", "資源枯渇", "interact"),
        belief_support=3,
        belief_turn=12,
        evidence_text=(
            "時間がたったので浜に枯れ葉が戻っているかと思ったが、やはり何も落ちていなかった。"
        ),
        evidence_cue="tool:interact|spot:浜辺",
        evidence_turn=40,
    ),
    Scene(
        name="overlooked",
        expect_change=False,
        belief_text="枯れ葉は森の入口では見つからない",
        belief_tags=("探索", "資源", "枯れ葉", "explore"),
        belief_support=1,
        belief_turn=10,
        evidence_text=(
            "森の入口には枯れ葉が無いと思っていたが、前は調べなかった倒木の陰を見たら、"
            "湿っていない枯れ葉が厚く積もっていた。"
        ),
        evidence_cue="tool:explore|spot:森の入口",
        evidence_turn=14,
    ),
)


class _CostCountingClient:
    """LiteLLMClient の 1 回ごとの費用を数える。"""

    def __init__(self, inner: LiteLLMClient) -> None:
        self._inner = inner
        self.calls = 0
        self.cost_usd = 0.0
        original = inner._call_with_selective_retry

        def _counting(*args: Any, **kwargs: Any) -> Any:
            response = original(*args, **kwargs)
            self.calls += 1
            self.cost_usd += LiteLLMClient._extract_cost_usd(response)
            return response

        inner._call_with_selective_retry = _counting  # type: ignore[method-assign]


class _Recorder:
    def __init__(self) -> None:
        self._inner = NullTraceRecorder()
        self.events: list[Any] = []

    def record(self, kind: Any, **kw: Any) -> Any:
        ev = self._inner.record(kind, **kw)
        self.events.append(ev)
        return ev

    def close(self) -> None:
        self._inner.close()


def _entry(entry_id: str, text: str, tags: tuple[str, ...], support: int, turn: int) -> SemanticMemoryEntry:
    return SemanticMemoryEntry(
        entry_id=entry_id,
        player_id=_PLAYER.value,
        being_id=_BEING,
        text=text,
        evidence_episode_ids=(f"ep-{entry_id}",),
        confidence=0.6,
        created_at=_NOW,
        importance_score=6,
        tags=tags,
        belief_id=entry_id,
        support_evidence_ids=tuple(f"ev-{entry_id}-{i}" for i in range(support)),
        last_observed_turn=turn,
    )


def run_scene(scene: Scene, client: LiteLLMClient) -> dict[str, Any]:
    semantic = InMemorySemanticMemoryStore()
    buffer = InMemoryBeliefEvidenceBufferStore()
    turns = InMemoryMemoryTurnClock()
    for _ in range(scene.evidence_turn + 1):
        turns.advance_turn(_BEING)
    recorder = _Recorder()
    coordinator = BeliefConsolidationCoordinator(
        evidence_buffer_store=buffer,
        semantic_store=semantic,
        completion=client,
        memory_turn_reader=turns,
        trace_recorder_provider=lambda: recorder,
    )
    semantic.add_by_being(
        _BEING,
        _entry("sem-state", scene.belief_text, scene.belief_tags, scene.belief_support, scene.belief_turn),
    )
    for entry_id, text, tags, support, turn in _BACKGROUND_BELIEFS:
        semantic.add_by_being(_BEING, _entry(entry_id, text, tags, support, turn))
    buffer.append_by_being(
        _BEING,
        BeliefEvidence(
            evidence_id="ev-now",
            source_kind=BeliefEvidenceSourceKind.PREDICTION_ERROR,
            episode_ids=("ep-now",),
            cue_signature=scene.evidence_cue,
            text=scene.evidence_text,
            salience=BELIEF_EVIDENCE_SALIENCE_LOW,
            occurred_at=_NOW,
            observed_turn=scene.evidence_turn,
        ),
    )

    coordinator.flush_player(_PLAYER, _BEING)

    traces = [e.payload for e in recorder.events if e.kind == TraceEventKind.BELIEF_CONSOLIDATION]
    payload = traces[0] if traces else {}
    active = [e.text for e in semantic.list_for_being(_BEING) if e.status == SEMANTIC_MEMORY_STATUS_ACTIVE]
    return {
        "scene": scene.name,
        "expect_change": scene.expect_change,
        "consolidated": bool(traces),
        "actions": [d.get("action") for d in payload.get("decisions", [])],
        "decisions": payload.get("decisions", []),
        "skipped": payload.get("skipped_decisions", []),
        "state_belief_active": scene.belief_text in active,
        "active_beliefs": active,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--profile", required=True, help="信念を固める処理を有効にした profile の名前 (例: station_drill)"
    )
    parser.add_argument("--reps", type=int, default=5)
    parser.add_argument("--max-calls", type=int, default=50)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()

    from dotenv import load_dotenv

    load_dotenv(_REPO_ROOT / ".env")
    profile = json.loads(
        (_REPO_ROOT / "data" / "experiment_profiles" / f"{args.profile}.json").read_text()
    )
    config = ResolvedLlmRuntimeConfig.from_mapping(
        values=_runtime_config_mapping_from_source(profile)
    )
    inner = create_llm_client_from_config(config)
    if not isinstance(inner, LiteLLMClient):
        raise SystemExit("profile の LLM_CLIENT が litellm ではない")
    counter = _CostCountingClient(inner)

    planned = args.reps * len(SCENES)
    if planned > args.max_calls:
        raise SystemExit(f"予定の呼び出し {planned} 回が上限 {args.max_calls} 回を超える")

    results = [run_scene(scene, inner) for _ in range(args.reps) for scene in SCENES]

    print(f"model={config.llm_model} calls={counter.calls} cost_usd={counter.cost_usd:.4f}")
    for scene in SCENES:
        rows = [r for r in results if r["scene"] == scene.name]
        changed = sum("explain_change" in r["actions"] for r in rows)
        actions = Counter(a for r in rows for a in r["actions"])
        print(
            f"- {scene.name} (変わり方を期待={scene.expect_change}): "
            f"explain_change {changed}/{len(rows)} / 操作 {dict(actions)}"
        )
        for r in rows:
            made = [d.get("text") for d in r["decisions"] if d.get("text")]
            print(f"    {r['actions']} {made}")
    if args.out:
        args.out.write_text(
            json.dumps(
                {"model": config.llm_model, "calls": counter.calls, "cost_usd": counter.cost_usd, "results": results},
                ensure_ascii=False,
                indent=2,
            )
        )


if __name__ == "__main__":
    main()
