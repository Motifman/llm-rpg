"""``scripts/being_snapshot_cli.py`` の end-to-end smoke test (Phase 5)。

実 sqlite ファイルに対して save → load を回し、CLI 経由でも memory が
復元されることを確認する。memo store は in-memory なので CLI 起動ごとに
新規になるが、snapshot JSON から書き戻されることを担保する。
"""

from __future__ import annotations

import importlib.util
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import pytest

from ai_rpg_world.domain.being.aggregate.being import Being
from ai_rpg_world.domain.being.value_object.being_attachment import BeingAttachment
from ai_rpg_world.domain.being.value_object.being_id import BeingId
from ai_rpg_world.domain.being.value_object.being_identity import BeingIdentity
from ai_rpg_world.domain.being.value_object.memory_kind import MemoryKind
from ai_rpg_world.domain.memory.semantic.value_object.semantic_memory_entry import (
    SemanticMemoryEntry,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world.value_object.world_id import WorldId
from ai_rpg_world.infrastructure.repository.sqlite_being_repository import (
    SqliteBeingRepository,
)
from ai_rpg_world.infrastructure.repository.sqlite_semantic_memory_store import (
    SqliteSemanticMemoryStore,
)


def _load_cli_module():
    """``scripts/being_snapshot_cli.py`` を import 可能な形で読み込む。"""
    path = (
        Path(__file__).resolve().parents[2]
        / "scripts"
        / "being_snapshot_cli.py"
    )
    spec = importlib.util.spec_from_file_location("being_snapshot_cli", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_NOW = datetime(2026, 6, 14, 12, 0, tzinfo=timezone.utc)


def _populate_source_dbs(
    *,
    being_db: Path,
    memory_db: Path,
) -> BeingId:
    """source 側 sqlite DB 群に Being + semantic を書き込み、その being_id を返す。"""
    repo = SqliteBeingRepository.connect(str(being_db))
    being = Being(
        being_id=BeingId("being_w1_p1"),
        identity=BeingIdentity(name="アダ", first_person="わたし"),
        attachment=BeingAttachment(world_id=WorldId(1), player_id=PlayerId(1)),
        declared_memory_kinds=[MemoryKind.SEMANTIC],
    )
    repo.save(being)

    sem_conn = sqlite3.connect(str(memory_db), check_same_thread=False)
    sem = SqliteSemanticMemoryStore(sem_conn)
    sem.add_by_being(
        being.being_id,
        SemanticMemoryEntry(
            entry_id="s-cli",
            player_id=1,
            text="CLI 経由でも生き残る",
            evidence_episode_ids=("ep-1",),
            confidence=0.9,
            created_at=_NOW,
        ),
    )
    return being.being_id


class TestBeingSnapshotCliEndToEnd:
    """save → load を CLI 経由で回した時の round-trip。"""

    def test_save_load_round_trip(self, tmp_path: Path) -> None:
        cli = _load_cli_module()

        src_being_db = tmp_path / "src_beings.db"
        src_memory_db = tmp_path / "src_memory.db"
        src_episode_db = tmp_path / "src_episodes.db"
        src_reinterp_db = tmp_path / "src_reinterp.db"
        being_id = _populate_source_dbs(
            being_db=src_being_db, memory_db=src_memory_db
        )
        # episode / reinterpretation は空 DB で OK (= 空 store からの capture)

        snapshot_json = tmp_path / "snapshot.json"
        rc = cli.main(
            [
                "save",
                "--being-db",
                str(src_being_db),
                "--memory-db",
                str(src_memory_db),
                "--episode-db",
                str(src_episode_db),
                "--reinterpretation-db",
                str(src_reinterp_db),
                "--being-id",
                being_id.value,
                "--output",
                str(snapshot_json),
            ]
        )
        assert rc == 0
        assert snapshot_json.exists()
        # 内容が v2 で payload あり。
        data = json.loads(snapshot_json.read_text(encoding="utf-8"))
        assert data["snapshot_version"] == 2
        assert data["memory_payload_json"] is not None
        assert "CLI 経由でも生き残る" in data["memory_payload_json"]

        # 別 DB ファイルに load。
        dst_being_db = tmp_path / "dst_beings.db"
        dst_memory_db = tmp_path / "dst_memory.db"
        dst_episode_db = tmp_path / "dst_episodes.db"
        dst_reinterp_db = tmp_path / "dst_reinterp.db"
        rc = cli.main(
            [
                "load",
                "--being-db",
                str(dst_being_db),
                "--memory-db",
                str(dst_memory_db),
                "--episode-db",
                str(dst_episode_db),
                "--reinterpretation-db",
                str(dst_reinterp_db),
                "--input",
                str(snapshot_json),
            ]
        )
        assert rc == 0

        # dst 側 DB に Being と semantic が復元されている。
        dst_repo = SqliteBeingRepository.connect(str(dst_being_db))
        loaded = dst_repo.find_by_id(being_id)
        assert loaded is not None
        assert loaded.identity.name == "アダ"

        dst_sem_conn = sqlite3.connect(str(dst_memory_db), check_same_thread=False)
        dst_sem = SqliteSemanticMemoryStore(dst_sem_conn)
        entries = dst_sem.list_for_being(being_id)
        assert [e.entry_id for e in entries] == ["s-cli"]

    def test_存在しない_source_DB_の_save_は_exit_code_1(self, tmp_path: Path) -> None:
        """source DB が無い save は sqlite が自動生成する前に弾かれる。"""
        cli = _load_cli_module()
        rc = cli.main(
            [
                "save",
                "--being-db",
                str(tmp_path / "nonexistent.db"),  # 存在しない
                "--memory-db",
                str(tmp_path / "x_memory.db"),
                "--episode-db",
                str(tmp_path / "x_episodes.db"),
                "--reinterpretation-db",
                str(tmp_path / "x_reinterp.db"),
                "--being-id",
                "being_w1_p1",
                "--output",
                str(tmp_path / "out.json"),
            ]
        )
        assert rc == 1

    def test_存在しない_input_の_load_は_exit_code_1(self, tmp_path: Path) -> None:
        """load で input file が無い場合は traceback ではなく exit 1。"""
        cli = _load_cli_module()
        rc = cli.main(
            [
                "load",
                "--being-db",
                str(tmp_path / "dst_b.db"),
                "--memory-db",
                str(tmp_path / "dst_m.db"),
                "--episode-db",
                str(tmp_path / "dst_e.db"),
                "--reinterpretation-db",
                str(tmp_path / "dst_r.db"),
                "--input",
                str(tmp_path / "no-such-file.json"),
            ]
        )
        assert rc == 1

    def test_未登録_being_id_の_save_は_exit_code_1(self, tmp_path: Path) -> None:
        cli = _load_cli_module()
        rc = cli.main(
            [
                "save",
                "--being-db",
                str(tmp_path / "x_beings.db"),
                "--memory-db",
                str(tmp_path / "x_memory.db"),
                "--episode-db",
                str(tmp_path / "x_episodes.db"),
                "--reinterpretation-db",
                str(tmp_path / "x_reinterp.db"),
                "--being-id",
                "being_w1_p99",
                "--output",
                str(tmp_path / "out.json"),
            ]
        )
        assert rc == 1


def test_help_は_subcommand_を表示する() -> None:
    """argparse の help 出力に save / load の両 subcommand が出る。"""
    cli = _load_cli_module()
    parser = cli.build_parser()
    help_text = parser.format_help()
    assert "save" in help_text
    assert "load" in help_text
