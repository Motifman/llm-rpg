---
id: feature-sns-trade-login-tool-mode
title: SNS ツール拡充と SNS モード切替
slug: sns-trade-login-tool-mode
status: in_progress
created_at: 2026-03-21
updated_at: 2026-03-21
source: flow-plan
branch: codex/sns-trade-login-tool-mode
related_idea_file: .ai-workflow/ideas/2026-03-21-sns-trade-login-tool-mode.md
---

# Goal

- LLM エージェントが **SNS ドメインの能力をツール経由で漏れなく使える**ようにし、application 層の **コマンド／クエリで既にある操作**とツール定義のギャップを埋める。
- **「ログイン」は Web サービスの認証ではない。** ゲーム内で **SNS アプリを開いた／閉じた** に相当する **SNS 専用状態（SNS モード）への遷移**として表現する。
- **SNS モード ON** の間は SNS・Trade・タイムライン系ツールが使え、**ログアウト**で通常プレイのツールセットに戻る。通常時のツール一覧では **SNS モードに入る操作を先頭に見せる**。

# Success Signals

- `application/social/contracts/commands.py` にある SNS 系コマンドのうち、意図的に除外しない限り **対応する LLM ツールまたは読み取り経路**が説明できる。
- **SNS モード OFF** では `sns_*`（モード遷移用を除く）・`trade_*`・タイムライン系ツールが **一覧に出ない**。
- **SNS モード ON** では上記が利用可能になり、**ログアウト**で通常プレイ側へ戻る。
- MVP の読み取り系ツールとして **ホームTL（フォロー中のみ）**、**自分の投稿一覧**、**特定ユーザーの投稿一覧** が使える。

# Non-Goals

- 外部 OAuth・パスワード認証など **実アカウント認証**は扱わない。
- **プレイヤーと SNS の初回紐付け／ユーザー作成**をこの feature の必須フローにしない。
- ドメインモデルの大規模再設計（SNS 集約の全面見直し）は別 idea に切る。
- Shop・ギルド等を SNS モード必須に広げることは今回のスコープ外。

# Problem

1. **ツールとコマンド／クエリの非対称**
   - 現状の SNS ツールは投稿・リプライ・いいね・フォロー系・ブロック系までで、削除・プロフィール更新・通知既読などに対応していない。
   - Query service にホームTLやユーザーTLなどがある一方で、LLM から読む専用ツールが未整備。
2. **SNS 利用可否がモードと結びついていない**
   - `SnsToolAvailabilityResolver` は `context is not None` のみ。
   - Trade も在庫や取引有無で出し分けるだけで、**SNS アプリ起動状態**を見ていない。
3. **要件は「拒否」ではなく「見えない」**
   - resolver で実行拒否するだけでは、ツール一覧から消したいという要求を満たせない。

# Constraints

- DDD: ツールは **アプリケーション層のユースケース呼び出し**に留め、SNS モード自体をドメインの大規模概念にしない。
- 既存パターン: `tool_catalog/*`、`tool_constants`、`sns_executor` / `trade_executor`、`register_default_tools`、`DefaultAvailableToolsProvider`、`PlayerCurrentStateDto` を起点に拡張する。
- モード状態の第一候補は **`PlayerCurrentStateDto` 拡張**。別コンテキスト新設は今回は採らない。
- カタログ戦略は **B: モード別に登録集合を切り替える** を前提に plan 化する。

# Code Context

- SNS ツール定義: `src/ai_rpg_world/application/llm/services/tool_catalog/sns.py`
- Trade ツール定義: `src/ai_rpg_world/application/llm/services/tool_catalog/trade.py`
- 利用可否: `src/ai_rpg_world/application/llm/services/availability_resolvers.py`
- ツール登録: `src/ai_rpg_world/application/llm/services/tool_catalog/__init__.py`
- 利用可能一覧: `src/ai_rpg_world/application/llm/services/available_tools_provider.py`
- wiring: `src/ai_rpg_world/application/llm/wiring/__init__.py`
- 現在状態 DTO: `src/ai_rpg_world/application/world/contracts/dtos.py`
- 現在状態組み立て: `src/ai_rpg_world/application/world/services/player_current_state_builder.py`
- SNS command/query: `src/ai_rpg_world/application/social/contracts/commands.py`, `src/ai_rpg_world/application/social/services/post_query_service.py`, `src/ai_rpg_world/application/social/services/user_query_service.py`, `src/ai_rpg_world/application/social/services/notification_query_service.py`

# Open Questions

- プロフィール一覧、通知一覧、人気投稿/検索を MVP に含めるかは phase 中に再確認する。
- SNS モード状態をどこから復元するか（ワールド状態由来か、プレイヤープロフィール由来か、既存 runtime 文脈の合成か）は実装調査が必要。

# Decision Snapshot

- Proposal:
  - `PlayerCurrentStateDto` に SNS モード状態を追加し、**通常プレイ用**と **SNS モード用**のツール集合を切り替える。
  - SNS モード OFF では **`sns_enter` 相当のツールのみ**を見せ、SNS モード ON で `sns_*` / `trade_*` / timeline 系 / `sns_logout` を出す。
  - 不足している command/query への対応ツールを段階的に追加する。
- Options considered:
  - A: resolver だけで実行拒否する
  - B: 既存 registry/provider を活かしつつ、モード別に登録集合を切り替える
  - C: 専用 registry 差し替え層を作る
- Selected option:
  - **B**
- Why this option now:
  - 「一覧に出ない」が要件の中核であり、既存 `PlayerCurrentStateDto` + provider/registry の流れにも最も素直に乗るため。

# Alignment Notes

- Initial interpretation:
  - ログインは認証ではなく **SNS アプリを開くメタファ**。
- User-confirmed intent:
  - MVP timeline は **ホームTL**、**自分の投稿一覧**、**特定ユーザーの投稿一覧**。
  - カタログ戦略は **B**。
  - 状態置き場は **`PlayerCurrentStateDto` 拡張**を採る。
- Cost or complexity concerns raised during discussion:
  - resolver だけでは要件未達。provider/registry/wiring まで触る必要がある。
  - timeline や補助 read tool を増やしすぎると prompt/tool 数が膨らむ。
- Assumptions:
  - プレイヤーとゲーム内 SNS ユーザーは既に紐づいている。
  - Trade は SNS モードと同じ理由でモード必須にする。
- Reopen alignment if:
  - DTO 拡張ではなく独立セッション文脈が必要なほどモード種別が増えると判明した場合。
  - 「見えない」要件を緩めて executor 側拒否でよい、という再合意が生じた場合。

# Phase 1: 状態契約とツール行列（固定済み）

詳細は同一 feature 内の [`STATE_AND_TOOL_MATRIX.md`](./STATE_AND_TOOL_MATRIX.md) を正とする。

- **状態項目**: `PlayerCurrentStateDto.is_sns_mode_active: bool`（ゲーム内 SNS アプリを開いているか）
- **表示**: OFF 時は SNS 系は `sns_enter` のみ（先頭付近）、ON 時は SNS / Trade / timeline MVP / `sns_logout`
- **Command parity**: `commands.py` について Phase 3・4 で埋める対象と defer を表で固定済み

# Promotion Criteria

- [x] SNS モード状態の第一候補を `PlayerCurrentStateDto` に置くと決まっている
- [x] モード別カタログ戦略を B で進めると決まっている
- [x] MVP timeline としてホームTL / 自分の投稿一覧 / 特定ユーザー投稿一覧が決まっている
