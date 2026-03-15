---
id: feature-domain-event-refactoring
title: Domain Event Refactoring
slug: domain-event-refactoring
status: idea
created_at: 2026-03-16
updated_at: 2026-03-16
source: brainstorm
branch: null
related_idea_file: null
---

# Goal

ドメインイベント関連のリファクタリングにより、以下を達成する：

1. **Sync/Async の使い分けを明確化**: ガイドライン整備と全ハンドラのレビュー・必要に応じた修正
2. **トランザクション境界の適正化**: UoW とイベント処理の責務分離、DDD 的に妥当な実装へ寄せる

ユーザー価値として、将来の拡張・デバッグがしやすく、一貫したルールに従ったコードベースを得る。

# Success Signals

- 全ハンドラが Sync/Async の基準でレビューされ、誤分類があれば修正済み
- Sync/Async とトランザクション境界のルールが文書化され、新規ハンドラはそれに従う
- 非同期ハンドラの二重 UoW 問題が解消されている
- 非同期ハンドラの例外が適切に扱われ（握りつぶしをやめる）、監視・デバッグが可能
- `process_sync_events` の呼び出しタイミングが「意味的な単位」で一貫している

# Non-Goals

- イベント駆動アーキテクチャ全体の見直しはしない
- 非同期キュー・リトライ機構の新規導入は今回のスコープ外（将来的な検討は可）
- 実 DB を使った本番インフラへの影響は最小限に留める

# Problem

**現状の課題**

1. **Sync/Async の選択根拠が不明**: 一部レジストリは `is_synchronous` を未指定（デフォルト async）のまま
2. **`process_sync_events` の呼び出し粒度が混在**: モンスターごと / 1 行動 / 1 ステップなど、サービスごとにばらつき
3. **UoW がイベント処理を抱え込みすぎ**: トランザクション管理以外に、イベント収集・同期/非同期処理まで担当
4. **非同期ハンドラの二重 UoW**: 外側の `separate_uow` とハンドラ内の UoW が重複し、責務が曖昧
5. **非同期ハンドラの例外握りつぶし**: `print()` のみで失敗をログに残さず、監視・リトライが困難
6. **イベント収集経路が二本立て**: `register_aggregate` と `add_events` が混在し、ルールが文書化されていない

# Constraints

- DDD 原則（ドメイン層はリポジトリに依存しない、アプリケーション層で UoW とリポジトリを調整）を維持
- 既存の event-handler-patterns スキル、InMemoryEventPublisherWithUow の基本動作を尊重
- テストの回帰を避け、既存の統合テストが通ることを担保
- 段階的移行を許容（Big Bang は避ける）

# Code Context

**関連モジュール**

- `infrastructure/events/`: EventPublisher, registries, EventHandlerComposition
- `infrastructure/unit_of_work/in_memory_unit_of_work.py`: process_sync_events, _process_events_in_separate_transaction
- `application/world/services/`: MonsterBehaviorCoordinator, MonsterLifecycleSurvivalCoordinator, MovementStepExecutor, MonsterSpawnSlotService
- `application/trade/handlers/`, `application/observation/handlers/`: 非同期ハンドラ（UnitOfWorkFactory を保持）
- `.cursor/skills/event-handler-patterns/SKILL.md`: 既存パターン定義

**イベント収集経路**

- 経路 A: `register_aggregate` → `_collect_events_from_aggregates`（集約の get_events）
- 経路 B: `event_publisher.publish` / `publish_all` → `add_events`

**process_sync_events 呼び出し箇所**

- `InMemoryUnitOfWork.commit()` 内
- MonsterLifecycleSurvivalCoordinator（starve / die の各モンスターごと）
- MonsterBehaviorCoordinator（1 モンスター行動後）
- MovementStepExecutor（1 ステップ後）
- MonsterSpawnSlotService（スポーン後）

# Open Questions

- QuestProgressHandler を async に寄せる場合、既存の「GatewayTriggeredEvent を quest も購読」という設計との整合性
- イベント収集を 1 本化する際、全 Repository の `register_aggregate` 置き換えの影響範囲
- 非同期ディスパッチャで「1 イベント 1 トランザクション」にする場合のパフォーマンス影響

# Decision Snapshot

**Proposal**

推奨される選択肢に沿ってリファクタリングを実施する：

1. UoW の責務をトランザクション管理に限定（長期的には process_sync_events を UoW から外す）
2. `process_sync_events` の呼び出しを「意味的な単位で 1 回」に統一（パターンB）
3. 非同期ハンドラの外側 UoW を廃止し、各ハンドラが自分で UoW を管理
4. 非同期ハンドラの例外握りつぶしをやめ、ログ＋再 raise または失敗リスト返却
5. イベント収集経路を 1 本化（すべて `add_events` 経由、Repository で save 時に add_events を呼ぶ）
6. Sync/Async のガイドライン化と全ハンドラのレビュー・必要に応じた修正

**Options considered**

- イベント収集: 2 経路維持 vs 1 本化 → **1 本化**（実装可能で責務が明確）
- 同期ハンドラの「同一 tx 必須」vs「別 tx でもよい」→ **2 分類で十分**。別 tx でもよいものは async に寄せる
- process_sync_events 呼び出し: 各 save 直後 vs 意味的単位の終わり → **意味的単位の終わり**（パターンB）

**Selected option**

- 段階的移行（Phase 1〜4）を採用
- Phase 1: ガイドライン整備 + 全ハンドラ Sync/Async レビュー
- Phase 2: 非同期の外側 UoW 廃止 + 例外握りつぶし廃止
- Phase 3: process_sync_events 呼び出しタイミングの統一
- Phase 4: UoW とイベント処理の完全分離（任意・長期）

**Why this option now**

- DDD 的なベストプラクティスに沿いつつ、既存アーキテクチャを大きく壊さない範囲で進められる
- ユーザーが「ガイドラインとトランザクション境界の両方」を望み、「アーキテクチャ全体の見直しはしない」と明示

# Alignment Notes

**Initial interpretation**

- Sync/Async と UoW の使い分けが不明確で、トランザクション境界を改めて見直したい

**User-confirmed intent**

- ガイドライン整備とトランザクション境界の両方を行う
- 全ハンドラを Sync/Async 基準でレビューし、必要なら修正
- アーキテクチャの全体的な見直しはしない
- UoW について DDD 的に違和感がある部分を挙げてほしい（認識合わせ）

**Cost or complexity concerns raised during discussion**

- UoW とイベント処理の完全分離は段階的・長期的に
- イベント収集 1 本化は Repository の変更が必要だが、実装可能

**Assumptions**

- 同一 tx で find が必要なハンドラは sync、それ以外は async という基準で十分
- QuestProgressHandler は「別 tx でもよい」に該当し、async 寄せを検討対象
- 非同期ハンドラの「外側 UoW」廃止後も、各ハンドラが UnitOfWorkFactory で自分で tx を持つ現状の設計は維持

**Reopen alignment if**

- イベント収集 1 本化で Repository の変更が想定より大きいことが判明した
- 「1 イベント 1 トランザクション」でパフォーマンス問題が顕在化した
- Quest や Trade など、ReadModel 更新の sync/async を再考する必要が出た
- Phase 4（UoW 完全分離）に着手する際、設計の見直しが必要になった

# Promotion Criteria

- Phase 1（ガイドライン + 全ハンドラレビュー）の対象ハンドラ一覧が確定している
- Sync/Async ガイドラインが event-handler-patterns スキルまたは docs に反映されている
- Phase 2 の具体的な変更対象ファイル（InMemoryUnitOfWork, _process_events_in_separate_transaction 等）が特定されている
- flow-plan での feature 化・phase 分割の準備が整っている
