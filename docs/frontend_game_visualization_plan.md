# Frontend Game Visualization Plan

## 1. Goal

本計画の目的は、2D 見下ろし RPG 風の最小 E2E デモを構築することです。

- 複数スポットから成る世界を用意する
- 各スポットは固有座標系を持つ独立シーンとして描画する
- プレイヤー 2〜3 体が LLM により行動する
- 人間は 1 体に対してのみ手動介入できる
- UI では一時停止 / 再開 / 速度変更 / 移動指示ができる
- マップ上でプレイヤー移動と天候変化が可視化される
- 将来的に戦闘、会話、採取、モンスター行動を段階的に追加できる


## 2. Fixed Decisions

- フロントエンド技術: React + Phaser
- 画風: 2D 見下ろし RPG 風
- マップ形式: Tiled JSON
- 最初のデモ範囲: 移動 + 天候
- UI 介入: 一時停止 / 再開 / 速度変更 + 移動指示
- 手動操作対象: 1 体のみ
- スポット構造: スポットごとに座標は独立し、ゲートウェイ通過で別スポットへ転送
- 描画モデル: スポットごとのシーン分離
- カメラモード: 定点カメラ / プレイヤー追跡カメラの切替
- collision の正本: Tiled JSON を import して内部形式へ変換して利用
- 手動移動の初期粒度: tile 単位
- 手動移動 UI: 矢印キー / WASD
- 追跡中のスポット遷移: 自動で scene 切替


## 2.1 Current Implementation Status

2026-03-28 時点の実装状況:

- Phase 1: 完了
  - UI DTO / importer DTO / exceptions / projection を追加済み
- Phase 2: 完了
  - `PlayerLocationChangedEvent`, `WorldObjectMovedEvent`, `GatewayTriggeredEvent`, `SpotWeatherChangedEvent` の UI 変換を追加済み
- Phase 3: 完了
  - `GameSceneSnapshotService` と world overview を追加済み
- Phase 4: 完了
  - framework-agnostic な `GameSceneApi` と `GameSceneStreamService` を追加済み
  - FastAPI adapter と WebSocket adapter を追加済み
  - HTTP / WebSocket 入力境界の正常系・例外系テストを追加済み
- Phase 5: 完了
  - `SimulationControlService` と `ManualActorControlService` を追加済み
  - `GameControlApi` を追加済み
- Phase 5.5: 完了
  - SQLite-backed web runtime composition を追加済み
  - projection bootstrap / request-scoped movement port / ASGI 起動導線を追加済み
  - 実 SQLite DB を使う integration-style test を追加済み
- Phase 6: 完了
  - `frontend/` に Vite + React shell を追加済み
  - Phaser mount point と scene runtime hook を追加済み
  - snapshot / WebSocket polling / control command のクライアント層を追加済み
  - frontend dependency install と production build を確認済み
- Phase 7: 完了
  - 新規 Tiled JSON サンプルマップを追加済み
  - Phaser renderer を Tiled JSON 読み込み前提へ更新済み
  - Fixed / Follow camera 切替 UI を追加済み
  - actor tween / weather overlay の簡易版を追加済み
  - Node `>=20` 前提で frontend build を確認済み
- Phase 8: 完了
  - gateway 遷移時の `actor_removed` + `scene_changed` delta を追加済み
  - follow camera 時の scene auto-switch を frontend で接続済み
  - WASD / 矢印キー長押しの手動 step 移動を追加済み
  - actor の idle / walk 演出と weather fade を追加済み
  - Vitest による frontend の正常系・境界系テストを追加済み
- Phase 9 以降: 未着手

追加済みの主要ファイル:

- `src/ai_rpg_world/application/ui/contracts/dtos.py`
- `src/ai_rpg_world/application/ui/services/game_scene_projection.py`
- `src/ai_rpg_world/application/ui/services/tiled_scene_importer.py`
- `src/ai_rpg_world/application/ui/services/game_scene_snapshot_service.py`
- `src/ai_rpg_world/application/ui/services/game_scene_stream_service.py`
- `src/ai_rpg_world/application/ui/services/simulation_control_service.py`
- `src/ai_rpg_world/application/ui/services/manual_actor_control_service.py`
- `src/ai_rpg_world/application/ui/handlers/ui_event_handler.py`
- `src/ai_rpg_world/infrastructure/events/ui_event_handler_registry.py`
- `src/ai_rpg_world/infrastructure/ui/in_memory_game_scene_event_broker.py`
- `src/ai_rpg_world/presentation/game_scene_api.py`
- `src/ai_rpg_world/presentation/game_control_api.py`
- `src/ai_rpg_world/presentation/web/app.py`
- `src/ai_rpg_world/application/ui/services/game_scene_projection_bootstrap_service.py`
- `src/ai_rpg_world/infrastructure/ui/sqlite_manual_movement_port.py`
- `src/ai_rpg_world/presentation/web/runtime.py`
- `src/ai_rpg_world/presentation/web/server.py`
- `frontend/package.json`
- `frontend/src/App.tsx`
- `frontend/src/hooks/useSceneRuntime.ts`
- `frontend/src/phaser/GameCanvas.tsx`
- `frontend/src/phaser/SceneRenderer.ts`
- `frontend/public/data/maps/spot_1.json`
- `frontend/public/data/maps/spot_2.json`
- `frontend/README.md`


## 3. Scene Model

### 3.1 Spot as Scene

本プロジェクトでは、スポット間に単一の物理座標空間を持たせず、各スポットを独立したシーンとして扱います。

- `spot_id` ごとに 1 つの Tiled JSON マップを持つ
- プレイヤーやモンスターの `coordinate` はそのスポット内でのみ意味を持つ
- スポット遷移は「歩いて境界を越える」のではなく、ゲートウェイを踏んだ結果として target spot に移る
- フロントエンドは「現在見ているスポット」を 1 つ表示する

この方針は既存の `SpotId` と `GatewayTriggeredEvent` を活かしやすく、現在のドメイン構造と整合します。

### 3.2 Area in Spot

スポット内には複数のエリアを置きます。

- 例: 広場、宿屋前、市場、門前
- エリアは Tiled の object layer または polygon/rectangle object で表現する
- 既存の `location_area_id` / `LocationEnteredEvent` / `LocationExitedEvent` と接続できるようにする


## 4. Architecture Overview

実装は以下の流れで構成します。

```text
Domain Event
  -> EventPublisher
    -> UI Event Handler
      -> Game Scene Projection
      -> UI Event Broker
        -> HTTP Snapshot API / WebSocket Stream
          -> React + Phaser
```

重要な原則は次の 3 点です。

- フロントエンドはドメインイベントを直接読まない
- 初回表示は snapshot、以降は delta event で更新する
- UI 向け state と LLM 向け observation は分ける


## 5. Backend-First Implementation Plan

### Phase 1: UI Contracts and Projection

まず UI 向けの表現をバックエンド内で定義します。

追加候補:

- `src/ai_rpg_world/application/ui/contracts/`
- `src/ai_rpg_world/application/ui/services/`
- `src/ai_rpg_world/application/ui/handlers/`
- `src/ai_rpg_world/infrastructure/events/ui_event_handler_registry.py`

主要 DTO:

- `GameSceneSnapshotDto`
- `SceneMapDto`
- `SceneActorDto`
- `SceneMonsterDto`
- `SceneWeatherDto`
- `SceneCameraTargetDto`
- `GameSceneDeltaEventDto`

delta event の最小セット:

- `scene_initialized`
- `actor_spawned`
- `actor_moved`
- `actor_removed`
- `weather_changed`
- `scene_changed`
- `log_appended`
- `simulation_paused`
- `simulation_resumed`
- `simulation_speed_changed`

`GameSceneProjection` が保持する内容:

- spot ごとの現在表示状態
- actor / monster の現在 tile 座標
- actor / monster の sprite key
- 現在天候
- ゲートウェイ情報
- 直近ログ
- scene version

### Phase 2: Domain Event to UI Event Mapping

既存イベントを UI 用に変換するハンドラを実装します。

最初に対応するイベント:

- `PlayerLocationChangedEvent`
- `WorldObjectMovedEvent`
- `GatewayTriggeredEvent`
- `SpotWeatherChangedEvent`
- `MonsterSpawnedEvent`（最初は optional）
- `MonsterDiedEvent`（最初は optional）

変換例:

- `WorldObjectMovedEvent` -> `actor_moved`
- `SpotWeatherChangedEvent` -> `weather_changed`
- `GatewayTriggeredEvent` -> `scene_changed`
- `PlayerLocationChangedEvent` -> `log_appended` および必要なら actor state 更新

ここではドメインイベントをそのまま流さず、フロントが使いやすい payload に正規化します。

### Phase 3: Scene Snapshot Query

UI 初回表示用の snapshot 生成サービスを作ります。

追加候補:

- `GameSceneSnapshotService`
- `GameSceneQueryService`

取得対象:

- 表示対象 spot の Tiled map metadata
- その spot にいる actor / monster 一覧
- weather 状態
- gateway 一覧
- area 一覧
- カメラ初期設定

初回表示は毎回この snapshot から開始し、その後 WebSocket の delta で追従します。

実装状況:

- `GameSceneSnapshotService` を追加済み
- projection を元に `get_scene_snapshot(spot_id)` と `get_world_overview()` を返せる
- `SpotRepository` がある場合は snapshot の `spot_name` を補正する

### Phase 4: Delivery Layer

配信方式は次をおすすめとします。

- 初回表示: HTTP
- 差分更新: WebSocket
- UI 介入コマンド: 最初は HTTP

理由:

- 実装責務が分離され、デバッグしやすい
- 双方向性が必要な部分だけを WebSocket に寄せられる
- 将来 WebSocket command に統合する余地を残せる

API 草案:

- `GET /api/scenes/{spot_id}/snapshot`
- `GET /api/world/overview`
- `POST /api/control/pause`
- `POST /api/control/resume`
- `POST /api/control/speed`
- `POST /api/actors/{actor_id}/move`
- `WS /api/scenes/{spot_id}/stream`

`move` は最初は「手動介入対象 actor だけ許可」とするのが安全です。

実装状況:

- `GameSceneStreamService` を追加済み
- `GameSceneApi` を追加済み
- `create_web_app(...)` を追加済み
- `GET /api/scenes/{spot_id}/snapshot` を実装済み
- `GET /api/world/overview` を実装済み
- `POST /api/control/pause`, `POST /api/control/resume`, `POST /api/control/speed` を実装済み
- `POST /api/actors/{actor_id}/move` を実装済み
- `WS /api/scenes/{scene_id}/stream` を実装済み
- WebSocket は以下を扱う
  - 初期 backlog 配信
  - `poll` による scene_version ベースの差分取得
  - `ping` / `pong`
  - 無効 cursor / 無効 payload / unsupported action の error 応答

### Phase 5: Simulation Control

UI からの介入のため、シミュレーション制御インターフェースを追加します。

候補:

- `SimulationControlService.pause()`
- `SimulationControlService.resume()`
- `SimulationControlService.set_speed(multiplier)`
- `ManualActorCommandService.move_to_gateway(...)`
- `ManualActorCommandService.move_to_tile(...)`

おすすめ:

- 最初は `move_to_tile` ではなく `move_to_gateway` または `move_to_named_destination`
- 理由: 既存の移動モデルと衝突しにくく、LLM と人間の操作が近い抽象になる

ただし見た目のデバッグ効率を考えると、スポット内移動確認のために `move_to_tile` も早めに欲しくなる可能性があります。

実装状況:

- `SimulationControlService` を追加済み
- `ManualActorControlService` を追加済み
- 手動移動は `move_to_tile` を正式採用
- キー長押しは UI 側で `step move` を連続発行する前提
- `GameControlApi` を追加済み

現在の方針:

- ゲームロジックは常に tile 単位
- 見た目の連続性はフロント側補間で実現する
- manual control の対象 actor は明示 whitelist で管理する

### Phase 5.5: Startup Wiring and Live Composition

Phase 6 に入る前に、FastAPI app を既存の runtime / SQLite / UoW と接続し、
モック前提ではない live composition を作る。

実装内容:

- SQLite game DB から projection の初期 snapshot を起こす bootstrap service
- HTTP command ごとに real な SQLite transaction / event publisher / movement service を組み立てる port
- FastAPI app を起動可能な runtime composition root
- `uvicorn` で起動できる ASGI entrypoint

実装状況:

- `GameSceneProjectionBootstrapService` を追加済み
- `SqliteManualMovementPort` を追加済み
- `create_sqlite_web_runtime(...)` / `create_sqlite_web_app(...)` を追加済み
- `create_sqlite_web_app_from_env()` と `server.py` を追加済み
- 実 DB へ seed した状態で
  - snapshot 取得
  - manual move
  - WebSocket backlog 取得
  が通る integration-style test を追加済み


## 6. Frontend Implementation Plan

### Phase 6: React Shell

React 側で以下を用意します。

- メインレイアウト
- スポット切替 UI
- カメラモード切替 UI
- シミュレーション制御 UI
- ログパネル
- actor 詳細パネル

実装状況:

- `frontend/` を独立 frontend workspace として追加済み
- Vite + React + TypeScript の scaffold を追加済み
- `App.tsx` で
  - scene selector
  - simulation control
  - manual move UI
  - actor / log panel
  を追加済み
- `useSceneRuntime` で
  - overview 取得
  - snapshot 取得
  - WebSocket polling
  を追加済み
- `GameCanvas` / `SceneRenderer` で Phaser mount と簡易 2D scene 描画を追加済み
- `npm install` と `npm run build` を確認済み
- 実行時は Node `>=20` が必要

### Phase 7: Phaser Scene Viewer

Phaser 側で以下を実装します。

- Tiled JSON の読み込み
- tile layer 描画
- actor sprite 配置
- weather overlay 表示
- camera mode 切替
- delta event に基づく actor 更新

実装状況:

- Phaser renderer を簡易 grid から Tiled JSON 読み込み前提へ更新済み
- tile layer と object layer を読み、gateway / area を描画できるようにした
- actor は再生成ではなく tween 補間で追従するようにした
- weather は overlay 表示を追加済み
- camera mode は fixed / follow を React shell から切替可能
- Tiled JSON の本格 import とアセット spritesheet 連携は次の段階

### Phase 8: Movement and Weather Visualization

最初のデモで成立すべき演出:

- actor が tile 間を補間移動する
- 向きが変わる
- idle / walk のアニメが切り替わる
- 雨や霧などの overlay が切り替わる
- ゲートウェイ通過で scene が切り替わる

実装状況:

- `UiEventHandler` は gateway 遷移時に source scene 向け `actor_removed` と target scene 向け `scene_changed` の 2 つの delta を publish する
- frontend の state reducer は `actor_removed` / `scene_changed` / `weather_changed` を扱い、scene list の actor count もローカル更新する
- follow camera で追跡中 actor が scene を跨いだ場合は、frontend が target spot へ自動で切り替える
- manual actor は WASD / 矢印キー長押しで 1 tile step を一定間隔で発行する
- Phaser renderer は actor の idle / walk 演出、facing marker 更新、weather overlay のフェード切替を行う
- frontend は Vitest で
  - delta reducer
  - scene auto-switch 判定
  - keyboard hold 制御
  - visual helper
  を検証済み

### Phase 9: Live Simulation Runtime Control

目的:

- UI の `pause / resume / speed` を projection 表示だけでなく、実際の world simulation loop に効かせる
- LLM agent / world tick / monster update を常駐実行で回し、viewer へリアルタイム反映する

実装候補:

- `ISimulationRuntimeControlPort` の SQLite / in-process 実装を追加
- `world_simulation_service.py` と接続する runtime loop manager を追加
- simulation thread / task の start / stop / tick rate 管理を追加
- pause 中は movement / weather / monster AI の進行を止める
- speed 変更時は tick sleep / scheduler interval を再計算する

テスト方針:

- control port unit test
- runtime loop の pause / resume / speed 変更 integration test
- Web API から control command を送った際に loop state が変わることの E2E test

完了条件:

- UI の pause / resume / speed が実 simulation に効く
- tick を進めると weather / actor / monster delta が継続的に stream へ流れる

### Phase 10: Asset Catalog and SpriteSheet Integration

目的:

- 仮の図形 actor を実アセットへ置き換える
- sprite key と spritesheet / animation 定義を結び、Phaser が real animation を再生できるようにする

実装候補:

- `frontend/public/assets/` に sprite / tileset / weather 素材を配置
- `frontend/src/phaser/assetCatalog.ts` を追加
- `actor sprite key` / `monster sprite key` / `weather overlay key` を asset catalog で解決
- `preload` 相当の asset loading を `SceneRenderer` に追加
- Tiled tileset image の読み込みルールを固定する

テスト方針:

- asset catalog の正常 / 欠落 key test
- animation 定義の contract test
- missing asset 時に fallback sprite へ落ちる例外系 test

完了条件:

- player / monster / weather が sprite / animation 付きで表示される
- missing asset でも viewer が落ちず fallback で表示できる

### Phase 11: Content Pipeline and Seed World

目的:

- 実際の最小世界を Tiled JSON + SQLite seed で再現できるようにする
- 2〜3 体の agent が動ける初期 world を reproducible に準備する

実装候補:

- Tiled map と DB seed の対応表を docs 化
- gateway / spawn / area / weather 初期値の seed script を追加
- starter town / field / dungeon entrance の 3 spot 構成を投入
- manual player 1 体 + LLM players 2 体 + monster templates を初期化

テスト方針:

- seed script integration test
- projection bootstrap が seed world を正しく snapshot 化する test
- gateway / spawn / weather が Tiled と DB で整合する test

完了条件:

- seed した DB を指定すれば backend / frontend がそのまま起動する
- spot 間移動と天候変化が最小世界で確認できる

### Phase 12: Multi-Agent E2E Demo

目的:

- 2〜3 体の LLM player を live world に接続し、viewer で追えるようにする
- 最小の「見て面白い」E2E デモを成立させる

実装候補:

- LLM runtime 起動導線と web runtime の同時起動
- agent role preset（探索 / 社交 / 採取 など）
- event log に agent の行動理由や失敗理由を表示
- replay / capture 用ログの保存

テスト方針:

- runtime composition integration test
- multi-agent actor update が stream へ流れる test
- fixed / follow camera で scene 切替が破綻しない test

完了条件:

- 2〜3 体の agent が map 上で動き、人間が観察・介入できる
- movement + weather + scene transition が viewer 上で一通り見える

## 11.1 Current Validation Against Initial Goal

当初目標に対する達成状況:

- 複数スポットから成る world:
  - 部分達成。sample Tiled JSON は複数 spot 対応済みで、backend も spot ごとの scene model を実装済み
- 各スポットを独立 scene として描画:
  - 達成。`spot_id` ごとの snapshot / stream と viewer scene 切替がある
- 人間が 1 体に手動介入:
  - 達成。HTTP move command と WASD / 矢印キー長押しがある
- 一時停止 / 再開 / 速度変更:
  - 部分達成。UI / API / projection は実装済みだが、live simulation loop への本接続は未実装
- マップ上で移動と天候が可視化:
  - 達成。actor movement tween と weather fade がある
- ゲートウェイ通過で scene 遷移:
  - 達成。delta と follow auto-switch を実装済み
- 2〜3 体の LLM player を live world で走らせる:
  - 未達成。viewer 基盤はあるが、常駐 simulation と LLM runtime 接続が次段階
- 実アセットによる表示:
  - 未達成。現在は placeholder rendering で、Phase 10 で置換予定

## 11.2 Local Verification Guide

現状、ユーザーが手元で確認しやすい導線:

1. backend test を流す
   - `uv run pytest tests/application/ui tests/presentation/web/test_app.py tests/presentation/web/test_runtime.py tests/presentation/web/test_runtime_env.py -q`
2. frontend dependency を入れる
   - `cd frontend`
   - `npm install`
3. frontend test / build を流す
   - `npm run test`
   - `npm run build`
4. backend を起動する
   - `AI_RPG_WORLD_GAME_DB=/path/to/game.db AI_RPG_WORLD_MANUAL_PLAYER_IDS=1 uv run python -m ai_rpg_world.presentation.web.server`
5. frontend を起動する
   - `cd frontend`
   - `npm run dev`
6. ブラウザで確認する
   - `http://127.0.0.1:5173`
   - scene selector
   - fixed / follow camera
   - pause / resume / speed
   - manual actor の button / WASD / 矢印キー移動
   - gateway を跨いだときの scene 切替

補足:

- 起動用 DB の seed 導線はまだ正式化していない。現時点では `tests/presentation/web/test_runtime.py` の `_seed_world(...)` が最小例に最も近い
- live simulation loop は未接続なので、pause / resume / speed は今は viewer 状態の確認が主目的


## 7. Data and Asset Plan

### 7.1 Tiled JSON

各スポットごとに 1 つの Tiled JSON を持ちます。

最低限必要な layer / object:

- ground layer
- decoration layer
- collision layer
- gateway object layer
- area object layer
- spawn point object layer

### 7.2 Required Map Metadata

#### tile map

マップをタイル単位で表現するデータです。

- 各スポットの地面や建物配置を保持する
- Tiled JSON の tile layer に相当
- Phaser はこれを読み込んで背景を描画する

#### collision/passable

そのタイルやオブジェクトを通れるかどうかを示す情報です。

- `passable = true`: 通行可能
- `passable = false`: 通行不可
- collision layer や tileset property で表現する
- バックエンドの移動検証とフロントのデバッグ表示で整合を取る必要がある

#### spawn points

プレイヤー、モンスター、NPC、ゲートウェイ着地点の出現位置です。

用途:

- 初期配置
- respawn
- gateway 遷移後の landing

Tiled では object layer の point / rectangle object として持つのが扱いやすいです。

#### actor sprite key

プレイヤーや NPC の見た目を引くためのキーです。

例:

- `player_knight_blue`
- `npc_innkeeper_female`

バックエンドはキーだけを持ち、フロントがアセットカタログで実ファイルに解決します。

#### monster sprite key

モンスター用スプライトの識別キーです。

例:

- `slime_green`
- `wolf_gray`

actor と分けて管理してもよいですが、最終的には共通の `sprite_key` に寄せても構いません。

#### weather overlay key

天候演出を表すキーです。

例:

- `rain_light`
- `rain_heavy`
- `fog_morning`

フロントはこのキーを見てパーティクル、スクリーントーン、霧などを切り替えます。

### 7.3 Asset Catalog

アセット参照は domain に持ち込まず、UI 向けカタログで管理します。

必要な辞書:

- `tileset_key -> tileset image / atlas`
- `sprite_key -> spritesheet / frame size / animation definitions`
- `weather_overlay_key -> overlay effect config`


## 8. Camera Plan

カメラモードは 2 つを用意します。

### Fixed Spot Camera

- スポット全体またはスポットの一部を定点表示する
- 観戦用、管理用に向く
- 複数 actor をまとめて見たいときに使う

### Follow Camera

- 特定プレイヤーを追跡する
- 手動介入対象 actor や注目プレイヤーの観察に向く
- scene 切替時には追跡対象の新 spot へ自動遷移する

最初の実装では「表示中スポット内の actor のみ追跡可能」にするとシンプルです。


## 9. Recommended Backend Payload Design

`actor_moved` payload の推奨項目:

- `event_id`
- `spot_id`
- `actor_id`
- `actor_type`
- `sprite_key`
- `from_tile`
- `to_tile`
- `facing`
- `started_at`
- `duration_ms`
- `scene_version`

`weather_changed` payload の推奨項目:

- `spot_id`
- `weather_type`
- `weather_intensity`
- `weather_overlay_key`
- `transition_ms`

`scene_changed` payload の推奨項目:

- `actor_id`
- `from_spot_id`
- `to_spot_id`
- `landing_tile`
- `reason`

### 9.1 Recommended Snapshot Schema

`GameSceneSnapshotDto` のおすすめ構成は以下です。

- `scene_id: str`
- `spot_id: int`
- `spot_name: str`
- `map: SceneMapDto`
- `camera: SceneCameraDto`
- `simulation: SimulationStateDto`
- `actors: list[SceneActorDto]`
- `monsters: list[SceneMonsterDto]`
- `weather: SceneWeatherDto`
- `gateways: list[SceneGatewayDto]`
- `areas: list[SceneAreaDto]`
- `ui_logs: list[SceneLogEntryDto]`
- `scene_version: int`
- `server_time_ms: int`

`SceneMapDto`

- `map_asset_key: str`
- `tiled_map_path: str`
- `tile_width: int`
- `tile_height: int`
- `map_width_tiles: int`
- `map_height_tiles: int`
- `collision_layer_name: str`
- `tileset_keys: list[str]`

`SceneActorDto`

- `actor_id: int`
- `player_id: int | null`
- `display_name: str`
- `actor_kind: str`
- `tile_x: int`
- `tile_y: int`
- `facing: str`
- `sprite_key: str`
- `is_manual_controlled: bool`
- `is_llm_controlled: bool`
- `state: str`

`SceneMonsterDto`

- `monster_id: int`
- `display_name: str`
- `tile_x: int`
- `tile_y: int`
- `facing: str`
- `sprite_key: str`
- `state: str`

`SceneWeatherDto`

- `weather_type: str`
- `weather_intensity: float`
- `weather_overlay_key: str | null`

`SceneGatewayDto`

- `gateway_id: int`
- `tile_x: int`
- `tile_y: int`
- `target_spot_id: int`
- `target_spot_name: str`
- `landing_tile_x: int`
- `landing_tile_y: int`

`SceneAreaDto`

- `area_id: int`
- `name: str`
- `shape_kind: str`
- `points: list[{x:int,y:int}]`

`SceneCameraDto`

- `mode: str`
- `tracked_actor_id: int | null`
- `viewport_width: int`
- `viewport_height: int`

`SimulationStateDto`

- `is_paused: bool`
- `speed_multiplier: float`

方針:

- snapshot は「今描画に必要な全状態」を返す
- フロントエンドは snapshot だけで scene を初期化できる
- Tiled JSON 本体はフロントが直接読むが、必要なメタデータは snapshot にも含める

### 9.2 Recommended Delta Event Schema

`GameSceneDeltaEventDto` は envelope + payload 方式をおすすめします。

- `event_id: str`
- `event_type: str`
- `scene_id: str`
- `spot_id: int`
- `scene_version: int`
- `emitted_at_ms: int`
- `payload: object`

最初に定義する `event_type`:

- `actor_spawned`
- `actor_moved`
- `actor_removed`
- `actor_state_changed`
- `weather_changed`
- `scene_changed`
- `simulation_paused`
- `simulation_resumed`
- `simulation_speed_changed`
- `log_appended`

`actor_moved.payload`

- `actor_id: int`
- `from_tile_x: int`
- `from_tile_y: int`
- `to_tile_x: int`
- `to_tile_y: int`
- `facing: str`
- `move_duration_ms: int`
- `move_mode: str`

`weather_changed.payload`

- `weather_type: str`
- `weather_intensity: float`
- `weather_overlay_key: str | null`
- `transition_ms: int`

`scene_changed.payload`

- `actor_id: int`
- `from_spot_id: int`
- `to_spot_id: int`
- `landing_tile_x: int`
- `landing_tile_y: int`
- `auto_follow_switched: bool`

`simulation_speed_changed.payload`

- `speed_multiplier: float`

`log_appended.payload`

- `level: str`
- `message: str`
- `related_actor_id: int | null`

方針:

- すべての delta event に `scene_version` を持たせる
- 順序逆転や再接続時は snapshot を再取得して復旧しやすくする
- 長押し移動でもイベントは常に 1 tile 1 event にする

### 9.3 Recommended Manual Movement Model

長押し移動を含めても、移動モデルは離散 tile のまま維持することをおすすめします。

方針:

- キー長押し = 一定間隔で `step move` 要求を発行
- バックエンドは毎回 1 tile だけ検証して処理
- フロントは補間アニメーションで滑らかに見せる

おすすめ理由:

- 既存の離散座標系と衝突しない
- LLM と人間で同じ移動ルールを共有できる
- collision / gateway / busy state の判定が単純

実装上の推奨:

- repeat 間隔は `move_duration_ms` と同等か少し長め
- 進行中の step が終わるまで次入力は保留または破棄
- UI では「押しっぱなしで流れる」が、サーバー内部では逐次 step 実行
- 斜め移動は初期段階では禁止

### 9.4 Recommended Tiled Importer Contract

Tiled importer は「描画用 JSON をそのままゲームロジックへ流す」のではなく、以下の情報だけを内部形式へ正規化して渡すことをおすすめします。

入力:

- Tiled JSON
- tileset metadata
- object layer metadata
- custom property definitions

出力:

- `ImportedSceneMap`
- `ImportedCollisionGrid`
- `ImportedGatewaySet`
- `ImportedAreaSet`
- `ImportedSpawnPointSet`
- `ImportedRenderMetadata`

`ImportedSceneMap`

- `spot_id`
- `map_width_tiles`
- `map_height_tiles`
- `tile_width`
- `tile_height`
- `tileset_keys`
- `render_layers`

`ImportedCollisionGrid`

- `passable[x][y]`
- `movement_cost[x][y]` optional
- `terrain_tag[x][y]` optional

`ImportedGatewaySet`

- `gateway_id`
- `tile_x`
- `tile_y`
- `target_spot_id`
- `landing_tile_x`
- `landing_tile_y`

`ImportedAreaSet`

- `area_id`
- `name`
- `shape_kind`
- `points`

`ImportedSpawnPointSet`

- `spawn_id`
- `spawn_kind`
- `tile_x`
- `tile_y`
- `sprite_key` optional
- `metadata`

`ImportedRenderMetadata`

- `map_asset_key`
- `tiled_map_path`
- `upper_layers`
- `shadow_layers`
- `overlay_anchor_points`

Tiled から読むべきおすすめ要素:

- tile layers
- object layers
- tile properties
- object properties
- map custom properties

Tiled で使う custom property のおすすめ:

- tile property: `passable: bool`
- tile property: `terrain_tag: str`
- object property: `object_kind: gateway|area|spawn`
- object property: `target_spot_id: int`
- object property: `landing_tile_x: int`
- object property: `landing_tile_y: int`
- object property: `area_id: int`
- object property: `sprite_key: str`
- map property: `spot_id: int`
- map property: `map_asset_key: str`

この importer の責務:

- Tiled 表現を検証する
- ゲームロジックに必要な最小情報へ変換する
- UI が欲しい描画メタデータも抽出する

この importer の責務に含めないもの:

- actor の現在位置管理
- weather の現在状態
- simulation state
- LLM runtime の状態


## 10. Animation and 2.5D Presentation

2D のまま少し 3D っぽく見せるため、以下を採用します。

- Y 座標ベースの depth sort
- actor の足元 shadow
- overlay layer と upper decoration layer の分離
- 雨 / 霧 / 光量変化による環境演出
- 建物や木の前後関係の表現
- camera easing

バックエンド側で必要なこと:

- actor の tile 座標
- facing
- movement duration
- scene transition event

フロント側で必要なこと:

- tile 座標から pixel 座標への変換
- 補間移動
- idle / walk animation 切替
- depth sort
- overlay effect


## 11. Implementation Order

### Wave 1: Backend Foundation

- UI contracts 追加
- projection 追加
- UI event handler 追加
- UI registry 追加
- snapshot service 追加
- HTTP + WebSocket 配信口追加

### Wave 2: Minimal Frontend Viewer

- React shell
- Phaser scene viewer
- snapshot 読み込み
- delta event 反映
- actor 移動補間
- weather overlay

### Wave 3: Control and Scene Switching

- pause / resume / speed control
- manual move command
- fixed / follow camera
- gateway による scene switching

### Wave 4: LLM Integration

- 2〜3 体の LLM プレイヤー起動
- actor 行動ログ可視化
- 手動介入対象の切替


## 12. Open Questions

以下は実装着手前または Wave 1 〜 2 中に決める必要があります。

### Q1. Backend authoritative collision source

選択肢:

- A. Tiled JSON をバックエンドが直接読んで collision を使う
- B. Tiled JSON から内部 PhysicalMap 形式へ import する

決定:

- B. import 方式

理由:

- ドメインモデルと UI 表示モデルの境界を保ちやすい
- 将来 Tiled の表現が増えても変換層に閉じ込められる

### Q2. Manual move granularity

選択肢:

- A. destination/waypoint 単位
- B. tile 単位

決定:

- 初期は tile 単位
- 入力方法は矢印キー / WASD

補足:

- キー入力は「1 tile 先へ移動要求」を送る
- バックエンドは collision / busy state / scene transition を検証したうえで受理する
- 将来的に destination 指示も追加可能
- 長押し入力は「連続 tile 移動要求の生成」として扱う
- 自由座標の連続移動にはしない

### Q3. Scene switching behavior

選択肢:

- A. ゲートウェイ通過 actor を追って自動で scene 切替
- B. 現在表示スポットは固定し、通知だけ出す

決定:

- follow camera 中は A
- fixed camera 中は B

### Q4. Multi-spot overview

将来的には、1 スポット単位ビューに加えて世界全体の俯瞰ビューが欲しくなる可能性があります。
ただし最初の実装ではスコープ外とします。


## 13. Risks

- Tiled JSON をそのままドメインに食わせると責務が混ざりやすい
- UI 用イベントと observation を混ぜると責務が崩れる
- WebSocket に command と event を一気に乗せると初期デバッグが難しくなる
- spot 遷移時の scene synchronization を曖昧にすると表示バグが出やすい


## 14. Recommended Next Step

次に着手すべき作業は以下です。

1. React + Phaser の最小 viewer を実装し、snapshot 読み込みと WebSocket delta 反映を開始する
2. Tiled importer と scene snapshot の接続を強め、マップファイル実読込の integration test を追加する
3. follow / fixed camera の UI と scene switching の E2E 動作を固める
4. world tick loop と `runtime control port` を接続し、pause / resume / speed を live simulation に反映する
