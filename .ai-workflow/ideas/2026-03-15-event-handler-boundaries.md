---
id: feature-event-handler-boundaries
title: Event Handler Boundaries
slug: event-handler-boundaries
status: idea
created_at: 2026-03-15
updated_at: 2026-03-15
source: brainstorm
branch: null
related_idea_file: null
---

# Goal

ドメインイベントとイベントハンドラの責務境界を整理し、このリポジトリで「即時整合性が必要な本体ロジック」と「後続反応として切り出せる処理」を見分けられる状態にする。最終的には、戦闘・スポーン/デスポーン・ショップ・クエスト周辺で、どの処理を集約/アプリケーションサービスへ戻し、どの処理を同期/非同期ハンドラとして残すかを決められるようにする。

# Problem

現在のイベント基盤は `is_synchronous=True/False` の二値で扱われており、`after_commit` 相当のフェーズがない。そのため「同一トランザクション内で失敗させるべき処理」と「コミット後に別トランザクションで反応すればよい処理」の整理がコードから読み取りづらい。

特に戦闘・モンスター死亡まわりでは、重要な状態変更がイベントハンドラ側に分散している。`HitBoxHitRecordedEvent` から `HitBoxDamageHandler` がダメージ適用を行い、`MonsterDiedEvent` から報酬付与・飢餓更新・マップ除去が同期ハンドラで実行されるため、「何が本体ロジックで、どこまでを同一トランザクションで保証したいのか」が曖昧になりやすい。

また、非同期扱いのハンドラは別トランザクションで処理されるが、Outbox や配信保証の仕組みはなく、`publish_pending_events()` 側では例外を握りつぶしている。結果として、非同期処理の再試行・監視・冪等性の責務が設計として明示されていない。

# Constraints

- DDD の観点で、集約の不変条件や即時整合性が必要な更新はイベント連鎖の奥に隠しすぎない。
- 既存の `AggregateRoot.add_event()` / `UnitOfWork.register_aggregate()` / `EventHandlerRegistry` パターンを尊重しつつ、段階的に改善できる案にする。
- まずは責務整理と改善方針の明文化が目的であり、この idea 段階では一気に Outbox 導入やメッセージブローカー導入を前提にしない。
- ChatGPT との会話に含まれるコード例はそのまま採用せず、このコードベースの実装実態を優先して評価する。

# Code Context

- イベント基盤: `src/ai_rpg_world/infrastructure/events/in_memory_event_publisher_with_uow.py`, `src/ai_rpg_world/infrastructure/unit_of_work/in_memory_unit_of_work.py`, `src/ai_rpg_world/infrastructure/events/event_handler_composition.py`
- 戦闘の代表例: `src/ai_rpg_world/infrastructure/events/combat_event_handler_registry.py`, `src/ai_rpg_world/application/world/handlers/hit_box_damage_handler.py`, `src/ai_rpg_world/application/world/handlers/combat_aggro_handler.py`
- モンスター死亡後処理: `src/ai_rpg_world/application/world/handlers/monster_death_reward_handler.py`, `src/ai_rpg_world/application/world/handlers/monster_died_map_removal_handler.py`
- 非同期の既存パターン: `src/ai_rpg_world/infrastructure/events/quest_event_handler_registry.py`, `src/ai_rpg_world/application/quest/handlers/quest_progress_handler.py`, `src/ai_rpg_world/application/shop/handlers/shop_event_handler.py`, `src/ai_rpg_world/infrastructure/events/observation_event_handler_registry.py`
- 既存パターンとして、クエスト進行やショップ ReadModel 更新は「イベントを別トランザクションで受けて更新する」構成がすでにある。これは result consistency を許容する read model / progression 系の候補として再利用できる。
- `ShopEventHandlerRegistry` や他の registry で `is_synchronous` を明示していない箇所が、設計意図どおりのフェーズになっているか。
- `MonsterDiedEvent` と `HitBoxHitRecordedEvent` にぶら下がる処理のうち、本当に同期で rollback 対象にすべきものはどこまでか。
- スポーン/デスポーン、スキル発動、ショップ購入のアプリケーションサービス側フローが、イベントを「事実通知」として使っているのか、「メイン処理の接着」として使っているのか。

# Open Questions

- 今回の改善対象をまずどの領域から着手するか。第一候補は戦闘/死亡処理だが、ショップやクエストまで同時に整理するかは切り分けが必要。
- このプロジェクトで許容したい非同期保証レベルはどこまでか。少なくとも「別トランザクションで後追い更新」はあるが、再試行・重複耐性・失敗監視をどこまで設計に含めるかは未確定。
- `after_commit` フェーズを新設したいのか、それとも「同期本体」と「別トランザクションの非同期」に二分したまま、本体ロジックの配置だけ見直したいのか。

# Promotion Criteria

- 対象領域ごとに、主要イベントを `in_transaction` / `after_commit` / `separate_transaction(async)` のどこへ置くべきかを表にできる。
- 少なくとも 1 つの高優先度シナリオ（戦闘か死亡後処理）で、「イベントに残す処理」と「明示的な本体フローへ戻す処理」の候補が言語化できる。
- 既存の非同期ハンドラで再利用できるパターンと、追加で必要な基盤変更（例: delivery phase の明示、例外方針の見直し、Outbox の要否）が整理できる。
- scope を 1 つの feature に収まる単位へ絞り、planning で phase 分割できる見通しが立つ。

# Detailed Findings

## Current combat/death flow

- `HitBoxAggregate.record_hit()` が `HitBoxHitRecordedEvent` を発行し、これを起点に `HitBoxDamageHandler` と `CombatAggroHandler` が同期ハンドラとして実行される。
- `HitBoxDamageHandler` は単なる通知処理ではなく、実効ステータス計算、回避判定結果の反映、`player.apply_damage()` / `monster.apply_damage()` の呼び出し、対象集約の保存まで担っている。
- `MonsterAggregate.apply_damage()` は `MonsterDamagedEvent` を発行し、死亡時はそのまま `_die()` を呼んで `MonsterDiedEvent` を追加する。つまり死亡判定自体は aggregate 内にあるが、死亡後の重要更新は `MonsterDiedEvent` 側へ流れている。
- `CombatEventHandlerRegistry` では `MonsterDiedEvent` に対して `MonsterDeathRewardHandler`、`MonsterDeathHungerHandler`、`MonsterDiedMapRemovalHandler` がすべて同期で登録されている。
- `QuestProgressHandler` と `ObservationEventHandler` は `MonsterDiedEvent` を別トランザクションで購読しており、同じイベント型に「同一トランザクションの本体寄り処理」と「結果整合でよい反応処理」が混在している。
- `MonsterBehaviorCoordinator`、`MonsterLifecycleSurvivalCoordinator`、`MovementStepExecutor` など複数のアプリケーションサービスが明示的に `unit_of_work.process_sync_events()` を呼んでいる。これはイベントが commit 後通知ではなく、アプリケーションフロー途中の処理段階として使われていることを示す。

## Main risks in current design

- `HitBoxHitRecordedEvent` が「事実通知」ではなく、ダメージ適用の実行トリガーとして使われているため、戦闘本体がイベント連鎖の奥に隠れやすい。
- `MonsterDiedEvent` にぶら下がる同期ハンドラのうち、報酬付与やマップ削除のような意味の異なる処理が同列に rollback 対象になっている。
- `ShopEventHandlerRegistry` のように `is_synchronous` を明示していない registry があり、デフォルト値に実行意味が埋め込まれている。
- `publish_pending_events()` や `AsyncEventPublisher.publish()` は例外を標準出力へ流すだけで、再試行・監視・DLQ 相当の責務がない。
- 現状の基盤は `in_transaction` と `separate_transaction(async)` の 2 相で、`after_commit` のような「コミット後だが呼び出し元スレッドで待つ」段階を表現できない。

# Combat And Death Routing Matrix

| Concern / step | Current trigger | Recommended phase | Notes |
| --- | --- | --- | --- |
| Hit registration (hitbox active, duplicate hit prevention) | `HitBoxAggregate.record_hit()` | `in_transaction` | 当たり判定の成立条件そのもの。aggregate または戦闘サービス側で明示的に見えるべき。 |
| Damage calculation | `HitBoxDamageHandler` | `in_transaction` | 戦闘本体。イベントハンドラに残すより、combat application service / domain service の明示フローへ寄せたい。 |
| HP update / evade update | `HitBoxDamageHandler` -> player/monster aggregate | `in_transaction` | 即時整合性が必要。現在でも同期処理だが、責務の見え方を改善したい。 |
| Death judgement | `MonsterAggregate.apply_damage()` | `in_transaction` | aggregate 内にあり自然。維持候補。 |
| Monster damaged / died event emission | aggregate events | `in_transaction` publish | 「事実の発生」は残してよい。後続処理の切り分けを明確にする。 |
| Aggro update for defender monster | `CombatAggroHandler` | `in_transaction` | 戦闘 AI の即時反応として妥当。明示フロー化するか、補助同期ハンドラとして残すかは planning で判断。 |
| Reward grant to killer | `MonsterDeathRewardHandler` | `in_transaction` 寄り | 現状は経験値・所持金・ルート付与を同時確定している。ゲーム仕様上「キル成立と同時に確定したい」なら同期維持候補。重いなら loot だけ分離余地あり。 |
| Remove dead monster from map | `MonsterDiedMapRemovalHandler` | `in_transaction` | ワールド整合性として即時に外したい処理。死亡の本体フローに近く、イベントハンドラより明示フロー側が読みやすい可能性が高い。 |
| Hunger decrease for killer monster prey logic | `MonsterDeathHungerHandler` | `in_transaction` または `after_commit` 候補 | 生態系ルールとして同 tick 反映したいなら同期。多少遅れてもよいなら `after_commit` 候補。優先度は報酬・マップ削除より低い。 |
| Quest progress | `QuestProgressHandler` | `separate_transaction(async)` | 既存どおり結果整合でよい。再試行方針と冪等性だけ強化したい。 |
| Observation / UI-facing narration | `ObservationEventHandler` | `separate_transaction(async)` | 典型的な結果整合。失敗で戦闘結果を巻き戻さない。 |
| Analytics / future external integrations | not formalized | `separate_transaction(async)` | 将来の Outbox 候補。 |

## Initial recommendation for combat/death

- 第 1 段階では、`HitBoxHitRecordedEvent` と `MonsterDiedEvent` を消さずに残しつつ、同期ハンドラの中で「本体」に近いものをアプリケーションサービスへ戻す。
- 最初の移動候補は `HitBoxDamageHandler` と `MonsterDiedMapRemovalHandler`。どちらも結果反応というより、戦闘/ワールド整合性の本体に見える。
- `CombatAggroHandler` は戦闘 AI の同 tick 反応として残す選択肢があるが、`in_transaction` の補助同期ハンドラとして意味を明示したい。
- `MonsterDeathRewardHandler` は仕様依存。報酬をキル成立条件に含めるなら `in_transaction` 維持、そうでなければ `after_commit` または async 分離の検討対象。
- `QuestProgressHandler` と `ObservationEventHandler` は separate transaction の代表例として残し、代わりに delivery policy を強化する。

# Event Infrastructure Direction

## Desired event phases

- `in_transaction`
- 同一 Unit of Work / rollback 対象。失敗したら元の操作も失敗させる。
- `after_commit`
- 元の state change は確定済みだが、同じリクエスト内で軽い後処理を行う。失敗しても rollback はしない。
- `separate_transaction_async`
- 別トランザクションで処理し、結果整合に任せる。再試行・冪等性・監視が前提。

## Direction for framework cleanup

- `EventPublisher.register_handler(..., is_synchronous: bool)` を段階的に `delivery_phase` ベースへ置き換える。少なくとも enum 化して意味を名前で表したい。
- registry 側で実行フェーズを必ず明示し、デフォルト引数に意味を埋め込まない。
- `InMemoryUnitOfWork.commit()` の処理を `collect -> dispatch_in_transaction -> commit state -> dispatch_after_commit -> dispatch_async` の概念に分けて読める形へ整理する。
- async 側は最低でも「失敗を握りつぶさない」「再試行可能な記録を残す」方針へ変える。最初は簡易な failure store / retry queue でもよい。
- 中長期では Outbox 導入余地を残すが、最初の feature では delivery phase の明示と失敗方針の統一を優先する。

## Usage guidelines draft

- 集約の不変条件、HP/死亡、ワールド上の存在有無のような成立条件は `in_transaction`。
- read model 更新、観測、クエスト進行、分析のような「成立後に反応するだけの処理」は `separate_transaction_async`。
- その中間で、「軽くてローカルだが rollback には巻き込みたくない処理」が出たときだけ `after_commit` を使う。
- 同じイベント型に複数フェーズのハンドラがあってよいが、各ハンドラの phase は固定し、実行時分岐で切り替えない。
- 同期ハンドラに本体ロジックを隠しすぎない。重要な処理は application service / domain service から見える一本道を優先する。
