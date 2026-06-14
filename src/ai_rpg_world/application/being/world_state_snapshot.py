"""``WorldStateSnapshot`` — シナリオ全体に共有な world state を 1 JSON にまとめる VO。

Phase 9 (Issue #470): Being snapshot だけでは「memory は引き継がれるが world
state はリセットされる」だけだったため、scenario の「世界そのものの続き」を
再現するために導入する。

## Being snapshot との関係

- ``BeingSnapshot`` = 1 player の memory + identity (= player 単位)
- ``WorldStateSnapshot`` = 全 player 共有の world state (= scenario 単位)

snapshot directory (``OUT/snapshots/``) 配下に **両方が共存** する:

```
OUT/snapshots/
├── world.json           # WorldStateSnapshot (Phase 9 で導入)
├── being_w1_p1.json     # BeingSnapshot (Phase 4-5 既存)
├── being_w1_p2.json
└── being_w1_p3.json
```

## scenario 一致は hard-error

memory snapshot は cross-scenario transfer を warning のみで許容するが、
world snapshot は ``source_scenario`` が異なる場合 **load を fail-fast**
で拒否する。理由: spot_id / item_spec / event 名等が scenario に依存して
おり、別 scenario に load しても意味が成立しない。

## subsystem ごとの version

world state は **多くの subsystem** (player / spot / weather / monster / ...)
の集合体で、それぞれが独立に進化する。なので **subsystem ごとに**
``schema_version`` を持たせ、未知 version は load 時に fail-fast。

```json
{
  "schema_version": 1,
  "source_scenario": "decay_demo",
  "captured_at": "2026-06-14T...",
  "world_tick": 30,
  "subsystems": {
    "player_status":  {"schema_version": 1, "entries": [...]},
    "spot_interior":  {"schema_version": 1, "entries": [...]},
    "world_flags":    {"schema_version": 1, "flags": {...}},
    ...
  }
}
```

Phase 9-1 (= 本 PR) は **器だけ** 用意する。各 subsystem の中身は Phase 9-2
以降で 1 つずつ埋めていく (= ``subsystems`` は最初は空 dict)。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


CURRENT_WORLD_SNAPSHOT_VERSION: int = 1
SUPPORTED_WORLD_SNAPSHOT_VERSIONS: frozenset[int] = frozenset({1})


@dataclass(frozen=True)
class WorldStateSnapshot:
    """シナリオ全体の world state を表す JSON-serializable VO。"""

    source_scenario: str
    world_tick: int
    subsystems: dict[str, dict[str, Any]] = field(default_factory=dict)
    schema_version: int = CURRENT_WORLD_SNAPSHOT_VERSION
    captured_at: str | None = None  # ISO 8601 UTC; runner で埋める

    def __post_init__(self) -> None:
        if not isinstance(self.source_scenario, str) or not self.source_scenario:
            raise ValueError(
                "source_scenario must be non-empty str "
                f"(got {self.source_scenario!r})"
            )
        if (
            isinstance(self.world_tick, bool)
            or not isinstance(self.world_tick, int)
            or self.world_tick < 0
        ):
            raise ValueError(
                f"world_tick must be non-negative int (got {self.world_tick!r})"
            )
        if not isinstance(self.subsystems, dict):
            raise ValueError(
                f"subsystems must be dict (got {type(self.subsystems).__name__})"
            )
        if (
            isinstance(self.schema_version, bool)
            or not isinstance(self.schema_version, int)
            or self.schema_version <= 0
        ):
            raise ValueError(
                f"schema_version must be positive int "
                f"(got {self.schema_version!r})"
            )
        if self.captured_at is not None and not isinstance(self.captured_at, str):
            raise ValueError(
                f"captured_at must be str or None "
                f"(got {type(self.captured_at).__name__})"
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "source_scenario": self.source_scenario,
            "world_tick": self.world_tick,
            "captured_at": self.captured_at,
            "subsystems": dict(self.subsystems),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "WorldStateSnapshot":
        if not isinstance(data, dict):
            raise TypeError(f"data must be dict (got {type(data).__name__})")
        return cls(
            source_scenario=str(data["source_scenario"]),
            world_tick=int(data["world_tick"]),
            subsystems=dict(data.get("subsystems", {})),
            schema_version=int(data.get("schema_version", 1)),
            captured_at=data.get("captured_at"),
        )


class WorldStateSnapshotVersionError(Exception):
    """world snapshot の ``schema_version`` が現 codec で読めないとき。"""


class WorldStateScenarioMismatchError(Exception):
    """world snapshot の ``source_scenario`` が現 scenario と異なるとき。

    memory snapshot は cross-scenario を warning で許容するが、world snapshot
    は spot_id 等が scenario 依存なので **load 時に fail-fast** する。
    """


__all__ = [
    "WorldStateSnapshot",
    "WorldStateSnapshotVersionError",
    "WorldStateScenarioMismatchError",
    "CURRENT_WORLD_SNAPSHOT_VERSION",
    "SUPPORTED_WORLD_SNAPSHOT_VERSIONS",
]
