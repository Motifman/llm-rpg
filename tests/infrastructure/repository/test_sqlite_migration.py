"""SQLite migration helper and unified game DB bootstrap tests."""

from __future__ import annotations

import sqlite3

import pytest

from ai_rpg_world.infrastructure.repository.game_db_schema import init_game_db_schema
from ai_rpg_world.infrastructure.repository.sqlite_migration import (
    SqliteMigration,
    apply_migrations,
    get_applied_version,
)


class TestSqliteMigration:
    def test_apply_migrations_tracks_namespace_version(self) -> None:
        conn = sqlite3.connect(":memory:")
        apply_migrations(
            conn,
            namespace="demo",
            migrations=(
                SqliteMigration(
                    version=1,
                    apply=lambda c: c.execute(
                        "CREATE TABLE IF NOT EXISTS demo_table (id INTEGER PRIMARY KEY)"
                    ),
                ),
            ),
        )

        assert get_applied_version(conn, "demo") == 1
        cur = conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'demo_table'"
        )
        assert cur.fetchone() is not None

    def test_apply_migrations_is_idempotent(self) -> None:
        conn = sqlite3.connect(":memory:")
        calls = {"count": 0}

        def _apply(c: sqlite3.Connection) -> None:
            calls["count"] += 1
            c.execute("CREATE TABLE IF NOT EXISTS demo_table (id INTEGER PRIMARY KEY)")

        migrations = (SqliteMigration(version=1, apply=_apply),)
        apply_migrations(conn, namespace="demo", migrations=migrations)
        apply_migrations(conn, namespace="demo", migrations=migrations)

        assert calls["count"] == 1
        assert get_applied_version(conn, "demo") == 1

    def test_apply_migrations_rolls_back_all_changes_on_failure(self) -> None:
        conn = sqlite3.connect(":memory:")

        def _ok(c: sqlite3.Connection) -> None:
            c.execute("CREATE TABLE demo_ok (id INTEGER PRIMARY KEY)")

        def _ng(c: sqlite3.Connection) -> None:
            c.execute("CREATE TABLE demo_ng (id INTEGER PRIMARY KEY)")
            raise RuntimeError("boom")

        with pytest.raises(RuntimeError, match="boom"):
            apply_migrations(
                conn,
                namespace="demo",
                migrations=(
                    SqliteMigration(version=1, apply=_ok),
                    SqliteMigration(version=2, apply=_ng),
                ),
            )

        assert get_applied_version(conn, "demo") == 0
        cur = conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name IN ('demo_ok', 'demo_ng')"
        )
        assert cur.fetchall() == []

    def test_apply_migrations_uses_savepoint_inside_outer_transaction(self) -> None:
        conn = sqlite3.connect(":memory:")
        conn.execute("CREATE TABLE outer_table (id INTEGER PRIMARY KEY)")
        conn.execute("BEGIN")
        conn.execute("INSERT INTO outer_table (id) VALUES (1)")

        def _ng(c: sqlite3.Connection) -> None:
            c.execute("CREATE TABLE nested_fail (id INTEGER PRIMARY KEY)")
            raise RuntimeError("nested boom")

        with pytest.raises(RuntimeError, match="nested boom"):
            apply_migrations(
                conn,
                namespace="demo",
                migrations=(SqliteMigration(version=1, apply=_ng),),
            )

        cur = conn.execute("SELECT id FROM outer_table")
        assert [row[0] for row in cur.fetchall()] == [1]
        cur = conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'nested_fail'"
        )
        assert cur.fetchone() is None
        conn.commit()


class TestInitGameDbSchema:
    def test_unified_bootstrap_materializes_known_tables_and_versions(self) -> None:
        conn = sqlite3.connect(":memory:")
        init_game_db_schema(conn)

        cur = conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
        names = {row[0] for row in cur.fetchall()}
        assert "schema_migrations" in names
        assert "game_player_profiles" in names
        assert "game_item_specs" in names
        assert "game_recipes" in names
        assert "game_shops" in names
        assert "game_shop_summary_read_models" in names
        assert "game_shop_listing_read_models" in names
        assert "game_guilds" in names
        assert "game_guild_banks" in names
        assert "game_quests" in names
        assert "game_skill_loadouts" in names
        assert "game_skill_deck_progresses" in names
        assert "game_skill_specs" in names
        assert "game_dialogue_trees" in names
        assert "game_dialogue_tree_nodes" in names
        assert "game_guild_members" in names
        assert "game_quest_objectives" in names
        assert "game_skill_loadout_slots" in names
        assert "game_skill_deck_progress_proposals" in names
        assert "game_skill_spec_hit_pattern_segments" in names
        assert "game_dialogue_node_choices" in names
        assert "game_monster_template_attack_status_effects" in names
        assert "command_event_outbox" in names
        assert "game_sns_users" in names
        assert "game_sns_posts" in names
        assert "game_sns_replies" in names
        assert "game_sns_notifications" in names
        assert "trade_read_models" in names
        assert "trade_detail_read_models" in names
        assert "personal_trade_listing_read_models" in names
        assert "global_market_listing_read_models" in names

        cur = conn.execute(
            "SELECT namespace, version FROM schema_migrations ORDER BY namespace"
        )
        applied = {row[0]: row[1] for row in cur.fetchall()}
        assert applied == {
            "game_write": 33,
            "global_market_listing_read_model": 1,
            "personal_trade_listing_read_model": 1,
            "trade_detail_read_model": 1,
            "trade_read_model": 1,
        }

    def test_migration_v32_normalizes_legacy_naive_trade_datetime(self) -> None:
        """旧schemaのタイムゾーンなし取引日時をUTC付きにし、outboxイベントへ引き継げる。"""
        from ai_rpg_world.infrastructure.repository.game_write_sqlite_schema import (
            _GAME_WRITE_MIGRATIONS,
            init_game_write_schema,
        )

        conn = sqlite3.connect(":memory:")
        apply_migrations(
            conn,
            namespace="game_write",
            migrations=_GAME_WRITE_MIGRATIONS[:-2],
        )
        conn.execute(
            """
            INSERT INTO trade_aggregates (
                trade_id, seller_id, offered_item_id, requested_gold, created_at,
                trade_type, target_player_id, status, version, buyer_id
            ) VALUES (1, 1, 10, 50, '2026-08-14T01:02:03',
                      'global', NULL, 'active', 1, NULL)
            """
        )
        conn.commit()

        init_game_write_schema(conn)

        row = conn.execute(
            "SELECT created_at FROM trade_aggregates WHERE trade_id = 1"
        ).fetchone()
        assert row is not None
        assert row[0] == "2026-08-14T01:02:03+00:00"
        assert get_applied_version(conn, "game_write") == 33

    def test_migration_v32_rejects_invalid_legacy_trade_datetime(self) -> None:
        """解釈できない旧取引日時は推測変換せず、v32 migration全体をrollbackする。"""
        from ai_rpg_world.infrastructure.repository.game_write_sqlite_schema import (
            _GAME_WRITE_MIGRATIONS,
            init_game_write_schema,
        )

        conn = sqlite3.connect(":memory:")
        apply_migrations(
            conn,
            namespace="game_write",
            migrations=_GAME_WRITE_MIGRATIONS[:-2],
        )
        conn.execute(
            """
            INSERT INTO trade_aggregates (
                trade_id, seller_id, offered_item_id, requested_gold, created_at,
                trade_type, target_player_id, status, version, buyer_id
            ) VALUES (1, 1, 10, 50, 'not-a-datetime',
                      'global', NULL, 'active', 1, NULL)
            """
        )
        conn.commit()

        with pytest.raises(RuntimeError, match="trade_id=1"):
            init_game_write_schema(conn)

        assert get_applied_version(conn, "game_write") == 31
        table = conn.execute(
            "SELECT name FROM sqlite_master "
            "WHERE type = 'table' AND name = 'command_event_outbox'"
        ).fetchone()
        assert table is None

    def test_migration_v33_preserves_existing_outbox_rows_and_order(self) -> None:
        """v32のpending・delivered行を失わず、従来の作成順をoutbox_idへ移す。"""
        from ai_rpg_world.infrastructure.repository.game_write_sqlite_schema import (
            _GAME_WRITE_MIGRATIONS,
            init_game_write_schema,
        )

        conn = sqlite3.connect(":memory:")
        apply_migrations(
            conn,
            namespace="game_write",
            migrations=_GAME_WRITE_MIGRATIONS[:-1],
        )
        conn.execute(
            """
            INSERT INTO command_event_outbox (
                event_id, event_type, payload, payload_schema_version,
                status, created_at, delivered_at
            ) VALUES ('2', 'demo:Event', X'02', 1, 'pending',
                      '2026-08-14T00:00:02+00:00', NULL)
            """
        )
        conn.execute(
            """
            INSERT INTO command_event_outbox (
                event_id, event_type, payload, payload_schema_version,
                status, created_at, delivered_at
            ) VALUES ('1', 'demo:Event', X'01', 1, 'delivered',
                      '2026-08-14T00:00:01+00:00',
                      '2026-08-14T00:00:03+00:00')
            """
        )
        conn.commit()

        init_game_write_schema(conn)

        rows = conn.execute(
            """
            SELECT outbox_id, event_id, payload, status, delivered_at,
                   attempt_count, last_error
            FROM command_event_outbox
            ORDER BY outbox_id
            """
        ).fetchall()
        assert rows == [
            (1, "1", b"\x01", "delivered", "2026-08-14T00:00:03+00:00", 0, None),
            (2, "2", b"\x02", "pending", None, 0, None),
        ]

    def test_migration_v24_adds_six_phase4ab_columns(self) -> None:
        """v24 適用後、game_monsters に Phase 4a/4b 用 6 カラムが追加されている。"""
        import sqlite3

        from ai_rpg_world.infrastructure.repository.game_write_sqlite_schema import (
            init_game_write_schema,
        )

        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        init_game_write_schema(conn)
        conn.commit()

        cur = conn.execute("PRAGMA table_info(game_monsters)")
        column_names = {row["name"] for row in cur.fetchall()}
        assert "behavior_last_observed_target_spot_id" in column_names
        assert "behavior_flee_until_tick" in column_names
        assert "behavior_chase_attacker_ref_kind" in column_names
        assert "behavior_chase_attacker_ref_player_id" in column_names
        assert "behavior_chase_attacker_ref_monster_id" in column_names
        assert "behavior_chase_started_at_tick" in column_names

    def test_migration_v29_adds_item_usage_hint_column(self) -> None:
        """v29 適用後、game_item_specs に作者定義の usage_hint 列がある。"""
        from ai_rpg_world.infrastructure.repository.game_write_sqlite_schema import (
            init_game_write_schema,
        )

        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        init_game_write_schema(conn)
        conn.commit()

        cur = conn.execute("PRAGMA table_info(game_item_specs)")
        columns = {row["name"]: row for row in cur.fetchall()}
        assert columns["usage_hint"]["notnull"] == 1
        assert columns["usage_hint"]["dflt_value"] == "''"

    def test_migration_v30_adds_item_category_column(self) -> None:
        """v30 適用後、game_item_specs に作者定義の category 列がある。"""
        from ai_rpg_world.infrastructure.repository.game_write_sqlite_schema import (
            init_game_write_schema,
        )

        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        init_game_write_schema(conn)
        conn.commit()

        cur = conn.execute("PRAGMA table_info(game_item_specs)")
        columns = {row["name"]: row for row in cur.fetchall()}
        assert columns["category"]["notnull"] == 1
        assert columns["category"]["dflt_value"] == "''"
