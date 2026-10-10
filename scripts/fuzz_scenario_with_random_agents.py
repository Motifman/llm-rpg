"""でたらめに行動するエージェントでシナリオを回し、組み合わせの穴を実 run の前に見つける (#1557)。

全員が :class:`RandomLlmClient` で、提示された tool と候補からシードに従って行動を
選ぶ。次を見つけたら、そのシードは失敗として、tick と行動の並びを添えて出す。

- ``exception``: 例外が ``advance_tick`` の外まで抜けて run が止まった。または、世界の tick が
  1 体ぶんの例外を取りやめて run を続けた (trace の ``world_tick_unit_failed``、#1558)
- ``swallowed_exception``: ツールの中で想定外の例外が握られ、trace にだけ残った
- ``logged_error``: engine が ERROR 以上のログを出した
- ``leak``: エージェントへの文に、内部の番号やシナリオの ID が出た
- ``check``: シナリオごとに足した検査 (``extra_checks``) が文を返した
- ``unreadable_candidates``: 候補表にスタブが読み戻せない行があった。でたらめな行動が黙って減る

漏れは、メッセージの本文とツール定義の説明文の両方で探す。Issue にしてまだ直っていない穴は
``KNOWN_HOLES`` に書く。見つけても run を失敗にせず、Issue 番号を添えて出す。

同じシード・同じ tick 数・同じコードなら、同じ行動の並びになる。世界の乱数
(``SCENARIO_RANDOM_SEED``) にも同じシードを渡す。

    uv run python scripts/fuzz_scenario_with_random_agents.py \\
        --scenario data/scenarios/mine_village_v1.json --seeds 0-19 --ticks 30
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
import tempfile
import traceback
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
SMOKE_STUB_PROFILE = REPO_ROOT / "data" / "experiment_profiles" / "smoke_stub.json"

#: 内部の番号が文に出た形。「スポット 19」「到達不能: 16 → 19」「spot_id=3」「tick=20」、
#: 世界の外の日付「2026-10-10 22:56」。
INTERNAL_NUMBER_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"(?:スポット|オブジェクト|プレイヤー|アイテム|エンティティ)\s*(?:ID\s*)?[#:=：]?\s*\d+"),
    re.compile(r"(?<![\d:])\d+\s*(?:→|->)\s*\d+(?![\d:])"),
    re.compile(r"\b[a-z]+_id\b\s*[=:：]?\s*\d+"),
    re.compile(r"\b(?:Spot|Object|Player|Item|Entity)Id\b"),
    re.compile(r"\btick\s*[=:：]\s*\d+"),
    re.compile(r"\b20\d\d-\d\d-\d\d\b"),
)

#: 世界の tick で 1 体ぶんの例外を取りやめて run を続けたときの trace (#1558)。止まらなくても例外として数える。
WORLD_TICK_UNIT_FAILED = "world_tick_unit_failed"

#: ターンの文を見て、穴を見つけたら説明の文を返す検査。シナリオごとに足す。
TurnCheck = Callable[["TurnView"], Iterable[str]]


@dataclass(frozen=True)
class TurnView:
    """1 回の LLM 呼び出しで、エージェントに見えていたもの。"""

    tick: int
    texts: tuple[str, ...]


@dataclass(frozen=True)
class FuzzAction:
    tick: int
    player_id: int
    tool: str
    arguments: Mapping[str, Any]

    def describe(self) -> str:
        args = json.dumps(
            {k: v for k, v in self.arguments.items() if k != "inner_thought"},
            ensure_ascii=False,
            sort_keys=True,
        )
        return f"tick {self.tick} P{self.player_id} {self.tool} {args}"


@dataclass(frozen=True)
class FuzzFinding:
    kind: str
    tick: int
    detail: str
    known_issue: int | None = None


@dataclass(frozen=True)
class KnownHole:
    """Issue にしてまだ直っていない穴。見つけても run を失敗にせず、Issue 番号を添えて出す。"""

    issue: int
    kind: str
    pattern: re.Pattern[str]


#: 直したら消す。残すと、同じ形が再発しても見逃す。新しい穴が紛れないよう、形はなるべく狭く書く。
KNOWN_HOLES: tuple[KnownHole, ...] = (
    KnownHole(
        1562,
        "leak",
        re.compile(r"今ターンは行動を控えた: tick=\d+|\[tick=\d+, 経過 \d+ tick\]|残り行動可能 tick: \d+"),
    ),
    KnownHole(1563, "leak", re.compile(r"\(追加: 20\d\d-\d\d-\d\d \d\d:\d\d\)")),
)


def classify(finding: FuzzFinding, known_holes: Sequence[KnownHole]) -> FuzzFinding:
    for hole in known_holes:
        if hole.kind == finding.kind and hole.pattern.search(finding.detail):
            return FuzzFinding(finding.kind, finding.tick, finding.detail, hole.issue)
    return finding


@dataclass
class FuzzResult:
    scenario: str
    seed: int
    max_world_ticks: int
    reached_tick: int = 0
    actions: list[FuzzAction] = field(default_factory=list)
    findings: list[FuzzFinding] = field(default_factory=list)

    @property
    def failed(self) -> bool:
        return any(f.known_issue is None for f in self.findings)

    @property
    def known_issues(self) -> list[int]:
        return sorted({f.known_issue for f in self.findings if f.known_issue is not None})

    def report(self, *, last_actions: int = 20) -> str:
        """失敗の再現に要るもの (シナリオ・シード・tick・行動の並び・見つけたもの) を文にする。"""
        head = (
            f"{self.scenario} seed={self.seed} ticks={self.max_world_ticks} "
            f"reached={self.reached_tick} actions={len(self.actions)}"
        )
        known = " known=" + ",".join(f"#{n}" for n in self.known_issues) if self.known_issues else ""
        if not self.failed:
            return f"OK   {head}{known}"
        lines = [f"FAIL {head}{known}"]
        lines += [f"  [{f.kind}] tick {f.tick}: {f.detail}" for f in self.findings if f.known_issue is None]
        first_tick = min(f.tick for f in self.findings if f.known_issue is None)
        upto = [a for a in self.actions if a.tick <= first_tick][-last_actions:]
        lines.append(f"  直前までの行動 (最後の {len(upto)} 件):")
        lines += [f"    {a.describe()}" for a in upto]
        return "\n".join(lines)


def scenario_identifiers(scenario_path: Path) -> frozenset[str]:
    """シナリオ JSON の ``id`` に書かれた英字の識別子。エージェントへの文に出たら漏れ。"""
    found: set[str] = set()

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                if key == "id" and isinstance(value, str) and re.fullmatch(r"[a-z][a-z0-9_]*_[a-z0-9_]+", value):
                    found.add(value)
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    walk(json.loads(scenario_path.read_text(encoding="utf-8")))
    return frozenset(found)


def find_leaks(text: str, identifiers: Iterable[str]) -> list[str]:
    """文のうち、内部の番号かシナリオの ID が出ている行を返す。"""
    id_pattern = _identifier_pattern(identifiers)
    leaks: list[str] = []
    for line in text.splitlines():
        if any(p.search(line) for p in INTERNAL_NUMBER_PATTERNS) or (id_pattern and id_pattern.search(line)):
            leaks.append(line.strip())
    return leaks


def unreadable_candidate_lines(text: str) -> list[str]:
    """【現在選べる対象引数】の表のうち、スタブが読み戻せなかった行。あれば、でたらめな行動が黙って減っている。"""
    from ai_rpg_world.application.llm.services.dynamic_argument_candidates import (
        parse_dynamic_argument_candidate_table,
    )

    lines = text.splitlines()
    if "【現在選べる対象引数】" not in lines:
        return []
    start = lines.index("【現在選べる対象引数】") + 1
    rows = []
    for line in lines[start:]:
        if not line.startswith("- "):
            break
        rows.append(line)
    return rows[len(parse_dynamic_argument_candidate_table(text)) :]


def tool_texts(tools: Sequence[Mapping[str, Any]]) -> list[str]:
    """ツール定義のうち、エージェントが読む説明文と enum の値。"""
    texts: list[str] = []

    def walk(node: Any) -> None:
        if isinstance(node, Mapping):
            for key, value in node.items():
                if key == "description" and isinstance(value, str):
                    texts.append(value)
                elif key == "enum" and isinstance(value, list):
                    texts.append(" ".join(map(str, value)))
                else:
                    walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    walk(list(tools))
    return texts


def leak_shape(line: str) -> str:
    """時刻・数字・memo の印を伏せた形。同じ漏れが tick ごとに数字だけ変えて何度も出るのを 1 件にまとめる。"""
    line = re.sub(r"^- \[Day [^\]]*\]\s*", "", line)
    line = re.sub(r"\[?(?:memo_)?[0-9a-f]{6,}…?\]?|\[STALE\]\s*", "", line)
    return re.sub(r"\d+", "N", line)


def _identifier_pattern(identifiers: Iterable[str]) -> re.Pattern[str] | None:
    ids = sorted(identifiers, key=len, reverse=True)
    if not ids:
        return None
    return re.compile(r"(?<![A-Za-z0-9_])(?:" + "|".join(map(re.escape, ids)) + r")(?![A-Za-z0-9_])")


def _smoke_stub_runtime_config(seed: int) -> Any:
    from ai_rpg_world.application.llm.wiring.resolved_runtime_config import ResolvedLlmRuntimeConfig

    profile = json.loads(SMOKE_STUB_PROFILE.read_text(encoding="utf-8"))
    # 待ちの上限を 1 tick にして、全員が毎 tick 行動する。同じ tick 数で試す組み合わせを増やすため。
    values = {**profile["runtime_config"], "SCENARIO_RANDOM_SEED": seed, "LLM_IDLE_TIMEOUT_TICKS": 1}
    rendered = {
        key: ("1" if v else "0") if isinstance(v, bool) else str(v) for key, v in values.items()
    }
    return ResolvedLlmRuntimeConfig.from_mapping(values=rendered)


class _ErrorLogCollector(logging.Handler):
    def __init__(self, clock: Callable[[], int]) -> None:
        super().__init__(level=logging.ERROR)
        self._clock = clock
        self.records: list[tuple[int, str]] = []

    def emit(self, record: logging.LogRecord) -> None:
        detail = record.getMessage()
        if record.exc_info and record.exc_info[1] is not None:
            exc = record.exc_info[1]
            detail = f"{detail} ({type(exc).__name__}: {exc})"
        self.records.append((self._clock(), f"{record.name}: {detail}"))


def _compact(payload: Mapping[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)[:300]


def _swallowed_exception(payload: Mapping[str, Any]) -> str | None:
    nested = payload.get("tool_trace_payload")
    for source in (payload, nested if isinstance(nested, Mapping) else {}):
        exc_type = source.get("tool_exception_type")
        if exc_type:
            return f"{exc_type} at {source.get('tool_exception_location')}/{source.get('tool_exception_stage')}"
    if payload.get("error_code") == "SYSTEM_ERROR":
        return f"SYSTEM_ERROR: {payload.get('result_summary')}"
    return None


def _describe_exception(exc: BaseException) -> str:
    chain = [exc]
    while chain[-1].__cause__ is not None and len(chain) < 5:
        chain.append(chain[-1].__cause__)
    causes = " <= ".join(f"{type(e).__name__}: {e}" for e in chain)
    return f"{causes} [{_src_frames(chain[-1])}]"


def _src_frames(exc: BaseException, limit: int = 4) -> str:
    frames = [f for f in traceback.extract_tb(exc.__traceback__) if "/ai_rpg_world/" in f.filename]
    return " <- ".join(
        f"{Path(f.filename).name}:{f.lineno} {f.name}" for f in reversed(frames[-limit:])
    )


def run_random_agents(
    scenario_path: Path,
    *,
    seed: int,
    max_world_ticks: int,
    extra_checks: Sequence[TurnCheck] = (),
    known_holes: Sequence[KnownHole] = KNOWN_HOLES,
) -> FuzzResult:
    """シナリオを、全員でたらめに行動させて ``max_world_ticks`` まで回す。"""
    result = FuzzResult(scenario=scenario_path.stem, seed=seed, max_world_ticks=max_world_ticks)
    identifiers = scenario_identifiers(scenario_path)
    seen_leaks: set[str] = set()

    saved_tick_loop = os.environ.get("SPOT_GRAPH_TICK_LOOP_ENABLED")
    os.environ["SPOT_GRAPH_TICK_LOOP_ENABLED"] = "false"
    try:
        _drive(scenario_path, seed, max_world_ticks, extra_checks, result, identifiers, seen_leaks)
    finally:
        if saved_tick_loop is None:
            os.environ.pop("SPOT_GRAPH_TICK_LOOP_ENABLED", None)
        else:
            os.environ["SPOT_GRAPH_TICK_LOOP_ENABLED"] = saved_tick_loop
    result.findings = [classify(f, known_holes) for f in result.findings]
    return result


def _drive(
    scenario_path: Path,
    seed: int,
    max_world_ticks: int,
    extra_checks: Sequence[TurnCheck],
    result: FuzzResult,
    identifiers: frozenset[str],
    seen_leaks: set[str],
) -> None:
    from ai_rpg_world.application.llm.ports.llm_client_port import ILLMClient
    from ai_rpg_world.application.llm.services.llm_client_random import RandomLlmClient
    from ai_rpg_world.application.trace.recorder import NullTraceRecorder
    from ai_rpg_world.presentation.spot_graph_game.runtime_manager import GameRuntimeManager
    from ai_rpg_world.presentation.spot_graph_game.schemas import (
        CharacterCreateRequest,
        SessionCreateRequest,
    )

    with tempfile.TemporaryDirectory() as tmp:
        mgr = GameRuntimeManager(
            scenarios_dir=scenario_path.parent,
            characters_path=Path(tmp) / "characters.json",
            runtime_config=_smoke_stub_runtime_config(seed),
        )
        char = mgr.create_character(CharacterCreateRequest(name="fuzz"))
        summary = mgr.create_session(
            SessionCreateRequest(world_id=scenario_path.stem, character_ids=[char.id])
        )
        state = mgr._sessions[summary.session_id]
        runtime = state.runtime

        def on_trace(kind: str, tick: int | None, player_id: int | None, payload: Mapping[str, Any]) -> None:
            if kind == "action":
                result.actions.append(
                    FuzzAction(int(tick or 0), int(player_id or 0), str(payload.get("tool")), dict(payload.get("arguments") or {}))
                )
            elif kind == WORLD_TICK_UNIT_FAILED:
                result.findings.append(FuzzFinding("exception", int(tick or 0), f"世界の tick で 1 体ぶん取りやめた: {_compact(payload)}"))
            elif kind == "action_result":
                swallowed = _swallowed_exception(payload)
                if swallowed:
                    result.findings.append(FuzzFinding("swallowed_exception", int(tick or 0), f"{payload.get('tool')}: {swallowed}"))

        class _Recorder(NullTraceRecorder):
            def record(self, kind, *, tick=None, player_id=None, **payload):  # type: ignore[override]
                event = super().record(kind, tick=tick, player_id=player_id, **payload)
                on_trace(str(kind), tick, player_id, payload)
                return event

        random_client = RandomLlmClient(seed)

        class _ObservedClient(ILLMClient):
            """エージェントに見えていた文を検査してから、でたらめな選択を返す。"""

            def invoke(self, messages, tools, tool_choice="required", **kwargs):  # type: ignore[override]
                tick = runtime.current_tick()
                texts = tuple(str(m.get("content") or "") for m in messages)
                unreadable = unreadable_candidate_lines(texts[-1] if texts else "")
                if unreadable:
                    result.findings.append(FuzzFinding("unreadable_candidates", tick, unreadable[0]))
                for text in (*texts, *tool_texts(tools)):
                    for line in find_leaks(text, identifiers):
                        shape = leak_shape(line)
                        if shape not in seen_leaks:
                            seen_leaks.add(shape)
                            result.findings.append(FuzzFinding("leak", tick, line))
                for check in extra_checks:
                    for detail in check(TurnView(tick=tick, texts=texts)):
                        result.findings.append(FuzzFinding("check", tick, detail))
                return random_client.invoke(messages, tools, tool_choice, **kwargs)

        state.llm_wiring.llm_client = _ObservedClient()
        runtime.set_trace_recorder(_Recorder())
        errors = _ErrorLogCollector(runtime.current_tick)
        engine_logger = logging.getLogger("ai_rpg_world")
        saved_level = engine_logger.level
        # 外側で root の level を絞っていても、ERROR は捨てられる前にここで拾う。
        engine_logger.setLevel(min(engine_logger.getEffectiveLevel(), logging.ERROR))
        engine_logger.addHandler(errors)
        try:
            for pid in runtime.get_player_ids():
                state.llm_wiring.llm_turn_trigger.schedule_turn(pid)
            iterations = 0
            while runtime.current_tick() < max_world_ticks and iterations < max_world_ticks * 2:
                iterations += 1
                tick = runtime.current_tick()
                try:
                    runtime.advance_tick()
                except Exception as exc:  # noqa: BLE001
                    result.findings.append(FuzzFinding("exception", tick, _describe_exception(exc)))
                    break
            result.reached_tick = runtime.current_tick()
        finally:
            engine_logger.removeHandler(errors)
            engine_logger.setLevel(saved_level)
        result.findings += [FuzzFinding("logged_error", t, d) for t, d in errors.records]


def _parse_seeds(text: str) -> list[int]:
    seeds: list[int] = []
    for part in text.split(","):
        if "-" in part:
            lo, hi = part.split("-", 1)
            seeds.extend(range(int(lo), int(hi) + 1))
        else:
            seeds.append(int(part))
    return seeds


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--scenario", type=Path, action="append", required=True)
    parser.add_argument("--seeds", default="0-9", help="例: 0-19 / 3,7,11")
    parser.add_argument("--ticks", type=int, default=30)
    args = parser.parse_args(argv)

    logging.getLogger().addHandler(logging.NullHandler())
    results: list[FuzzResult] = []
    for scenario in args.scenario:
        for seed in _parse_seeds(args.seeds):
            result = run_random_agents(scenario, seed=seed, max_world_ticks=args.ticks)
            results.append(result)
            print(result.report(), flush=True)
    print(summarize(results))
    return 1 if any(r.failed for r in results) else 0


def summarize(results: Sequence[FuzzResult]) -> str:
    """見つけた穴を形ごとにまとめ、どのシードの何 tick で最初に出たかを並べる。"""
    shapes: dict[tuple[str, str, str], list[tuple[int, int]]] = {}
    for result in results:
        for finding in result.findings:
            label = finding.kind if finding.known_issue is None else f"{finding.kind} 既知 #{finding.known_issue}"
            key = (result.scenario, label, leak_shape(finding.detail))
            shapes.setdefault(key, []).append((result.seed, finding.tick))
    failed = sum(r.failed for r in results)
    lines = [f"== {len(results)} run(s), {failed} failed, {len(shapes)} distinct finding(s)"]
    for (scenario, kind, shape), hits in sorted(shapes.items(), key=lambda item: -len(item[1])):
        seeds = sorted({seed for seed, _ in hits})
        first_seed, first_tick = min(hits, key=lambda hit: (hit[1], hit[0]))
        lines.append(
            f"{scenario} [{kind}] seeds={len(seeds)} (first: seed {first_seed} tick {first_tick}) {shape[:200]}"
        )
    return "\n".join(lines)


if __name__ == "__main__":
    sys.exit(main())
