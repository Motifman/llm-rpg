#!/usr/bin/env python3
"""Being + memory 状態を JSON ファイルに save / load する CLI (Phase 5 / Issue #470)。

run 途中再開 (mid-run resume) milestone の UX 層。``BeingMemorySnapshotService``
を経由して memory store + Being repository の状態を 1 つの JSON ファイルに
往復させる。

## 使い方

### snapshot を取る (save)

```bash
uv run python scripts/being_snapshot_cli.py save \
    --being-db var/game/beings.db \
    --being-id being_w1_p1 \
    --output var/snapshots/being_w1_p1.json
```

### snapshot を復元する (load)

```bash
uv run python scripts/being_snapshot_cli.py load \
    --being-db var/restored_beings.db \
    --input var/snapshots/being_w1_p1.json
```
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
for p in (_REPO_ROOT, _REPO_ROOT / "src"):
    s = str(p)
    if s not in sys.path:
        sys.path.insert(0, s)

from ai_rpg_world.application.being.being_memory_snapshot_service import (  # noqa: E402
    BeingMemorySnapshotService,
)
from ai_rpg_world.application.being.being_snapshot_file_gateway import (  # noqa: E402
    BeingSnapshotFileGateway,
)
from ai_rpg_world.application.being.capture_being_snapshot_to_file_use_case import (  # noqa: E402
    BeingNotFoundForSnapshotError,
    CaptureBeingSnapshotToFileUseCase,
)
from ai_rpg_world.application.being.restore_being_snapshot_from_file_use_case import (  # noqa: E402
    RestoreBeingSnapshotFromFileUseCase,
)
from ai_rpg_world.domain.being.value_object.being_id import BeingId  # noqa: E402
from ai_rpg_world.infrastructure.repository.sqlite_being_repository import (  # noqa: E402
    SqliteBeingRepository,
)

logger = logging.getLogger("being_snapshot_cli")


def _build_stack(
    *,
    being_db: Path,
) -> tuple[
    SqliteBeingRepository,
    BeingMemorySnapshotService,
    BeingSnapshotFileGateway,
]:
    """Being の sqlite DB と in-memory の store から本 CLI 用 stack を組む。"""
    being_repo = SqliteBeingRepository.connect(str(being_db))

    from ai_rpg_world.being.infrastructure.in_memory_acquaintance_repository import (
        InMemoryAcquaintanceRepository,
    )
    from ai_rpg_world.being.infrastructure.in_memory_episode_repository import (
        InMemoryEpisodeRepository,
    )
    from ai_rpg_world.being.infrastructure.in_memory_memo_book_repository import (
        InMemoryMemoBookRepository,
    )
    from ai_rpg_world.being.infrastructure.in_memory_memory_turn_clock import (
        InMemoryMemoryTurnClock,
    )
    from ai_rpg_world.being.infrastructure.in_memory_short_term_memory_repository import (
        InMemoryShortTermMemoryRepository,
    )

    memory_snapshot = BeingMemorySnapshotService(
        acquaintance_store=InMemoryAcquaintanceRepository(),
        being_episode_store=InMemoryEpisodeRepository(),
        being_memo_store=InMemoryMemoBookRepository(),
        memory_turn_clock=InMemoryMemoryTurnClock(),
        being_short_term_memory_store=InMemoryShortTermMemoryRepository(),
    )
    return being_repo, memory_snapshot, BeingSnapshotFileGateway()


def _add_db_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--being-db",
        type=Path,
        required=True,
        help="SqliteBeingRepository の DB ファイルパス",
    )


def cmd_save(args: argparse.Namespace) -> int:
    # source DB が存在しないと sqlite3 が空ファイルを自動生成し、その後で
    # 「Being が見つからない」という間接エラーになって UX が悪い。早期に弾く。
    source_db: Path = args.being_db
    if not source_db.exists():
        logger.error(
            "source being DB does not exist: %s (use 'load' to bootstrap a new DB from a snapshot)",
            source_db,
        )
        return 1

    being_repo, memory_snapshot, gateway = _build_stack(
        being_db=args.being_db,
    )
    # CLI 経由の dump は RAM 上の sidecar に到達できないので、これらは常に
    # 空のまま保存される。取りこぼしていることがユーザに伝わるよう、明示的に
    # warning を残す。
    logger.warning(
        "memory turn / acquaintances / being "
        "episodes / being memo book are in-memory sidecars and "
        "are NOT captured via this CLI. The resulting snapshot will have "
        "those layers empty."
    )
    use_case = CaptureBeingSnapshotToFileUseCase(
        being_repository=being_repo,
        memory_snapshot_service=memory_snapshot,
        file_gateway=gateway,
    )

    output_path: Path = args.output
    output_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        result = use_case.execute(BeingId(args.being_id), output_path)
    except BeingNotFoundForSnapshotError as exc:
        logger.error("snapshot save failed: %s", exc)
        return 1
    except Exception as exc:  # noqa: BLE001 - CLI 境界で broad catch は意図的
        logger.error("snapshot save failed: %s", exc)
        return 1
    logger.info(
        "snapshot saved: being_id=%s output=%s version=%d has_payload=%s",
        result.being_id.value,
        result.output_path,
        result.snapshot_version,
        result.has_memory_payload,
    )
    return 0


def cmd_load(args: argparse.Namespace) -> int:
    input_path: Path = args.input
    if not input_path.exists():
        logger.error("snapshot file not found: %s", input_path)
        return 1

    being_repo, memory_snapshot, gateway = _build_stack(
        being_db=args.being_db,
    )
    use_case = RestoreBeingSnapshotFromFileUseCase(
        being_repository=being_repo,
        memory_snapshot_service=memory_snapshot,
        file_gateway=gateway,
    )

    try:
        result = use_case.execute(input_path)
    except Exception as exc:  # noqa: BLE001 - CLI 境界で broad catch は意図的
        # 注: snapshot は repo に書かれた後で memory.restore が失敗した場合、
        # partial state が DB に残る (= 設計判断 #15)。CLI の運用者には
        # 「同じ snapshot で再実行すれば idempotent に復元される」を案内。
        logger.error(
            "snapshot load failed: %s (re-running with the same snapshot is idempotent if the DB state is partial)",
            exc,
        )
        return 1
    logger.info(
        "snapshot restored: being_id=%s input=%s version=%d memory_restored=%s removed_memory_keys=%s",
        result.being_id.value,
        result.input_path,
        result.snapshot_version,
        result.memory_restored,
        result.removed_memory_key_counts,
    )
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="being_snapshot_cli",
        description="Being + memory 状態を JSON ファイルに save / load する CLI",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    save_p = sub.add_parser("save", help="Being snapshot を JSON ファイルに書き出す")
    _add_db_args(save_p)
    save_p.add_argument(
        "--being-id",
        required=True,
        help="保存対象の Being ID (例: being_w1_p1)",
    )
    save_p.add_argument(
        "--output",
        type=Path,
        required=True,
        help="snapshot JSON の出力先パス",
    )
    save_p.set_defaults(func=cmd_save)

    load_p = sub.add_parser("load", help="JSON ファイルから Being snapshot を復元する")
    _add_db_args(load_p)
    load_p.add_argument(
        "--input",
        type=Path,
        required=True,
        help="snapshot JSON の入力ファイルパス",
    )
    load_p.set_defaults(func=cmd_load)

    return parser


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    sys.exit(main())
