"""SQLite migration helper and unified game DB bootstrap tests."""

from __future__ import annotations

import sqlite3

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
            "game_write": 20,
            "global_market_listing_read_model": 1,
            "personal_trade_listing_read_model": 1,
            "trade_detail_read_model": 1,
            "trade_read_model": 1,
        }
