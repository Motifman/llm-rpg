# Stage 1 — dispatch 意味論の 3 相分解と契約化 (codex 敵対的レビュー反映)

> 状態: **改訂版**。codex レビュー (2026-07-20) の CRITICAL/HIGH/MEDIUM/LOW を反映。
> 親計画: [domain_event_dispatch_refactor_plan.md](./domain_event_dispatch_refactor_plan.md)
> 前提: [Stage 0a 棚卸し](./domain_event_dispatch_stage0a_inventory.md) /
> Stage 0b 特性化テスト (PR #747)。
> **この段はプロダクトコードを変更しない。** 目標の配信契約を明文化・型化し、
> Stage 2 (`DomainEventCollector` 導入) が実装する仕様を確定する。

## 0. Stage 1 の狙いと「やらないこと」

codex の指摘: 2 つの publisher は同名 port でも意味論が別物であり、port を単純統一
すると壊れる。だから **port 統一より先に相の契約を確定する**。

**重要な方針転換 (codex CRITICAL 反映)**: この契約は「Pipeline の現状 (= 全 side
handler の例外を握る) を正当化する文書」ではない。現状の危険な握りを**相分解で
正す**文書である。特に load-bearing な同期副作用の失敗を握ってはいけない。

- やること: dispatch を相に分解し、各相の (実行タイミング / 例外方針 / 順序 /
  冪等性) を明文化し、目標インタフェースの型を提示する。
- やらないこと: publisher の実装統合、収集経路の変更、emission サイトの書き換え
  (それぞれ Stage 2 以降)。`UseItemService` (U1/U2) は親計画で射程外 = 本計画で扱わない。

## 1. 現状 2 regime の事実 (行番号付き)

### regime P: `PipelineEventPublisher` (本番 spot_graph runtime)
`application/world_runtime/pipeline_event_publisher.py`

- `register_handler` (55-70): **`is_synchronous` を無視**。`(event_type, handler)` を
  1 本の `_side_handlers` list に登録順で積む。sync/async の区別なし。
- `publish` / `publish_all` / `publish_async_events` (72-81): **3 つとも同一の
  `_dispatch` をイベント単位で呼ぶだけ**。名前が async でも同期実行。
- `_dispatch` (83-124):
  1. `_side_handlers` を isinstance フィルタして**同期実行**。**各 handler の例外は
     `logger.exception` で握って継続** (93-103)。← この「全握り」が CRITICAL の対象。
  2. `_obs_pipeline.run(event)` (103) → items があれば `appender.append` +
     `scheduler.maybe_schedule` (120-124)。**この観測経路は try で囲われていない**
     = 例外は呼び出し元へ伝播する。
- **トランザクションゲートなし。dedup なし。**

### regime U: `InMemoryEventPublisherWithUow` (テスト / 別ランタイム)
`infrastructure/events/in_memory_event_publisher_with_uow.py`

- `register_handler` (45-50): `is_synchronous` で `_sync_handlers` /
  `_async_handlers` の **dict[type, list] に振り分け**。
- `publish` / `publish_all` (52-68): **transaction 内でないと `RuntimeError`**。
  handler は呼ばず `uow.add_events` で **pending へ遅延**するだけ。
- `publish_sync_events` (124-136): `_sync_handlers` を**即時実行**、**例外は伝播**
  (「トランザクション失敗のため」)。`_published_events` に object 同一性/等価性 dedup。
- `publish_async_events` (82-96): `_async_handlers` からタスク化し transport/executor/
  inline で実行。object 同一性/等価性 dedup (73-79)。inline 時**例外は伝播**。
- `TransactionalScope.__exit__` (`transactional_scope.py:49-62`): commit 成功後に
  `get_committed_events → publish_async_events → clear_committed_events`。
  = **async handler は post-commit**。

### 決定的な非対称 (codex HIGH の実体)

| 観点 | regime P (本番) | regime U (テスト/別) |
|---|---|---|
| publish の意味 | 即時 dispatch (副作用+観測) | pending へ遅延 (tx 内限定) |
| tx ゲート | なし (tx 外でも動く) | tx 外で `RuntimeError` |
| sync/async 区別 | なし (全部同期) | dict 振り分け + post-commit |
| 相① 例外 | **全握り (← 要修正)** | 伝播 (tx 失敗) |
| dedup | なし | object 同一性/等価性 |
| 真の post-commit 非同期 | **存在しない** (`publish_async_events` == `publish`) | `TransactionalScope` が担う |

**本番 spot_graph runtime では「相」は実在しない**。全イベントが各 emission
サイトで `_dispatch` の 2 ステップ (side handler 同期 → 観測) として即時実行され、
真の post-commit 非同期は畳まれている。emission は tick stage (tick UoW 内) と
LLM ツール (UoW 外) の両方から起きるが、regime P が tx 非依存だから両方動く。

**ただし「2 ステップ」には例外が 2 つある (codex MEDIUM)**:
1. **direct append の観測 side handler**: `PlayerRevivedPostHocObservationHandler` は
   `ObservationPipeline` を通さず `observation_appender.append` を**直接**呼ぶ
   (`player_revived_post_hoc_observation_handler.py:72-95`)。= 第 2 の観測経路が
   side handler 内にある。
2. **nested publish**: `ConsumableEffectHandler` は side handler 内でさらに
   `event_publisher.publish_all` する (`consumable_effect_handler.py:81-90`)。
   = 相① の中で別イベントの相①/相② が発火する (ネスト dispatch)。

→ 「相」は**目標の抽象**であり、現状を写像すると相② は eager、かつ上記ネストが
ある。Stage 2 実装者が落とさないよう、以下の相体系は direct-append と nested を
明示的に含める。

## 2. dispatch 相の契約 (目標セマンティクス)

codex CRITICAL 反映: 旧「相①」を **副作用の致命度で 3 つに分割**する。

### 相①a CRITICAL_SYNC_SIDE_EFFECT — 失敗は伝播、成功観測を出さない
- **対象** (失敗時に `SystemErrorException` を投げる設計の handler):
  - `PlayerDownedOutcomeHandler` (grace 登録。`player_downed_outcome_handler.py:59-71`)
  - `PlayerRevivedOutcomeHandler` (grace 解除。`player_revived_outcome_handler.py:33-49`)
  - `ConsumableEffectHandler` (HP/MP/need 反映。`consumable_effect_handler.py:55-65`)
- **タイミング契約**: 発行オペレーションが**戻る前**に完了。`PlayerDownedEvent` は
  同 tick の death_grace_stage が走る前に grace 登録完了 (Stage 0b で固定)。
- **例外方針 (最重要)**: **失敗は伝播し、operation/tick を失敗扱いにする。
  相②(観測)へ進まない。LLM に成功観測を出してはいけない。** 現状 Pipeline の
  「握って observation 継続」は**目標契約にしない**。握るとゲーム状態と LLM 観測が
  矛盾し (倒れた観測は出るが grace 未登録 → 死亡猶予モデル崩壊 / 復帰観測は出るが
  cancel 失敗 → 後続 tick で DEAD / 効果適用済みと返るが HP 不変)、実験データが壊れる。
- **順序契約**: 複数あれば登録順。
- **冪等性**: operation-local, event_id ベース (D2)。

### 相①b BEST_EFFORT_SIDE_EFFECT — 失敗は握るが warning/trace に必ず出す
- **対象**: `PlayerDownedStateCollapseEvidenceHandler`、`SpotArrivalEncounterHandler`
  (`spot_arrival_encounter_handler.py:76-83` が自ら握る)、encounter familiarity、
  補助 memory など、失敗してもゲーム状態の整合を壊さない副作用。
- **例外方針**: 握って継続。ただし **warning/trace に必ず残す** (静かな失敗にしない)。
- **順序契約**: `SpotArrivalEncounterHandler` は best-effort だが、**post-tick hook
  内で heartbeat/llm_turn_trigger より前** という順序制約あり (graph_event_flusher で
  到着 event → encounter memory 更新 → そのターンの prompt に反映。codex MEDIUM A4)。

### 相①c SYNC_OBSERVATION_SIDE_EFFECT — 相① 内で直接 observation append する side handler
- **対象**: `PlayerRevivedPostHocObservationHandler`
  (`player_revived_post_hoc_observation_handler.py:72-95`、direct `appender.append`)。
- **タイミング/順序契約**: `PlayerRevivedOutcomeHandler` (相①a cancel) より**先に
  登録・先に実行** (`world_runtime.py:3831-3844`、handler コメント 17-20 が順序依存を明記)。
  cancel 前に `grace_timer.downed_at_tick` を読む必要があるため load-bearing。
- **例外方針**: 本人向け復帰観測なので best-effort 寄りだが、順序が壊れると宛先/内容が
  変わる。相② の通常観測 batch に**混ぜてはいけない** (ObservationPipeline 経由ではない)。

### 相② OBSERVE_AND_SCHEDULE — 後置可 (通常観測経路)
- **対象**: 上記 side handler を経ないほぼ全イベント。`ObservationPipeline.run` →
  `ObservationAppender.append` → `ObservationTurnScheduler.maybe_schedule`。
  `schedules_turn` は formatter が `ObservationOutput` で決める。
- **タイミング契約**: 同一イベントの相① の後。post-tick では
  `graph_event_flusher → heartbeat → llm_turn_trigger` (Stage 0b で固定)。
- **例外方針 (事実として固定、codex HIGH D3 + LOW 反映)**:
  - tick stage 内の観測例外は**伝播して tick を失敗させる**。
    **ただし状態の rollback は保証しない** (sim の `InMemoryUnitOfWork()` は data_store
    非共有 `world_runtime.py:3632`、rollback は data_store+snapshot がある時のみ復元
    `in_memory_unit_of_work.py:54-56,109-116`)。save 済み状態は戻らない可能性が高い。
  - post-tick hook は hook 単位で catch し集約 (`_run_post_tick_hooks`)。
  - 「境界 isolation で 1 観測失敗を全 tick に波及させない」への変更は**挙動変更なので
    別 PR**。Stage 1 契約は現状の「伝播・rollback 非保証」を事実として固定する。
- **ネスト (codex HIGH C8)**: `ConsumableUsedEvent` の相①a handler
  (`ConsumableEffectHandler`) が `PlayerHpHealedEvent` 等 (C8) を publish_all するため、
  C8 の相② 観測は **B3 の相② より前** (相①a 内ネスト) に出る。Stage 2 で単純に
  「B3 の相① 後に C8 を同列の相② として後置」すると観測順が変わる。順序は Stage 0b/2 で固定。

### 相③ ASYNC_POST_COMMIT
- **対象**: spot_graph には**実在しない** (regime P では相① に畳まれる)。
- **判断 (codex D4)**: spot_graph 一元化では相③ を**新設しない**。eager を保つ
  (post-commit 化は挙動変更が大きすぎる)。将来 SQLite 統合時の余地だけ契約に残す。

## 3. 現状から契約への写像表 (codex D5 反映)

| サイト (棚卸し ID) | イベント | 契約上の相 | 備考 |
|---|---|---|---|
| A1/A2/A3/B2/C1 | PlayerDownedEvent | **①a** + ①b(evidence) + ② | grace 登録が①a。evidence は①b |
| B5 | PlayerRevivedEvent | **①c**(post-hoc direct append) + **①a**(cancel) + ② | 登録順 load-bearing: ①c → ①a |
| B3/U2 | ConsumableUsedEvent | **①a**(効果適用) + ② | ①a 内で C8 を nested publish |
| C8 | PlayerHpHealedEvent 等 | **②(①a 内ネスト発火)** | 発火は B3 の①a 内。観測順を固定要 |
| A4 | EntityEnteredSpotEvent | **①b**(encounter) + ② | post-tick で heartbeat/llm 前の順序制約 |
| A4 | graph 系その他 | ② | |
| A5 | TimeOfDayChangedEvent | ② | 例外握り (callback) |
| B1/B4/C2/C3/C4/C5/C6/C7/C9 | 各種 | ② | 相① 副作用なし |
| A6 | 初回 spawn EntityEntered | 契約外 (非 publish、encounter 直行を保つ) | |
| U1/U2 | (UseItemService) | **本計画の射程外** | 別計画の入力。Stage 5 に含めない |

## 4. 目標インタフェースの型 (Stage 2 で実装する仕様)

**この PR ではコードを追加しない。** Stage 2 で導入する。

```python
class DispatchPhase(Enum):
    CRITICAL_SYNC_SIDE_EFFECT = "critical_sync_side_effect"    # 相①a: 失敗伝播
    BEST_EFFORT_SIDE_EFFECT = "best_effort_side_effect"        # 相①b: 握るが警告
    SYNC_OBSERVATION_SIDE_EFFECT = "sync_observation_side_effect"  # 相①c: 直接 append
    OBSERVE_AND_SCHEDULE = "observe_and_schedule"              # 相②
    ASYNC_POST_COMMIT = "async_post_commit"                    # 相③ (spot_graph 未使用)

# operation 境界に注入。集約 event も手作り非集約 event も add できる
# (「その場生成」9 サイトのため — repo-tracking では拾えない)。
class DomainEventCollector(Protocol):
    def add(self, event: DomainEvent) -> None:
        """event_id を要求 (hasattr(event, "event_id"))。欠落は fail-fast。"""
    def add_all(self, events: Iterable[DomainEvent]) -> None: ...
    def drain(self) -> list[DomainEvent]: ...  # operation-local, event_id dedup 済み

# 相を明示的に分けた dispatcher。publisher の 2 regime 差をこの契約の上で吸収する。
class PhasedEventDispatcher(Protocol):
    def run_critical_sync(self, events: Sequence[DomainEvent]) -> None:
        """相①a。失敗は伝播。operation/tick を失敗させ、相②へ進めない。"""
    def run_best_effort_sync(self, events: Sequence[DomainEvent]) -> None:
        """相①b。失敗は握るが warning/trace に必ず出す。"""
    def run_sync_observation(self, events: Sequence[DomainEvent]) -> None:
        """相①c。direct append。相①a との登録順を保つ。"""
    def run_observation(self, events: Sequence[DomainEvent]) -> None:
        """相②。tick stage 内は伝播 (rollback 非保証)、post-tick hook は hook 単位 catch。"""
    def run_async_post_commit(self, events: Sequence[DomainEvent]) -> None:
        """相③。commit 後のみ。spot_graph では no-op。"""
```

Stage 2 は `item_transfer` (相② のみ、順序依存最小) を最初の 1 サービスとして移行。
相①a/①c を含む needs_decay / revive / consumable は Stage 3 で最後に、Stage 0b の
順序不変条件で厳重ガード。

## 5. codex 判定を反映した決定事項

- **D1 (相① 例外方針)** — **決定**: 相① を①a CRITICAL (伝播・operation 失敗・成功観測
  を出さない) と①b BEST_EFFORT (握るが警告) に分割。加えて①c (直接 append 観測)。
  現状 Pipeline の「全握り」は目標契約にしない。
- **D2 (dedup キー)** — **決定**: event_id ベースの operation-local dedup を新設。全
  spot_graph scope の event は `BaseDomainEvent` 継承で `event_id` (int, `uuid4().int`)
  を持つ。deepcopy でも同値。`collector.add` は event_id 欠落を fail-fast。
  **注意**: `DomainEventProtocol.event_id` は `str` 宣言だが実装は `int`
  (`domain_event.py:12-27,24-40`)。型不一致は「実装上 int」と明記 (Protocol 側の修正は別 PR)。
- **D3 (相② 例外)** — **決定**: 現状維持。ただし契約文言は「巻き戻す」ではなく
  「伝播して tick 失敗、**rollback 非保証**」。isolation 化は別 PR。
- **D4 (相③ 非新設)** — **決定**: spot_graph に相③ を作らず eager 維持。
  U1 の死に経路除去は**本計画の Stage 5 に含めない** (別計画の入力。scope 再膨張を防ぐ)。
- **D5 (写像の穴)** — **修正済み**: §3 に C8 (①a 内ネスト)、B5 の①c
  (PostHocObservation direct append)、A4 EntityEntered の①b(encounter)+順序制約を反映。

## 6. 挙動変更

なし (ドキュメントのみ)。相の分割は目標契約であり、実装 (握り→伝播への変更等) は
Stage 3 で該当サイトを移行するときに、Stage 0b の不変条件でガードしながら行う。
