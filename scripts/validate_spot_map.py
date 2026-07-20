#!/usr/bin/env python3
"""spot グラフのマップ品質を検査する。"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Optional

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


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("scenario", type=Path, help="検査対象の scenario JSON")
    parser.add_argument("--strict", action="store_true", help="構造警告の一部を error に昇格する")
    parser.add_argument("--start-spot", help="到達性検査の開始 spot id")
    parser.add_argument(
        "--key-spot",
        action="append",
        default=[],
        type=_parse_key_spot,
        help="2経路性を検査する key spot。形式: spot_id または spot_id:error",
    )
    parser.add_argument("--max-direct-connection-distance", type=float)
    parser.add_argument("--distance-to-tick-ratio", type=float)
    args = parser.parse_args(argv)

    raw = json.loads(args.scenario.read_text(encoding="utf-8"))
    config = MapValidationConfig(
        start_spot_id=args.start_spot,
        key_spots=tuple(args.key_spot),
        strict=args.strict,
        max_direct_connection_distance=args.max_direct_connection_distance,
        distance_to_tick_ratio=(
            args.distance_to_tick_ratio
            if args.distance_to_tick_ratio is not None
            else MapValidationConfig().distance_to_tick_ratio
        ),
    )
    result = validate_spot_map(raw, config)
    print(json.dumps(result.to_dict(), ensure_ascii=False, sort_keys=True))
    return 0 if result.ok else 1


def _parse_key_spot(raw: str) -> KeySpotRequirement:
    if ":" not in raw:
        return KeySpotRequirement(raw, severity="warning")
    spot_id, severity = raw.rsplit(":", 1)
    if severity not in {"warning", "error"}:
        raise argparse.ArgumentTypeError(
            "--key-spot severity must be warning or error"
        )
    return KeySpotRequirement(spot_id, severity=severity)


if __name__ == "__main__":
    raise SystemExit(main())
