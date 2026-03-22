id: feature-trade-page-tool-gating
title: Trade 独立モードと取引所ページ
slug: trade-page-tool-gating
status: planned
created_at: 2026-03-22
updated_at: 2026-03-22
branch: feature/trade-page-tool-gating
---

# Objective

Trade を SNS 依存の配線から切り離し、単独のゲーム内アプリモードとして起動できるようにする。同時に、取引所の `market` / `search` / `my_trades` を LLM が読みやすいページスナップショットとして提供し、既存の取引ミューテーションをそのページ文脈に沿って gated に露出させる。

# Success Criteria

- `register_default_tools` で Trade ツールが `trade_enabled` のみで登録され、`sns_enabled` に依存しない。
- 単一の active app slot により、SNS と Trade が同時にアクティブにならず、別アプリへ入るには明示的 exit が必要である。
- Trade モード ON のときだけ `trade_enter` 以外の Trade ツールが利用可能になり、SNS モード ON では Trade ツールが見えない。
- `market` / `search` / `my_trades` のページスナップショットが取得でき、`item_name + price range + rarity/type` の検索が成立する。
- テストでは provider / wiring / session / page query / executor の各層で、モード排他と page-local ref 契約を確認する。

# Alignment Loop

- Initial phase proposal:
  - まず active app slot を導入して相互排他を固定し、その上で Trade モード導線、Trade page session/query、tool gating 統合、旧前提の掃除へ進む。
- User-confirmed success definition:
  - Trade は SNS と完全に別物として扱う。
  - 別アプリへ入る前には明示的 exit を要求する。
  - 取引所 UI は `market` / `search` / `my_trades` を起点にし、検索は `item_name + price range + rarity/type` を含める。
- User-confirmed phase ordering:
  - 軽い暫定実装で先に露出だけ変えるのではなく、相互排他の基盤と Trade page の最終形を前提に phase を切る。
- Cost or scope tradeoffs discussed:
  - `SnsModeSessionService` 前提の既存テストと wiring が広く、active app slot への置換は横断的になる。
  - Trade page を SNS virtual pages と同品質で作るには、session・snapshot・tool gating・prompt 表示まで一貫して揃える必要がある。

# Scope Contract

- In scope:
  - active app slot 導入と、SNS/Trade の相互排他ルール
  - `trade_enter` / `trade_exit` と Trade モード専用 availability
  - `market` / `search` / `my_trades` のページ定義
  - Trade page session、snapshot DTO、page-local `trade_ref`
  - `GlobalMarketQueryService` / `PersonalTradeQueryService` / `TradeQueryService` の再利用
  - provider / resolver / executor / wiring / prompt への統合
- Out of scope:
  - SNS 画面契約の変更
  - オークション、価格履歴、レコメンド、ウォッチリスト
  - 永続化されたアプリセッション
  - Trade 以外の新規アプリモード追加
- User-confirmed constraints:
  - 別アプリへの切替は自動ではなく明示的 exit 前提
  - 検索は `item_name + price range + rarity/type` を第 1 弾から含める
  - ドメインへ UI 用 ref や app mode を持ち込まない
- Reopen alignment if:
  - `my_trades` に必要な情報が既存 query / read model 再利用で賄えない場合
  - `trade_ref` 導入が既存 `trade_label` との両立を著しく複雑化する場合
  - active app slot だけでは SNS 側 page session との整合が壊れる場合

# Code Context

- Existing modules to extend
  - `src/ai_rpg_world/application/llm/services/tool_catalog/__init__.py`
  - `src/ai_rpg_world/application/llm/services/tool_catalog/trade.py`
  - `src/ai_rpg_world/application/llm/services/availability_resolvers.py`
  - `src/ai_rpg_world/application/llm/services/executors/sns_executor.py`
  - `src/ai_rpg_world/application/llm/services/executors/trade_executor.py`
  - `src/ai_rpg_world/application/llm/wiring/__init__.py`
  - `src/ai_rpg_world/application/world/contracts/dtos.py`
  - `src/ai_rpg_world/application/world/services/player_current_state_builder.py`
  - `src/ai_rpg_world/application/social/services/sns_mode_session_service.py`
  - `src/ai_rpg_world/application/social/sns_virtual_pages/sns_page_session_service.py`
  - `src/ai_rpg_world/application/trade/services/global_market_query_service.py`
  - `src/ai_rpg_world/application/trade/services/personal_trade_query_service.py`
  - `src/ai_rpg_world/application/trade/services/trade_query_service.py`
- Existing exceptions, events, inheritance, and test patterns to follow
  - query service の例外ラップ方針
  - `SnsPageSessionService` / `SnsPageQueryService` の session + snapshot + ref パターン
  - `tests/application/llm/test_available_tools_provider.py`
  - `tests/application/llm/test_sns_mode_wiring_e2e.py`
  - `tests/application/trade/services/test_global_market_query_service.py`
  - `tests/application/trade/services/test_trade_query_service.py`
- Integration points and known risks
  - `PlayerCurrentStateDto` は現状 `is_sns_mode_active` を正としており、active app slot へ移行する際の互換保持が必要
  - `register_default_tools` と resolver の二重ゲートがあり、どちらを最終的な責務境界にするか整理が必要
  - Trade executor は既存で `trade_id` / inventory 解決前提のため、page-local `trade_ref` への入力導線を追加する必要がある

# Risks And Unknowns

- active app slot 導入時に既存 SNS テストが広く壊れ、Trade feature 以上の修正が必要になる可能性がある。
- `my_trades` の UX を 1 画面にまとめすぎると、売り手向けと受信向けの可用ツールが複雑化する。
- 既存 `available_trades` サマリと新しい Trade page snapshot の責務が重複しうる。
- `trade_label` と `trade_ref` を中途半端に共存させると、argument resolver と prompt の理解負荷が上がる。

# Phases

## Trade Screen Scope Contracts（Phase 1 で固定し、以後は原則変更しない）

- Goal:
  - Trade 仮想ページの final shape を固定する。
- Scope:
  - page kind: `market` | `search` | `my_trades`
  - `my_trades` tab: `selling` | `incoming`
  - 共通ページング: `limit` 省略時 20、最大 100、`offset` ベース
  - 共通メタ: `page_kind`, `active_tab`, `filters`, `paging`, `snapshot_generation`
  - 行参照: `trade_ref` は現在の Trade page session と現スナップショット世代でのみ有効
- Dependencies:
  - 既存 Trade query / read model 能力の把握
- Parallelizable:
  - 低い
- Success definition:
  - 各ページの表示項目、許可操作、フィルタ、ref 契約が plan 上で曖昧なく固定されている。
- Checkpoint:
  - 下記 3 ページの契約が `PLAN.md` に記載されている。
- Reopen alignment if:
  - `my_trades` に詳細ページが必須と判明した場合
- Notes:
  - 生 ID をそのまま LLM のページ文脈に出さず、ページ内参照は `trade_ref` を第一候補とする。

### `market`

- 表示項目:
  - アクティブ出品一覧、アイテム名、価格、種別、rarity、equipment_type、作成時刻、`trade_ref`
- 許可操作:
  - 再読込、次ページ、検索ページへ遷移、出品
- 供給元:
  - `GlobalMarketQueryService.get_market_listings`

### `search`

- 表示項目:
  - 現在フィルタ（`item_name`, `min_price`, `max_price`, `item_types`, `rarities`, `equipment_types`）、検索結果一覧、`trade_ref`
- 許可操作:
  - 検索条件更新、再読込、次ページ、`market` へ戻る、出品
- 供給元:
  - `GlobalMarketQueryService.get_market_listings(filter_dto=...)`

### `my_trades`

- タブ:
  - `selling`: 自分の出品
  - `incoming`: 自分宛の直接取引
- 表示項目:
  - `selling` はアイテム名、価格、状態、`trade_ref`
  - `incoming` は送り手、アイテム名、価格、`trade_ref`
- 許可操作:
  - タブ切替、再読込、次ページ、`selling` で cancel、`incoming` で accept/decline
- 供給元:
  - `selling`: `TradeQueryService.get_trades_for_player`
  - `incoming`: `PersonalTradeQueryService.get_personal_trades`

## Phase 1: Active App Slot 契約の固定

- Goal:
  - SNS/Trade 相互排他を bool の足し算ではなく単一スロットで表現する。
- Scope:
  - `ActiveGameAppSessionService` 相当の導入
  - `PlayerCurrentStateDto` に `active_game_app` と `is_trade_mode_active` を追加
  - 既存 `is_sns_mode_active` は互換のため派生保持
  - enter 前に他 app が active なら拒否する契約を定義
- Dependencies:
  - なし
- Parallelizable:
  - 低い
- Success definition:
  - active app の真実の置き場が 1 箇所に決まり、SNS/Trade 同時 ON が不可能になる。
- Checkpoint:
  - session service 単体テストで `none -> sns -> none -> trade` と拒否ケースが固定される。
- Reopen alignment if:
  - 既存 SNS page session が active app slot と強く衝突する場合
- Notes:
  - ここでは Trade page 自体はまだ作らない。

## Phase 2: Trade モード導線と露出分離

- Goal:
  - Trade を `trade_enabled` のみで登録し、Trade モード ON/OFF に応じて露出を切り替える。
- Scope:
  - `register_default_tools` の Trade 登録条件見直し
  - `TradeModeRequiredAvailabilityResolver` と `TradeEnter/Exit` 用 resolver
  - `trade_enter` / `trade_exit` の tool constants・tool catalog・executor 追加
  - `sns_enter` / `sns_logout` を active app slot 契約に合わせて更新
- Dependencies:
  - Phase 1
- Parallelizable:
  - 中程度
- Success definition:
  - 通常時は `trade_enter` のみ、Trade モード時は Trade family のみ、SNS モード時は Trade family が見えない。
- Checkpoint:
  - provider / wiring テストで 3 状態（none, sns, trade）の露出差分が確認できる。
- Reopen alignment if:
  - `trade_enter` / `trade_exit` を別 executor に置くより既存 executor 統合の方が自然と判明した場合
- Notes:
  - 既存 4 ミューテーションはこの phase で Trade モードゲートへ切り替える。

## Phase 3: Trade Page Session と Snapshot DTO

- Goal:
  - Trade 向け current page、tab、filters、paging、ref map を保持するセッション基盤を導入する。
- Scope:
  - `TradePageSessionService` 相当
  - page kind / my trades tab enum
  - snapshot generation と `trade_ref` 発行・解決
  - `PlayerCurrentStateDto` への Trade page kind / snapshot JSON の配線方針確定
- Dependencies:
  - Phase 1
- Parallelizable:
  - 中程度
- Success definition:
  - Trade page の最小状態遷移と ref invalidation が self-contained に成立する。
- Checkpoint:
  - unit test で `market -> search -> my_trades` 遷移と ref 世代更新が確認できる。
- Reopen alignment if:
  - `PlayerCurrentStateDto` に snapshot を載せると責務が重すぎると判明した場合
- Notes:
  - SNS page と似せるが、実装は独立でよい。

## Phase 4: Trade Page Query Service 実装

- Goal:
  - 既存 Trade query service を束ねて、3 画面のスナップショットを返す。
- Scope:
  - `market` snapshot
  - `search` snapshot
  - `my_trades` snapshot (`selling` / `incoming`)
  - filter DTO 変換と paging 適用
  - `trade_ref` を含む line DTO 組み立て
- Dependencies:
  - Phase 3
- Parallelizable:
  - 中程度
- Success definition:
  - 検索条件とタブ状態に応じて、Trade page snapshot が query service 再利用だけで組み立てられる。
- Checkpoint:
  - page query service テストで item name / price / rarity/type の検索と `my_trades` 2 タブが通る。
- Reopen alignment if:
  - `incoming` と `selling` を統合した snapshot 形が不自然で、ページ分割が必要になった場合
- Notes:
  - 新規 read model は最後の手段とし、まず既存 `GlobalMarketQueryService` と `PersonalTradeQueryService` を使う。

## Phase 5: Tool Catalog / Executor / Prompt 統合

- Goal:
  - Trade page を LLM stack に統合し、ページごとに適切なツールだけ見せる。
- Scope:
  - `trade_view_current_page`
  - `trade_open_page`
  - `trade_page_next`
  - `trade_page_refresh`
  - `trade_switch_tab`
  - `trade_search` もしくは `trade_open_page(search, filters...)`
  - `trade_accept` / `trade_decline` / `trade_cancel` の page-specific gating と `trade_ref` 入力対応
  - prompt への current Trade page snapshot 差し込み
- Dependencies:
  - Phase 2
  - Phase 4
- Parallelizable:
  - 中程度
- Success definition:
  - Trade モード中、現在ページに応じて利用可能ツールが切り替わり、検索から accept/cancel までページ文脈で操作できる。
- Checkpoint:
  - wiring / available tools / executor の回帰テストが通る。
- Reopen alignment if:
  - 汎用 page tool 群だけでは UX が悪く、ページ専用ツールを増やす必要が出た場合
- Notes:
  - 既存 `trade_label` を残す場合でも、prompt とページ導線は `trade_ref` 優先にする。

## Phase 6: 旧前提の整理と回帰テスト固定

- Goal:
  - 「Trade は SNS 配下」という旧前提をテストとコメントから外し、将来の回帰を防ぐ。
- Scope:
  - `register_default_tools` の doc/comment 更新
  - `test_available_tools_provider.py` / `test_sns_mode_wiring_e2e.py` の期待更新
  - 必要なら `trade_label` ベースの旧導線の縮退または互換整理
- Dependencies:
  - Phase 5
- Parallelizable:
  - 中程度
- Success definition:
  - Trade 独立モード前提がテストとコードコメントの両方で一貫する。
- Checkpoint:
  - `pytest` の関連テスト群が通り、新しい期待値が仕様として読める。
- Reopen alignment if:
  - 既存 downstream テストが多数破綻し、互換レイヤを一時的に残す必要が出た場合
- Notes:
  - cleanup は最後に行う。

# Review Standard

- No placeholder or temporary implementation
- DDD boundaries stay explicit
- Exceptions are handled deliberately
- Tests cover happy path and meaningful failure cases
- Existing strict test style is preserved
- App mode exclusivity is enforced by one source of truth
- Trade page refs never leak into domain objects

# Execution Deltas

- Change trigger:
  - active app slot の導入範囲が SNS 周辺を越えて広がるとき
- Scope delta:
  - `my_trades` のページ分割
  - `trade_ref` 導入見送り
  - 新規 read model の追加
- User re-confirmation needed:
  - 明示的 exit 方針を自動切替へ戻すとき
  - 検索スコープを `item_name + price range + rarity/type` より縮小するとき
  - `market` / `search` / `my_trades` のページ構成を変えるとき

# Plan Revision Gate

- Revise future phases when:
  - active app slot の表現方法が実装上変わるとき
  - Trade page 契約に新しい page kind や detail page を追加するとき
- Keep future phases unchanged when:
  - 内部の service 名や DTO 分割だけが変わり、公開契約と phase の成果物が同じとき
- Ask user before editing future phases or adding a new phase:
  - 明示的 exit を撤回する
  - 検索条件を増減する
  - page-local `trade_ref` をやめて別参照方式へ変える
- Plan-change commit needed when:
  - phase 順序や最終的なページ構成が実質的に変わるとき

# Change Log

- 2026-03-22: Initial plan created
- 2026-03-22: Promoted idea into feature plan with explicit-exit app exclusivity and Trade page contracts
