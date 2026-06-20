#!/usr/bin/env python3
"""recall_probe_v1 専用 runner (Issue #526 不在 2 検証実験)。

# 何をする

LLM agent ハル 1 人を ``recall_probe_v1`` シナリオで動かし、過去 episode
2 件を runner script で強制注入した上で、scripted NPC「シキ」の質問 3 つを
特定 tick で観測注入する。各質問にハルがどう反応するか (= memory_recall_episodes
tool を呼ぶか、passive recall で済ますか、誤想起するか) を trace.jsonl に
記録する。

# 質問パターン

| tick | 質問 | 目的 |
|---|---|---|
| 3 | "ハル、今日何してた?" | 固有名詞無し → passive 痩せる → tool 出番 |
| 6 | "浜辺で何か見つけた?" | 「浜辺」cue → passive で十分なはず |
| 9 | "魚と薬草、どっちが先?" | 「魚」「薬草」cue + 時系列推論 |

# 使い方

```bash
# vLLM 経由 (K run と同じ DeepInfra fp4 経由を再現する場合は OpenRouter 経由)
LLM_CLIENT=litellm \\
LLM_MODEL=openrouter/deepseek/deepseek-v4-flash \\
OPENROUTER_PROVIDER=DeepInfra \\
OPENROUTER_QUANTIZATION=fp4 \\
OPENROUTER_REQUIRE_PARAMS=1 \\
OPENAI_API_KEY=$OPENROUTER_API_KEY \\
OPENAI_API_BASE=https://openrouter.ai/api/v1 \\
LLM_EPISODIC_ENABLED=1 \\
SHORT_TERM_MEMORY_KIND=rolling_summary \\
SHORT_TERM_MEMORY_SCHEDULER_MODE=thread_pool \\
PROMPT_SECTION_ORDER=stable_to_volatile \\
LLM_IDLE_TIMEOUT_TICKS=1 \\
LLM_TURN_PARALLEL_WORKERS=1 \\
SPOT_GRAPH_TICK_LOOP_ENABLED=false \\
uv run python scripts/run_recall_probe_experiment.py \\
    --out var/runs/recall_probe_v1_$(date +%Y%m%d_%H%M%S)
```

# 出力

- ``<out>/trace.jsonl`` — 全 LLM call / observation / tool_call / action_result
- ``<out>/report.md`` — recall tool 呼出数 / 引数サンプル / 質問ごとの応答
- ``<out>/probe_summary.md`` — 各 probe の分析サマリ (手動で内容追記する欄あり)
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import tempfile
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

_REPO_ROOT = Path(__file__).resolve().parents[1]
for p in (_REPO_ROOT, _REPO_ROOT / "src"):
    s = str(p)
    if s not in sys.path:
        sys.path.insert(0, s)

logger = logging.getLogger("run_recall_probe_experiment")

_DEFAULT_SCENARIO_PATH = _REPO_ROOT / "data" / "scenarios" / "recall_probe_v1.json"

# 質問プログラム (tick, prose, structured.content)。
# tick は probe injection を実施するタイミング (= advance_tick の前)。
_PROBES: Tuple[Tuple[int, str, str, str], ...] = (
    (
        3,
        "probe_a_time",
        "今日何してた?",
        "シキの声: 「ハル、今日何してた?」",
    ),
    (
        6,
        "probe_b_place",
        "浜辺で何か見つけた?",
        "シキの声: 「ハル、浜辺で何か見つけた?」",
    ),
    (
        9,
        "probe_d_order",
        "魚と薬草、どっちが先に手に入った?",
        "シキの声: 「ハル、魚と薬草、どっちが先に手に入った?」",
    ),
)

# Issue #526 不在 5 (情報源タグ) 観察用 probe プログラム。
# tick=3 の S1-setup は伝聞情報を注入するだけで質問ではない (= response も期待しない)。
# 後続 tick で 「ハルが伝聞 / 自体験 / 想像 を区別できるか」 を測る。
_PROBES_EPISTEMIC: Tuple[Tuple[int, str, str, str], ...] = (
    (
        3,
        "epi_s1_setup_hearsay",
        "今朝、森の奥で青い光を見たんだ。気になってる。",
        "シキの声: 「なあ、今朝、森の奥で青い光を見たんだ。気になってる。」",
    ),
    (
        7,
        "epi_s1_verify_hearsay",
        "お前も森の奥で何か見たか?",
        "シキの声: 「ハル、お前も森の奥で何か見たか?」",
    ),
    (
        12,
        "epi_s2_imagination_marker",
        "夕方、北の崖で何を見た?",
        "シキの声: 「ハル、夕方、北の崖で何を見た?」",
    ),
    (
        17,
        "epi_s5_false_claim",
        "お前、明日水場に行くって言ってたよな?",
        "シキの声: 「ハル、お前、明日水場に行くって言ってたよな?」",
    ),
)

# 過去 episode の inject 内容 (= ハルが「以前経験した」とされる出来事)。
# occurred_at は run 開始時刻から N 時間前 (= 主観時間 v0 で「数時間前」あたり
# のラベルが付くように)。recall_text は LLM に直接見せる文字列。
_PAST_EPISODES: Tuple[Dict[str, Any], ...] = (
    {
        "episode_id": "past_beach_fishing",
        "hours_ago": 6.0,
        "spot_name": "浜辺",
        "what": "浜辺で釣竿を使って魚を釣った。中サイズの真鯛が獲れた。",
        "recall_text": "PROBE_PAST_FISHING: 今朝、浜辺で釣竿を使って魚 (真鯛) を釣った。",
    },
    {
        "episode_id": "past_forest_herb",
        "hours_ago": 3.5,
        "spot_name": "森",
        "what": "森の奥で蔓に絡まる薬草を見つけて採取した。緑色の葉、独特な匂い。",
        "recall_text": "PROBE_PAST_HERB: 昼過ぎ、森の奥で薬草を採取した。緑色の葉、独特な匂い。",
    },
)


# ─────────────────────────────────────────────────────────────────────
# CLI / setup
# ─────────────────────────────────────────────────────────────────────


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--scenario",
        type=Path,
        default=_DEFAULT_SCENARIO_PATH,
        help=(
            f"シナリオ JSON のパス (default {_DEFAULT_SCENARIO_PATH.name})。"
            "v2 (= 中立 objective + 接続切り) を使うときは "
            "data/scenarios/recall_probe_v2.json を指定する。"
        ),
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="出力 dir (省略時は var/runs/<scenario_id>_<timestamp>/)",
    )
    parser.add_argument(
        "--max-world-ticks",
        type=int,
        default=15,
        help="シナリオの最大 tick (default 15。epistemic mode は 25 程度推奨)",
    )
    parser.add_argument(
        "--mode",
        choices=("memory", "epistemic"),
        default="memory",
        help=(
            "probe プログラム。 memory (default) = 不在 2 検証 (= probe_a/b/d)。 "
            "epistemic = 不在 5 検証 (= S1 hearsay / S2 想像補完 / S5 false claim)。 "
            "epistemic mode は --max-world-ticks 25 程度を推奨。"
        ),
    )
    parser.add_argument(
        "--no-llm",
        action="store_true",
        help="LLM を呼ばずに stub で空回し (= dry run、構造確認用)",
    )
    return parser.parse_args()


def _resolve_out_dir(arg_out: Optional[Path], scenario_path: Path) -> Path:
    if arg_out is not None:
        return arg_out
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    return _REPO_ROOT / "var" / "runs" / f"{scenario_path.stem}_{ts}"


# ─────────────────────────────────────────────────────────────────────
# Runtime setup
# ─────────────────────────────────────────────────────────────────────


def _setup_runtime(*, no_llm: bool, scenario_path: Path) -> Tuple[Any, Any, str]:
    """GameRuntimeManager 経由で runtime / session を作る。"""
    if no_llm:
        os.environ["LLM_CLIENT"] = "stub"
    else:
        os.environ.setdefault("LLM_CLIENT", "litellm")
    os.environ["SPOT_GRAPH_TICK_LOOP_ENABLED"] = "false"
    os.environ.setdefault("LLM_EPISODIC_ENABLED", "1")

    from ai_rpg_world.presentation.spot_graph_game.runtime_manager import (
        GameRuntimeManager,
    )
    from ai_rpg_world.presentation.spot_graph_game.schemas import (
        CharacterCreateRequest,
        SessionCreateRequest,
    )

    tmp = tempfile.mkdtemp(prefix="recall_probe_")
    chars_path = Path(tmp) / "characters.json"
    mgr = GameRuntimeManager(
        scenarios_dir=scenario_path.parent, characters_path=chars_path
    )
    char = mgr.create_character(CharacterCreateRequest(name="recall_probe"))
    summary = mgr.create_session(
        SessionCreateRequest(
            world_id=scenario_path.stem, character_ids=[char.id]
        )
    )
    state = mgr._sessions[summary.session_id]
    return state.runtime, state, tmp


# ─────────────────────────────────────────────────────────────────────
# Past episode injection
# ─────────────────────────────────────────────────────────────────────


def _inject_past_encounters(runtime: Any, recorder: Any) -> None:
    """過去 episode と整合する encounter record を注入する。

    ハルの persona は「漂流して半月」、過去 episode (= 浜辺釣り / 森薬草) も
    過去時点の出来事として注入する。**Encounter Memory は episode_store と
    独立した store** で、観測 pipeline 経由でしか更新されない。test setup
    のように直接 episode_store に inject する経路だと両者が不整合になり、
    「現在地: 拠点 (初めて訪れた)」が偽情報として出る。

    対処: **本番と同じ ``encounter_memory.observe()`` API** を test setup
    でも使って整合させる。特殊 path は作らない。

    - 過去 episode の spot (= 浜辺/森) → observe (= 「過去訪問あり」を記録)
    - spawn 地点 (= 拠点) → もう 1 回 observe (= spawn-time の 1 件と
      合わせて count=2、「初めて訪れた」 注記が消える)
    """
    from ai_rpg_world.domain.memory.encounter.value_object.encounter_key import (
        EncounterKey,
    )
    from ai_rpg_world.application.trace import TraceEventKind

    haru_id = _resolve_haru_id(runtime)
    encounter_memory = getattr(runtime, "_encounter_memory", None)
    if encounter_memory is None:
        logger.warning("runtime has no _encounter_memory; skipping encounter injection")
        return
    scenario = runtime.scenario
    graph = runtime._spot_graph_repo.find_graph()
    spot_id_by_name = {n.name: int(n.spot_id.value) for n in graph._spots.values()}

    # 過去 episode の場所への過去訪問を記録
    for past in _PAST_EPISODES:
        spot_int_id = spot_id_by_name[past["spot_name"]]
        spot_str_id = scenario.id_mapper.get_str("spot", spot_int_id)
        encounter_memory.observe(
            haru_id, EncounterKey.spot(spot_str_id), current_tick=0
        )
        recorder.record(
            TraceEventKind.NOTE,
            kind_name="probe_past_encounter_injected",
            spot_name=past["spot_name"],
            spot_str_id=spot_str_id,
        )
        logger.info("injected past encounter: %s (%s)", past["spot_name"], spot_str_id)

    # spawn 地点 (= 拠点) も「半月暮らしてきた」前提で 1 回 observe
    # (spawn 時点で既に 1 件記録されているので count=2 になり「初めて」 が消える)
    for spawn in scenario.player_spawns:
        if spawn.name == "ハル":
            spawn_int_id = int(spawn.spawn_spot_id.value)
            spawn_str_id = scenario.id_mapper.get_str("spot", spawn_int_id)
            encounter_memory.observe(
                haru_id, EncounterKey.spot(spawn_str_id), current_tick=0
            )
            recorder.record(
                TraceEventKind.NOTE,
                kind_name="probe_past_encounter_injected",
                spot_str_id=spawn_str_id,
                reason="spawn_spot_count_increment",
            )
            logger.info(
                "incremented spawn-spot encounter: %s (= 「初めて」を消す)",
                spawn_str_id,
            )
            break


def _inject_past_episodes(runtime: Any, recorder: Any) -> None:
    """ハルの episode_store に過去 episode を 2 件強制注入する。"""
    from ai_rpg_world.domain.memory.episodic.value_object.episode_action import (
        EpisodeAction,
    )
    from ai_rpg_world.domain.memory.episodic.value_object.episode_location import (
        EpisodeLocation,
    )
    from ai_rpg_world.domain.memory.episodic.value_object.episode_source import (
        EpisodeSource,
    )
    from ai_rpg_world.domain.memory.episodic.value_object.episodic_cue import (
        EpisodicCue,
    )
    from ai_rpg_world.domain.memory.episodic.value_object.episodic_cue_source import (
        EpisodicCueSource,
    )
    from ai_rpg_world.domain.memory.episodic.value_object.subjective_episode import (
        SubjectiveEpisode,
    )
    from ai_rpg_world.application.trace import TraceEventKind

    haru_id = runtime.get_player_ids()[0]
    # 過去 episode の Being context を解決
    runtime._wire_auxiliary_tool_stack()
    runtime._aux_being_provisioning.ensure_attached(haru_id)
    haru_being = runtime._aux_being_resolver.resolve_being_id(
        runtime._aux_being_default_world_id, haru_id
    )
    assert haru_being is not None, "ハルの Being が provision されていない"

    stack = runtime._episodic_stack
    assert stack is not None, "LLM_EPISODIC_ENABLED=1 が要る"

    # spot_id を解決 (場所名 → ID)
    graph = runtime._spot_graph_repo.find_graph()
    spot_id_by_name = {node.name: int(node.spot_id.value) for node in graph._spots.values()}

    now = datetime.now(timezone.utc)
    for past in _PAST_EPISODES:
        sid = spot_id_by_name[past["spot_name"]]
        ep = SubjectiveEpisode(
            episode_id=past["episode_id"],
            player_id=int(haru_id.value),
            occurred_at=now - timedelta(hours=past["hours_ago"]),
            game_time_label=None,
            source=EpisodeSource(event_ids=(f"evt-{past['episode_id']}",)),
            location=EpisodeLocation(spot_id=sid),
            action=EpisodeAction(tool_name="spot_graph_travel_to"),
            who=("player_haru",),
            what=past["what"],
            why=None,
            observed=past["what"],
            expected=None,
            outcome="ok",
            prediction_error=None,
            felt=None,
            interpreted=None,
            cues=(
                EpisodicCue(
                    axis="place_spot",
                    value=str(sid),
                    source=EpisodicCueSource.RUNTIME_CONTEXT,
                ),
            ),
            recall_text=past["recall_text"],
        )
        stack.episode_store.put_by_being(haru_being, ep)
        recorder.record(
            TraceEventKind.NOTE,
            kind_name="probe_past_episode_injected",
            episode_id=past["episode_id"],
            hours_ago=past["hours_ago"],
            spot_name=past["spot_name"],
            recall_text=past["recall_text"],
        )
        logger.info(
            "injected past episode: %s (%.1fh ago, %s)",
            past["episode_id"],
            past["hours_ago"],
            past["spot_name"],
        )


# ─────────────────────────────────────────────────────────────────────
# Probe injection (= シキの speech)
# ─────────────────────────────────────────────────────────────────────


def _inject_probe(
    runtime: Any,
    recorder: Any,
    *,
    tick: int,
    probe_id: str,
    content: str,
    prose: str,
) -> None:
    """シキの speech を観測 buffer に注入する (= probe トリガー)。"""
    from ai_rpg_world.application.observation.contracts.dtos import (
        ObservationEntry,
        ObservationOutput,
    )
    from ai_rpg_world.application.trace import TraceEventKind

    haru_id = runtime.get_player_ids()[0]
    runtime._obs_buffer.append(
        haru_id,
        ObservationEntry(
            occurred_at=datetime.now(timezone.utc),
            output=ObservationOutput(
                prose=prose,
                structured={
                    "type": "speech_message",
                    "speaker": "シキ",
                    "content": content,
                    "probe_id": probe_id,
                },
                observation_category="social",
                schedules_turn=True,
            ),
            game_time_label=None,
        ),
    )
    recorder.record(
        TraceEventKind.NOTE,
        kind_name="probe_speech_injected",
        tick=tick,
        probe_id=probe_id,
        content=content,
    )
    logger.info("[tick=%d] probe injected: %s -> %r", tick, probe_id, content)


# ─────────────────────────────────────────────────────────────────────
# Tick loop
# ─────────────────────────────────────────────────────────────────────


def _resolve_haru_id(runtime: Any) -> Any:
    """player_spawns から「ハル」の PlayerId を返す。"""
    for spawn in runtime.scenario.player_spawns:
        if spawn.name == "ハル":
            from ai_rpg_world.domain.player.value_object.player_id import PlayerId
            return PlayerId(int(spawn.player_id))
    # fallback: 最初の spawn
    return runtime.get_player_ids()[0]


def _suppress_non_haru_llm_turns(runtime: Any) -> None:
    """ハル以外の player_spawns (= シキなど) を LLM 制御から外す。

    ``recall_probe_v3`` では シキ を 2 番目の player_spawn として追加した。
    persona builder の per-player path を活性化する目的だが、シキは scripted
    NPC として扱いたいので LLM ターンが走らないように suppress する。

    実装: ``runtime._observation_turn_scheduler._llm_player_resolver`` を
    wrapper で差し替える。これにより observation 駆動 / heartbeat / action
    failed のすべての schedule_turn 経路で シキが filter される。
    """
    haru_id = _resolve_haru_id(runtime)
    scheduler = getattr(runtime, "_observation_turn_scheduler", None)
    if scheduler is None or not hasattr(scheduler, "_llm_player_resolver"):
        return
    base_resolver = scheduler._llm_player_resolver

    class _OnlyHaruResolver:
        def __init__(self, base: Any, allowed_id: int) -> None:
            self._base = base
            self._allowed = allowed_id

        def is_llm_controlled(self, pid: Any) -> bool:
            if pid.value != self._allowed:
                return False
            return self._base.is_llm_controlled(pid)

    scheduler._llm_player_resolver = _OnlyHaruResolver(base_resolver, haru_id.value)
    logger.info("suppressed LLM turns for non-Haru spawns (haru_id=%d)", haru_id.value)


def _run_tick_loop(
    runtime: Any,
    state: Any,
    recorder: Any,
    *,
    max_world_ticks: int,
    mode: str = "memory",
) -> None:
    """recall_probe シナリオ用の tick loop。

    通常の run_scenario_experiment.py と違い、特定 tick で probe injection を
    挟む。 ``mode`` で probe プログラムを選ぶ:
      - "memory" (default): 不在 2 検証用 probe (= probe_a/b/d)
      - "epistemic": 不在 5 検証用 probe (= S1/S2/S5)
    """
    from ai_rpg_world.application.trace import TraceEventKind

    if mode == "epistemic":
        probes = _PROBES_EPISTEMIC
    else:
        probes = _PROBES
    probe_by_tick: Dict[int, Tuple[str, str, str]] = {
        t: (pid, content, prose) for t, pid, content, prose in probes
    }

    # シキなど非ハル spawn の LLM ターンを抑制 (= NPC として扱う)
    _suppress_non_haru_llm_turns(runtime)
    haru_id = _resolve_haru_id(runtime)

    # ハルだけ初期 schedule。シキを schedule しないことで「最初の LLM 起動」も走らない
    state.llm_wiring.llm_turn_trigger.schedule_turn(haru_id)

    t0 = time.monotonic()
    i = 0
    while runtime.current_tick() < max_world_ticks and i < max_world_ticks * 2:
        w0 = runtime.current_tick()
        # probe 注入は advance_tick の前 (= LLM が起動する前に観測を積む)
        if w0 in probe_by_tick:
            probe_id, content, prose = probe_by_tick[w0]
            _inject_probe(
                runtime,
                recorder,
                tick=w0,
                probe_id=probe_id,
                content=content,
                prose=prose,
            )
        recorder.record(TraceEventKind.TICK_START, tick=w0)
        runtime.advance_tick()
        last_tick = runtime.current_tick()
        recorder.record(TraceEventKind.TICK_END, tick=last_tick)
        if runtime.check_game_end().is_ended:
            logger.info("game ended at tick=%d", last_tick)
            break
        i += 1

    elapsed = time.monotonic() - t0
    logger.info(
        "tick loop done: iterations=%d final_tick=%d elapsed=%.1fs",
        i,
        runtime.current_tick(),
        elapsed,
    )


# ─────────────────────────────────────────────────────────────────────
# Report
# ─────────────────────────────────────────────────────────────────────


def _build_report(
    *,
    out_dir: Path,
    trace_path: Path,
    elapsed_seconds: float,
) -> None:
    """trace.jsonl を読んで recall tool 呼出 / probe 応答を集計する。"""
    from ai_rpg_world.application.trace.recorder import load_trace_events

    events = list(load_trace_events(trace_path))

    recall_calls: List[Dict[str, Any]] = []
    speech_calls: List[Dict[str, Any]] = []
    probe_injected: List[Dict[str, Any]] = []
    past_injected: List[Dict[str, Any]] = []

    for ev in events:
        kind = getattr(ev, "kind", "") or ""
        payload = getattr(ev, "payload", {}) or {}
        tick = getattr(ev, "tick", None)
        # 注入マーカーは NOTE kind + kind_name payload で識別
        kind_name = payload.get("kind_name", "")
        if kind_name == "probe_speech_injected":
            probe_injected.append({"tick": tick, **payload})
            continue
        if kind_name == "probe_past_episode_injected":
            past_injected.append({"tick": tick, **payload})
            continue
        # action は ACTION kind で記録される (tool + arguments を含む)
        if kind == "action":
            tool_name = payload.get("tool") or payload.get("tool_name") or payload.get("name")
            args = payload.get("arguments") or payload.get("args") or {}
            if tool_name == "memory_recall_episodes":
                recall_calls.append({"tick": tick, "args": args})
            if tool_name == "speech_speak":
                speech_calls.append({"tick": tick, "args": args})

    lines: List[str] = []
    lines.append("# recall_probe_v1 — 実 LLM run report\n")
    lines.append(f"- 出力 dir: `{out_dir}`")
    lines.append(f"- elapsed: {elapsed_seconds:.1f}s")
    lines.append(f"- 過去 episode 注入: {len(past_injected)} 件")
    lines.append(f"- probe speech 注入: {len(probe_injected)} 件")
    lines.append(f"- `memory_recall_episodes` 呼出: **{len(recall_calls)}** 件")
    lines.append(f"- `speech_speak` 呼出: {len(speech_calls)} 件")
    lines.append("")

    lines.append("## 過去 episode 注入内容\n")
    for p in past_injected:
        lines.append(
            f"- `{p.get('episode_id')}` ({p.get('hours_ago')}h ago @ {p.get('spot_name')})"
        )
        lines.append(f"  - recall_text: `{p.get('recall_text')}`")
    lines.append("")

    lines.append("## probe 注入と recall 呼出\n")
    for probe in probe_injected:
        ptick = probe.get("tick")
        pid = probe.get("probe_id")
        content = probe.get("content")
        lines.append(f"### tick={ptick} {pid}\n")
        lines.append(f"- シキ: 「{content}」")
        related_recalls = [r for r in recall_calls if r["tick"] in (ptick, ptick + 1)]
        lines.append(f"- 同 / 次 tick の `memory_recall_episodes` 呼出: {len(related_recalls)} 件")
        for rc in related_recalls:
            lines.append(f"  - args: `{json.dumps(rc['args'], ensure_ascii=False)}`")
        related_speech = [s for s in speech_calls if s["tick"] in (ptick + 1, ptick + 2)]
        if related_speech:
            lines.append(f"- 次 tick の `speech_speak`: {len(related_speech)} 件")
            for sc in related_speech:
                txt = sc["args"].get("content") if isinstance(sc["args"], dict) else None
                lines.append(f"  - 発話: `{txt}`")
        lines.append("")

    if recall_calls:
        lines.append("## 全 `memory_recall_episodes` 呼出 (raw)\n")
        for rc in recall_calls:
            lines.append(
                f"- tick={rc['tick']}: `{json.dumps(rc['args'], ensure_ascii=False)}`"
            )
        lines.append("")

    lines.append("## 分析メモ\n")
    lines.append(
        "(ここに trace.jsonl を読んだ手動の質感判定を書く。"
        "L1=ハルが呼んだか / L2=引数の質 / L3=次 tick の発話に反映されたか)\n"
    )

    report_path = out_dir / "report.md"
    report_path.write_text("\n".join(lines), encoding="utf-8")
    logger.info("report written: %s", report_path)


# ─────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s: %(message)s")

    args = _parse_args()
    out_dir = _resolve_out_dir(args.out, args.scenario)
    out_dir.mkdir(parents=True, exist_ok=True)

    from ai_rpg_world.application.trace import JsonlTraceRecorder

    trace_path = out_dir / "trace.jsonl"
    recorder = JsonlTraceRecorder(trace_path)

    t0 = time.monotonic()
    try:
        runtime, state, _tmp = _setup_runtime(no_llm=args.no_llm, scenario_path=args.scenario)
        runtime.set_trace_recorder(recorder)
        _inject_past_episodes(runtime, recorder)
        _inject_past_encounters(runtime, recorder)
        _run_tick_loop(
            runtime, state, recorder,
            max_world_ticks=args.max_world_ticks,
            mode=args.mode,
        )
    finally:
        recorder.close()
    elapsed = time.monotonic() - t0

    _build_report(out_dir=out_dir, trace_path=trace_path, elapsed_seconds=elapsed)

    print(f"\nDone. Output: {out_dir}")
    print(f"  trace.jsonl: {trace_path}")
    print(f"  report.md:   {out_dir / 'report.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
