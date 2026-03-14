# Phase 11: Tick Facade Extraction - Research

**Researched:** 2026-03-14
**Domain:** `WorldSimulationApplicationService` の tick facade 分割と順序保証
**Confidence:** MEDIUM

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
## Implementation Decisions

### Stage boundary
- Phase 11 の目標粒度は 6-stage split とし、環境処理、継続移動、採取完了、monster lifecycle、monster behavior、HitBox 更新を個別 stage として扱う。
- ただし Phase 11 の実装は一気に完全分離するのではなく、既存 private method と既存順序を活かした incremental 移行で進める。
- stage service 導入は将来の細分化余地を残しつつ、まず facade から責務の束を読み取れる状態を優先する。

### Facade responsibility
- `WorldSimulationService` は Phase 11 で order coordinator として寄せ、tick entry point、unit of work 境界、順序制御、エラー変換を主責務として残す。
- active spot 集約や tick 中の各 stage 呼び出し順は facade に残してよいが、個別の業務処理本体は stage 側へ委譲する前提で整理する。
- facade は world simulation 全体の公開契約を維持し、既存 wiring から見た差し替え先として残す。

### Migration style
- 導入方針は behavior-safe incremental を優先し、既存の private method や helper を足場にして段階的に stage service へ移す。
- 新しい stage API に一気に寄せる clean cut refactor は Phase 11 の目的にしない。
- wrapper 的な橋渡しは許容するが、最終的に「どこが coordinator で、どこが stage 本体か」が読める構造まで持っていく。

### Regression focus
- Phase 11 の最優先回帰契約は `pursuit continuation -> movement` の順序、observation の発火タイミング、LLM / reflection scheduling を含む wiring 契約とする。
- monster behavior や HitBox の広範な再整理は Phase 11 の主眼ではなく、順序と facade 契約を守るために必要な範囲で扱う。
- Phase 11 の検証は「分割後も tick coordinator の外部挙動が変わらない」ことを示す観点を優先する。

### Placement and packaging
- 新しい stage service 群は Phase 11 では `application/world/services/` 直下に置く。
- `simulation/` のような subpackage への再編は、分割対象の輪郭が安定してから後続 phase で再検討する。

### Claude's Discretion
- 各 stage service の具体的な命名 (`EnvironmentTickService` など) と constructor shape
- 既存 private helper をそのまま移設するか、薄い orchestrator helper を挟むか
- active spot 集約や map 再取得処理を facade に残すか、補助 coordinator に分けるかの細部

### Deferred Ideas (OUT OF SCOPE)
## Deferred Ideas

- 飢餓移住 policy の repository 非依存な本格抽出
- stage service / policy 単位のテスト厚み付け
- `application/world/services/simulation/` のような subpackage への再編
- monster lifecycle / behavior のより深い責務分離
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| WSIM-01 | `WorldSimulationService` は tick 全体の facade として残り、環境処理、継続移動、採取完了、モンスター lifecycle、モンスター behavior、HitBox 更新を専用の stage service に委譲できる | facade に UoW・順序制御・error handling を残し、既存 private method 群を薄い stage service へ委譲する incremental 方針を採る |
| WSIM-02 | tick の実行順序と副作用は既存挙動と両立し、world progression・observation・LLM / reflection scheduling の回帰を起こさない | 既存順序の固定化、active spot 凍結、距離順 actor 処理、LLM/Reflection 末尾実行、既存統合テストを軸にした validation map を使う |
</phase_requirements>

## Summary

`WorldSimulationApplicationService` はすでに facade に近い位置にありますが、実態は tick coordinator と stage 実装の両方を 1 クラスで抱えています。`tick()` はエラー変換の公開窓口で、`_tick_impl()` の内側で UoW、tick advance、weather sync、movement、harvest、active spot 集約、monster lifecycle、monster behavior、HitBox、そして UoW 脱出後の LLM / reflection を直列に制御しています。Phase 11 はこの公開契約を残したまま、中段の実務処理だけを明示的な stage service に押し出すのが正解です。

安全な切れ目は既存の private method 群にあります。`_update_weather_if_needed` + `_sync_weather_to_map`、`_advance_pending_player_movements`、`_complete_due_harvests`、`_process_spawn_and_respawn_by_slots` / `_process_respawn_legacy`、actor loop 内の lifecycle 判定 + `_process_single_actor_behavior`、`_update_hit_boxes` は、それぞれ単独メソッドとしてまとまっており、まずは facade からの委譲先として包むだけでも責務境界を可視化できます。逆に `active_spot_ids` 算出、`maps = find_all()` の再取得、UoW 境界、例外変換、LLM / reflection は facade に残すべきです。

最大の回帰リスクは順序です。特に `pursuit continuation -> movement`、movement/harvest 後の map 再取得、player presence に基づく active spot 凍結、同一 spot 内での player 近接順 actor 実行、最新 map 再取得後の HitBox 更新、tick 完了後の `run_scheduled_turns()` / `run_after_tick()` は壊せません。Phase 11 の plan は「新クラス追加」よりも「順序の固定化と委譲境界の明文化」を主に据えるべきです。

**Primary recommendation:** `WorldSimulationApplicationService` を facade のまま残し、6 stage を薄い service に順次移しつつ、facade には UoW・順序制御・active spot 集約・post-tick wiring だけを残してください。

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Python | 3.10+ | 実装言語 | `pyproject.toml` の前提。既存コードとテストがこの前提で揃っている |
| `WorldSimulationApplicationService` | repo-local | facade / tick coordinator | 既存 runtime wiring の公開契約であり、Phase 11 でも差し替え点として残す必要がある |
| `UnitOfWork` | repo-local | tick 全体のトランザクション境界 | `tick()` が単一 UoW で world progression を実行している |
| `PursuitContinuationService` | repo-local | movement 前の追跡継続判定 | Phase 3 由来の順序契約が既存テストで固定されている |
| `BehaviorService` + `MonsterActionResolverImpl` | repo-local | monster behavior の観測と次アクション解決 | actor stage の既存実装がこの組み合わせを前提にしている |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `pytest` | 8.4.1 | 回帰テスト | Phase 11 の順序・副作用回帰ガードに使う |
| `DefaultWorldTimeConfigService` | repo-local | `ticks_per_day` / `time_of_day` 計算 | lifecycle / respawn / active time 判定を stage へ移すときに共通利用する |
| `HitBoxCollisionDomainService` + `HitBoxConfigService` | repo-local | HitBox 更新・衝突解決 | HitBox stage の既存実装をそのまま委譲する |
| `HarvestCommandService` | repo-local | 採取完了の UoW 内実行 | harvest stage の委譲先として既存 seam を利用できる |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| incremental wrapper extraction | 一気に `_tick_impl()` を stage API ベースで全面書き換え | 設計はきれいになるが、順序回帰点が増え Phase 11 の安全性を落とす |
| `application/world/services/` 直下配置 | `application/world/services/simulation/` へ即再編 | 将来の整理には有利だが、今回は rename/move ノイズが大きく差分読解を悪化させる |
| facade に active spot 集約を残す | active spot coordinator を別 service 化 | 可能だが、Phase 11 では stage 本体抽出より優先度が低い |

**Installation:**
```bash
python -m pip install -e .
```

## Architecture Patterns

### Recommended Project Structure
```text
src/ai_rpg_world/application/world/services/
├── world_simulation_service.py                # facade / UoW / order coordinator
├── world_simulation_environment_stage_service.py
├── world_simulation_movement_stage_service.py
├── world_simulation_harvest_stage_service.py
├── world_simulation_monster_lifecycle_stage_service.py
├── world_simulation_monster_behavior_stage_service.py
└── world_simulation_hit_box_stage_service.py
```

### Pattern 1: Facade Keeps Orchestration, Stage Owns Work
**What:** facade は tick entry point、UoW、順序、map 再取得、post-tick wiring のみ担当し、業務処理は stage service へ委譲する。
**When to use:** 既存 runtime wiring を壊さずに大きい application service を薄くしたいとき。
**Example:**
```python
class WorldSimulationApplicationService:
    def tick(self) -> WorldTick:
        return self._execute_with_error_handling(
            operation=lambda: self._tick_impl(),
            context={"action": "tick"},
        )

    def _tick_impl(self) -> WorldTick:
        with self._unit_of_work:
            current_tick = self._time_provider.advance_tick()
            latest_weather = self._environment_stage.advance_weather(current_tick)
            maps = self._environment_stage.sync_weather(latest_weather)
            maps = self._movement_stage.advance_pending_movements(maps, current_tick)
            maps = self._harvest_stage.complete_due_harvests(maps, current_tick)
            active_spot_ids, player_map_map = self._collect_active_spots(maps)
            self._environment_stage.apply_environmental_effects(player_map_map)
            self._monster_lifecycle_stage.run(maps, active_spot_ids, current_tick)
            self._monster_behavior_stage.run(maps, active_spot_ids, current_tick)
            self._hit_box_stage.run(maps, active_spot_ids, current_tick)
        self._run_post_tick(current_tick)
        return current_tick
```

### Pattern 2: Use Existing Private Methods as First Extraction Seams
**What:** 既存 private method を最初は service にそのまま移し、facade から呼ぶだけに留める。
**When to use:** order-sensitive な refactor を最小差分で進めたいとき。
**Example:**
```python
class WorldSimulationMovementStageService:
    def advance_pending_movements(self, current_tick: WorldTick) -> None:
        tick_movement = getattr(
            self._movement_service,
            "tick_movement_in_current_unit_of_work",
            None,
        )
        if not callable(tick_movement):
            return
        ...
```

### Pattern 3: Separate Monster Lifecycle from Monster Behavior
**What:** `monster.tick_hunger() / starve() / die_from_old_age()` と `build_observation() -> transition -> resolve_action()` を別 stage に分ける。
**When to use:** behavior loop を後続 phase でさらに分割したい前提を残したいとき。
**Example:**
```python
for actor in self._actors_sorted_by_distance_to_players(physical_map):
    if actor.is_busy(current_tick):
        continue
    if self._monster_lifecycle_stage.should_consume_actor(actor, current_tick):
        continue
    self._monster_behavior_stage.process_actor(actor, physical_map, current_tick)
```

### Pattern 4: Facade Owns Active Spot Freeze
**What:** active spot 判定は stage に分散させず、facade で `active_spot_ids` を一回計算して各 stage に渡す。
**When to use:** 複数 stage が同じ「player がいる spot のみ更新」という契約を共有するとき。
**Example:**
```python
active_spot_ids = {pm.spot_id for pm in player_map_map.values()}
for stage in (self._monster_lifecycle_stage, self._monster_behavior_stage, self._hit_box_stage):
    stage.run(maps=maps, active_spot_ids=active_spot_ids, current_tick=current_tick)
```

### Anti-Patterns to Avoid
- **stage が独自に UoW を開く:** tick 全体が単一 UoW でなくなり、既存イベント順序と save タイミングが崩れる。
- **map 再取得を削る:** movement / harvest 後や HitBox 前の `find_all()` / `find_by_spot_id()` を消すと、同期イベント反映後の最新 map を見失う。
- **monster lifecycle と behavior を同時に再設計する:** Phase 11 の目標は facade 抽出であり、policy 再設計は Phase 12 領域。
- **stage 名を抽象化しすぎる:** `TickStageA` のような名前は plan とコードの対応を悪くする。

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| pursuit continuation 判定 | facade 内の新しい if/else 巨塊 | `PursuitContinuationService.evaluate_tick()` | 追跡の failure reason と replan 条件が既存 service / tests に閉じている |
| monster 次アクション解決 | stage 内独自の chase / flee / skill 分岐 | `monster_action_resolver_factory(...).resolve_action()` | 既存 resolver に pathfinding と skill policy の知識が集約されている |
| HitBox 更新ループ | 新しい collision ループ | `_update_hit_boxes()` を段階移設 | 衝突回数 guard、activation tick、repository save を既に内包している |
| weather 計算 | stage 独自 weather 遷移 | `WeatherSimulationService` と既存 sync ロジック | zone 更新と map 同期の二段構えが既存仕様 |

**Key insight:** Phase 11 は「責務の見える化」が目的であって、tick ルールの再発明ではありません。既存 private method を first-class stage に格上げするだけで十分価値があります。

## Common Pitfalls

### Pitfall 1: `pursuit continuation -> movement` の逆転
**What goes wrong:** move 実行後に continuation 判定すると、同 tick の path refresh と failure reason がずれる。
**Why it happens:** movement stage を単独で抜く際に、continuation 判定を facade か別 stage に誤配置しやすい。
**How to avoid:** movement stage 自体に continuation 呼び出しを抱かせるか、facade で明示的に continuation 後に movement を呼ぶ。
**Warning signs:** `test_tick_runs_pursuit_continuation_before_movement_execution` が落ちる。

### Pitfall 2: movement / harvest 後の map 再取得を忘れる
**What goes wrong:** player map 集約や後続 stage が stale な map を読む。
**Why it happens:** stage 抽出で return value を単純化し、`find_all()` の再取得を削りたくなる。
**How to avoid:** movement stage と harvest stage の戻り値は「必要なら maps を再ロード済みで返す」に固定する。
**Warning signs:** active spot 判定、harvest 完了、observation 発火 spot がズレる。

### Pitfall 3: active spot freeze が stage ごとにばらける
**What goes wrong:** behavior だけ active spot 判定を守り、spawn/hitbox/save は inactive spot に対して動いてしまう。
**Why it happens:** 各 stage が個別に `player_map_map` を再構築し始めるから。
**How to avoid:** facade で一回だけ `active_spot_ids` を作り、共有入力として stage に渡す。
**Warning signs:** inactive spot 系テストや save 回数テストが落ちる。

### Pitfall 4: LLM / reflection を UoW 内や stage 内へ移す
**What goes wrong:** world state 確定前に scheduled turns / reflection が走る。
**Why it happens:** post-tick hook を「最後の stage」と誤認するため。
**How to avoid:** `run_scheduled_turns()` と `run_after_tick()` は facade の UoW 脱出後に固定する。
**Warning signs:** wiring integration 系テストが崩れる、例外が `tick failed` に包まれなくなる。

### Pitfall 5: stage 粒度を深掘りしすぎる
**What goes wrong:** Phase 11 の差分が monster policy / hunger migration の設計変更まで広がる。
**Why it happens:** actor loop を触るとつい内部 policy も整理したくなる。
**How to avoid:** Phase 11 は stage boundary の抽出に限定し、policy 抽出は wrapper か TODO で止める。
**Warning signs:** constructor 変更が大きくなり、テスト追加より既存テスト修復が増える。

## Code Examples

Verified patterns from current codebase:

### Current Tick Order Contract
```python
current_tick = self._time_provider.advance_tick()
latest_weather = self._update_weather_if_needed(current_tick)
maps = self._physical_map_repository.find_all()

for physical_map in maps:
    self._sync_weather_to_map(physical_map, latest_weather)

if self._movement_service is not None:
    self._advance_pending_player_movements(current_tick)
    maps = self._physical_map_repository.find_all()

if self._harvest_command_service is not None:
    self._complete_due_harvests(maps, current_tick)
    maps = self._physical_map_repository.find_all()
```
Source: `src/ai_rpg_world/application/world/services/world_simulation_service.py`

### Post-Tick Wiring Must Stay Outside UoW
```python
if self._llm_turn_trigger is not None:
    self._llm_turn_trigger.run_scheduled_turns()
if self._reflection_runner is not None:
    self._reflection_runner.run_after_tick(current_tick)
```
Source: `src/ai_rpg_world/application/world/services/world_simulation_service.py`

### Pursuit Continuation Returns a Stable Decision Object
```python
decision = self._pursuit_continuation_service.evaluate_tick(status)
if not decision.should_advance_movement:
    continue
tick_movement(int(status.player_id))
```
Source: `src/ai_rpg_world/application/world/services/world_simulation_service.py`

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| world tick が monolith class の private method 群に閉じる | facade + stage service へ段階抽出 | Phase 11 | runtime 契約を残したまま責務境界を読みやすくできる |
| player movement を tick loop と疎結合に扱う | `PursuitContinuationService` が tick 前判定を返す | Phase 3 | movement stage は continuation を前提に扱う必要がある |
| inactive spot も一律更新しうる設計 | player presence による active spot freeze | 既存テストで固定済み | stage は active spot 入力を共有すべき |

**Deprecated/outdated:**
- `_tick_impl()` に stage 実装を直接積み増す方針: これ以上続けると Phase 12/13 の計画精度が下がる。

## Open Questions

1. **monster lifecycle stage に hunger migration を含めるか**
   - What we know: 現状は spawn/respawn の後、behavior loop の前に hunger migration が走る。
   - What's unclear: Phase 11 の 6-stage split における配置名を lifecycle に含めるか、別 helper に置くか。
   - Recommendation: Phase 11 では lifecycle stage の内部 helper として残し、public stage 数は増やさない。

2. **stage service の constructor に repository 群を直接渡すか**
   - What we know: 既存 facade constructor は依存が多い。
   - What's unclear: stage へ依存を分配すると constructor diff が大きくなる。
   - Recommendation: Phase 11 では facade constructor で stage を組み立てず、既存依存をそのまま stage へ注入する薄い composition で十分。

3. **class 名を `*StageService` にするか `*TickService` にするか**
   - What we know: 既存 `application/world/services/` は `*Service` / `*ApplicationService` が主流。
   - What's unclear: `StageService` が repo で未使用。
   - Recommendation: `WorldSimulationEnvironmentStageService` のように domain を含む明示名にし、`tick` 専用であることを class docstring で補う。

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | `pytest` 8.4.1 |
| Config file | `pytest.ini` |
| Quick run command | `python -m pytest tests/application/world/services/test_world_simulation_service.py -k 'pursuit_continuation_before_movement_execution or actors_processed_in_order_of_distance_to_player_when_player_on_map or only_active_spot_gets_build_observation_and_save'` |
| Full suite command | `python -m pytest` |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| WSIM-01 | facade から各 stage 境界へ委譲しても active spot / actor order / save 契約が維持される | integration | `python -m pytest tests/application/world/services/test_world_simulation_service.py -k 'actors_processed_in_order_of_distance_to_player_when_player_on_map or only_active_spot_gets_build_observation_and_save or inactive_spot_actors_never_get_build_observation or dead_monster_respawns_when_interval_elapsed_and_condition_met'` | ✅ |
| WSIM-02 | tick 順序と副作用、LLM / reflection wiring 契約が崩れない | integration | `python -m pytest tests/application/world/services/test_world_simulation_service.py -k 'llm_turn_trigger or pursuit_continuation_before_movement_execution or tick_auto_completes_due_player_harvest'` | ✅ |
| WSIM-02 | create_llm_agent_wiring 由来の trigger / reflection を渡した facade が post-tick 契約を守る | integration | `python -m pytest tests/application/llm/test_llm_wiring_integration.py -k 'WorldSimulationService and trigger'` | ✅ |

### Sampling Rate
- **Per task commit:** `python -m pytest tests/application/world/services/test_world_simulation_service.py -k 'pursuit_continuation_before_movement_execution or only_active_spot_gets_build_observation_and_save'`
- **Per wave merge:** `python -m pytest tests/application/world/services/test_world_simulation_service.py -k 'llm_turn_trigger or pursuit_continuation_before_movement_execution or actors_processed_in_order_of_distance_to_player_when_player_on_map or only_active_spot_gets_build_observation_and_save or dead_monster_respawns_when_interval_elapsed_and_condition_met'`
- **Phase gate:** `python -m pytest tests/application/world/services/test_world_simulation_service.py tests/application/llm/test_llm_wiring_integration.py`

### Wave 0 Gaps
- [ ] ローカル環境に `pytest` が未導入。`python -m pytest ...` は `No module named pytest` で失敗したため、まず `python -m pip install -e .` が必要
- [ ] `reflection_runner.run_after_tick()` の明示的アサートは `test_world_simulation_service.py` に不足。Phase 11 か Phase 13 で facade regression に追加したい
- [ ] stage service 単位のテストファイルはまだ存在しない。Phase 11 では新規作成は任意だが、少なくとも facade tests を壊さないこと

## Sources

### Primary (HIGH confidence)
- `src/ai_rpg_world/application/world/services/world_simulation_service.py` - 現行 tick 順序、UoW 境界、LLM / reflection 実行位置
- `src/ai_rpg_world/application/world/services/pursuit_continuation_service.py` - movement 前の continuation 契約
- `src/ai_rpg_world/application/world/services/monster_action_resolver.py` - monster behavior 解決の既存 seam
- `tests/application/world/services/test_world_simulation_service.py` - 順序、active spot、harvest、HitBox、respawn、LLM trigger 回帰点
- `tests/application/llm/test_llm_wiring_integration.py` - bootstrap wiring と `WorldSimulationApplicationService` への注入契約
- `.planning/phases/11-tick-facade-extraction/11-CONTEXT.md` - Phase 11 の locked decisions と deferred scope
- `.planning/REQUIREMENTS.md` - WSIM-01 / WSIM-02 の成功条件
- `.planning/config.json` - Nyquist validation が有効であること

### Secondary (MEDIUM confidence)
- `pytest.ini` - テスト検出ルール
- `pyproject.toml` - Python / pytest バージョン前提

### Tertiary (LOW confidence)
- None

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - この phase は新規ライブラリ選定ではなく既存コード基盤の分割で、根拠がすべて repo 内にある
- Architecture: MEDIUM - 推奨分割は既存 seam に強く依存して妥当だが、最終的な class 粒度には裁量が残る
- Pitfalls: HIGH - 主要回帰点が既存統合テストでかなり明示されている

**Research date:** 2026-03-14
**Valid until:** 2026-04-13
