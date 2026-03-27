"""Trade コマンド経路向けドメイン書き込みテーブル（`GAME_DB_PATH` 単一 DB に同居）。"""
from __future__ import annotations

import sqlite3

from ai_rpg_world.infrastructure.repository.sqlite_migration import (
    SqliteMigration,
    apply_migrations,
)


_GAME_WRITE_NAMESPACE = "game_write"


def _migration_v1(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS game_sequences (
            name TEXT PRIMARY KEY NOT NULL,
            next_value INTEGER NOT NULL
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS trade_aggregates (
            trade_id INTEGER PRIMARY KEY NOT NULL,
            seller_id INTEGER NOT NULL,
            offered_item_id INTEGER NOT NULL,
            requested_gold INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            trade_type TEXT NOT NULL,
            target_player_id INTEGER,
            status TEXT NOT NULL,
            version INTEGER NOT NULL,
            buyer_id INTEGER
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS game_player_profiles (
            player_id INTEGER PRIMARY KEY NOT NULL,
            name TEXT NOT NULL,
            role TEXT NOT NULL,
            race TEXT NOT NULL,
            element TEXT NOT NULL,
            control_type TEXT NOT NULL
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS game_items (
            item_instance_id INTEGER PRIMARY KEY NOT NULL,
            item_spec_id INTEGER NOT NULL,
            payload_json TEXT NOT NULL
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS game_player_inventories (
            player_id INTEGER PRIMARY KEY NOT NULL,
            payload_json TEXT NOT NULL
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS game_player_statuses (
            player_id INTEGER PRIMARY KEY NOT NULL,
            aggregate_blob BLOB NOT NULL
        )
        """
    )


def _migration_v2(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS game_physical_maps (
            spot_id INTEGER PRIMARY KEY NOT NULL,
            aggregate_blob BLOB NOT NULL
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS game_world_object_locations (
            world_object_id INTEGER PRIMARY KEY NOT NULL,
            spot_id INTEGER NOT NULL
        )
        """
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_game_world_object_locations_spot
            ON game_world_object_locations(spot_id, world_object_id)
        """
    )


def _migration_v3(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS game_monsters (
            monster_id INTEGER PRIMARY KEY NOT NULL,
            world_object_id INTEGER NOT NULL UNIQUE,
            spot_id INTEGER,
            aggregate_blob BLOB NOT NULL
        )
        """
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_game_monsters_spot_monster
            ON game_monsters(spot_id, monster_id)
        """
    )


def _migration_v4(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS game_hit_boxes (
            hit_box_id INTEGER PRIMARY KEY NOT NULL,
            spot_id INTEGER NOT NULL,
            owner_id INTEGER NOT NULL,
            is_active INTEGER NOT NULL,
            aggregate_blob BLOB NOT NULL
        )
        """
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_game_hit_boxes_spot_active_hit_box
            ON game_hit_boxes(spot_id, is_active, hit_box_id)
        """
    )


def _migration_v5(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS game_spots (
            spot_id INTEGER PRIMARY KEY NOT NULL,
            name TEXT NOT NULL,
            description TEXT NOT NULL,
            category TEXT NOT NULL,
            parent_id INTEGER
        )
        """
    )
    connection.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_game_spots_name
            ON game_spots(name)
        """
    )


def _migration_v6(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS game_location_establishments (
            spot_id INTEGER NOT NULL,
            location_area_id INTEGER NOT NULL,
            establishment_type TEXT,
            establishment_id INTEGER,
            aggregate_blob BLOB NOT NULL,
            PRIMARY KEY (spot_id, location_area_id)
        )
        """
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_game_location_establishments_establishment
            ON game_location_establishments(establishment_type, establishment_id)
        """
    )


def _migration_v7(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS game_transition_policies (
            from_spot_id INTEGER NOT NULL,
            to_spot_id INTEGER NOT NULL,
            payload_json TEXT NOT NULL,
            PRIMARY KEY (from_spot_id, to_spot_id)
        )
        """
    )


def _migration_v8(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS game_gateway_connections (
            from_spot_id INTEGER NOT NULL,
            to_spot_id INTEGER NOT NULL,
            PRIMARY KEY (from_spot_id, to_spot_id)
        )
        """
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_game_gateway_connections_from_spot
            ON game_gateway_connections(from_spot_id, to_spot_id)
        """
    )


def _migration_v9(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS game_weather_zones (
            zone_id INTEGER PRIMARY KEY NOT NULL,
            name TEXT NOT NULL,
            weather_type TEXT NOT NULL,
            intensity REAL NOT NULL,
            aggregate_blob BLOB NOT NULL
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS game_weather_zone_spots (
            spot_id INTEGER PRIMARY KEY NOT NULL,
            zone_id INTEGER NOT NULL
        )
        """
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_game_weather_zone_spots_zone
            ON game_weather_zone_spots(zone_id, spot_id)
        """
    )


def _migration_v10(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS game_spawn_tables (
            spot_id INTEGER PRIMARY KEY NOT NULL,
            aggregate_blob BLOB NOT NULL
        )
        """
    )


def _migration_v11(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS game_monster_templates (
            template_id INTEGER PRIMARY KEY NOT NULL,
            name TEXT NOT NULL,
            aggregate_blob BLOB NOT NULL
        )
        """
    )
    connection.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_game_monster_templates_name
            ON game_monster_templates(name)
        """
    )


def _migration_v12(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS game_loot_tables (
            loot_table_id INTEGER PRIMARY KEY NOT NULL,
            name TEXT NOT NULL,
            aggregate_blob BLOB NOT NULL
        )
        """
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_game_loot_tables_name
            ON game_loot_tables(name, loot_table_id)
        """
    )


def _migration_v13(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS game_item_specs (
            item_spec_id INTEGER PRIMARY KEY NOT NULL,
            name TEXT NOT NULL,
            item_type TEXT NOT NULL,
            rarity TEXT NOT NULL,
            is_tradeable INTEGER NOT NULL,
            payload_json TEXT NOT NULL
        )
        """
    )
    connection.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_game_item_specs_name
            ON game_item_specs(name)
        """
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_game_item_specs_type
            ON game_item_specs(item_type, item_spec_id)
        """
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_game_item_specs_rarity
            ON game_item_specs(rarity, item_spec_id)
        """
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_game_item_specs_tradeable
            ON game_item_specs(is_tradeable, item_spec_id)
        """
    )


def _migration_v14(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS game_recipes (
            recipe_id INTEGER PRIMARY KEY NOT NULL,
            name TEXT NOT NULL,
            result_item_spec_id INTEGER NOT NULL,
            payload_json TEXT NOT NULL
        )
        """
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_game_recipes_result_item
            ON game_recipes(result_item_spec_id, recipe_id)
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS game_recipe_ingredients (
            recipe_id INTEGER NOT NULL,
            ingredient_item_spec_id INTEGER NOT NULL,
            quantity INTEGER NOT NULL,
            PRIMARY KEY (recipe_id, ingredient_item_spec_id)
        )
        """
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_game_recipe_ingredients_item
            ON game_recipe_ingredients(ingredient_item_spec_id, recipe_id)
        """
    )


def _migration_v15(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS game_shops (
            shop_id INTEGER PRIMARY KEY NOT NULL,
            spot_id INTEGER NOT NULL,
            location_area_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            payload_json TEXT NOT NULL
        )
        """
    )
    connection.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_game_shops_location
            ON game_shops(spot_id, location_area_id)
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS game_shop_summary_read_models (
            shop_id INTEGER PRIMARY KEY NOT NULL,
            spot_id INTEGER NOT NULL,
            location_area_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            description TEXT NOT NULL,
            owner_ids_json TEXT NOT NULL,
            listing_count INTEGER NOT NULL,
            created_at TEXT NOT NULL
        )
        """
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_game_shop_summary_location
            ON game_shop_summary_read_models(spot_id, location_area_id, shop_id)
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS game_shop_listing_read_models (
            listing_id INTEGER PRIMARY KEY NOT NULL,
            shop_id INTEGER NOT NULL,
            item_instance_id INTEGER NOT NULL,
            item_name TEXT NOT NULL,
            item_spec_id INTEGER NOT NULL,
            price_per_unit INTEGER NOT NULL,
            quantity INTEGER NOT NULL,
            listed_by INTEGER NOT NULL,
            listed_at TEXT
        )
        """
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_game_shop_listing_shop
            ON game_shop_listing_read_models(shop_id, listing_id)
        """
    )


def _migration_v16(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS game_guilds (
            guild_id INTEGER PRIMARY KEY NOT NULL,
            spot_id INTEGER NOT NULL,
            location_area_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            description TEXT NOT NULL
        )
        """
    )
    connection.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_game_guilds_location
            ON game_guilds(spot_id, location_area_id)
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS game_guild_members (
            guild_id INTEGER NOT NULL,
            player_id INTEGER NOT NULL,
            role TEXT NOT NULL,
            joined_at TEXT NOT NULL,
            contribution_points INTEGER NOT NULL,
            PRIMARY KEY (guild_id, player_id)
        )
        """
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_game_guild_members_player
            ON game_guild_members(player_id, guild_id)
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS game_guild_banks (
            guild_id INTEGER PRIMARY KEY NOT NULL,
            gold INTEGER NOT NULL
        )
        """
    )


def _migration_v17(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS game_quests (
            quest_id INTEGER PRIMARY KEY NOT NULL,
            status TEXT NOT NULL,
            issuer_player_id INTEGER,
            guild_id INTEGER,
            acceptor_player_id INTEGER,
            scope_type TEXT NOT NULL,
            scope_target_player_id INTEGER,
            scope_guild_id INTEGER,
            reward_gold INTEGER NOT NULL,
            reward_exp INTEGER NOT NULL,
            reserved_gold INTEGER NOT NULL,
            version INTEGER NOT NULL,
            created_at TEXT NOT NULL
        )
        """
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_game_quests_acceptor_status
            ON game_quests(acceptor_player_id, status, quest_id)
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS game_quest_objectives (
            quest_id INTEGER NOT NULL,
            objective_index INTEGER NOT NULL,
            objective_type TEXT NOT NULL,
            target_id INTEGER NOT NULL,
            required_count INTEGER NOT NULL,
            current_count INTEGER NOT NULL,
            target_id_secondary INTEGER,
            PRIMARY KEY (quest_id, objective_index)
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS game_quest_reward_items (
            quest_id INTEGER NOT NULL,
            reward_index INTEGER NOT NULL,
            item_spec_id INTEGER NOT NULL,
            quantity INTEGER NOT NULL,
            PRIMARY KEY (quest_id, reward_index)
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS game_quest_reserved_items (
            quest_id INTEGER NOT NULL,
            item_index INTEGER NOT NULL,
            item_instance_id INTEGER NOT NULL,
            PRIMARY KEY (quest_id, item_index)
        )
        """
    )


def _migration_v18(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS game_skill_loadouts (
            loadout_id INTEGER PRIMARY KEY NOT NULL,
            owner_id INTEGER NOT NULL UNIQUE,
            normal_capacity INTEGER NOT NULL,
            awakened_capacity INTEGER NOT NULL,
            awaken_is_active INTEGER NOT NULL,
            awaken_active_until_tick INTEGER NOT NULL,
            awaken_cooldown_reduction_rate REAL NOT NULL,
            cast_lock_until_tick INTEGER NOT NULL
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS game_skill_deck_progresses (
            progress_id INTEGER PRIMARY KEY NOT NULL,
            owner_id INTEGER NOT NULL UNIQUE,
            deck_level INTEGER NOT NULL,
            deck_exp INTEGER NOT NULL,
            exp_table_base_exp INTEGER NOT NULL,
            exp_table_exponent REAL NOT NULL,
            exp_table_level_offset INTEGER NOT NULL,
            capacity_growth_per_level INTEGER NOT NULL
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS game_skill_specs (
            skill_id INTEGER PRIMARY KEY NOT NULL,
            name TEXT NOT NULL,
            element TEXT NOT NULL,
            deck_cost INTEGER NOT NULL,
            cast_lock_ticks INTEGER NOT NULL,
            cooldown_ticks INTEGER NOT NULL,
            power_multiplier REAL NOT NULL,
            pattern_type TEXT NOT NULL,
            mp_cost INTEGER,
            stamina_cost INTEGER,
            hp_cost INTEGER,
            is_awakened_deck_only INTEGER NOT NULL,
            targeting_range INTEGER NOT NULL
        )
        """
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_game_skill_specs_name
            ON game_skill_specs(name, skill_id)
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS game_skill_loadout_slots (
            loadout_id INTEGER NOT NULL,
            deck_tier TEXT NOT NULL,
            slot_index INTEGER NOT NULL,
            skill_id INTEGER NOT NULL,
            PRIMARY KEY (loadout_id, deck_tier, slot_index)
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS game_skill_loadout_cooldowns (
            loadout_id INTEGER NOT NULL,
            skill_id INTEGER NOT NULL,
            ready_at_tick INTEGER NOT NULL,
            PRIMARY KEY (loadout_id, skill_id)
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS game_skill_deck_progress_capacity_bonuses (
            progress_id INTEGER NOT NULL,
            level INTEGER NOT NULL,
            bonus_capacity INTEGER NOT NULL,
            PRIMARY KEY (progress_id, level)
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS game_skill_deck_progress_proposals (
            progress_id INTEGER NOT NULL,
            proposal_id INTEGER NOT NULL,
            proposal_type TEXT NOT NULL,
            offered_skill_id INTEGER NOT NULL,
            deck_tier TEXT NOT NULL,
            target_slot_index INTEGER,
            reason TEXT NOT NULL,
            PRIMARY KEY (progress_id, proposal_id)
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS game_skill_deck_progress_proposal_required_skills (
            progress_id INTEGER NOT NULL,
            proposal_id INTEGER NOT NULL,
            required_index INTEGER NOT NULL,
            skill_id INTEGER NOT NULL,
            PRIMARY KEY (progress_id, proposal_id, required_index)
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS game_skill_spec_required_skills (
            skill_id INTEGER NOT NULL,
            required_index INTEGER NOT NULL,
            required_skill_id INTEGER NOT NULL,
            PRIMARY KEY (skill_id, required_index)
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS game_skill_spec_slayer_races (
            skill_id INTEGER NOT NULL,
            race_index INTEGER NOT NULL,
            race TEXT NOT NULL,
            PRIMARY KEY (skill_id, race_index)
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS game_skill_spec_hit_effects (
            skill_id INTEGER NOT NULL,
            effect_index INTEGER NOT NULL,
            effect_type TEXT NOT NULL,
            duration_ticks INTEGER NOT NULL,
            intensity REAL NOT NULL,
            chance REAL NOT NULL,
            PRIMARY KEY (skill_id, effect_index)
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS game_skill_spec_hit_pattern_segments (
            skill_id INTEGER NOT NULL,
            segment_index INTEGER NOT NULL,
            start_offset_ticks INTEGER NOT NULL,
            duration_ticks INTEGER NOT NULL,
            velocity_dx REAL NOT NULL,
            velocity_dy REAL NOT NULL,
            velocity_dz REAL NOT NULL,
            spawn_dx INTEGER NOT NULL,
            spawn_dy INTEGER NOT NULL,
            spawn_dz INTEGER NOT NULL,
            segment_power_multiplier REAL NOT NULL,
            PRIMARY KEY (skill_id, segment_index)
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS game_skill_spec_hit_pattern_coords (
            skill_id INTEGER NOT NULL,
            segment_index INTEGER NOT NULL,
            coord_index INTEGER NOT NULL,
            dx INTEGER NOT NULL,
            dy INTEGER NOT NULL,
            dz INTEGER NOT NULL,
            PRIMARY KEY (skill_id, segment_index, coord_index)
        )
        """
    )


def _migration_v19(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS game_dialogue_trees (
            tree_id INTEGER PRIMARY KEY NOT NULL,
            entry_node_id INTEGER NOT NULL
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS game_dialogue_tree_nodes (
            tree_id INTEGER NOT NULL,
            node_id INTEGER NOT NULL,
            text TEXT NOT NULL,
            next_node_id INTEGER,
            is_terminal INTEGER NOT NULL,
            reward_gold INTEGER NOT NULL,
            PRIMARY KEY (tree_id, node_id)
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS game_dialogue_node_choices (
            tree_id INTEGER NOT NULL,
            node_id INTEGER NOT NULL,
            choice_index INTEGER NOT NULL,
            label TEXT NOT NULL,
            next_node_id INTEGER NOT NULL,
            PRIMARY KEY (tree_id, node_id, choice_index)
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS game_dialogue_node_reward_items (
            tree_id INTEGER NOT NULL,
            node_id INTEGER NOT NULL,
            reward_index INTEGER NOT NULL,
            item_spec_id INTEGER NOT NULL,
            quantity INTEGER NOT NULL,
            PRIMARY KEY (tree_id, node_id, reward_index)
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS game_dialogue_node_quest_unlocks (
            tree_id INTEGER NOT NULL,
            node_id INTEGER NOT NULL,
            quest_index INTEGER NOT NULL,
            quest_id INTEGER NOT NULL,
            PRIMARY KEY (tree_id, node_id, quest_index)
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS game_dialogue_node_quest_completions (
            tree_id INTEGER NOT NULL,
            node_id INTEGER NOT NULL,
            quest_index INTEGER NOT NULL,
            quest_id INTEGER NOT NULL,
            PRIMARY KEY (tree_id, node_id, quest_index)
        )
        """
    )


def _migration_v20(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS game_sns_users (
            user_id INTEGER PRIMARY KEY NOT NULL,
            user_name TEXT NOT NULL UNIQUE,
            display_name TEXT NOT NULL,
            bio TEXT NOT NULL
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS game_sns_follows (
            follower_user_id INTEGER NOT NULL,
            followee_user_id INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            PRIMARY KEY (follower_user_id, followee_user_id)
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS game_sns_blocks (
            blocker_user_id INTEGER NOT NULL,
            blocked_user_id INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            PRIMARY KEY (blocker_user_id, blocked_user_id)
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS game_sns_subscriptions (
            subscriber_user_id INTEGER NOT NULL,
            subscribed_user_id INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            PRIMARY KEY (subscriber_user_id, subscribed_user_id)
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS game_sns_posts (
            post_id INTEGER PRIMARY KEY NOT NULL,
            author_user_id INTEGER NOT NULL,
            content TEXT NOT NULL,
            visibility TEXT NOT NULL,
            deleted INTEGER NOT NULL,
            created_at TEXT NOT NULL
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS game_sns_post_hashtags (
            post_id INTEGER NOT NULL,
            hashtag TEXT NOT NULL,
            PRIMARY KEY (post_id, hashtag)
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS game_sns_post_likes (
            post_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            PRIMARY KEY (post_id, user_id)
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS game_sns_post_mentions (
            post_id INTEGER NOT NULL,
            user_name TEXT NOT NULL,
            PRIMARY KEY (post_id, user_name)
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS game_sns_replies (
            reply_id INTEGER PRIMARY KEY NOT NULL,
            author_user_id INTEGER NOT NULL,
            parent_post_id INTEGER,
            parent_reply_id INTEGER,
            content TEXT NOT NULL,
            visibility TEXT NOT NULL,
            deleted INTEGER NOT NULL,
            created_at TEXT NOT NULL
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS game_sns_reply_hashtags (
            reply_id INTEGER NOT NULL,
            hashtag TEXT NOT NULL,
            PRIMARY KEY (reply_id, hashtag)
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS game_sns_reply_likes (
            reply_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            PRIMARY KEY (reply_id, user_id)
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS game_sns_reply_mentions (
            reply_id INTEGER NOT NULL,
            user_name TEXT NOT NULL,
            PRIMARY KEY (reply_id, user_name)
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS game_sns_notifications (
            notification_id INTEGER PRIMARY KEY NOT NULL,
            user_id INTEGER NOT NULL,
            notification_type TEXT NOT NULL,
            title TEXT NOT NULL,
            message TEXT NOT NULL,
            actor_user_id INTEGER NOT NULL,
            actor_user_name TEXT NOT NULL,
            related_post_id INTEGER,
            related_reply_id INTEGER,
            content_type TEXT,
            content_text TEXT,
            created_at TEXT NOT NULL,
            is_read INTEGER NOT NULL,
            expires_at TEXT
        )
        """
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_game_sns_follows_followee
            ON game_sns_follows(followee_user_id, follower_user_id)
        """
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_game_sns_blocks_blocked
            ON game_sns_blocks(blocked_user_id, blocker_user_id)
        """
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_game_sns_subscriptions_subscribed
            ON game_sns_subscriptions(subscribed_user_id, subscriber_user_id)
        """
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_game_sns_posts_author_created
            ON game_sns_posts(author_user_id, created_at DESC, post_id DESC)
        """
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_game_sns_post_hashtags_hashtag
            ON game_sns_post_hashtags(hashtag, post_id)
        """
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_game_sns_post_mentions_user
            ON game_sns_post_mentions(user_name, post_id)
        """
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_game_sns_post_likes_user
            ON game_sns_post_likes(user_id, post_id)
        """
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_game_sns_replies_parent_post_created
            ON game_sns_replies(parent_post_id, created_at DESC, reply_id DESC)
        """
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_game_sns_replies_parent_reply_created
            ON game_sns_replies(parent_reply_id, created_at DESC, reply_id DESC)
        """
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_game_sns_replies_author_created
            ON game_sns_replies(author_user_id, created_at DESC, reply_id DESC)
        """
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_game_sns_reply_mentions_user
            ON game_sns_reply_mentions(user_name, reply_id)
        """
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_game_sns_reply_likes_user
            ON game_sns_reply_likes(user_id, reply_id)
        """
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_game_sns_notifications_user_created
            ON game_sns_notifications(user_id, created_at DESC, notification_id DESC)
        """
    )


_GAME_WRITE_MIGRATIONS = (
    SqliteMigration(version=1, apply=_migration_v1),
    SqliteMigration(version=2, apply=_migration_v2),
    SqliteMigration(version=3, apply=_migration_v3),
    SqliteMigration(version=4, apply=_migration_v4),
    SqliteMigration(version=5, apply=_migration_v5),
    SqliteMigration(version=6, apply=_migration_v6),
    SqliteMigration(version=7, apply=_migration_v7),
    SqliteMigration(version=8, apply=_migration_v8),
    SqliteMigration(version=9, apply=_migration_v9),
    SqliteMigration(version=10, apply=_migration_v10),
    SqliteMigration(version=11, apply=_migration_v11),
    SqliteMigration(version=12, apply=_migration_v12),
    SqliteMigration(version=13, apply=_migration_v13),
    SqliteMigration(version=14, apply=_migration_v14),
    SqliteMigration(version=15, apply=_migration_v15),
    SqliteMigration(version=16, apply=_migration_v16),
    SqliteMigration(version=17, apply=_migration_v17),
    SqliteMigration(version=18, apply=_migration_v18),
    SqliteMigration(version=19, apply=_migration_v19),
    SqliteMigration(version=20, apply=_migration_v20),
)


def init_game_write_schema(connection: sqlite3.Connection) -> None:
    """`CREATE TABLE IF NOT EXISTS` のみ。コミットは呼び出し側（UoW またはブートストラップ）。"""
    apply_migrations(
        connection,
        namespace=_GAME_WRITE_NAMESPACE,
        migrations=_GAME_WRITE_MIGRATIONS,
    )
    # シーケンス行は allocate_sequence_value 初回呼び出しで INSERT OR IGNORE する。
    # ここで INSERT すると sqlite3 の暗黙トランザクションが開いたまま残り、
    # 後続の明示 BEGIN と衝突するため行わない。


def allocate_sequence_value(
    connection: sqlite3.Connection,
    name: str,
    *,
    initial_value: int = 0,
) -> int:
    """同一接続・同一トランザクション内で採番する。rollback すると採番も巻き戻る。"""
    connection.execute(
        "INSERT OR IGNORE INTO game_sequences (name, next_value) VALUES (?, ?)",
        (name, initial_value),
    )
    connection.execute(
        "UPDATE game_sequences SET next_value = next_value + 1 WHERE name = ?",
        (name,),
    )
    cur = connection.execute(
        "SELECT next_value FROM game_sequences WHERE name = ?",
        (name,),
    )
    row = cur.fetchone()
    if row is None:
        raise RuntimeError(f"sequence missing after init: {name}")
    return int(row[0])


__all__ = ["allocate_sequence_value", "init_game_write_schema"]
