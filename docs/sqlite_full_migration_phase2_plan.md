# SQLite Full Migration Phase 2 Working Plan

このファイルは Phase 2-3 の実装中に使う一時プランです。

## Goals

- SQLite の共通基盤の上に `world/player` の中核リポジトリを載せる
- `PhysicalMapRepository` を SQLite 化し、`world_object_id -> spot_id` 索引と採番を DB 側で持つ
- 既存の `player_profile/status/inventory/item` SQLite 実装と合わせて world 系 wiring を作る
- 後続の `MonsterRepository` / `HitBoxRepository` 移行で再利用できる共通方針を固める

## Current Slice

1. `game_write` スキーマに world state 用テーブルを追加する
2. `allocate_sequence_value` を初期値付き採番に拡張する
3. `SqlitePhysicalMapRepository` を追加する
4. world/player 用 SQLite repository bundle を追加する
5. repository contract と rollback をテストで固定する

## Follow-ups

- `MonsterRepository` を同じ `world_object_id` シーケンスへ接続する
- `HitBoxRepository` を同一 DB / UoW 契約で移行する
- `SpotRepository` を列ベース保存で SQLite 化し、query 系の移行足場を作る
- `PhysicalMapAggregate` の snapshot から一部 read model を分離するか再評価する
