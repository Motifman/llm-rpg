"""trace.jsonl を読み、複数の episodic chunk 境界ポリシーで chunk_written 件数 /
平均サイズ / boundary 内訳を **ドライラン** で比較するシミュレータ。

# 何のため

PR #322 (Issue #311 後続) で chunk_boundary/rules.py を cognitive science ベース
に書き換える前に、第21回実験の実 trace 上でパラメータを動かし、人間っぽい
チャンク粒度に近いものを定量比較するために作った。今後のチューニングでも
同じスクリプトで「実走 trace → 仮想 chunk 数」を回せる。

# 使い方

```
python scripts/episodic_chunk_simulation.py <trace.jsonl のパス>
```

引数省略時は ``ON_FULL_trace.jsonl`` (相対パス) を見る。

# 注意点

このスクリプトは本実装の ``decide_chunk_boundary`` を完全には再現していない。
具体的には:

- 観測スライス: 本実装は wall-clock ``[t0, t1]`` を見るが、シミュレータは
  trace の ``seq`` を代用 (時系列順序は保たれる)
- 観測 trace 自体が subset (heartbeat 等の一部は ``observation`` kind で
  記録されないことがある) → 観測件数は実走より少なめに見える

このため**絶対値より相対比較**を見ること。
"""
from __future__ import annotations

import json
import statistics
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional


@dataclass
class Action:
    tick: int
    player_id: int
    tool_name: str
    success: bool
    timestamp_iso: str
    seq: int


@dataclass
class Observation:
    tick: Optional[int]
    player_id: int
    category: Optional[str]
    schedules_turn: bool
    breaks_movement: bool
    actor: Optional[str]
    spot_id_value: Optional[int]
    timestamp_iso: str
    seq: int


def parse_trace(path: Path) -> tuple[list[Action], list[Observation]]:
    acts: list[Action] = []
    obss: list[Observation] = []
    with path.open() as f:
        for line in f:
            e = json.loads(line)
            kind = e["kind"]
            if kind == "action_result":
                acts.append(
                    Action(
                        tick=e["tick"] or 0,
                        player_id=e["player_id"] or 0,
                        tool_name=e["payload"].get("tool", ""),
                        success=e["payload"].get("success", True),
                        timestamp_iso=e["timestamp"],
                        seq=e["seq"],
                    )
                )
            elif kind == "observation":
                p = e["payload"]
                obss.append(
                    Observation(
                        tick=e["tick"],
                        player_id=e["player_id"] or 0,
                        category=p.get("category"),
                        schedules_turn=bool(p.get("schedules_turn", False)),
                        breaks_movement=bool(p.get("breaks_movement", False)),
                        actor=p.get("actor"),
                        spot_id_value=p.get("spot_id_value"),
                        timestamp_iso=e["timestamp"],
                        seq=e["seq"],
                    )
                )
    return acts, obss


@dataclass
class PolicyParams:
    name: str
    obs_count_threshold: int = 3
    salient_predicate: Callable[[Observation], bool] = (
        lambda o: o.schedules_turn or o.breaks_movement
    )
    use_category_shift: bool = True
    min_actions: int = 1  # この件数未満は閉じない (boundary 判定を skip)
    max_actions: int = 999  # この件数到達で強制クローズ
    use_spot_transition: bool = False
    use_temporal_gap_ticks: Optional[int] = None  # bucket スパンが N tick 超で強制クローズ


@dataclass
class ChunkResult:
    actions: list[Action]
    observations: list[Observation]
    reason: str


def simulate(
    acts: list[Action], obss: list[Observation], policy: PolicyParams
) -> dict[int, list[ChunkResult]]:
    """plyer ごとに chunk 列を生成"""
    chunks_per_player: dict[int, list[ChunkResult]] = {}
    # player ごとに action / observation を時系列でマージ再生
    pids = sorted({a.player_id for a in acts})
    for pid in pids:
        p_acts = sorted([a for a in acts if a.player_id == pid], key=lambda a: a.seq)
        p_obss = sorted([o for o in obss if o.player_id == pid], key=lambda o: o.seq)
        bucket: list[Action] = []
        last_spot: Optional[int] = None
        chunks: list[ChunkResult] = []
        for act in p_acts:
            # bucket に追加
            bucket.append(act)
            # bucket の時間範囲 [t0_seq, t1_seq]
            t0_seq = bucket[0].seq
            t1_seq = bucket[-1].seq
            obs_slice = [
                o for o in p_obss if t0_seq <= o.seq <= t1_seq
            ]
            # 境界判定
            reason: Optional[str] = None
            # MIN action check — 不足なら HOLD
            if len(bucket) < policy.min_actions:
                continue
            # MAX action — 強制クローズ
            if len(bucket) >= policy.max_actions:
                reason = "max_actions"
            # spot transition — bucket 内に spot 変化があれば閉じる
            if reason is None and policy.use_spot_transition:
                spot_ids = [
                    o.spot_id_value for o in obs_slice if o.spot_id_value is not None
                ]
                if spot_ids and last_spot is not None and any(
                    s != last_spot for s in spot_ids
                ):
                    reason = "spot_transition"
            # temporal gap (bucket span が長い)
            if reason is None and policy.use_temporal_gap_ticks is not None:
                tick_span = bucket[-1].tick - bucket[0].tick
                if tick_span > policy.use_temporal_gap_ticks:
                    reason = "temporal_gap"
            # OBSERVATION_COUNT_THRESHOLD
            if reason is None and len(obs_slice) >= policy.obs_count_threshold:
                reason = "observation_count_threshold"
            # OBSERVATION_SALIENT
            if reason is None and any(policy.salient_predicate(o) for o in obs_slice):
                reason = "observation_salient"
            # CATEGORY_SHIFT
            if reason is None and policy.use_category_shift and len(obs_slice) >= 2:
                cats = [o.category for o in obs_slice if o.category]
                if len(set(cats)) >= 2:
                    reason = "category_shift"
            if reason is not None:
                chunks.append(
                    ChunkResult(
                        actions=bucket.copy(),
                        observations=obs_slice.copy(),
                        reason=reason,
                    )
                )
                # update last_spot from obs_slice
                spot_ids = [
                    o.spot_id_value for o in obs_slice if o.spot_id_value is not None
                ]
                if spot_ids:
                    last_spot = spot_ids[-1]
                bucket.clear()
        # 末尾に残った bucket は捨てる (chunk 化しないのが現実装)
        chunks_per_player[pid] = chunks
    return chunks_per_player


def summarize(label: str, chunks_per_player: dict[int, list[ChunkResult]]) -> str:
    total_chunks = sum(len(v) for v in chunks_per_player.values())
    all_chunks = [c for v in chunks_per_player.values() for c in v]
    if not all_chunks:
        return f"{label}: chunks=0"
    act_sizes = [len(c.actions) for c in all_chunks]
    obs_sizes = [len(c.observations) for c in all_chunks]
    spans = [
        c.actions[-1].tick - c.actions[0].tick
        for c in all_chunks
        if c.actions
    ]
    from collections import Counter
    reasons = Counter(c.reason for c in all_chunks)
    out = [
        f"{label}: total_chunks={total_chunks}",
        f"  action/chunk:  avg={statistics.mean(act_sizes):.1f}  med={statistics.median(act_sizes):.0f}  max={max(act_sizes)}",
        f"  obs/chunk:     avg={statistics.mean(obs_sizes):.1f}  med={statistics.median(obs_sizes):.0f}  max={max(obs_sizes)}",
        f"  tick span/chunk: avg={statistics.mean(spans):.1f} med={statistics.median(spans):.0f}",
        f"  reasons: {dict(reasons.most_common())}",
    ]
    return "\n".join(out)


def main() -> None:
    trace_path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("ON_FULL_trace.jsonl")
    acts, obss = parse_trace(trace_path)
    print(f"\n## Source trace: {trace_path.name}")
    print(f"actions={len(acts)} observations={len(obss)}")
    print(f"players: {sorted({a.player_id for a in acts})}")

    policies = [
        PolicyParams(
            name="現状 (3 obs / salient=schedules_turn)",
        ),
        PolicyParams(
            name="C+D 機械的 (min=2, max=7)",
            min_actions=2, max_actions=7,
        ),
        PolicyParams(
            name="原則 v1 厳格 (obs=8, salient=breaks_only, min=2, max=7, spot+gap)",
            obs_count_threshold=8,
            salient_predicate=lambda o: o.breaks_movement,
            min_actions=2,
            max_actions=7,
            use_spot_transition=True,
            use_temporal_gap_ticks=10,
        ),
        PolicyParams(
            name="原則 v2 緩 (obs=5, salient=breaks_only, min=2, max=5, spot+gap5)",
            obs_count_threshold=5,
            salient_predicate=lambda o: o.breaks_movement,
            min_actions=2,
            max_actions=5,
            use_spot_transition=True,
            use_temporal_gap_ticks=5,
        ),
        PolicyParams(
            name="原則 v3 中庸 (obs=5, salient=breaks_only, min=3, max=7, spot+gap8)",
            obs_count_threshold=5,
            salient_predicate=lambda o: o.breaks_movement,
            min_actions=3,
            max_actions=7,
            use_spot_transition=True,
            use_temporal_gap_ticks=8,
        ),
    ]
    for p in policies:
        chunks = simulate(acts, obss, p)
        print()
        print(summarize(p.name, chunks))


if __name__ == "__main__":
    main()
