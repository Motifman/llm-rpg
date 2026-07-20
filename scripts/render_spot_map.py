#!/usr/bin/env python3
"""scenario JSON から spot グラフの俯瞰地図 HTML を生成する。"""

from __future__ import annotations

import argparse
import html
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence

_REPO_ROOT = Path(__file__).resolve().parents[1]
for p in (_REPO_ROOT, _REPO_ROOT / "src"):
    s = str(p)
    if s not in sys.path:
        sys.path.insert(0, s)

from ai_rpg_world.infrastructure.scenario.spot_map_validator import (  # noqa: E402
    KeySpotRequirement,
    MapValidationConfig,
    validate_spot_map,
)


_MARGIN = 24.0
_TARGET_SPAN = 400.0


@dataclass(frozen=True)
class _Spot:
    spot_id: str
    name: str
    x: Optional[float]
    y: Optional[float]

    @property
    def is_positioned(self) -> bool:
        return self.x is not None and self.y is not None


@dataclass(frozen=True)
class _Connection:
    connection_id: str
    from_spot: str
    to_spot: str
    travel_ticks: Any
    is_bidirectional: bool


@dataclass(frozen=True)
class _ScreenPoint:
    x: float
    y: float


def render_spot_map_html(
    raw: Mapping[str, Any],
    *,
    title: str = "spot map",
    key_spots: Sequence[str] = (),
    start_spot_id: Optional[str] = None,
) -> str:
    """scenario JSON 由来の dict から単体で開ける地図 HTML を生成する。"""

    spots = _spots(raw)
    connections = _connections(raw)
    spot_by_id = {spot.spot_id: spot for spot in spots}
    positioned = [spot for spot in spots if spot.is_positioned]
    unpositioned = [spot for spot in spots if not spot.is_positioned]
    screen_points = _screen_points(positioned)
    validation = validate_spot_map(
        raw,
        MapValidationConfig(
            start_spot_id=start_spot_id,
            key_spots=tuple(KeySpotRequirement(spot_id) for spot_id in key_spots),
        ),
    )
    unreachable_spots = set(validation.metrics.get("unreachable_spots", []))
    key_spot_set = set(key_spots)

    width = _svg_width(screen_points)
    height = _svg_height(screen_points)
    body = "\n".join(
        [
            _render_edges(connections, spot_by_id, screen_points),
            _render_spots(positioned, screen_points, key_spot_set, unreachable_spots),
        ]
    )
    unpositioned_html = _render_unpositioned(unpositioned, total_count=len(spots))
    summary_html = _render_summary(
        validation_ok=validation.ok,
        warning_count=len(validation.warnings),
        error_count=len(validation.errors),
        positioned_count=len(positioned),
        total_count=len(spots),
    )
    escaped_title = html.escape(title)
    return f"""<!doctype html>
<html lang="ja">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{escaped_title}</title>
  <style>
    :root {{
      color-scheme: dark;
      --bg: #211b1b;
      --panel: #2f2727;
      --ink: #f5f0df;
      --muted: #a8a19a;
      --accent: #65dce8;
      --edge: #9b8f78;
      --node: #f0eef5;
      --key: #ffd166;
      --bad: #ff6b6b;
    }}
    body {{
      margin: 0;
      background: linear-gradient(120deg, #201b1b, #1b211d);
      color: var(--ink);
      font-family: ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Hiragino Sans", sans-serif;
    }}
    main {{
      display: grid;
      grid-template-columns: minmax(0, 1fr) 320px;
      gap: 16px;
      padding: 18px;
    }}
    h1 {{ margin: 0 0 12px; font-size: 24px; }}
    h2 {{ margin: 0 0 10px; font-size: 16px; color: var(--accent); }}
    .panel {{
      background: rgba(47, 39, 39, 0.9);
      border: 1px solid #795548;
      border-radius: 10px;
      padding: 14px;
      box-shadow: 0 12px 28px rgba(0, 0, 0, 0.25);
    }}
    svg {{
      width: 100%;
      height: min(78vh, 780px);
      min-height: 420px;
      background: radial-gradient(circle at 50% 40%, #29302a, #1d2220);
      border-radius: 8px;
      border: 1px solid #51453e;
    }}
    .connection-line {{ stroke: var(--edge); stroke-width: 3; opacity: 0.9; }}
    .connection-line.one-way {{ stroke: #e7b56d; }}
    .edge-label {{
      fill: #d9cfb8;
      font-size: 12px;
      paint-order: stroke;
      stroke: #171313;
      stroke-width: 4px;
      stroke-linejoin: round;
    }}
    .spot-node circle {{
      fill: var(--node);
      stroke: #7a6db8;
      stroke-width: 3;
    }}
    .spot-node.key-spot circle {{ fill: var(--key); stroke: #a86f00; }}
    .spot-node.unreachable-spot circle {{ fill: var(--bad); stroke: #8d2020; }}
    .spot-label {{
      fill: #181515;
      font-weight: 700;
      font-size: 13px;
      text-anchor: middle;
      dominant-baseline: middle;
      pointer-events: none;
    }}
    .legend {{ display: grid; gap: 8px; margin-top: 12px; color: var(--muted); }}
    .legend span {{ display: inline-block; width: 12px; height: 12px; border-radius: 50%; margin-right: 6px; vertical-align: -1px; }}
    .legend .key {{ background: var(--key); }}
    .legend .bad {{ background: var(--bad); }}
    .legend .normal {{ background: var(--node); }}
    .summary {{ display: grid; gap: 6px; color: var(--muted); margin-bottom: 14px; }}
    .summary strong {{ color: var(--ink); }}
    .unpositioned-list {{ margin: 0; padding-left: 18px; color: var(--ink); }}
    .unpositioned-list li {{ margin: 5px 0; }}
    .empty-note {{ color: var(--muted); }}
    @media (max-width: 900px) {{ main {{ grid-template-columns: 1fr; }} }}
  </style>
</head>
<body>
  <main>
    <section class="panel">
      <h1>{escaped_title}</h1>
      <svg viewBox="0 0 {width:.1f} {height:.1f}" role="img" aria-label="{escaped_title}">
        <defs>
          <marker id="arrow-one-way" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
            <path d="M 0 0 L 10 5 L 0 10 z" fill="#e7b56d"></path>
          </marker>
        </defs>
        {body}
      </svg>
      <div class="legend">
        <div><span class="normal"></span>通常 spot</div>
        <div><span class="key"></span>重要地点</div>
        <div><span class="bad"></span>到達不能</div>
      </div>
    </section>
    <aside class="panel">
      {summary_html}
      {unpositioned_html}
    </aside>
  </main>
</body>
</html>
"""


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("scenario", type=Path, help="描画対象の scenario JSON")
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=Path("spot_map.html"),
        help="出力 HTML path",
    )
    parser.add_argument("--title", help="HTML のタイトル。未指定なら scenario ファイル名")
    parser.add_argument(
        "--key-spot",
        action="append",
        default=[],
        help="重要地点として色分けする spot id。複数指定可",
    )
    parser.add_argument("--start-spot", help="到達性検査の開始 spot id")
    args = parser.parse_args(argv)

    raw = json.loads(args.scenario.read_text(encoding="utf-8"))
    title = args.title or args.scenario.stem
    rendered = render_spot_map_html(
        raw,
        title=title,
        key_spots=tuple(args.key_spot),
        start_spot_id=args.start_spot,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(rendered, encoding="utf-8")
    print(str(args.output))
    return 0


def _spots(raw: Mapping[str, Any]) -> list[_Spot]:
    out: list[_Spot] = []
    for item in _list_value(raw, "spots"):
        if not isinstance(item, Mapping):
            continue
        spot_id = item.get("id")
        if not isinstance(spot_id, str) or not spot_id:
            continue
        name = item.get("name")
        position = item.get("position")
        x: Optional[float] = None
        y: Optional[float] = None
        if isinstance(position, Mapping):
            raw_x = position.get("x")
            raw_y = position.get("y")
            if isinstance(raw_x, (int, float)) and isinstance(raw_y, (int, float)):
                if not isinstance(raw_x, bool) and not isinstance(raw_y, bool):
                    x = float(raw_x)
                    y = float(raw_y)
        out.append(_Spot(spot_id=spot_id, name=str(name or spot_id), x=x, y=y))
    return out


def _connections(raw: Mapping[str, Any]) -> list[_Connection]:
    out: list[_Connection] = []
    for index, item in enumerate(_list_value(raw, "connections")):
        if not isinstance(item, Mapping):
            continue
        source = item.get("from")
        target = item.get("to")
        if not isinstance(source, str) or not isinstance(target, str):
            continue
        is_bidirectional = item.get("is_bidirectional", True)
        out.append(
            _Connection(
                connection_id=str(item.get("id") or f"connection[{index}]"),
                from_spot=source,
                to_spot=target,
                travel_ticks=item.get("travel_ticks", 1),
                is_bidirectional=is_bidirectional if isinstance(is_bidirectional, bool) else True,
            )
        )
    return out


def _screen_points(spots: Sequence[_Spot]) -> dict[str, _ScreenPoint]:
    if not spots:
        return {}
    xs = [spot.x for spot in spots if spot.x is not None]
    ys = [spot.y for spot in spots if spot.y is not None]
    min_x = min(xs)
    max_x = max(xs)
    min_y = min(ys)
    max_y = max(ys)
    span = max(max_x - min_x, max_y - min_y, 1.0)
    scale = _TARGET_SPAN / span
    out: dict[str, _ScreenPoint] = {}
    for spot in spots:
        assert spot.x is not None
        assert spot.y is not None
        out[spot.spot_id] = _ScreenPoint(
            x=_MARGIN + (spot.x - min_x) * scale,
            y=_MARGIN + (max_y - spot.y) * scale,
        )
    return out


def _svg_width(screen_points: Mapping[str, _ScreenPoint]) -> float:
    if not screen_points:
        return 640.0
    return max(640.0, max(point.x for point in screen_points.values()) + _MARGIN)


def _svg_height(screen_points: Mapping[str, _ScreenPoint]) -> float:
    if not screen_points:
        return 420.0
    return max(420.0, max(point.y for point in screen_points.values()) + _MARGIN)


def _render_edges(
    connections: Sequence[_Connection],
    spot_by_id: Mapping[str, _Spot],
    screen_points: Mapping[str, _ScreenPoint],
) -> str:
    rows: list[str] = []
    for connection in connections:
        if connection.from_spot not in screen_points or connection.to_spot not in screen_points:
            continue
        if connection.from_spot not in spot_by_id or connection.to_spot not in spot_by_id:
            continue
        start = screen_points[connection.from_spot]
        end = screen_points[connection.to_spot]
        marker = "" if connection.is_bidirectional else ' marker-end="url(#arrow-one-way)"'
        classes = "connection-line" if connection.is_bidirectional else "connection-line one-way"
        mid_x = (start.x + end.x) / 2
        mid_y = (start.y + end.y) / 2
        rows.append(
            f'<line class="{classes}" data-connection-id="{html.escape(connection.connection_id)}" '
            f'x1="{start.x:.1f}" y1="{start.y:.1f}" x2="{end.x:.1f}" y2="{end.y:.1f}"{marker}></line>'
        )
        rows.append(
            f'<text class="edge-label" x="{mid_x:.1f}" y="{mid_y - 6:.1f}">'
            f'travel_ticks: {html.escape(str(connection.travel_ticks))}</text>'
        )
    return "\n        ".join(rows)


def _render_spots(
    spots: Sequence[_Spot],
    screen_points: Mapping[str, _ScreenPoint],
    key_spots: set[str],
    unreachable_spots: set[str],
) -> str:
    rows: list[str] = []
    for spot in spots:
        point = screen_points[spot.spot_id]
        classes = ["spot-node"]
        if spot.spot_id in key_spots:
            classes.append("key-spot")
        if spot.spot_id in unreachable_spots:
            classes.append("unreachable-spot")
        rows.append(
            f'<g class="{" ".join(classes)}" data-spot-id="{html.escape(spot.spot_id)}" '
            f'data-screen-x="{point.x:.1f}" data-screen-y="{point.y:.1f}">'
            f'<circle cx="{point.x:.1f}" cy="{point.y:.1f}" r="28"></circle>'
            f'<text class="spot-label" x="{point.x:.1f}" y="{point.y:.1f}">{html.escape(spot.name)}</text>'
            "</g>"
        )
    return "\n        ".join(rows)


def _render_unpositioned(spots: Sequence[_Spot], *, total_count: int) -> str:
    title = f"未配置 spot: {len(spots)} / {total_count}"
    if not spots:
        return f"<h2>{title}</h2><p class=\"empty-note\">すべての spot に position があります。</p>"
    rows = "\n".join(
        f'<li data-unpositioned-spot-id="{html.escape(spot.spot_id)}">'
        f"{html.escape(spot.name)} <small>({html.escape(spot.spot_id)})</small></li>"
        for spot in spots
    )
    return f"<h2>{title}</h2><ol class=\"unpositioned-list\">{rows}</ol>"


def _render_summary(
    *,
    validation_ok: bool,
    warning_count: int,
    error_count: int,
    positioned_count: int,
    total_count: int,
) -> str:
    ok_text = "OK" if validation_ok else "ERROR"
    return f"""<section class="summary">
        <div>検査結果: <strong>{ok_text}</strong></div>
        <div>errors: <strong>{error_count}</strong> / warnings: <strong>{warning_count}</strong></div>
        <div>position: <strong>{positioned_count}</strong> / {total_count}</div>
      </section>"""


def _list_value(raw: Mapping[str, Any], key: str) -> list[Any]:
    value = raw.get(key)
    return value if isinstance(value, list) else []


if __name__ == "__main__":
    raise SystemExit(main())
