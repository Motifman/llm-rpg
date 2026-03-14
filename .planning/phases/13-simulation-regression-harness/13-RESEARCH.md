# Phase 13: Simulation Regression Harness - Research

**Researched:** 2026-03-14
**Domain:** World simulation regression strategy, pytest test architecture, fixture/builder refactoring
**Confidence:** HIGH

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
### Regression priority
- Phase 13 で最優先に守る回帰契約は、`WorldSimulationApplicationService.tick()` の全体 stage 順序と post-tick hook を含む順序保証とする。
- 具体的には `environment -> movement -> harvest -> lifecycle -> behavior -> hit box -> post-tick hook` の大きな流れを、代表的な統合ケースで固定する。
- 順序契約に付随する副作用のうち、最初に強く守る対象は `llm_turn_trigger` / `reflection_runner` を含む post-tick hook 契約とする。
- Phase 13 では細かい枝分かれの網羅より、代表経路で「tick coordinator の約束が壊れていない」ことを優先する。

### Integration test shape
- 大きな統合テストは残すが、今の巨大ファイルへ寄せ続けるのではなく、中くらいの網として契約ごとに役割を分ける。
- 統合テストの中心は「プレイヤー1体 + pursuit / movement + モンスター1体」が同居する代表ケースとし、world simulation 本流のつながりを 1 本のゴールデンパスとして守る。
- 追加の統合テストは、順序契約、active spot / save 契約、post-tick hook 契約など、守る約束ごとに目的を分離して持つ。
- `test_world_simulation_service.py` は薄くしてよく、責務の近い統合テストは service / 契約単位へ整理する。

### Fixture and builder strategy
- 現在の大きい `setup_service` fixture を唯一の入口にせず、必要な依存だけを組み立てられる薄い builder / helper 群へ分ける。
- 新しい回帰ケースでは、「どんな world 状態を作っているか」が helper 名から分かることを重視する。
- 既存の重い fixture は移行期間の足場として残してよいが、Phase 13 の新規追加テストは軽い builder を優先する。
- fixture / builder の目的はテストコード短縮だけでなく、失敗時に前提 world 状態を読み取りやすくすることとする。

### Small regression boundaries
- Phase 13 の小粒テストは stage 単位を主軸とし、特に `movement`・`monster lifecycle`・`monster behavior` stage を優先する。
- 小粒テストで最初に守るのは、正常系の巨大シナリオではなく、skip / guard / support 有無による collaborator 呼び出し契約である。
- `active spot ではない`, `busy actor`, `support が未注入`, `skip 対象 actor` などの条件で、何が呼ばれるか / 呼ばれないかを直接検証する。
- 既に存在する `HungerMigrationPolicy` や `MonsterBehaviorCoordinator` などの小粒テストは核として活かし、足りない stage service の境界だけを追加していく。

### Failure diagnostics
- テストが落ちたとき、最初に「どの契約が壊れたか」が分かることを強く重視する。
- 命名は service 名先行ではなく契約ベースを基本とし、`stage order`, `active spot save`, `post-tick hook` のように守りたい約束がテスト名から読める形を優先する。
- 1 テスト 1 契約を原則とし、近い契約をまとめすぎない。
- 補助手段として、fixture / builder 名でも前提 world 状態を説明できるようにし、失敗時にケースの意図を追いやすくする。

### Claude's Discretion
- builder / helper の具体的な API 形状と配置先
- 統合テストを契約別ファイルへどう分けるかの最終ファイル構成
- stage service テストのうち、どの guard 条件を Phase 13 で先に拾い、どれを後続へ回すかの優先順位

### Deferred Ideas (OUT OF SCOPE)
- world simulation の新 capability 追加や tick 順序そのものの変更
- hit box / combat 系の細かい枝分かれを全面的に整理し直すこと
- monster 個別ルールごとの詳細な網羅を Phase 13 の主眼に据えること
- fixture / builder 基盤を world simulation 以外のテスト全体へ一気に横展開すること
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| WSTEST-01 | `WorldSimulationService` の既存統合テストは責務分割後も主要な tick 順序と副作用を検証し続けられる | 統合テストを `stage order` / `active spot save` / `post-tick hook` 契約へ分け、代表ケースを維持する方針 |
| WSTEST-02 | 分離した stage service / policy 単位で、巨大 fixture に依存しすぎない回帰テストを追加できる | `movement` / `monster lifecycle` / `monster behavior` stage の guard 条件を直接叩く unit 寄りテストと、薄い builder 群の導入順序 |
</phase_requirements>

## Summary

Phase 13 は新しい world simulation 機能を足すフェーズではなく、Phase 11/12 でできた seam を使って、既存の巨大 integration test を「何を守るテストなのか」が明確な契約ベースの網へ再配置するフェーズです。既存コードを見る限り、`WorldSimulationApplicationService` が守るべきものは stage 順序、`active_spot_ids` の伝播、`save` 境界、post-tick の `llm_turn_trigger` / `reflection_runner` hook で、個別ルールの大半はすでに stage / coordinator / policy 側へ寄せられています。

自然な plan split は 2 本です。Plan 01 で「大きい網」を整理し、代表ケースと契約別 integration を切り分けつつ、軽量 builder / fixture を整える。Plan 02 で `movement`・`monster lifecycle`・`monster behavior` stage の小粒テストを guard 条件中心に増やし、既存の `HungerMigrationPolicy` / `MonsterBehaviorCoordinator` / `MonsterLifecycleSurvivalCoordinator` の単体テスト文化と接続する。この順序にすると、WSTEST-01 を先に安定させてから WSTEST-02 を拡張できる。

**Primary recommendation:** Phase 13 は `13-01` を「契約別 integration + builder 抽出」、`13-02` を「stage guard regression 拡張」に分ける。

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Python | `>=3.10` | 実装言語 | 既存アプリケーションと planning artifact が前提にしている実行環境 |
| pytest | `8.4.1` | テスト実行と regression harness | 既存 suite・`pytest.ini`・phase summaries がすべて pytest 前提 |
| pytest-cov | `6.2.1` | coverage 補助 | 既存 `pyproject.toml` に含まれ、必要なら phase gate で流用できる |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `unittest.mock` | stdlib | collaborator 呼び出し契約の確認 | stage / coordinator テストで side effect を狭く見るとき |
| InMemory repositories / UoW | repo local | integration 寄り fixture の土台 | facade 契約を大きく壊さずに world state を組むとき |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| pytest + existing in-memory fixtures | 新しい test framework / factory library | Phase 13 は test boundary 再編が目的で、新規導入コストが不要 |
| service-level full integration only | 全面 unit 化 | stage order / hook 契約を見失いやすく、WSTEST-01 を取りこぼす |

**Installation:**
```bash
python -m pip install -e .
```

## Architecture Patterns

### Recommended Project Structure
```text
tests/application/world/services/
├── test_world_simulation_service.py              # facade 全体の代表ケースだけを残す
├── test_world_simulation_stage_order.py         # stage order / post-tick hook 契約
├── test_world_simulation_active_spot_contract.py # active spot / save 契約
├── test_world_simulation_movement_stage_service.py
├── test_world_simulation_monster_lifecycle_stage_service.py
└── test_world_simulation_monster_behavior_stage_service.py
```

### Pattern 1: Contract-Sliced Integration Tests
**What:** 巨大 integration file を、守る契約ごとに薄いファイルへ分ける。
**When to use:** facade が複数の副作用を束ねるが、phase goal が「どの契約が壊れたか分かること」にあるとき。
**Example:**
```python
def test_tick_preserves_stage_order_for_representative_world(...): ...
def test_tick_saves_only_active_spots(...): ...
def test_tick_runs_post_tick_hooks_after_uow(...): ...
```

### Pattern 2: Thin Builder, Narrow Assertions
**What:** `setup_service` の全部入り fixture をそのまま使わず、必要な依存だけ返す builder を作る。
**When to use:** 新しい regression case が 1 契約 1 テストで、world state の説明責任を上げたいとき。
**Example:**
```python
service, deps = build_world_simulation_service(with_movement=True, with_hooks=True)
world = build_active_spot_with_player_and_monster()
```

### Pattern 3: Stage Guard Regressions
**What:** stage service を直接呼び、skip / guard / support 有無で collaborator がどう呼ばれるかだけを確認する。
**When to use:** 既に facade order が別 integration で守られていて、WSTEST-02 の増やしやすさを担保したいとき。
**Example:**
```python
stage.run(maps, active_spot_ids, current_tick, skipped_actor_ids={monster_id})
coordinator.process_actor_behavior.assert_not_called()
```

### Anti-Patterns to Avoid
- **全部入り fixture の使い回し:** 1 契約 1 テストでも準備が重くなり、Phase 13 の主目的に逆行する。
- **service 名ベースの雑多なファイル分割:** 「何を守るテストか」が見えにくく、失敗診断が鈍る。
- **stage テストで最終状態まで全部見る:** collaborator 呼び出し契約が目的なのに、不要な world state 依存を増やす。

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| stage 単位回帰 | 独自 mini harness | 既存 stage service + `unittest.mock` | 既存 ctor seam だけで guard 条件を十分押さえられる |
| integration fixture | 新しい外部 factory framework | 既存 in-memory repo + 小さい builder helper | repo 依存の実態に合っていて、Phase 13 の変更範囲も小さい |
| hook 検証 | 擬似 event bus | `llm_turn_trigger` / `reflection_runner` mock | post-tick hook 契約は collaborator 呼び出しで直接確認できる |

**Key insight:** Phase 13 は新しい test 技法を導入するフェーズではなく、既にある seam を読みやすい regression harness に並べ替えるフェーズである。

## Common Pitfalls

### Pitfall 1: Integration と Stage の責務が混ざる
**What goes wrong:** stage テストで world simulation 全体の order まで守ろうとして、fixture が再び肥大化する。
**Why it happens:** `test_world_simulation_service.py` の既存成功体験をそのまま新規テストへ持ち込むため。
**How to avoid:** facade integration は order / hook / active spot に限定し、stage テストは guard 条件と collaborator 呼び出し契約に絞る。
**Warning signs:** stage test なのに map / monster / loadout / event publisher を全部組んでいる。

### Pitfall 2: Post-tick hook を後回しにして順序保証が片手落ちになる
**What goes wrong:** stage 順序だけ守っても、`llm_turn_trigger` / `reflection_runner` の後段契約が抜ける。
**Why it happens:** hook が facade 外に見えて、回帰対象から漏れやすい。
**How to avoid:** representative integration に post-tick hook assertion を含める。契約別 file を作るなら hook 契約を独立させる。
**Warning signs:** `llm_turn_trigger` だけ確認し、`reflection_runner` を明示アサートしていない。

### Pitfall 3: `setup_service` 分解前に大量の新規ケースを足す
**What goes wrong:** WSTEST-02 のためにテストを増やしたつもりが、すべて重い fixture 依存になって保守性が改善しない。
**Why it happens:** 先にケースを増やす方が速く見えるため。
**How to avoid:** Plan 01 で薄い builder を先に作り、Plan 02 で stage test を増やす順序を守る。
**Warning signs:** 新規 test file でも `setup_service` をそのまま import / copy している。

## Code Examples

Verified patterns from repository sources:

### Pure Policy Regression
```python
policy = HungerMigrationPolicy()
selected = policy.select_migrant([first, second])
assert selected is first
```
Source: `tests/application/world/services/test_hunger_migration_policy.py`

### Coordinator Order Regression
```python
assert order == [
    "foraging",
    "observation",
    "transition",
    "pre-failure",
    "resolver",
    "post-failure",
]
```
Source: `tests/application/world/services/test_monster_behavior_coordinator.py`

### Stage Guard Contract
```python
for actor in self._actors_sorted_by_distance_to_players(physical_map):
    if actor.object_id in skipped:
        continue
    if actor.is_busy(current_tick):
        continue
```
Source: `src/ai_rpg_world/application/world/services/world_simulation_monster_behavior_stage_service.py`

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `WorldSimulationApplicationService` に私有 helper が集中 | stage / coordinator / policy へ責務分割 | Phase 11-12 (2026-03-14) | 回帰テストを facade 全体と小粒境界に分けられる |
| hunger migration / monster behavior を facade 経由でしか追えない | `HungerMigrationPolicy` / `MonsterBehaviorCoordinator` / `MonsterLifecycleSurvivalCoordinator` がある | Phase 12 (2026-03-14) | WSTEST-02 の起点が既に存在する |

**Deprecated/outdated:**
- `test_world_simulation_service.py` 1 ファイルへ回帰ケースを積み増し続ける方針: Phase 13 の目的と矛盾する。

## Open Questions

1. **builder を `conftest.py` に寄せるか、test module 内 helper から始めるか**
   - What we know: Phase 13 では世界状態が分かる名前付けが重要。
   - What's unclear: 初期 builder を共有化しすぎると、逆に責務が曖昧になる。
   - Recommendation: Plan 01 は対象領域の近くに helper を置き、重複が見えてから `conftest.py` 化する。

2. **HitBox stage を Phase 13 でどこまで扱うか**
   - What we know: hit box は既存 integration が厚く、Phase 13 の deferred でも細かい枝分かれ全面整理は外している。
   - What's unclear: `save` 契約だけは active spot 契約と近い。
   - Recommendation: Plan 01 では facade 契約側で最低限押さえ、Plan 02 の stage expansion 優先対象には入れない。

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | `pytest 8.4.1` |
| Config file | `pytest.ini` |
| Quick run command | `python -m pytest tests/application/world/services/test_world_simulation_service.py -k "pursuit_continuation_before_movement_execution or tick_runs_monster_lifecycle_before_behavior_stage or only_active_spot_gets_build_observation_and_save"` |
| Full suite command | `python -m pytest` |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| WSTEST-01 | representative world で stage order と post-tick hook が維持される | integration | `python -m pytest tests/application/world/services/test_world_simulation_service.py -k "pursuit_continuation_before_movement_execution or tick_runs_monster_lifecycle_before_behavior_stage or llm_turn_trigger"` | ✅ |
| WSTEST-01 | active spot / save 契約が回帰しない | integration | `python -m pytest tests/application/world/services/test_world_simulation_service.py -k "only_active_spot_gets_build_observation_and_save or inactive_spot_actors_never_get_build_observation or active_spot_save_called_once_per_active_map"` | ✅ |
| WSTEST-02 | `movement` stage の support/skip 契約を直接追加できる | unit-ish | `python -m pytest tests/application/world/services/test_world_simulation_movement_stage_service.py -x` | ❌ Wave 0 |
| WSTEST-02 | `monster lifecycle` stage の spawn/survival guard を直接追加できる | unit-ish | `python -m pytest tests/application/world/services/test_world_simulation_monster_lifecycle_stage_service.py -x` | ❌ Wave 0 |
| WSTEST-02 | `monster behavior` stage の skipped/busy/active-time guard を直接追加できる | unit-ish | `python -m pytest tests/application/world/services/test_world_simulation_monster_behavior_stage_service.py -x` | ❌ Wave 0 |

### Sampling Rate
- **Per task commit:** `python -m pytest tests/application/world/services/test_world_simulation_service.py -k "pursuit_continuation_before_movement_execution or tick_runs_monster_lifecycle_before_behavior_stage or only_active_spot_gets_build_observation_and_save" -x`
- **Per wave merge:** `python -m pytest tests/application/world/services/test_world_simulation_service.py tests/application/world/services/test_hunger_migration_policy.py tests/application/world/services/test_monster_behavior_coordinator.py tests/application/world/services/test_monster_lifecycle_survival_coordinator.py -x`
- **Phase gate:** `python -m pytest tests/application/world/services/test_world_simulation_service.py tests/application/world/services/test_hunger_migration.py tests/application/world/services/test_hunger_migration_policy.py tests/application/world/services/test_monster_behavior_coordinator.py tests/application/world/services/test_monster_lifecycle_survival_coordinator.py tests/application/llm/test_llm_wiring_integration.py -x`

### Wave 0 Gaps
- [ ] `tests/application/world/services/test_world_simulation_movement_stage_service.py` — movement stage の guard / support regression
- [ ] `tests/application/world/services/test_world_simulation_monster_lifecycle_stage_service.py` — spawn/survival handoff regression
- [ ] `tests/application/world/services/test_world_simulation_monster_behavior_stage_service.py` — skipped/busy/active-time regression
- [ ] representative integration で `reflection_runner.run_after_tick()` を明示アサートするケース
- [ ] 軽量 builder/helper の置き場を Plan 01 で決める

## Recommended Plan Split

### Plan 13-01: Contract-Sliced Integration Harness
- **Goal:** facade 回帰を契約ごとに切り分け、代表ケースと builder/helper を整える。
- **Artifacts:**
  - `tests/application/world/services/test_world_simulation_service.py`
  - `tests/application/world/services/test_world_simulation_stage_order.py` または同等の契約別 file
  - `tests/application/world/services/test_world_simulation_active_spot_contract.py` または同等の契約別 file
  - 必要なら近傍 helper / fixture module
- **Focus:**
  - stage order
  - active spot / save
  - post-tick hook
  - builder 抽出の最初の一歩

### Plan 13-02: Stage Guard Regression Expansion
- **Goal:** `movement` / `monster lifecycle` / `monster behavior` stage に、小さい guard regression を追加する。
- **Artifacts:**
  - `tests/application/world/services/test_world_simulation_movement_stage_service.py`
  - `tests/application/world/services/test_world_simulation_monster_lifecycle_stage_service.py`
  - `tests/application/world/services/test_world_simulation_monster_behavior_stage_service.py`
- **Focus:**
  - support 未注入時の no-op
  - busy / skipped / inactive / inactive spot
  - lifecycle blocked actor handoff
  - existing coordinator/policy tests との役割分担

## Risks

- **Medium:** builder を共有化しすぎると、逆に contract ごとの前提が見えなくなる。
- **Medium:** post-tick hook 契約を `llm_turn_trigger` だけで済ませると、`reflection_runner` の regression を見落とす。
- **Low:** stage test を増やしても facade integration を削りすぎると WSTEST-01 が弱くなる。

## Sources

### Primary (HIGH confidence)
- `.planning/phases/13-simulation-regression-harness/13-CONTEXT.md` - locked decisions and scope
- `.planning/ROADMAP.md` - Phase 13 goal and success criteria
- `.planning/REQUIREMENTS.md` - WSTEST-01 / WSTEST-02 definitions
- `.planning/STATE.md` - current milestone state and known concern
- `src/ai_rpg_world/application/world/services/world_simulation_service.py` - facade order, active spot derivation, post-tick hook location
- `src/ai_rpg_world/application/world/services/world_simulation_movement_stage_service.py` - movement guard seam
- `src/ai_rpg_world/application/world/services/world_simulation_monster_lifecycle_stage_service.py` - lifecycle/survival handoff seam
- `src/ai_rpg_world/application/world/services/world_simulation_monster_behavior_stage_service.py` - skipped/busy/active-time seam
- `src/ai_rpg_world/application/world/services/world_simulation_environment_stage_service.py` - environment stage seam
- `src/ai_rpg_world/application/world/services/world_simulation_hit_box_stage_service.py` - active spot + save seam
- `tests/application/world/services/test_world_simulation_service.py` - current broad regression harness
- `tests/application/world/services/test_hunger_migration.py` - lifecycle/apply regression mix
- `tests/application/world/services/test_hunger_migration_policy.py` - pure policy regression pattern
- `tests/application/world/services/test_monster_behavior_coordinator.py` - coordinator regression pattern
- `tests/application/world/services/test_monster_lifecycle_survival_coordinator.py` - survival coordinator regression pattern
- `tests/application/llm/test_llm_wiring_integration.py` - wiring and hook-adjacent integration
- `pyproject.toml` - Python / pytest versions
- `pytest.ini` - pytest config and markers

### Secondary (MEDIUM confidence)
- `.planning/phases/11-tick-facade-extraction/11-RESEARCH.md` - previously identified reflection hook gap
- `.planning/phases/12-monster-policy-separation/12-monster-policy-separation-02-SUMMARY.md` - seams delivered by Phase 12

### Tertiary (LOW confidence)
- None

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - repo already fixes Python/pytest stack and Phase 13 adds no new library
- Architecture: HIGH - stage/coordinator seams and current test concentration are directly visible in source
- Pitfalls: HIGH - failures follow from current fixture concentration and missing hook assertions already noted in prior research

**Research date:** 2026-03-14
**Valid until:** 2026-04-13
