"""spot グラフのマップ品質検査。"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from math import ceil, hypot, isfinite
from typing import Any, Iterable, Literal, Mapping, Optional


Severity = Literal["error", "warning", "info"]


@dataclass(frozen=True)
class MapValidationIssue:
    """マップ品質検査で見つかった問題。"""

    code: str
    severity: Severity
    message: str
    spots: tuple[str, ...] = ()
    connection: Optional[str] = None
    details: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "code": self.code,
            "severity": self.severity,
            "message": self.message,
        }
        if self.spots:
            data["spots"] = list(self.spots)
        if self.connection is not None:
            data["connection"] = self.connection
        if self.details:
            data["details"] = dict(self.details)
        return data


@dataclass(frozen=True)
class KeySpotRequirement:
    """2 経路性を検査する重要地点。"""

    spot_id: str
    severity: Literal["error", "warning"] = "warning"


@dataclass(frozen=True)
class MapValidationConfig:
    """マップ品質検査の設定。"""

    start_spot_id: Optional[str] = None
    key_spots: tuple[KeySpotRequirement, ...] = ()
    strict: bool = False
    max_direct_connection_distance: Optional[float] = None
    distance_to_tick_ratio: Optional[float] = 1.0


@dataclass(frozen=True)
class MapValidationResult:
    """マップ品質検査の結果。"""

    ok: bool
    errors: list[MapValidationIssue]
    warnings: list[MapValidationIssue]
    infos: list[MapValidationIssue]
    skipped_checks: list[dict[str, Any]]
    metrics: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "errors": [issue.to_dict() for issue in self.errors],
            "warnings": [issue.to_dict() for issue in self.warnings],
            "infos": [issue.to_dict() for issue in self.infos],
            "skipped_checks": list(self.skipped_checks),
            "metrics": dict(self.metrics),
        }


@dataclass(frozen=True)
class _Edge:
    edge_id: str
    from_spot: str
    to_spot: str
    travel_ticks: int

    @property
    def label(self) -> str:
        return f"{self.from_spot}->{self.to_spot}"


def validate_spot_map(
    raw: Mapping[str, Any],
    config: MapValidationConfig = MapValidationConfig(),
) -> MapValidationResult:
    """scenario JSON 由来の dict から spot グラフの品質を検査する。"""

    collector = _IssueCollector()
    spots = _spot_ids(raw)
    spot_set = set(spots)
    edges = _edges(raw, spot_set, collector)
    adjacency = _adjacency(spots, edges)
    start_spot_id = _resolve_start_spot(raw, spots, config, collector)
    components = _connected_components(spots, adjacency)
    reachable = _reachable_from(start_spot_id, adjacency) if start_spot_id else set()
    unreachable = sorted(spot_set - reachable) if start_spot_id else []
    cycle_rank = len(edges) - len(spots) + len(components)
    articulation_spots = _articulation_spots(spots, adjacency)
    positions = _positions(raw)
    skipped_checks: list[dict[str, Any]] = []

    if unreachable:
        collector.add(
            "UNREACHABLE_SPOT",
            _strict_severity(config),
            f"{start_spot_id} から到達できない spot があります: {', '.join(unreachable)}",
            spots=tuple(unreachable),
        )
    if spots and cycle_rank == 0:
        collector.add(
            "TREE_GRAPH",
            _strict_severity(config),
            "spot グラフに閉路がありません",
        )
    for spot_id in articulation_spots:
        collector.add(
            "ARTICULATION_SPOT",
            "warning",
            f"{spot_id} を失うとグラフが分断されます",
            spots=(spot_id,),
        )

    _check_key_spots(
        config=config,
        collector=collector,
        spot_set=spot_set,
        start_spot_id=start_spot_id,
        spots=spots,
        edges=edges,
    )
    _check_distance_dependent_rules(
        config=config,
        collector=collector,
        spots=spots,
        edges=edges,
        positions=positions,
        skipped_checks=skipped_checks,
    )

    metrics = {
        "spot_count": len(spots),
        "undirected_edge_count": len(edges),
        "connected_component_count": len(components),
        "cycle_rank": cycle_rank,
        "articulation_spots": articulation_spots,
        "unreachable_spots": unreachable,
        "positioned_spot_count": len(positions),
    }
    return MapValidationResult(
        ok=not collector.errors,
        errors=collector.errors,
        warnings=collector.warnings,
        infos=collector.infos,
        skipped_checks=skipped_checks,
        metrics=metrics,
    )


class _IssueCollector:
    def __init__(self) -> None:
        self.errors: list[MapValidationIssue] = []
        self.warnings: list[MapValidationIssue] = []
        self.infos: list[MapValidationIssue] = []

    def add(
        self,
        code: str,
        severity: Severity,
        message: str,
        *,
        spots: tuple[str, ...] = (),
        connection: Optional[str] = None,
        details: Mapping[str, Any] | None = None,
    ) -> None:
        issue = MapValidationIssue(
            code=code,
            severity=severity,
            message=message,
            spots=spots,
            connection=connection,
            details=details or {},
        )
        if severity == "error":
            self.errors.append(issue)
        elif severity == "warning":
            self.warnings.append(issue)
        else:
            self.infos.append(issue)


def _spot_ids(raw: Mapping[str, Any]) -> list[str]:
    ids: list[str] = []
    for spot in _list_value(raw, "spots"):
        spot_id = spot.get("id") if isinstance(spot, Mapping) else None
        if isinstance(spot_id, str) and spot_id:
            ids.append(spot_id)
    return ids


def _edges(
    raw: Mapping[str, Any],
    spot_set: set[str],
    collector: _IssueCollector,
) -> list[_Edge]:
    edges: list[_Edge] = []
    for index, conn in enumerate(_list_value(raw, "connections")):
        if not isinstance(conn, Mapping):
            collector.add(
                "INVALID_CONNECTION",
                "error",
                f"connections[{index}] は object である必要があります",
            )
            continue
        edge_id = str(conn.get("id") or f"connection[{index}]")
        from_spot = conn.get("from")
        to_spot = conn.get("to")
        if not isinstance(from_spot, str) or not isinstance(to_spot, str):
            collector.add(
                "INVALID_CONNECTION_ENDPOINT",
                "error",
                f"{edge_id} の from/to は spot id 文字列である必要があります",
                connection=edge_id,
            )
            continue
        missing = tuple(sorted({from_spot, to_spot} - spot_set))
        if missing:
            collector.add(
                "UNKNOWN_CONNECTION_SPOT",
                "error",
                f"{edge_id} が存在しない spot を参照しています: {', '.join(missing)}",
                spots=missing,
                connection=edge_id,
            )
            continue
        try:
            travel_ticks = int(conn.get("travel_ticks", 1))
        except (TypeError, ValueError):
            travel_ticks = 1
        edges.append(
            _Edge(
                edge_id=edge_id,
                from_spot=from_spot,
                to_spot=to_spot,
                travel_ticks=travel_ticks,
            )
        )
    return edges


def _adjacency(spots: Iterable[str], edges: Iterable[_Edge]) -> dict[str, list[tuple[str, str]]]:
    adjacency: dict[str, list[tuple[str, str]]] = {spot_id: [] for spot_id in spots}
    for edge in edges:
        adjacency.setdefault(edge.from_spot, []).append((edge.to_spot, edge.edge_id))
        adjacency.setdefault(edge.to_spot, []).append((edge.from_spot, edge.edge_id))
    return adjacency


def _resolve_start_spot(
    raw: Mapping[str, Any],
    spots: list[str],
    config: MapValidationConfig,
    collector: _IssueCollector,
) -> Optional[str]:
    candidate = config.start_spot_id
    if candidate is None:
        for player in _list_value(raw, "players"):
            if isinstance(player, Mapping) and isinstance(player.get("spawn_spot"), str):
                candidate = player["spawn_spot"]
                break
    if candidate is None and spots:
        candidate = spots[0]
    if candidate is not None and candidate not in set(spots):
        collector.add(
            "UNKNOWN_START_SPOT",
            "error",
            f"start spot が存在しません: {candidate}",
            spots=(candidate,),
        )
        return None
    return candidate


def _connected_components(
    spots: Iterable[str],
    adjacency: Mapping[str, list[tuple[str, str]]],
) -> list[set[str]]:
    remaining = set(spots)
    components: list[set[str]] = []
    while remaining:
        start = min(remaining)
        component = _reachable_from(start, adjacency)
        components.append(component)
        remaining -= component
    return components


def _reachable_from(
    start: Optional[str],
    adjacency: Mapping[str, list[tuple[str, str]]],
    *,
    removed_edge_id: Optional[str] = None,
    removed_spot_id: Optional[str] = None,
) -> set[str]:
    if start is None or start == removed_spot_id:
        return set()
    seen = {start}
    queue: deque[str] = deque([start])
    while queue:
        current = queue.popleft()
        for neighbor, edge_id in adjacency.get(current, []):
            if edge_id == removed_edge_id or neighbor == removed_spot_id:
                continue
            if neighbor in seen:
                continue
            seen.add(neighbor)
            queue.append(neighbor)
    return seen


def _articulation_spots(
    spots: list[str],
    adjacency: Mapping[str, list[tuple[str, str]]],
) -> list[str]:
    if len(spots) <= 2:
        return []
    base_components = len(_connected_components(spots, adjacency))
    out: list[str] = []
    for removed in spots:
        remaining = [spot for spot in spots if spot != removed]
        components = _connected_components_without(remaining, adjacency, removed)
        if len(components) > base_components:
            out.append(removed)
    return sorted(out)


def _connected_components_without(
    spots: Iterable[str],
    adjacency: Mapping[str, list[tuple[str, str]]],
    removed_spot_id: str,
) -> list[set[str]]:
    remaining = set(spots)
    components: list[set[str]] = []
    while remaining:
        start = min(remaining)
        component = _reachable_from(start, adjacency, removed_spot_id=removed_spot_id)
        components.append(component)
        remaining -= component
    return components


def _check_key_spots(
    *,
    config: MapValidationConfig,
    collector: _IssueCollector,
    spot_set: set[str],
    start_spot_id: Optional[str],
    spots: list[str],
    edges: list[_Edge],
) -> None:
    if start_spot_id is None:
        return
    adjacency = _adjacency(spots, edges)
    for requirement in config.key_spots:
        key_spot = requirement.spot_id
        if key_spot not in spot_set:
            collector.add(
                "UNKNOWN_KEY_SPOT",
                "error",
                f"key_spot が存在しません: {key_spot}",
                spots=(key_spot,),
            )
            continue
        if key_spot == start_spot_id:
            continue
        edge_cut = [
            edge.edge_id
            for edge in edges
            if key_spot not in _reachable_from(
                start_spot_id,
                adjacency,
                removed_edge_id=edge.edge_id,
            )
        ]
        if edge_cut:
            collector.add(
                "KEY_SPOT_SINGLE_EDGE_ROUTE",
                requirement.severity,
                f"{key_spot} は単一接続の喪失で到達不能になります",
                spots=(start_spot_id, key_spot),
                details={"blocking_edge_ids": sorted(edge_cut)},
            )
        node_cut = [
            spot
            for spot in spots
            if spot not in {start_spot_id, key_spot}
            and key_spot not in _reachable_from(
                start_spot_id,
                adjacency,
                removed_spot_id=spot,
            )
        ]
        if node_cut:
            collector.add(
                "KEY_SPOT_SINGLE_NODE_ROUTE",
                requirement.severity,
                f"{key_spot} は単一 spot の喪失で到達不能になります",
                spots=(start_spot_id, key_spot),
                details={"blocking_spots": sorted(node_cut)},
            )


def _positions(raw: Mapping[str, Any]) -> dict[str, tuple[float, float]]:
    out: dict[str, tuple[float, float]] = {}
    for spot in _list_value(raw, "spots"):
        if not isinstance(spot, Mapping):
            continue
        spot_id = spot.get("id")
        position = spot.get("position")
        if not isinstance(spot_id, str) or not isinstance(position, Mapping):
            continue
        x = position.get("x")
        y = position.get("y")
        if _is_number(x) and _is_number(y):
            out[spot_id] = (float(x), float(y))
    return out


def _is_number(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and isfinite(value)


def _check_distance_dependent_rules(
    *,
    config: MapValidationConfig,
    collector: _IssueCollector,
    spots: list[str],
    edges: list[_Edge],
    positions: Mapping[str, tuple[float, float]],
    skipped_checks: list[dict[str, Any]],
) -> None:
    if not edges:
        return
    if not positions:
        skipped_checks.append(
            {
                "code": "TRAVEL_TICKS_DISTANCE_CHECK_SKIPPED",
                "reason": "position is not declared for every spot",
                "positioned_spot_count": 0,
                "spot_count": len(spots),
            }
        )
        return
    if len(positions) != len(spots):
        skipped_checks.append(
            {
                "code": "TRAVEL_TICKS_DISTANCE_CHECK_SKIPPED",
                "reason": "position is not declared for every spot",
                "positioned_spot_count": len(positions),
                "spot_count": len(spots),
            }
        )
        return
    for edge in edges:
        ax, ay = positions[edge.from_spot]
        bx, by = positions[edge.to_spot]
        distance = hypot(ax - bx, ay - by)
        if (
            config.max_direct_connection_distance is not None
            and distance > config.max_direct_connection_distance
        ):
            collector.add(
                "LONG_EDGE_DISTANCE",
                "warning",
                f"{edge.label} は直接接続として長すぎる可能性があります",
                connection=edge.edge_id,
                details={"distance": distance},
            )
        if config.distance_to_tick_ratio is None or config.distance_to_tick_ratio <= 0:
            continue
        expected = max(1, ceil(distance / config.distance_to_tick_ratio))
        lower = max(1, expected // 2)
        upper = max(1, expected * 2)
        if edge.travel_ticks < lower or edge.travel_ticks > upper:
            collector.add(
                "TRAVEL_TICKS_DISTANCE_MISMATCH",
                "warning",
                f"{edge.label} の travel_ticks が座標距離と大きくずれています",
                connection=edge.edge_id,
                details={
                    "distance": distance,
                    "travel_ticks": edge.travel_ticks,
                    "expected_ticks": expected,
                    "allowed_range": [lower, upper],
                },
            )


def _strict_severity(config: MapValidationConfig) -> Literal["error", "warning"]:
    return "error" if config.strict else "warning"


def _list_value(raw: Mapping[str, Any], key: str) -> list[Any]:
    value = raw.get(key)
    return value if isinstance(value, list) else []
