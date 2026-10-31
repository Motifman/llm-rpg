"""``scripts/being_snapshot_cli.py`` の end-to-end smoke test (Phase 5)。

実 sqlite ファイルに対して save → load を回し、CLI 経由でも Being が
復元されることを確認する。memory store はどれも in-memory なので、snapshot
JSON の memory payload は空の欄を持つ。
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

from ai_rpg_world.being.domain.being import Being
from ai_rpg_world.being.domain.being_attachment import BeingAttachment
from ai_rpg_world.being.domain.being_id import BeingId
from ai_rpg_world.being.domain.persona import Persona
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world.value_object.world_id import WorldId
from ai_rpg_world.infrastructure.repository.sqlite_being_repository import (
    SqliteBeingRepository,
)


def _load_cli_module():
    """``scripts/being_snapshot_cli.py`` を import 可能な形で読み込む。"""
    path = Path(__file__).resolve().parents[2] / "scripts" / "being_snapshot_cli.py"
    spec = importlib.util.spec_from_file_location("being_snapshot_cli", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _populate_source_dbs(
    *,
    being_db: Path,
) -> BeingId:
    """source 側 sqlite DB に Being を書き込み、その being_id を返す。"""
    repo = SqliteBeingRepository.connect(str(being_db))
    being = Being(
        being_id=BeingId("being_w1_p1"),
        persona=Persona(name="アダ", first_person="わたし"),
        attachment=BeingAttachment(environment_id="w1p1", environment_name="廃坑の山村"),
    )
    repo.save(being)

    return being.being_id


class TestBeingSnapshotCliEndToEnd:
    """save → load を CLI 経由で回した時の round-trip。"""

    def test_save_load_round_trip(self, tmp_path: Path) -> None:
        cli = _load_cli_module()

        src_being_db = tmp_path / "src_beings.db"
        being_id = _populate_source_dbs(being_db=src_being_db)

        snapshot_json = tmp_path / "snapshot.json"
        rc = cli.main(
            [
                "save",
                "--being-db",
                str(src_being_db),
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
        assert json.loads(data["memory_payload_json"])["schema_version"] == 1

        # 別 DB ファイルに load。
        dst_being_db = tmp_path / "dst_beings.db"
        rc = cli.main(
            [
                "load",
                "--being-db",
                str(dst_being_db),
                "--input",
                str(snapshot_json),
            ]
        )
        assert rc == 0

        # dst 側 DB に Being が復元されている。
        dst_repo = SqliteBeingRepository.connect(str(dst_being_db))
        loaded = dst_repo.find_by_id(being_id)
        assert loaded is not None
        assert loaded.persona.name == "アダ"

    def test_loading_an_old_snapshot_warns_that_the_attachment_was_dropped(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """番号の欄の古い snapshot を読むと、Being はどの環境にも入らず、捨てた番号を warning に残す (design_decisions D1928-2)。"""
        cli = _load_cli_module()
        src_being_db = tmp_path / "src_beings.db"
        being_id = _populate_source_dbs(being_db=src_being_db)
        snapshot_json = tmp_path / "snapshot.json"
        cli.main(
            ["save", "--being-db", str(src_being_db), "--being-id", being_id.value, "--output", str(snapshot_json)]
        )
        data = json.loads(snapshot_json.read_text(encoding="utf-8"))
        data.pop("attachment_environment_id")
        data.pop("attachment_environment_name")
        data.update(attachment_world_id=1, attachment_player_id=1)
        snapshot_json.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        dst_being_db = tmp_path / "dst_beings.db"

        with caplog.at_level("WARNING"):
            rc = cli.main(["load", "--being-db", str(dst_being_db), "--input", str(snapshot_json)])

        assert rc == 0
        assert SqliteBeingRepository.connect(str(dst_being_db)).find_by_id(being_id).attachment is None
        assert any("was not kept" in record.getMessage() for record in caplog.records)

    def test_save_missing_source_db_exits_one(self, tmp_path: Path) -> None:
        """source DB が無い save は sqlite が自動生成する前に弾かれる。"""
        cli = _load_cli_module()
        rc = cli.main(
            [
                "save",
                "--being-db",
                str(tmp_path / "nonexistent.db"),  # 存在しない
                "--being-id",
                "being_w1_p1",
                "--output",
                str(tmp_path / "out.json"),
            ]
        )
        assert rc == 1

    def test_load_missing_input_exits_one(self, tmp_path: Path) -> None:
        """load で input file が無い場合は traceback ではなく exit 1。"""
        cli = _load_cli_module()
        rc = cli.main(
            [
                "load",
                "--being-db",
                str(tmp_path / "dst_b.db"),
                "--input",
                str(tmp_path / "no-such-file.json"),
            ]
        )
        assert rc == 1

    def test_save_unregistered_being_id_exits_one(self, tmp_path: Path) -> None:
        """未登録 being id の save は exit code 1。"""
        cli = _load_cli_module()
        rc = cli.main(
            [
                "save",
                "--being-db",
                str(tmp_path / "x_beings.db"),
                "--being-id",
                "being_w1_p99",
                "--output",
                str(tmp_path / "out.json"),
            ]
        )
        assert rc == 1


def test_help_subcommand_displays() -> None:
    """argparse の help 出力に save / load の両 subcommand が出る。"""
    cli = _load_cli_module()
    parser = cli.build_parser()
    help_text = parser.format_help()
    assert "save" in help_text
    assert "load" in help_text
