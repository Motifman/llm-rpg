"""過去 run のループ警告の場面を組み直し、繰り返しの理由を Jev に見立てさせる (#1411)。

場面ごとに、その run の trace から警告を受けた本人の行動列を読み、本番と同じ
``ToolCallLoopGuardService`` に流し直す。警告が発火した時点で見立てを問うので、
Jev に渡る state は run 中に組まれるはずだったものと同じ形になる。

- 行動と結果: ``action`` と ``action_result`` の対
- tick: 各行動の tick
- 現在地: 本人のその tick のプロンプト (``prompt_dataset/calls.jsonl``) にある
  「現在地:」。``position_change`` は到着より遅れて trace に載るので使わない
  (market_town_v37_division では t25 のプロンプトが土手なのに、trace の到着は警告の後)
- いま届いている観測: 本人の ``observation`` を積み、本人の次の行動で空にする
  (プロンプトを組むときに buffer を読み切るのと同じ)

使い方:
    uv run python scripts/jev_loop_diagnosis_demo.py --runs-dir ../../../var/runs --out var/jev_loop_diagnosis/results.json
    uv run python scripts/jev_loop_diagnosis_demo.py --runs-dir ../../../var/runs --port stub
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT / "src"))

from ai_rpg_world.application.llm.ports.typed_judgment_port import (  # noqa: E402
    ITypedJudgmentPort,
)
from ai_rpg_world.application.llm.services.loop_diagnosis import (  # noqa: E402
    QUESTION_NAME,
    LoopDiagnosis,
)
from ai_rpg_world.application.llm.services.tool_call_loop_guard import (  # noqa: E402
    ToolCallLoopGuardService,
)
from ai_rpg_world.application.observation.contracts.dtos import (  # noqa: E402
    ObservationEntry,
    ObservationOutput,
)
from ai_rpg_world.application.observation.services.observation_context_buffer import (  # noqa: E402
    DefaultObservationContextBuffer,
)
from ai_rpg_world.application.trace import NullTraceRecorder, TraceEventKind  # noqa: E402
from ai_rpg_world.domain.player.value_object.player_id import PlayerId  # noqa: E402


@dataclass(frozen=True)
class Scene:
    run: str
    player_id: int
    warning_seq: int
    #: Issue 本文に書いた、実際に起きていたこと。見立ての当否を人が読むための対照
    what_happened: str


SCENES: tuple[Scene, ...] = (
    Scene(
        "market_town_v37_division",
        1,
        372,
        "t23 で到着済み。本人は移動中と思っていた。居場所の取り違え",
    ),
    Scene(
        "market_town_v37_division",
        3,
        569,
        "bake_bread の前提条件失敗が 8 tick 空けて再発。麦束が無いことは失敗文にある",
    ),
    Scene(
        "offering_race_v2_second",
        1,
        914,
        "ユノへの同じ申し出 ×3。返事が無いので言い直している",
    ),
    Scene(
        "station_drill_gemma31_jev_001",
        4,
        1713,
        "引数なしの wait ×3。他人が居なくなるのを待っていた可能性",
    ),
)


class _CapturingRecorder(NullTraceRecorder):
    def __init__(self) -> None:
        super().__init__()
        self.events: list[tuple[str, dict[str, Any]]] = []

    def record(self, kind, *, tick=None, player_id=None, **payload):  # type: ignore[no-untyped-def,override]
        self.events.append((kind, {"tick": tick, "player_id": player_id, **payload}))
        return super().record(kind, tick=tick, player_id=player_id, **payload)


def _load(run_dir: Path) -> list[dict[str, Any]]:
    with (run_dir / "trace.jsonl").open() as f:
        return [json.loads(line) for line in f]


_LOCATION = re.compile(r"現在地: ([^\s\\(（]+)")


def _prompt_locations(run_dir: Path, pid: int) -> dict[int, str]:
    """tick → その tick のプロンプトに出ていた本人の現在地。"""
    locations: dict[int, str] = {}
    calls = run_dir / "prompt_dataset" / "calls.jsonl"
    if not calls.exists():
        return locations
    with calls.open() as f:
        for line in f:
            call = json.loads(line)
            if call.get("player_id") != pid:
                continue
            m = _LOCATION.search(json.dumps(call.get("prompt"), ensure_ascii=False))
            if m:
                locations[int(call["world_tick"])] = m.group(1)
    return locations


def replay(scene: Scene, runs_dir: Path, port: ITypedJudgmentPort) -> dict[str, Any]:
    events = _load(runs_dir / scene.run)
    locations = _prompt_locations(runs_dir / scene.run, scene.player_id)
    pid = PlayerId.create(scene.player_id)
    location: list[str | None] = [None]
    tick = [0]
    buffer = DefaultObservationContextBuffer()
    recorder = _CapturingRecorder()
    guard = ToolCallLoopGuardService(
        buffer,
        time_label_provider=lambda: None,
        clock=lambda: datetime(2026, 1, 1, tzinfo=timezone.utc),
        trace_recorder=recorder,
        current_tick_provider=lambda: tick[0],
        loop_diagnosis=LoopDiagnosis(port=port),
        location_provider=lambda _pid: location[0],
    )
    pending_action: dict[str, Any] | None = None
    for e in events:
        if e["seq"] > scene.warning_seq:
            break
        if e.get("player_id") != scene.player_id:
            continue
        kind, p = e["kind"], e["payload"]
        if kind == "observation" and p.get("prose"):
            buffer.append(
                pid,
                ObservationEntry(
                    occurred_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
                    output=ObservationOutput(prose=p["prose"], structured=p.get("structured") or {}),
                ),
            )
        elif kind == "action":
            buffer.drain(pid)
            pending_action = p
        elif kind == "action_result" and pending_action is not None:
            tick[0] = int(e.get("tick") or 0)
            location[0] = locations.get(tick[0], location[0])
            guard.record_and_check(
                pid,
                p["tool"],
                pending_action.get("arguments") or {},
                success=p.get("success"),
                error_code=p.get("error_code"),
                result_summary=p.get("result_summary"),
            )
            pending_action = None
    judgments = [
        pl for k, pl in recorder.events if k == TraceEventKind.TYPED_JUDGMENT and pl.get("question") == QUESTION_NAME
    ]
    warnings = [pl for k, pl in recorder.events if k == TraceEventKind.LOOP_GUARD_WARNING]
    prose = [e.output.prose for e in buffer.get_observations(pid) if (e.output.structured or {}).get("loop_guard")]
    return {
        "scene": scene.__dict__,
        "judgment": judgments[-1] if judgments else None,
        "warning": warnings[-1] if warnings else None,
        "prose": prose[-1] if prose else None,
    }


def _port(kind: str) -> ITypedJudgmentPort:
    if kind == "stub":
        from ai_rpg_world.application.llm.services.typed_judgment_stub import DeterministicTypedJudgmentPort

        return DeterministicTypedJudgmentPort()
    from dotenv import load_dotenv

    load_dotenv()
    load_dotenv(_REPO_ROOT.parent.parent.parent / ".env")
    from ai_rpg_world.application.llm.wiring._typed_judgment_factory import create_typed_judgment_port_from_config
    from ai_rpg_world.application.llm.wiring.resolved_runtime_config import ResolvedLlmRuntimeConfig

    port = create_typed_judgment_port_from_config(ResolvedLlmRuntimeConfig.for_tests(typed_judgment_provider="jev"))
    assert port is not None
    return port


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs-dir", required=True)
    parser.add_argument("--out", default="var/jev_loop_diagnosis/results.json")
    parser.add_argument("--port", choices=("jev", "stub"), default="jev")
    args = parser.parse_args(argv)
    port = _port(args.port)
    results = [replay(s, Path(args.runs_dir), port) for s in SCENES]
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(results, ensure_ascii=False, indent=1))
    for r in results:
        s, j = r["scene"], r["judgment"]
        print(f"\n=== {s['run']} p{s['player_id']} seq {s['warning_seq']}")
        print(f"実際: {s['what_happened']}")
        if j is None:
            print("警告が発火しなかった (組み直しの誤り)")
            continue
        probs = ", ".join(f"{k}={v:.2f}" for k, v in sorted(j["probabilities"].items(), key=lambda kv: -kv[1]))
        print(
            f"見立て: {j['chosen']} 確信={j['confidence']} 採用={j['accepted']} 縮退={j['fallback_reason']} {j.get('unavailable_reason') or ''}"
        )
        print(f"確率: {probs}")
        print(f"文面: {r['prose']}")
    print(f"\n→ {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
