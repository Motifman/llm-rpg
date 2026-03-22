---
id: feature-player-current-state-dto-refactoring
title: PlayerCurrentStateDto の段階分割と互換維持リファクタリング
slug: player-current-state-dto-refactoring
status: planned
created_at: 2026-03-23
updated_at: 2026-03-23
branch: codex/player-current-state-dto-refactoring-phase4
---

# Objective

`PlayerCurrentStateDto` を、LLM 向け既存契約を大きく壊さずに段階分割し、今後の SNS / Trade / 他 app 状態追加でトップレベル属性を増やし続けなくて済む構造へ移行する。初手では `builder + DTO` の責務境界を固め、`property` 委譲ベースの compat を用意し、利用側の大規模書き換えは後段に送る。

# Success Criteria

- `PlayerCurrentStateDto` の全属性が `world` / `runtime` / `app_session` のどこに属するか整理され、`PLAN.md` 上で曖昧さなく説明できる。
- 新しい app-local 状態を追加するとき、`PlayerCurrentStateDto` のトップレベルに直接属性を足すのではなく、`app_session` 配下へ足す方針が固定される。
- phase 1 完了時点で、既存 formatter / availability / UI builder の public 契約を壊さずに sub DTO 導入が可能になる。
- `ToolAvailabilityContext = PlayerCurrentStateDto` の現契約を維持したまま、後続 phase で resolver / UI を新境界へ寄せられる道筋がある。
- テスト戦略として、DTO 単体、builder、formatter/UI/availability の互換確認ポイントが定義されている。

# Alignment Loop

- Initial phase proposal:
  - まず属性棚卸しと責務境界を固定し、次に `builder + DTO` だけを分割して compat property を導入し、その後 resolver / formatter / UI を段階移行する。
- Code-based reasoning:
  - `PlayerRuntimeContextBuilder` が既に runtime context の分離点になっているため、初手はこれを延長して DTO 側の塊を明確化するのが安全。
  - `src/ai_rpg_world/application/llm/contracts/dtos.py` に `ToolAvailabilityContext は PlayerCurrentStateDto をそのまま利用する` とあるため、phase 1 で resolver 側まで一気に切り替えると横断コストが高い。
  - `current_state_formatter.py` と `ui_context_builder.py` は参照パターンが異なり、UI builder の方が runtime 依存が濃く重いため、同時変更は避ける価値がある。
- User-confirmed choices:
  - compat 戦略は **property 委譲**を第一候補とする。
  - phase 1 は **builder + DTO のみ**に留める。
  - plan の主成功条件は **今後の追加耐性**を作ること。
- Cost or scope tradeoffs discussed:
  - adapter 新設は設計上は明快だが、`PlayerCurrentStateDto(...)` を直接組む既存テストが多く、初手の変更面が広がりやすい。
  - `ui_context_builder` を初手で触ると runtime target label 契約まで巻き込むため、phase を分けた方が安全。

# Scope Contract

- In scope:
  - `PlayerCurrentStateDto` の属性棚卸しと責務分類
  - `PlayerWorldStateDto` / `PlayerRuntimeContextDto` / `PlayerAppSessionStateDto` の素案
  - `property` 委譲ベースの compat 方針
  - `PlayerCurrentStateBuilder` の分割方針
  - formatter / availability / UI builder の段階移行順
  - テスト・checkpoint の定義
- Out of scope:
  - `PlayerCurrentStateDto` の即廃止
  - resolver / formatter / UI builder の一括全面置換
  - SNS / Trade モード仕様自体の見直し
  - 外部 API 契約の刷新
- User-confirmed constraints:
  - LLM 向け互換を優先する
  - 大規模な呼び出し変更は初手の非目標
  - app state 追加耐性を plan の中核成功条件に置く
- Reopen alignment if:
  - `property` 委譲では dataclass 初期化や immutability の制約により不自然さが大きいと判明した場合
  - `PlayerCurrentStateDto` が world query 以外の強い公開契約であり、sub DTO 内包が破壊的になりすぎる場合
  - 実際の依存調査で runtime より world/app の境界の方が曖昧で、3 分割案自体を再検討すべきと分かった場合

# Code Context

- Existing modules to extend
  - `src/ai_rpg_world/application/world/contracts/dtos.py`
  - `src/ai_rpg_world/application/world/services/player_current_state_builder.py`
  - `src/ai_rpg_world/application/world/services/player_runtime_context_builder.py`
  - `src/ai_rpg_world/application/llm/services/current_state_formatter.py`
  - `src/ai_rpg_world/application/llm/services/ui_context_builder.py`
  - `src/ai_rpg_world/application/llm/services/availability_resolvers.py`
  - `src/ai_rpg_world/application/llm/contracts/dtos.py`
- Existing exceptions, contracts, and test patterns to follow
  - `PlayerCurrentStateDto.__post_init__` の整合条件
  - `ToolAvailabilityContext = PlayerCurrentStateDto` という現契約
  - `PlayerRuntimeContextBuilder` による facade パターン
  - `tests/application/world/services/test_player_current_state_builder.py`
  - `tests/application/world/services/test_world_query_service.py`
  - `tests/application/llm/test_current_state_formatter.py`
  - `tests/application/llm/test_ui_context_builder.py`
  - `tests/application/llm/test_availability_resolvers.py`
- Integration points and known risks
  - `PlayerCurrentStateDto(...)` を直接生成するテストが多く、constructor 変更は広範囲に波及しうる
  - `ui_context_builder` は runtime target label 生成と強く結びついているため、runtime context の境界変更で破綻しやすい
  - SNS / Trade snapshot 類は app-local payload として肥大化しやすく、phase 1 で置き場を固定しないと再膨張しやすい

# Risks And Unknowns

- `property` 委譲だけでは dataclass の見通しがかえって悪くなり、compat レイヤが長生きしすぎる可能性がある。
- `available_trades` のように runtime と availability の両方で使う項目が、分類上は 1 箇所でも実装上 shortcut を多く要求する可能性がある。
- `visible_tile_map`、`sns_current_page_snapshot_json`、`trade_current_page_snapshot_json` のような重い payload を sub DTO 化しても、取得タイミングの見直しが要るかもしれない。
- formatter / UI builder / resolver のうち、どこが最初に sub DTO 直参照へ寄るべきかは、phase 1 後に再評価が必要。

# Phase 0 Deliverables

- Attribute inventory:
  - `PHASE0_ATTRIBUTE_INVENTORY.md` に `PlayerCurrentStateDto` の全属性と owner を記録する
- Classification rule:
  - `world` / `runtime` / `app_session` の判定ルールを固定する
- Shortcut policy:
  - Phase 1 の compat facade で優先維持する top-level shortcut 候補を列挙する
- Heavy payload policy:
  - `visible_tile_map`、SNS/Trade snapshot JSON を「optional だが owner は固定」として扱う
- Consumer map:
  - formatter / availability / UI builder が主にどの owner を読むかを整理する

# Phases

## Phase 0: 属性棚卸しと責務境界の固定

- Goal:
  - `PlayerCurrentStateDto` の全属性を責務ごとに分類し、後続実装の土台を固定する。
- Scope:
  - 全属性一覧の作成
  - `world` / `runtime` / `app_session` への分類
  - shortcut property が必要な属性候補の洗い出し
  - 重い payload / optional payload の扱い方針案
- Dependencies:
  - なし
- Parallelizable:
  - 低い
- Success definition:
  - すべての属性に所属先と暫定 owner が決まり、後続 phase の DTO 定義に迷いが残らない。
- Checkpoint:
  - `PLAN.md` と `PHASE0_ATTRIBUTE_INVENTORY.md` 上で属性棚卸し表と consumer map が完成している。
- Reopen alignment if:
  - 3 分割では割り切れない属性群が多く、別の境界が必要と判明した場合
- Notes:
  - この phase で「新しい app state は app_session へ」の原則を固定する。

## Phase 1: Sub DTO 導入と Compat Facade 化

- Goal:
  - `PlayerCurrentStateDto` を互換 facade として残しながら、内側に sub DTO を導入する。
- Scope:
  - `PlayerWorldStateDto` の導入
  - `PlayerRuntimeContextDto` の導入
  - `PlayerAppSessionStateDto` の導入
  - `PlayerCurrentStateDto` への sub DTO 内包
  - 既存トップレベル参照を維持する `property` 委譲
  - `__post_init__` と整合条件の移し替え
- Dependencies:
  - Phase 0
- Parallelizable:
  - 低い
- Success definition:
  - 既存呼び出し側から見た public 属性アクセスを大きく変えずに、内部構造だけを分割できる。
- Checkpoint:
  - DTO 単体テストで `active_game_app` / `is_sns_mode_active` / `is_trade_mode_active` など既存整合条件が維持される。
- Reopen alignment if:
  - dataclass 初期化シグネチャが不自然になり、互換 facade としての価値を損なう場合
- Notes:
  - 初手では resolver / formatter / UI builder の入力型は変えない。
  - 既存テストが top-level 属性を構築後に差し替えるため、Phase 1 の sub DTO は保存値よりも計算プロパティの方が安全な可能性が高い。

## Phase 2: Builder の責務分割

- Goal:
  - `PlayerCurrentStateBuilder` を、world / runtime / app session を組み立てる構造へ整理する。
- Scope:
  - world state 組み立てロジックの抽出
  - app session state 組み立てロジックの抽出
  - runtime context builder との境界見直し
  - compat facade への assemble 処理
- Dependencies:
  - Phase 1
- Parallelizable:
  - 中程度
- Success definition:
  - `PlayerCurrentStateBuilder` の責務が、最終 DTO 1 個の巨大組み立てではなく、複数コンテキストの compose として説明できる。
- Checkpoint:
  - `tests/application/world/services/test_player_current_state_builder.py` と関連 world query テストが通る設計になっている。
- Reopen alignment if:
  - runtime context builder 側に寄せるべき責務が多すぎて、phase 境界の引き直しが必要な場合
- Notes:
  - `PlayerRuntimeContextBuilder` を再利用し、重複抽出を避ける。
  - Phase 2 では `PlayerCurrentStateBuilder` の public return shape を変えず、private helper + `PlayerCurrentStateDto.from_components` に寄せて compose を明示する。

## Phase 3: Formatter / Availability / UI の依存整理

- Goal:
  - sub DTO 導入後の利用側を、安全な順で新境界へ寄せる。
- Scope:
  - `current_state_formatter` の参照棚卸し
  - `availability_resolvers` の参照棚卸し
  - `ui_context_builder` の参照棚卸し
  - どこまで sub DTO 直参照へ寄せるか、どこは compat property のままにするかを決定
- Dependencies:
  - Phase 2
- Parallelizable:
  - 中程度
- Success definition:
  - 利用側ごとに最終着地が定義され、互換レイヤを剥がす順序が決まる。
- Checkpoint:
  - formatter / availability / UI について、それぞれ「phase 4 で実装する変更点」が箇条書きで明文化される。
  - `PHASE3_CONSUMER_DEPENDENCY_PLAN.md` に consumer ごとの着地点と変更順序が記録されている。
- Reopen alignment if:
  - `ToolAvailabilityContext` を `PlayerCurrentStateDto` のまま維持する方が長期的にも自然と判明した場合
- Notes:
  - UI builder は runtime target label 契約が重いので、最後尾候補として扱う。
  - Phase 3 の結論として、入力型は維持しつつ内部だけ `world` / `runtime` / `app` alias に寄せる。

## Phase 4: 実装修正とテスト移行

- Goal:
  - phase 1-3 で固めた方針に沿って、実際の参照先とテストを更新する。
- Scope:
  - DTO / builder 実装
  - formatter / availability / UI builder の必要箇所更新
  - 直接 constructor を使うテストの修正
  - 互換レイヤの回帰テスト追加
- Dependencies:
  - Phase 3
- Parallelizable:
  - 中程度
- Success definition:
  - 既存テストの期待を壊さず、sub DTO 追加後も current state 生成と LLM 文脈生成が成立する。
- Checkpoint:
  - world / llm 関連テスト群が green になる。
- Reopen alignment if:
  - 直接 constructor を使うテストの更新量が想定より大きく、先に factory/fixture の整理が必要と判明した場合
- Notes:
  - 変更が広がる場合は、fixture 共通化を先に挟む選択肢を残す。
  - Phase 4 では public API を変えず、`dto.world_state` / `dto.runtime_context` / `dto.app_session_state` の local alias を内部参照へ広げる。

## Phase 5: Compat 縮小方針の固定

- Goal:
  - 互換レイヤをどこまで残し、どの順で縮小するかを決める。
- Scope:
  - deprecate 候補の洗い出し
  - top-level shortcut property の残置方針
  - 新規項目追加ルールの明文化
- Dependencies:
  - Phase 4
- Parallelizable:
  - 低い
- Success definition:
  - 今後の実装者が `PlayerCurrentStateDto` のトップレベルへ安易に属性追加しない運用ルールが定まる。
- Checkpoint:
  - feature 完了時の `SUMMARY.md` または follow-up note で追加ルールを参照できる。
- Reopen alignment if:
  - 実運用上、compat property を広く残す方が保守性が高いと判明した場合
- Notes:
  - この phase は実装修正と同時ではなく、出口戦略の明文化として扱う。

# Recommended Implementation Order

1. Phase 0 で属性棚卸しと境界を固定する
2. Phase 1 で compat facade を導入する
3. Phase 2 で builder を責務ごとに整理する
4. Phase 3 で利用側の着地点を決める
5. Phase 4 で実装修正とテスト移行を行う
6. Phase 5 で compat 縮小ルールを残す

# Branch Readiness

- Proposed branch: `feature/player-current-state-dto-refactoring`
- Branch creation is deferred until implementation starts.
- Preconditions before execution:
  - Phase 0 の属性棚卸し表 (`PHASE0_ATTRIBUTE_INVENTORY.md`) がある
  - phase 1 で導入する sub DTO 名と責務が固定されている
  - compat property に載せる代表属性が決まっている
