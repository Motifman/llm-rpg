# Phase 0 Attribute Inventory

Source of truth: `src/ai_rpg_world/application/world/contracts/dtos.py` の `PlayerCurrentStateDto`（2026-03-23 時点）

## Ownership Rule

- `world`: プレイヤーの位置、周辺環境、視界、移動可能性、行動状態のように「世界の現在状態」を表すもの
- `runtime`: LLM ツール選択や UI ラベル生成のための sibling list / summary / prompt context
- `app_session`: ゲーム内 app の active state、page state、snapshot、app-local meta

## Attribute Classification

| Attribute | Owner | Notes |
|-----------|-------|-------|
| `player_id` | world | 識別子。compat shortcut を残す |
| `player_name` | world | 識別ラベル。formatter 参照あり |
| `current_spot_id` | world | availability / UI runtime でも使う shortcut 候補 |
| `current_spot_name` | world | formatter 用 |
| `current_spot_description` | world | formatter 用 |
| `x` / `y` / `z` | world | UI runtime context の `current_x/y/z` にも使う |
| `current_player_count` | world | formatter 用 |
| `current_player_ids` | world | 現時点では builder 内の world facts。直接 consumer は薄い |
| `connected_spot_ids` | world | world facts |
| `connected_spot_names` | world | formatter 用 |
| `weather_type` / `weather_intensity` | world | formatter 用 |
| `current_terrain_type` | world | formatter 用 |
| `visible_objects` | world | availability / UI の双方で強依存 |
| `view_distance` | world | formatter 用 |
| `available_moves` | world | availability / UI の双方で利用 |
| `total_available_moves` | world | availability / formatter 用 |
| `attention_level` | world | formatter 用 |
| `area_ids` / `area_names` | world | `area_ids` は availability / runtime context でも利用 |
| `area_id` / `area_name` | world | 後方互換 shortcut |
| `available_location_areas` | world | availability / UI 用 |
| `current_location_description` | world | formatter 用 |
| `is_busy` / `busy_until_tick` / `has_active_path` | world | availability / formatter で使用 |
| `inventory_items` | runtime | availability / UI で頻出 shortcut |
| `chest_items` | runtime | availability / UI 用 |
| `active_conversation` | runtime | availability / UI 用 |
| `active_harvest` | runtime | availability / formatter / UI 用 |
| `usable_skills` | runtime | availability / UI 用 |
| `equipable_skill_candidates` | runtime | availability / UI 用 |
| `skill_equip_slots` | runtime | availability / UI 用 |
| `pending_skill_proposals` | runtime | availability / UI 用 |
| `awakened_action` | runtime | availability / UI 用 |
| `attention_level_options` | runtime | availability / UI 用 |
| `can_destroy_placeable` | runtime | availability / UI 用 |
| `actionable_objects` | runtime | availability / UI 用。`visible_objects` 由来だが tool-facing に加工済み |
| `notable_objects` | runtime | formatter / UI 用。`visible_objects` 由来だが tool-facing に加工済み |
| `active_quest_ids` | runtime | memory retrieval hints |
| `guild_ids` | runtime | memory retrieval hints |
| `nearby_shop_ids` | runtime | memory retrieval hints |
| `active_quests` | runtime | availability / UI 用 |
| `guild_memberships` | runtime | availability / UI 用 |
| `nearby_shops` | runtime | availability / UI 用 |
| `available_trades` | runtime | availability / UI 用。trade page 導入後も shortcut 残置候補 |
| `visible_tile_map` | world | 重い optional payload。formatter only |
| `current_game_time_label` | world | formatter 用 |
| `is_sns_mode_active` | app_session | compat boolean。真実は `active_game_app` |
| `active_game_app` | app_session | app session の single source |
| `is_trade_mode_active` | app_session | compat boolean。真実は `active_game_app` |
| `sns_virtual_page_kind` | app_session | SNS page state |
| `sns_home_tab` | app_session | SNS page state |
| `sns_page_snapshot_generation` | app_session | SNS page session meta |
| `sns_current_page_snapshot_json` | app_session | 重い optional payload |
| `sns_profile_is_self` | app_session | app-local tool gating 用 |
| `trade_virtual_page_kind` | app_session | Trade page state |
| `trade_my_trades_tab` | app_session | Trade page state |
| `trade_page_snapshot_generation` | app_session | Trade page session meta |
| `trade_current_page_snapshot_json` | app_session | 重い optional payload |

## Candidate Shortcut Properties

Phase 1 の compat facade で優先して shortcut を残す候補:

- world:
  - `current_spot_id`
  - `current_spot_name`
  - `x` / `y` / `z`
  - `visible_objects`
  - `available_moves`
  - `total_available_moves`
  - `available_location_areas`
  - `is_busy`
  - `busy_until_tick`
  - `has_active_path`
  - `area_ids`
- runtime:
  - `inventory_items`
  - `chest_items`
  - `active_conversation`
  - `active_harvest`
  - `usable_skills`
  - `equipable_skill_candidates`
  - `skill_equip_slots`
  - `pending_skill_proposals`
  - `awakened_action`
  - `attention_level_options`
  - `can_destroy_placeable`
  - `actionable_objects`
  - `notable_objects`
  - `active_quests`
  - `guild_memberships`
  - `nearby_shops`
  - `available_trades`
- app_session:
  - `active_game_app`
  - `is_sns_mode_active`
  - `is_trade_mode_active`
  - `sns_virtual_page_kind`
  - `sns_profile_is_self`
  - `trade_virtual_page_kind`
  - `trade_my_trades_tab`

## Heavy / Optional Payload Strategy

- `visible_tile_map`
  - owner は `world`
  - formatter 専用に近く、Phase 1 では `PlayerWorldStateDto` 配下へ移す
  - compat shortcut は残してよいが、新規 consumer は増やさない
- `sns_current_page_snapshot_json`
  - owner は `app_session`
  - app-local snapshot として扱い、top-level 直追加の前例にしない
- `trade_current_page_snapshot_json`
  - owner は `app_session`
  - app-local snapshot として扱い、SNS と同じ方針に揃える

## Consumer Map

主要 consumer と依存塊:

- `current_state_formatter.py`
  - 主に `world`
  - 一部 `runtime` (`active_harvest`, `notable_objects`, `actionable_objects`)
  - 一部 `app_session` (`sns_current_page_snapshot_json`, `trade_current_page_snapshot_json`)
- `availability_resolvers.py`
  - `runtime` 依存が最も強い
  - `world` では `current_spot_id`, `visible_objects`, `available_moves`, `is_busy`, `has_active_path`, `area_ids`
  - `app_session` では SNS / Trade mode と page state
- `ui_context_builder.py`
  - `runtime` 依存が最も強い
  - `world` では `visible_objects`, `available_moves`, `available_location_areas`, `x/y/z`, `current_spot_id`, `area_ids`
  - `app_session` では `is_trade_mode_active`, `trade_virtual_page_kind`

## Phase 1 Implications

- `PlayerRuntimeContextDto` は `inventory_items` 群だけでなく、tool-facing に加工済みの `actionable_objects` / `notable_objects` / `available_trades` も持つ
- `PlayerWorldStateDto` には raw world facts と行動状態を寄せる
- `PlayerAppSessionStateDto` は active app と page snapshot 類の単一の追加先にする
- `PlayerCurrentStateDto` は Phase 1 では facade として残し、上記 shortcut を property 委譲で公開する

## Open Points For Phase 1

- `player_id` / `player_name` を `world` に置くか facade root に残すか
- `actionable_objects` / `notable_objects` を `runtime` に置くことへの違和感がないか
- `current_game_time_label` を world のままにするか formatter-specific summary へ寄せるか
