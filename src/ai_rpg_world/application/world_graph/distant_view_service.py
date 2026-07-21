"""spot graph の area 単位の遠景文を生成する純計算サービス。"""

from __future__ import annotations

from dataclasses import dataclass, field
from math import atan2, degrees, hypot
from typing import Mapping, Sequence


DEFAULT_PROMINENCE_THRESHOLD = 0.25
DEFAULT_SCORE_THRESHOLD = 0.20
DEFAULT_OUTDOOR_VISIBILITY_RANGE = 6.0
DEFAULT_MAX_LINES = 2


@dataclass(frozen=True)
class DistantViewSpot:
    """遠景計算に必要な spot 情報だけを切り出した DTO。"""

    spot_id: int
    area_id: str | None
    x: float | None
    y: float | None
    is_outdoor: bool


@dataclass(frozen=True)
class DistantViewArea:
    """遠景候補になる area 情報。"""

    area_id: str
    name: str
    visible_name: str
    prominence: float
    x: float | None
    y: float | None
    distant_descriptions: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class DistantViewConnection:
    """現在地から見た outgoing 接続。隣接 area 除外に使う。"""

    from_spot_id: int
    to_spot_id: int


@dataclass(frozen=True)
class DistantViewResult:
    """遠景描画結果。本文と trace 用の構造情報を分けて持つ。"""

    lines: tuple[str, ...]
    rendered_area_ids: tuple[str, ...] = ()
    candidate_count: int = 0
    skipped_reasons: tuple[str, ...] = ()


@dataclass(frozen=True)
class _Candidate:
    area: DistantViewArea
    direction: str
    distance: float
    distance_band: str
    score: float


class DistantViewService:
    """area / position / connection から prompt 用の遠景文を作る。

    常時遠景は observation ではなく現在状態の一部なので、このサービスは
    副作用を持たない。trace 記録は呼び出し側が `DistantViewResult` を使って
    必要なときだけ行う。
    """

    def __init__(
        self,
        *,
        prominence_threshold: float = DEFAULT_PROMINENCE_THRESHOLD,
        score_threshold: float = DEFAULT_SCORE_THRESHOLD,
        outdoor_visibility_range: float = DEFAULT_OUTDOOR_VISIBILITY_RANGE,
        max_lines: int = DEFAULT_MAX_LINES,
    ) -> None:
        self._prominence_threshold = prominence_threshold
        self._score_threshold = score_threshold
        self._outdoor_visibility_range = outdoor_visibility_range
        self._max_lines = max(0, max_lines)

    @property
    def prominence_threshold(self) -> float:
        """目立ち度の下限。trace の説明にも使う。"""
        return self._prominence_threshold

    @property
    def score_threshold(self) -> float:
        """距離減衰後の表示下限。trace の説明にも使う。"""
        return self._score_threshold

    @property
    def outdoor_visibility_range(self) -> float:
        """屋外 spot の初期見晴らし距離。trace の説明にも使う。"""
        return self._outdoor_visibility_range

    @property
    def max_lines(self) -> int:
        """遠景文の最大件数。trace の説明にも使う。"""
        return self._max_lines

    def render(
        self,
        *,
        current_spot_id: int,
        spots: Sequence[DistantViewSpot],
        areas: Sequence[DistantViewArea],
        connections: Sequence[DistantViewConnection],
    ) -> DistantViewResult:
        """現在地から見える遠景文を返す。"""
        if not areas:
            return DistantViewResult(lines=(), skipped_reasons=("no_areas",))
        if self._max_lines <= 0:
            return DistantViewResult(lines=(), skipped_reasons=("max_lines_zero",))

        spots_by_id = {spot.spot_id: spot for spot in spots}
        current = spots_by_id.get(current_spot_id)
        if current is None:
            return DistantViewResult(lines=(), skipped_reasons=("current_spot_missing",))
        if not current.is_outdoor:
            return DistantViewResult(lines=(), skipped_reasons=("indoor",))
        if current.x is None or current.y is None:
            return DistantViewResult(
                lines=(), skipped_reasons=("current_spot_position_missing",)
            )

        visibility_range = self._resolve_visibility_range(current)
        if visibility_range <= 0:
            return DistantViewResult(
                lines=(), skipped_reasons=("visibility_range_zero",)
            )

        current_area_id = current.area_id
        adjacent_area_ids = self._adjacent_area_ids(
            current_spot_id=current_spot_id,
            spots_by_id=spots_by_id,
            connections=connections,
        )

        candidates: list[_Candidate] = []
        skipped: set[str] = set()
        for area in areas:
            if current_area_id is not None and area.area_id == current_area_id:
                skipped.add("current_area")
                continue
            if area.area_id in adjacent_area_ids:
                skipped.add("adjacent_area")
                continue
            if area.prominence < self._prominence_threshold:
                skipped.add("low_prominence")
                continue
            if area.x is None or area.y is None:
                skipped.add("area_position_missing")
                continue
            dx = area.x - current.x
            dy = area.y - current.y
            distance = hypot(dx, dy)
            if distance <= 0:
                skipped.add("zero_distance")
                continue
            score = area.prominence * min(1.0, visibility_range / max(distance, 1.0))
            if score < self._score_threshold:
                skipped.add("score_below_threshold")
                continue
            candidates.append(
                _Candidate(
                    area=area,
                    direction=_direction_from_delta(dx, dy),
                    distance=distance,
                    distance_band=_distance_band(distance, visibility_range),
                    score=score,
                )
            )

        if not candidates:
            if skipped:
                if "low_prominence" in skipped or "score_below_threshold" in skipped:
                    skipped.add("all_below_threshold")
                reasons = tuple(sorted(skipped))
            else:
                reasons = ("all_below_threshold",)
            return DistantViewResult(
                lines=(),
                candidate_count=0,
                skipped_reasons=reasons,
            )

        best_by_direction: dict[str, _Candidate] = {}
        for candidate in candidates:
            current_best = best_by_direction.get(candidate.direction)
            if current_best is None or _candidate_sort_key(candidate) < _candidate_sort_key(
                current_best
            ):
                best_by_direction[candidate.direction] = candidate

        selected = sorted(best_by_direction.values(), key=_candidate_sort_key)[
            : self._max_lines
        ]
        lines = tuple(_candidate_to_line(candidate) for candidate in selected)
        area_ids = tuple(candidate.area.area_id for candidate in selected)
        return DistantViewResult(
            lines=lines,
            rendered_area_ids=area_ids,
            candidate_count=len(candidates),
            skipped_reasons=tuple(sorted(skipped)),
        )

    def _resolve_visibility_range(self, spot: DistantViewSpot) -> float:
        if not spot.is_outdoor:
            return 0.0
        return self._outdoor_visibility_range

    @staticmethod
    def _adjacent_area_ids(
        *,
        current_spot_id: int,
        spots_by_id: Mapping[int, DistantViewSpot],
        connections: Sequence[DistantViewConnection],
    ) -> set[str]:
        out: set[str] = set()
        for connection in connections:
            if connection.from_spot_id != current_spot_id:
                continue
            dest = spots_by_id.get(connection.to_spot_id)
            if dest is not None and dest.area_id:
                out.add(dest.area_id)
        return out


def _candidate_sort_key(candidate: _Candidate) -> tuple[float, float, str]:
    """score 降順、距離昇順、area_id 昇順で安定化するためのキー。"""
    return (-candidate.score, candidate.distance, candidate.area.area_id)


_DIRECTIONS = (
    "北",
    "北東",
    "東",
    "南東",
    "南",
    "南西",
    "西",
    "北西",
)


def _direction_from_delta(dx: float, dy: float) -> str:
    """y 正方向を北とした8方位を返す。"""
    angle = (degrees(atan2(dx, dy)) + 360.0) % 360.0
    index = int((angle + 22.5) // 45.0) % 8
    return _DIRECTIONS[index]


def _distance_band(distance: float, visibility_range: float) -> str:
    if distance <= visibility_range * 0.45:
        return "middle"
    return "far"


def _candidate_to_line(candidate: _Candidate) -> str:
    custom = candidate.area.distant_descriptions.get(candidate.distance_band)
    if custom:
        return _ensure_sentence(custom.strip())
    name = candidate.area.visible_name or candidate.area.name
    return f"{candidate.direction}に{name}が見える。"


def _ensure_sentence(text: str) -> str:
    if not text:
        return text
    if text.endswith(("。", "！", "？", ".", "!", "?")):
        return text
    return text + "。"
