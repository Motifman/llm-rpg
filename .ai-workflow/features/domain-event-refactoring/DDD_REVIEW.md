# Domain Event Refactoring - DDD 観点の評価と追加 Phase 議論

**作成日**: 2026-03-17
**目的**: feature 目的を振り返り、DDD ベストプラクティスに沿っているか評価し、追加 Phase の要否を議論する。

---

## 1. 目的の振り返り

### 1.1 元の Objective（PLAN.md）

> Sync/Async の使い分けを明確化し、トランザクション境界を DDD ベストプラクティスに合わせる。ガイドライン整備、全ハンドラレビュー、非同期二重 UoW 廃止、例外処理改善、`process_sync_events` 呼び出し統一、イベント収集 1 本化を段階的に実施する。

### 1.2 Success Criteria 達成状況

| 条件 | 状態 |
|------|------|
| 全ハンドラが Sync/Async 基準でレビューされ、必要なら修正済み | ✅ Phase 1 完了 |
| 非同期ハンドラの外側 UoW が廃止され、各ハンドラが自分で UoW を管理 | ✅ Phase 2 完了 |
| 非同期ハンドラの例外が `logger.exception` で記録され、握りつぶしをしない | ✅ Phase 2 完了 |
| `process_sync_events` の呼び出しが「意味的な単位で 1 回」に統一 | ✅ Phase 3 完了 |
| イベント収集が `add_events` 経由 1 本に統一 | ✅ Phase 4 完了 |
| Phase 5 の完了をもって feature 全体の完了 | 🔄 Phase 5.4 残り |
| 既存テストが全て通過 | ✅ 全テスト通過 |

---

## 2. DDD 観点の評価

### 2.1 ドメイン層の純粋性 ✅

- **ドメインイベント**: `domain/common/domain_event.py` の `BaseDomainEvent` はインフラに依存しない
- **イベント種別**: `domain/*/event/` 配下（map_events, trade_event, item_event 等）は純粋な value として定義
- **集約のイベント収集**: `AggregateRoot` が `add_event` / `get_events` / `clear_events` を持つ。ドメイン層内で完結
- **結論**: ドメイン層にリポジトリやインフラの依存はなく、DDD 原則を満たしている

### 2.2 層の責務分離 ✅

| 層 | イベント周りの責務 | 評価 |
|----|-------------------|------|
| Domain | イベントの定義、集約からの発行 | ✅ 純粋 |
| Application | ハンドラ（リポジトリ find/save、ドメイン調整） | ✅ ユースケース統合 |
| Infrastructure | EventPublisher, SyncEventDispatcher, UoW, レジストリ | ✅ 技術的詳細 |

### 2.3 同期／非同期の判定 ✅

- 整合性が同一 tx で必要 → sync（combat, map_interaction, gateway, conversation 等）
- ReadModel／通知／分析 → async（quest, trade, shop, sns, observation）
- 判定基準が `docs/domain_events_sync_async_rules.md` と event-handler-patterns スキルに文書化済み

### 2.4 トランザクション境界 ✅

- **同期ハンドラ**: 呼び出し元 UoW 内で `flush_sync_events` により同一 tx 実行
- **非同期ハンドラ**: 各ハンドラが `_execute_in_separate_transaction` で自前 UoW を create
- **二重 UoW 廃止**: Phase 2 で `_process_events_in_separate_transaction` の外側 UoW を削除済み

### 2.5 UoW とイベント処理の分離 ✅

- `SyncEventDispatcher` が `flush_sync_events` を担当
- `UnitOfWork` Protocol から `process_sync_events` を削除済み（Phase 5.3）
- UoW はトランザクション境界とイベント蓄積のみを担う

### 2.6 例外処理 ✅

- 同期: handle 内で try/except、想定内スキップは return、業務例外は raise、その他は SystemErrorException
- 非同期: `logger.exception` + raise（握りつぶし禁止）
- event-handler-patterns スキルに方針が明記

### 2.7 軽微な懸念（設計改善余地）

| 項目 | 内容 | 深刻度 |
|------|------|--------|
| SyncEventDispatcher の UoW 内部参照 | `_processed_sync_count`, `_pending_events` を直接参照。カプセル化の観点では `get_pending_events_since(index)` のような public API 経由が理想 | 低（InMemory のみで、他実装なし） |
| event-handler-patterns の古い記述 | 「process_sync_events」の記述が残存。Phase 5.4 で「flush_sync_events」に更新予定 | 中（ドキュメント不整合） |
| Gateway 等の docstring | 「process_sync_events により」等の記述が残る可能性 | 低 |

---

## 3. 追加 Phase の要否

### 3.1 必須: Phase 5.4 完了

Phase 5.4 は PLAN 上の feature 完了条件に含まれる。以下を実施する必要あり。

- [ ] event-handler-patterns スキルの「process_sync_events」→「flush_sync_events（SyncEventDispatcher）」に更新
- [ ] gateway_handler 等の docstring で「process_sync_events」→「flush_sync_events」に修正
- [ ] 全 FakeUow／モックの `process_sync_events` 残存チェック
- [ ] DI／ワイヤリングで SyncEventDispatcher が正しく注入されることを確認

**結論**: Phase 5.4 は実施すべき（ドキュメント・用語の整合性のため）。

### 3.2 任意: SyncEventDispatcher のカプセル化強化

**案**: UoW に `get_pending_events_since(processed_count: int)` と `advance_sync_processed_count(new_count: int)` を public で追加し、SyncEventDispatcher が内部属性に直接触れないようにする。

- **メリット**: カプセル化の向上、将来の他 UoW 実装時に互換しやすい
- **デメリット**: 現状 InMemory のみで、即時の実利は限定的
- **結論**: **追加 Phase としては不要**。将来 UoW の別実装を導入する際に検討でよい。

### 3.3 範囲外: ハンドラ内ビジネスロジックの見直し

- ハンドラが「リポジトリ find → ドメインオブジェクト操作 → save」を行っているかは、個別レビューの対象
- 本 feature の scope は「イベント配信とトランザクション境界の整理」であり、ハンドラ内ロジックのリファクタは含まない
- **結論**: 追加 Phase としては対象外。別 feature で検討可能。

---

## 4. 総合評価

| 観点 | 評価 |
|------|------|
| ドメイン層の純粋性 | ✅ 満たしている |
| 層の責務分離 | ✅ 満たしている |
| Sync/Async の適切な使い分け | ✅ 基準に沿っている |
| トランザクション境界 | ✅ 明確 |
| 例外処理 | ✅ 握りつぶしなし、再送出あり |
| UoW とイベント処理の分離 | ✅ 完了 |
| イベント収集 1 本化 | ✅ add_events 経由 |

**DDD ベストプラクティスに沿ったイベント処理が実装できている。**

---

## 5. 推奨アクション

1. **Phase 5.4 を実施**し、 feature を完了とする
2. **追加 Phase は設けない**（カプセル化強化は将来の別タスクとする）
3. 本評価内容を PROGRESS.md の Phase Journal に反映する
