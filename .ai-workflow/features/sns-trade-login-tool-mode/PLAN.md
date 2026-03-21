---
id: feature-sns-trade-login-tool-mode
title: SNS ツール拡充と SNS モード切替
slug: sns-trade-login-tool-mode
status: completed
created_at: 2026-03-21
updated_at: 2026-03-21
branch: feature/sns-trade-login-tool-mode
---

# Objective

LLM エージェントが SNS ドメインを既存 application 層の command/query に沿って過不足なく使えるようにしつつ、SNS を「ゲーム内アプリを開いた状態」として表現する。通常時は `sns_enter` のみが見え、SNS モード中だけ SNS・Trade・timeline 系ツールが出る構成を、既存 `PlayerCurrentStateDto` と tool provider/registry の流れに乗せて段階導入する。

# Success Criteria

- **SNS モード OFF** では、通常プレイツール + `sns_enter` だけが一覧に出る。`sns_*`（enter を除く）、`trade_*`、timeline 取得ツールは出ない。
- **SNS モード ON** では、SNS 投稿/反応系・Trade・timeline 系・`sns_logout` が一覧に出る。
- MVP の読み取り系ツールとして **ホームTL**、**自分の投稿一覧**、**特定ユーザーの投稿一覧** が利用できる。
- `application/social/contracts/commands.py` の既存コマンドについて、今回除外しないものはツール入口が揃う。
- `tests/application/llm/test_available_tools_provider.py`、`tests/application/llm/test_tool_definitions.py`、`tests/application/llm/test_tool_command_mapper.py`、関連 social service / wiring テストで表示切替と実行経路が固定される。

# Alignment Loop

- Initial phase proposal:
  - 状態とツール行列の固定 → モード別カタログ切替 → enter/logout と不足 command tool 追加 → timeline/query tool 追加 → wiring/test 固定
- User-confirmed success definition:
  - ログインは認証ではなく **SNS アプリ起動メタファ**。
  - 通常時は **ログイン用ツールだけ**見える。
  - MVP timeline は **ホームTL / 自分の投稿一覧 / 特定ユーザー投稿一覧**。
- User-confirmed phase ordering:
  - 先に **状態置き場と表示切替の基盤**を固め、その上で command/query ツールを追加する。
- Cost or scope tradeoffs discussed:
  - resolver だけでは「見えない」を満たせないため不採用。
  - 別コンテキスト新設は将来拡張には強いが、今回は配線変更コストが高いため採らない。
  - 専用 registry 差し替え（C）は将来的にあり得るが、今回は既存 registry/provider を活かす B が妥当。

# Scope Contract

- In scope:
  - `PlayerCurrentStateDto` を起点にした SNS モード状態の表現
  - モード別のツール登録集合切替
  - `sns_enter` / `sns_logout` 相当のモード遷移ツール
  - SNS 既存 command の不足ツール補完
  - MVP timeline 読み取りツールの追加
  - Trade を SNS モード必須へ寄せる
  - provider / mapper / wiring / tests の更新
- Out of scope:
  - 外部 OAuth や実認証
  - 初回 SNS ユーザー作成の必須化
  - Shop / Guild など他カテゴリのモード必須化
  - SNS ドメイン aggregate の大規模再設計
  - 人気投稿・検索・通知一覧・関係プロフィール一覧の全投入を MVP 必須にすること
- User-confirmed constraints:
  - DDD 境界を守り、ツールは application 層呼び出しに留める
  - `PlayerCurrentStateDto` 拡張を第一候補とする
  - カタログ戦略は B
  - 通常時は SNS 系の入口を 1 つに絞る
- Reopen alignment if:
  - SNS モード状態の取得元が既存 current state build 流れに自然に乗らない
  - timeline/read tool 数が多すぎて prompt/tool UX を大きく損ねる
  - 通常時にも一部 SNS/Trade ツールを見せたい要求へ変わる

# Code Context

- `.ai-workflow/features/sns-trade-login-tool-mode/STATE_AND_TOOL_MATRIX.md`
  - Phase 1 で固定した状態契約・ツール表示行列・command parity（実装の参照点）。
- `src/ai_rpg_world/application/world/contracts/dtos.py`
  - `PlayerCurrentStateDto` は availability 判定の事実上の single source。状態置き場の第一候補（Phase 2 で `is_sns_mode_active` を追加）。
- `src/ai_rpg_world/application/world/services/player_current_state_builder.py`
  - DTO を組み立てるので、SNS モード状態の供給点候補。
- `src/ai_rpg_world/application/llm/services/tool_catalog/__init__.py`
  - いまは `trade_enabled` / `sns_enabled` のカテゴリ一括登録。モード別集合切替の主戦場。
- `src/ai_rpg_world/application/llm/services/tool_catalog/sns.py`
  - 既存 SNS tool 定義。enter/logout、削除、プロフィール、timeline 追加候補。
- `src/ai_rpg_world/application/llm/services/tool_catalog/trade.py`
  - Trade を SNS モード必須へ寄せる際の露出制御対象。
- `src/ai_rpg_world/application/llm/services/availability_resolvers.py`
  - 現状 `SnsToolAvailabilityResolver` は `context is not None` のみ。resolver 単独でなく provider/registry と併せて使う。
- `src/ai_rpg_world/application/llm/services/available_tools_provider.py`
  - 最終的に一覧へ出すツールを決めるため、モード別の見せ方固定点。
- `src/ai_rpg_world/application/llm/services/executors/sns_executor.py`
  - 既存 SNS command 実行入口。不足ツール追加時の実装点。
- `src/ai_rpg_world/application/llm/services/executors/trade_executor.py`
  - Trade 側 command 実行入口。
- `src/ai_rpg_world/application/social/contracts/commands.py`
  - command parity の基準。
- `src/ai_rpg_world/application/social/services/post_query_service.py`
  - `get_home_timeline`, `get_user_timeline`, `search_posts_by_keyword`, `get_popular_posts` が存在。MVP は home/user を使う。
- `src/ai_rpg_world/application/social/services/user_query_service.py`
  - 自分/他人プロフィールと関係プロフィール一覧取得の既存 query がある。
- `src/ai_rpg_world/application/social/services/notification_query_service.py`
  - 通知 query の既存入口。今回は MVP 必須ではないが後続 phase 候補。
- `tests/application/llm/test_available_tools_provider.py`
  - モード別表示切替の主テスト追加先。
- `tests/application/llm/test_tool_definitions.py`
  - tool catalog の定義存在・カテゴリ整合の確認先。
- `tests/application/llm/test_tool_command_mapper.py`
  - enter/logout と新規 SNS command tool の実行確認先。

# Risks And Unknowns

- `R1`: SNS モード状態の取得元が曖昧なままだと builder へ仮配線が生まれる。
- `R2`: `register_default_tools()` がカテゴリ一括登録前提なので、B 案でも引数設計を雑にすると分岐が散らばる。
- `R3`: timeline / profile / notification を一気に入れると tool 数が膨らみ、prompt 体験が悪化する。
- `R4`: command parity を厳密にやると「読む手段がない command」を無理に tool 化しがちなので、MVP と follow-up の切り分けが必要。
- `R5`: player_id と sns user_id の 1:1 前提が壊れているデータケースがあると enter/logout 周りで破綻する。

# Phases

## Phase 1: 状態契約とツール行列の固定

- Goal:
  - SNS モードをどこで表現し、通常時/モード時に何を見せるかを code-ready に固定する。
- Scope:
  - `PlayerCurrentStateDto` に追加する状態項目名と意味を決める
  - enter/logout、SNS command、Trade、timeline read tool の一覧を matrix 化する
  - command parity の対象と、今回 intentionally defer する query/tool を明示する
  - tool 名と説明文の命名方針を決める
- Artifact:
  - [`STATE_AND_TOOL_MATRIX.md`](./STATE_AND_TOOL_MATRIX.md)（状態項目 `is_sns_mode_active`、表示行列、パリティ・defer、MVP timeline 3 種の想定ツール名）
- Dependencies:
  - なし
- Parallelizable:
  - 低
- Success definition:
  - 後続 phase が迷わない tool matrix と状態契約が artifact に残る
- Checkpoint:
  - `PLAN.md` と `IDEA.md` に一致した契約がある
- Reopen alignment if:
  - `PlayerCurrentStateDto` へ置くと責務逸脱が大きいと判明したとき
- Notes:
  - ここで `sns_enter` を通常時先頭に置く要件も固定する

## Phase 2: モード別カタログ切替の基盤化

- Goal:
  - 通常時と SNS モード時でツール一覧が本当に切り替わる基盤を作る。
- Scope:
  - `register_default_tools()` 周辺を、モード別の登録集合を扱える形へ再構成する
  - `DefaultAvailableToolsProvider` / resolver / registry の責務分担を決め、一覧非表示要件を固定する
  - Trade を SNS モード側集合へ移す
  - `test_available_tools_provider.py` と `test_tool_definitions.py` にモード別期待値を追加する
- Dependencies:
  - Phase 1
- Parallelizable:
  - 中
- Success definition:
  - SNS モード OFF/ON で出る tool 名がテストで固定される
  - 通常時は `sns_enter` のみ見える
- Checkpoint:
  - provider / catalog 系テスト通過
- Reopen alignment if:
  - 既存 registry 構造のままでは B 案を無理なく表現できないと判明したとき
- Notes:
  - resolver は補助的に使い、主要件は登録集合差で達成する

## Phase 3: SNS モード遷移ツールと不足 command tool の追加

- Goal:
  - 既存 SNS command の書き込み側ギャップを埋める。
- Scope:
  - `sns_enter` / `sns_logout` 相当の tool 定義と executor 入口を追加する
  - delete post / delete reply / update profile / notification read 系など、今回スコープに含める command tool を追加する
  - 必要なら argument resolver を拡張する
  - `test_tool_command_mapper.py` に成功・失敗ケースを追加する
- Dependencies:
  - Phase 2
- Parallelizable:
  - 中
- Success definition:
  - command parity 対象が mapper/executor/tool 定義まで通る
  - enter/logout がモード切替のトリガとして機能する
- Checkpoint:
  - tool command mapper と関連 social service テスト通過
- Reopen alignment if:
  - モード状態の更新責務が application service 新設なしでは不自然と判明したとき
- Notes:
  - DDD を守るため、モード切替自体も application 層ユースケースへ寄せる

## Phase 4: MVP timeline/query tool の追加

- Goal:
  - 読み取り側の MVP を成立させる。
- Scope:
  - ホームTL、自分の投稿一覧、特定ユーザー投稿一覧の tool を追加する
  - 必要な query service 呼び出しを executor / mapper / response へ接続する
  - 「自分」や対象ユーザー指定の argument 取り扱いを固定する
  - 追加 read tool が SNS モード ON でのみ見えることをテストする
- Dependencies:
  - Phase 2
- Parallelizable:
  - 中
- Success definition:
  - MVP timeline 3 種が使え、通常時には見えない
- Checkpoint:
  - query tool の定義・mapper・provider テスト通過
- Reopen alignment if:
  - timeline 出力形式が既存 LLM 応答 DTO では扱いづらいと判明したとき
- Notes:
  - popular/search/notification/profile list はここでは follow-up 候補として残してよい

## Phase 5: Wiring 統合と回帰テスト固定

- Goal:
  - feature 全体を wiring に接続し、ship-ready な回帰ラインを作る。
- Scope:
  - `application/llm/wiring/__init__.py` の依存条件と登録フラグを更新する
  - prompt builder / available tools provider の end-to-end 表示確認を追加する
  - Phase 1 で defer した項目を見直し、残課題を `SUMMARY` / `PROGRESS` へ明記する
- Dependencies:
  - Phase 3, Phase 4
- Parallelizable:
  - 低
- Success definition:
  - wiring からモード切替と新規 tool 群が利用できる
  - main のツール体験を壊さない回帰テストが揃う
- Checkpoint:
  - llm wiring / prompt builder / provider 系テスト通過
- Reopen alignment if:
  - 既存 prompt/tool 表示順が大きく壊れ、UX 調整が別 phase 相当になるとき
- Notes:
  - 残した non-MVP SNS read tool は follow-up として明文化する

# Review Standard

- No placeholder or temporary implementation
- DDD boundaries stay explicit
- Exceptions are handled deliberately
- Tests cover happy path and meaningful failure cases
- Existing strict test style is preserved

# Execution Deltas

- Change trigger:
  - command parity の対象追加、または MVP read tool の増減
- Scope delta:
  - 通知一覧、人気投稿、検索、関係プロフィール一覧を MVP に昇格する場合はここで記録
- User re-confirmation needed:
  - B から C へ切り替えるとき
  - `PlayerCurrentStateDto` 以外へ状態置き場を変えるとき
  - SNS モード必須カテゴリを Shop/Guild 等へ広げるとき

# Plan Revision Gate

- Revise future phases when:
  - 状態取得元やモード切替基盤の設計変更で後続 phase の前提が崩れたとき
  - MVP 読み取り系ツールのセットが変わったとき
- Keep future phases unchanged when:
  - 既存 phase 内の命名・テスト配置・小さな helper 分割だけで収まるとき
- Ask user before editing future phases or adding a new phase:
  - Phase 4 以降に通知/検索/人気投稿/プロフィール一覧を必須追加するとき
  - C 案へ昇格させるとき
- Plan-change commit needed when:
  - 成功条件、phase 順序、state placement、catalog strategy が変わるとき

# Change Log

- 2026-03-21: idea artifact を feature 化し、`PlayerCurrentStateDto` 拡張 + B 案 + MVP timeline 3 種で初回 plan を作成
- 2026-03-21: Phase 1 完了 — `STATE_AND_TOOL_MATRIX.md` を追加し、`IDEA.md` と整合
- 2026-03-21: Phase 2 完了 — `is_sns_mode_active`、`sns_enter`、SNS/Trade のモード連動 resolver、`register_default_tools` で Trade は sns と同時登録のみ
- 2026-03-21: Phase 3 完了 — `SnsModeSessionService`、`sns_enter`/`sns_logout` 実行経路、削除・プロフィール更新・通知既読ツール、`create_llm_agent_wiring` の `sns_mode_session` / `notification_command_service` / `LlmAgentWiringResult.sns_mode_session`
- 2026-03-21: Phase 4 完了 — `sns_home_timeline` / `sns_list_my_posts` / `sns_list_user_posts`、`PostQueryService` 接続、`post_query_service` による wiring・`sns_enabled` 拡張、provider / mapper / tool_definitions テスト
- 2026-03-21: Phase 5 完了 — wiring モジュール doc に SNS セッション同一インスタンス契約と `post_query_service` を追記、`world_query_wiring` の `sns_mode_session` 説明を補強、`test_sns_mode_wiring_e2e.py` で `create_llm_agent_wiring` → `DefaultPromptBuilder.build` のツール一覧をモード別に回帰固定
