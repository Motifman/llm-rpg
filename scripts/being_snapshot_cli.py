#!/usr/bin/env python3
"""Being + memory 状態を JSON ファイルに save / load する CLI (Phase 5 / Issue #470)。

run 途中再開 (mid-run resume) milestone の UX 層。``BeingPersistenceService``
や ``BeingMemorySnapshotService`` を経由して 5 memory store + Being repository
の状態を 1 つの JSON ファイルに往復させる。

## 使い方

### snapshot を取る (save)

```bash
uv run python scripts/being_snapshot_cli.py save \
    --being-db var/game/beings.db \
    --memory-db var/game/memory_graph.db \
    --episode-db var/game/episodes.db \
    --reinterpretation-db var/game/reinterpretation.db \
    --being-id being_w1_p1 \
    --output var/snapshots/being_w1_p1.json
```

### snapshot を復元する (load)

```bash
uv run python scripts/being_snapshot_cli.py load \
    --being-db var/restored_beings.db \
    --memory-db var/restored_memory.db \
    --episode-db var/restored_episodes.db \
    --reinterpretation-db var/restored_reinterpretation.db \
    --input var/snapshots/being_w1_p1.json
```

## DB 配線の方針

memo store は in-memory のみで永続化されていないため、本 CLI は **memo は
in-memory で初期化** する。実用上は「LLM ターン中の memo が JSON snapshot
には残る → 復元時に in-memory に書き戻される」という流れで動く。

将来 memo に SQLite 実装が入ったら本 CLI に ``--memo-db`` 引数を追加する。
"""

from __future__ import annotations

import argparse
import logging
import sqlite3
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
from ai_rpg_world.application.llm.services.in_memory_memo_store import (  # noqa: E402
    InMemoryMemoStore,
)
from ai_rpg_world.domain.being.value_object.being_id import BeingId  # noqa: E402
from ai_rpg_world.infrastructure.repository.sqlite_being_repository import (  # noqa: E402
    SqliteBeingRepository,
)
from ai_rpg_world.infrastructure.repository.sqlite_episodic_reinterpretation_store import (  # noqa: E402
    SqliteEpisodicReinterpretationStore,
)
from ai_rpg_world.infrastructure.repository.sqlite_memory_link_store import (  # noqa: E402
    SqliteMemoryLinkStore,
)
from ai_rpg_world.infrastructure.repository.sqlite_semantic_memory_store import (  # noqa: E402
    SqliteSemanticMemoryStore,
)
from ai_rpg_world.infrastructure.repository.sqlite_subjective_episode_store import (  # noqa: E402
    SqliteSubjectiveEpisodeStore,
)

logger = logging.getLogger("being_snapshot_cli")


def _build_stack(
    *,
    being_db: Path,
    memory_db: Path,
    episode_db: Path,
    reinterpretation_db: Path,
) -> tuple[
    SqliteBeingRepository,
    BeingMemorySnapshotService,
    BeingSnapshotFileGateway,
]:
    """4 つの sqlite DB + in-memory memo store から本 CLI 用 stack を組む。

    memo store は SQLite 実装がないため in-memory で常に新規。snapshot JSON
    に memo が入っていれば restore で書き戻される。
    """
    being_repo = SqliteBeingRepository.connect(str(being_db))

    semantic_conn = sqlite3.connect(str(memory_db), check_same_thread=False)
    semantic_store = SqliteSemanticMemoryStore(semantic_conn)
    memory_link_store = SqliteMemoryLinkStore(semantic_conn)
    # semantic / memory_link は同一接続を共有 (= apply_memory_graph_migrations
    # が共通の memory_graph schema を扱うため)

    reinterpretation_store = SqliteEpisodicReinterpretationStore.connect(
        str(reinterpretation_db)
    )
    episode_store = SqliteSubjectiveEpisodeStore.connect(str(episode_db))

    # PR-G: 想起階層 (slot / afterglow / habituation) は CLI 経由の単発 dump で
    # 使う場面が無いので、空の in-memory store を渡すだけで足る。
    # U2: belief evidence buffer も同様に CLI では in-memory で足りる。
    from ai_rpg_world.application.llm.services.afterglow_store import (
        InMemoryAfterglowStore,
    )
    from ai_rpg_world.application.llm.services.episodic_recall_habituation_store import (
        InMemoryEpisodicRecallHabituationStore,
    )
    from ai_rpg_world.application.llm.services.episodic_recall_slot_store import (
        InMemoryEpisodicRecallSlotStore,
    )
    from ai_rpg_world.application.llm.services.episodic_recall_success_store import (
        InMemoryEpisodicRecallSuccessStore,
    )
    from ai_rpg_world.application.llm.services.in_memory_belief_evidence_buffer_store import (
        InMemoryBeliefEvidenceBufferStore,
    )
    from ai_rpg_world.application.llm.services.in_memory_pending_prediction_store import (
        InMemoryPendingPredictionStore,
    )
    from ai_rpg_world.application.llm.services.in_memory_goal_journal_store import (
        InMemoryGoalJournalStore,
    )
    from ai_rpg_world.application.llm.services.in_memory_stagnation_pressure_store import (
        InMemoryStagnationPressureStore,
    )

    memory_snapshot = BeingMemorySnapshotService(
        memo_store=InMemoryMemoStore(),
        semantic_store=semantic_store,
        memory_link_store=memory_link_store,
        recall_buffer_store=reinterpretation_store,
        reinterpretation_journal_store=reinterpretation_store,
        episodic_episode_store=episode_store,
        recall_slot_store=InMemoryEpisodicRecallSlotStore(),
        afterglow_store=InMemoryAfterglowStore(),
        recall_habituation_store=InMemoryEpisodicRecallHabituationStore(),
        belief_evidence_buffer_store=InMemoryBeliefEvidenceBufferStore(),
        # U9b: CLI 経由の単発 dump では的中側 sidecar も in-memory で足りる
        # (PR-G の想起階層 3 store と同じ扱い)。
        recall_success_store=InMemoryEpisodicRecallSuccessStore(),
        # U10a: CLI 経由の単発 dump では pending prediction も in-memory で
        # 足りる (的中側 sidecar と同じ扱い)。
        pending_prediction_store=InMemoryPendingPredictionStore(),
        # P5: CLI 経由の単発 dump では goal store も in-memory で足りる。
        goal_journal_store=InMemoryGoalJournalStore(),
        # P-U2: CLI 経由の単発 dump では停滞感 store も in-memory で足りる。
        stagnation_pressure_store=InMemoryStagnationPressureStore(),
    )
    return being_repo, memory_snapshot, BeingSnapshotFileGateway()


def _add_db_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--being-db",
        type=Path,
        required=True,
        help="SqliteBeingRepository の DB ファイルパス",
    )
    parser.add_argument(
        "--memory-db",
        type=Path,
        required=True,
        help="semantic + memory_link を保持する SQLite ファイル (memory_graph schema)",
    )
    parser.add_argument(
        "--episode-db",
        type=Path,
        required=True,
        help="SqliteSubjectiveEpisodeStore の DB ファイル",
    )
    parser.add_argument(
        "--reinterpretation-db",
        type=Path,
        required=True,
        help="SqliteEpisodicReinterpretationStore の DB ファイル (= recall_buffer + reinterpretation_journal)",
    )


def cmd_save(args: argparse.Namespace) -> int:
    # source DB が存在しないと sqlite3 が空ファイルを自動生成し、その後で
    # 「Being が見つからない」という間接エラーになって UX が悪い。早期に弾く。
    source_db: Path = args.being_db
    if not source_db.exists():
        logger.error(
            "source being DB does not exist: %s (use 'load' to bootstrap "
            "a new DB from a snapshot)",
            source_db,
        )
        return 1

    being_repo, memory_snapshot, gateway = _build_stack(
        being_db=args.being_db,
        memory_db=args.memory_db,
        episode_db=args.episode_db,
        reinterpretation_db=args.reinterpretation_db,
    )
    # PR-G: CLI 経由の dump は RAM 上の sidecar (slot / afterglow / habituation)
    # に到達できないので、これらは常に空のまま保存される。実験 run 中の想起
    # 状態を取りこぼしていることがユーザに伝わるよう、明示的に warning を残す。
    logger.warning(
        "recall_slot / afterglow / habituation are in-memory sidecars and "
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
        memory_db=args.memory_db,
        episode_db=args.episode_db,
        reinterpretation_db=args.reinterpretation_db,
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
            "snapshot load failed: %s (re-running with the same snapshot "
            "is idempotent if the DB state is partial)",
            exc,
        )
        return 1
    logger.info(
        "snapshot restored: being_id=%s input=%s version=%d memory_restored=%s",
        result.being_id.value,
        result.input_path,
        result.snapshot_version,
        result.memory_restored,
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
