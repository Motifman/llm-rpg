# Phase 10: Awakened Mode Tooling And Runtime Proof - Research

**Researched:** 2026-03-13
**Domain:** Awakened mode LLM tooling, server-side activation defaults, and runtime proof on the existing skill tool path
**Confidence:** HIGH

## User Constraints

### Locked Decisions
#### Success result messaging
- `skill_activate_awakened_mode` の成功文面は短く確定的にし、発動者本人への即時フィードバックとして返す
- tool 結果では「覚醒モードを発動した」という完了事実を主に伝え、周辺への伝播や追加の描写は observation 側へ委ねる
- コスト・duration・cooldown 軽減率などの内部数値は、通常の成功結果では user-facing に出さない
- user-facing の成立時点は tool 実行成功時点とみなし、observation は追認・周辺共有の役割で扱う

#### Availability expectations
- リソース不足や既に覚醒中など、通常の発動不能条件は tool 候補自体を出さない方針にする
- 特に「覚醒中」は現在の `awakened_action` builder 方針どおり action label を出さない
- loadout owner mismatch や stale runtime label など、事前に完全には防げない整合性崩れは実行時失敗で扱う
- 実行時失敗の文面は覚醒専用に盛り込みすぎず、既存の `exception_result(...)` と service 例外ハンドリングを基本とする

#### Runtime proof expectations
- Phase 10 の完了証明には、LLM wiring 経由の実行 path と observation / runtime 反映の両方を必要とする
- ただし observation 側は「覚醒発動が確認できること」を主眼とし、周辺効果の詳細検証までは必須にしない
- 既存 skill 系 tool との共存確認は最低限の回帰でよく、equip / proposal まで含めた大規模シナリオ証明は必須にしない
- テスト方針は unit と integration を半々にし、builder / resolver / executor の局所確認と wiring 経由の結線確認を両立する

### Claude's Discretion
- 成功メッセージの最終文面と語尾
- 発動不能条件のうち、どこまで current state builder 側で hidden 判定し、どこから service 側拒否へ委ねるかの実装配分
- runtime proof で使う統合テストの具体シナリオ構成

### Deferred Ideas (OUT OF SCOPE)
- 覚醒中の効果詳細や数値を user-facing に豊富表示すること
- 覚醒発動後の後続行動ボーナスまで含めた高粒度 observation 検証
- equip / proposal / awakened をすべて同一長尺シナリオで証明する重い E2E
- v1.1 外の pursuit / group control 拡張

## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| SKAW-01 | LLM 制御プレイヤーは専用ツールで覚醒モードを発動できる | `PlayerSkillToolApplicationService` に awakened facade を追加し、`WorldToolExecutor` と `ToolCommandMapper` の既存 skill path へ接続する |
| SKAW-02 | 覚醒モード発動ツールは LLM に内部数値を要求せず、コスト・持続時間・クールダウン軽減率はサーバ側設定で決定される | `awakened_action_label -> loadout_id` の resolver 契約を維持し、 facade か wiring 境界で server-side defaults を注入する |
| SKAW-03 | 覚醒モード発動ツールは、リソース不足・発動中・対象 loadout 不在などの条件では利用候補に出ない | `PlayerSupplementalContextBuilder.build_awakened_action(...)` を presence-based visibility の一次ソースにし、hidden-first を保ったまま不足資源判定を builder/query 側へ引き上げる |
| SKRT-02 | skill 装備・proposal 意思決定・覚醒発動の結果は既存 observation / LLM 再開フローと矛盾しない形で runtime path 上で確認できる | `available tools -> resolver -> mapper execute -> world executor -> skill service -> observation/current state` を繋ぐ回帰テストを追加し、観測への出現を runtime proof として固定する |

## Summary

phase10 は新しい tool contract を作る段階ではなく、phase8/9 で既に公開済みの awakened label 契約を、実際の実行経路と runtime proof まで閉じるフェーズです。現状のコードでは `skill_activate_awakened_mode` の definition、availability resolver、argument resolver、UI label 生成、`SkillCommandService.activate_player_awakened_mode(...)` までは存在しています。一方で、LLM が叩く facade、`WorldToolExecutor` の handler、default wiring 回帰、hidden-first をリソース不足まで広げる current-state 判定が未完了です。

実装の重心は 3 点です。第一に、`ActivatePlayerAwakenedModeCommand` が要求する数値パラメータを LLM に見せずに埋める server-side defaults の供給点を 1 箇所に定めること。第二に、その facade を既存の `skill_tool_service` に追加して `combat_use_skill` / Phase 9 skill tools と同じ mapper/executor 経路へ接続すること。第三に、発動成功が observation / runtime flow に現れることを skill 系ツール群との共存回帰として証明することです。

**Primary recommendation:** `PlayerSkillToolApplicationService` に awakened facade を追加して server-side defaults を 1 箇所に集約し、`PlayerSupplementalContextBuilder` で hidden-first availability を不足資源まで拡張、`WorldToolExecutor` と default wiring の統合テストで runtime proof を閉じる。

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Python | >=3.10 | 実装言語 | 既存の application/domain/service 層が dataclass と repository パターンで統一されている |
| pytest | 8.4.1 | テスト実行 | `pytest.ini` と既存 skill / llm / world テスト群が phase10 の回帰証明にそのまま使える |
| ai-rpg-world | 0.1.0 | 対象パッケージ | local package として `uv run` で build/test される前提が既に整っている |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| pydantic | 2.8.2 | 補助 validation 依存 | この phase の中心ではないが既存 app 依存として存在する |
| litellm | 1.44.9 | LLM backend | tool schema / runtime path の既存 wiring 前提としてのみ意識する |
| coverage | 7.9.2 | 回帰確認 | phase gate の補助として使う |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `PlayerSkillToolApplicationService` に awakened facade を追加 | `WorldToolExecutor` から `SkillCommandService` を直接叩く | server-side defaults 注入点が executor に漏れ、skill API の一貫性が崩れる |
| builder で hidden-first 判定を強化 | availability resolver だけで不足資源判定を持つ | current state / prompt / available tools の整合が崩れやすい |
| 既存 world executor path を使う | 新規 awakened 専用 executor を作る | skill tool 群が二系統になり、SKRT-02 の共存証明が重くなる |

**Installation:**
```bash
python -m pip install -e .
```

## Architecture Patterns

### Recommended Project Structure
```text
src/ai_rpg_world/
├── application/skill/services/player_skill_tool_service.py          # awakened facade と default 注入
├── application/skill/contracts/commands.py                          # 既存 command を再利用
├── application/llm/services/executors/world_executor.py             # awakened handler と成功文面
├── application/llm/wiring/__init__.py                               # default wiring 回帰
├── application/world/services/player_supplemental_context_builder.py# hidden-first availability 強化
└── application/world/contracts/dtos.py                              # 現行 AwakenedActionDto を継続利用

tests/
├── application/skill/services/test_player_skill_tool_service.py
├── application/llm/services/executors/test_world_executor.py
├── application/llm/test_tool_command_mapper.py
├── application/llm/test_llm_wiring.py
└── application/world/services/test_player_supplemental_context_builder.py
```

### Pattern 1: Facade Owns Server-Side Defaults
**What:** LLM-facing facade が `loadout_id` だけを受け、`current_tick`、duration、cooldown reduction、resource costs を server-side policy から埋めて `SkillCommandService` に渡す。
**When to use:** tool schema が intentionally thin で、application service 側に数値 policy を閉じ込めたい skill action。
**Example:**
```python
# Source pattern: src/ai_rpg_world/application/skill/services/player_skill_tool_service.py
self._skill_command_service.use_player_skill(
    UsePlayerSkillCommand(
        player_id=player_id,
        loadout_id=skill_loadout_id,
        slot_index=skill_slot_index,
        current_tick=self._time_provider.get_current_tick().value,
        ...
    )
)
```

### Pattern 2: Hidden-First Availability Comes From Current State
**What:** `available tools` の真偽は resolver や executor ではなく current-state builder が持つ `awakened_action` の有無に合わせる。
**When to use:** prompt に表示される候補と available tool list を完全に一致させたいとき。
**Example:**
```python
# Source: src/ai_rpg_world/application/llm/services/availability_resolvers.py
class SkillActivateAwakenedModeAvailabilityResolver(IAvailabilityResolver):
    def is_available(self, context: Optional[PlayerCurrentStateDto]) -> bool:
        return context is not None and context.awakened_action is not None
```

### Pattern 3: Resolver Contract Stays Thin, Executor Formats Result
**What:** `awakened_action_label` は `loadout_id` のみへ解決し、成功/失敗の user-facing 文面は executor が担当する。
**When to use:** public tool contract を最小に保ちつつ、tool result を既存 `LlmCommandResultDto` 流儀へ揃えたいとき。
**Example:**
```python
# Source: src/ai_rpg_world/application/llm/services/tool_argument_resolver.py
target = self._require_target_type(
    awakened_label,
    runtime_context,
    "覚醒モード発動ラベル",
    (AwakenedActionToolRuntimeTargetDto,),
)
return {"loadout_id": target.skill_loadout_id}
```

### Pattern 4: Runtime Proof Uses Existing Skill Tool Chain
**What:** proof は isolated service test だけでなく、`available tools -> resolver -> mapper -> executor -> facade` の既存 chain で作る。
**When to use:** SKRT-02 のように「runtime path 上で確認できる」が要件に含まれるとき。
**Example:**
```python
# Source pattern: src/ai_rpg_world/application/llm/services/tool_command_mapper.py
world_executor = WorldToolExecutor(
    ...,
    skill_tool_service=skill_tool_service,
)
self._executor_map.update(world_executor.get_handlers())
```

### Anti-Patterns to Avoid
- **Executor 直結で defaults を埋める:** awakened numeric policy が world executor に漏れ、skill tooling の責務が崩れる。
- **Visibility と execution rejection の二重実装:** builder で hidden にすべき条件を executor/service に寄せると prompt と available tools がずれる。
- **観測確認を service unit test だけで代用する:** SKRT-02 が要求する runtime proof を満たせない。
- **awakened 専用の別 wiring を足す:** 既存 skill tool family との共存回帰が弱くなる。

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| awakened label 解析 | executor 内の prefix 分解 | `DefaultToolArgumentResolver` の既存 target lookup | invalid label / kind 拒否が既に中央集約されている |
| resource gating の別状態管理 | LLM 専用の awakened availability cache | `PlayerSupplementalContextBuilder` + repository 読み取り | current state と tool visibility の不一致を防げる |
| tool 実行専用の awakened service | facade を迂回する専用 executor/service | `PlayerSkillToolApplicationService` 経由の既存 skill seam | server-side defaults と skill action API を 1 箇所に保てる |
| runtime proof の ad hoc script | 手動確認専用スクリプト | pytest ベースの mapper/wiring/current-state 回帰 | phase gate に残せる自動証拠になる |

**Key insight:** phase10 の難所は新機能追加よりも「既に薄く存在する awakened 契約を、既存 skill tool family と同じ seam で完結させる」ことです。新しい抽象化を増やすより、既存の facade / builder / executor / wiring を埋める方が正しいです。

## Common Pitfalls

### Pitfall 1: Server-Side Defaults が複数箇所に散る
**What goes wrong:** duration や resource cost が executor / wiring / facade の複数箇所で定義され、後から整合が取れなくなる。
**Why it happens:** `ActivatePlayerAwakenedModeCommand` が数値必須なので、呼び出し側で場当たり的に埋めたくなる。
**How to avoid:** awakened activation 用の default policy は facade の 1 箇所に集約し、executor は `loadout_id` を渡すだけにする。
**Warning signs:** 同じ numeric literal が複数ファイルに現れる。

### Pitfall 2: Hidden-First と不足資源判定が分離する
**What goes wrong:** tool は available だが実際には resource 不足で必ず失敗する状態が残る。
**Why it happens:** 現在の `build_awakened_action(...)` は「覚醒中かどうか」だけを見ている。
**How to avoid:** player status repository を builder に取り込み、resource sufficiency を current-state 生成時点で判定する。
**Warning signs:** available-tools provider テストは通るが、executor 統合で常に resource error になる。

### Pitfall 3: Owner mismatch / stale label を hidden 条件に混ぜる
**What goes wrong:** race や stale runtime まで hidden 条件に背負わせ、builder/query が過剰に複雑化する。
**Why it happens:** SKAW-03 の「非表示または失敗理由付き拒否」を 1 つの層で全部処理しようとする。
**How to avoid:** 通常の発動不能条件だけ hidden にし、owner mismatch や stale label は既存 exception path に任せる。
**Warning signs:** builder が write-side 整合性まで検証し始める。

### Pitfall 4: Runtime Proof が observation 不在のまま終わる
**What goes wrong:** tool 実行自体は成功するが、LLM 再開フローから発動確認できず SKRT-02 を満たさない。
**Why it happens:** service test と executor test だけで phase 完了と見なしてしまう。
**How to avoid:** wiring 経由の統合テストで、available tool exposure と runtime/observation 反映を同じシナリオで確認する。
**Warning signs:** plan の verification が `test_skill_command_service.py` に偏る。

### Pitfall 5: Success message が observation と競合する
**What goes wrong:** tool 結果で効果詳細を盛り込みすぎて、観測文と責務が重複する。
**Why it happens:** awakened は状態変化が大きいため、全部 tool result で説明したくなる。
**How to avoid:** executor の成功文面は短い完了通知だけに留め、観測が周辺共有を担う前提を守る。
**Warning signs:** executor success string に duration や buff 内容が入り始める。

## Code Examples

Verified patterns from repo sources:

### Awakened Label Resolves Without Numeric Payload
```python
# Source: src/ai_rpg_world/application/llm/services/tool_argument_resolver.py
def _resolve_activate_awakened_mode(
    self,
    args: Dict[str, Any],
    runtime_context: ToolRuntimeContextDto,
) -> Dict[str, Any]:
    awakened_label = args.get("awakened_action_label")
    target = self._require_target_type(
        awakened_label,
        runtime_context,
        "覚醒モード発動ラベル",
        (AwakenedActionToolRuntimeTargetDto,),
    )
    if target.skill_loadout_id is None:
        raise ToolArgumentResolutionException(
            f"覚醒モード発動に使えないラベルです: {awakened_label}",
            "INVALID_TARGET_KIND",
        )
    return {"loadout_id": target.skill_loadout_id}
```

### Current Builder Already Hides While Active
```python
# Source: src/ai_rpg_world/application/world/services/player_supplemental_context_builder.py
if (
    isinstance(is_active, bool)
    and is_active
    and isinstance(active_until_tick, int)
    and current_tick < active_until_tick
):
    return None
return AwakenedActionDto(
    skill_loadout_id=loadout.loadout_id.value,
    display_name="覚醒モードを発動",
)
```

### Command Service Already Owns Actual Activation
```python
# Source: src/ai_rpg_world/application/skill/services/skill_command_service.py
status.consume_resources(
    mp_cost=command.mp_cost,
    stamina_cost=command.stamina_cost,
    hp_cost=command.hp_cost,
)
loadout.activate_awakened_mode(
    current_tick=command.current_tick,
    duration_ticks=command.duration_ticks,
    cooldown_reduction_rate=command.cooldown_reduction_rate,
    actor_id=command.player_id,
)
```

## State of the Art

| Existing State | Required Phase 10 State | Evidence | Impact |
|----------------|-------------------------|----------|--------|
| tool definition / availability / resolver / UI label は既にある | 実行 facade・executor handler・runtime proof を追加する | local repo source | phase10 は wiring and proof closure が中心 |
| `build_awakened_action(...)` は「覚醒中」だけ hidden | resource insufficiency まで hidden-first に広げる | local repo source | SKAW-03 を current-state ベースで満たせる |
| `SkillCommandService.activate_player_awakened_mode(...)` は numeric payload 必須 | facade か policy object が server-side defaults を供給する | local repo source | SKAW-02 を public contract を変えずに満たせる |

**Deprecated/outdated:**
- `WorldToolExecutor` が skill tools を `use/equip/accept/reject` までしか知らない状態: phase10 では不十分。awakened handler 追加が必要。

## Open Questions

1. **server-side defaults をどこに置くか**
   - What we know: public tool contract は `loadout_id` のみで、`ActivatePlayerAwakenedModeCommand` には numeric fields が必要。
   - What's unclear: 既存コードベースに awakened 専用 config object はまだ見当たらない。
   - Recommendation: phase10 では `PlayerSkillToolApplicationService` に private default policy を置き、追加 config 化は deferred に回す。

2. **resource insufficiency を builder でどこまで判定できるか**
   - What we know: `PlayerSupplementalContextBuilder` は現在 `player_status_repository` を持っておらず、active state しか見ていない。
   - What's unclear: hidden 判定に必要な cost 値を builder が直接持つか、facade と共有する lightweight policy object を使うか。
   - Recommendation: planner は policy source を 1 箇所に定め、builder と facade の双方で参照可能な最小共有 seam を選ぶべき。

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | `pytest 8.4.1` |
| Config file | `pytest.ini` |
| Quick run command | `uv run pytest tests/application/llm/services/executors/test_world_executor.py tests/application/skill/services/test_player_skill_tool_service.py -x -k "awakened"` |
| Full suite command | `uv run pytest` |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| SKAW-01 | awakened tool が facade/executor 経由で実行できる | unit + integration | `uv run pytest tests/application/skill/services/test_player_skill_tool_service.py tests/application/llm/services/executors/test_world_executor.py -x -k "awakened"` | ❌ Wave 0 |
| SKAW-02 | numeric payload を public contract に出さず server-side defaults で実行する | unit | `uv run pytest tests/application/skill/services/test_player_skill_tool_service.py tests/application/llm/test_tool_command_mapper.py -x -k "awakened"` | ❌ Wave 0 |
| SKAW-03 | resource不足/覚醒中/loadout不整合の hidden or reject が成立する | unit + integration | `uv run pytest tests/application/world/services/test_player_supplemental_context_builder.py tests/application/llm/test_available_tools_provider.py -x -k "awakened"` | ⚠️ 部分的に存在 |
| SKRT-02 | awakened 発動が runtime path と skill tool family 共存回帰で確認できる | integration | `uv run pytest tests/application/llm/test_tool_command_mapper.py tests/application/llm/test_llm_wiring.py -x -k "awakened or skill"` | ❌ Wave 0 |

### Sampling Rate
- **Per task commit:** `uv run pytest tests/application/skill/services/test_player_skill_tool_service.py tests/application/llm/services/executors/test_world_executor.py -x -k "awakened"`
- **Per wave merge:** `uv run pytest tests/application/world/services/test_player_supplemental_context_builder.py tests/application/llm/test_available_tools_provider.py tests/application/llm/test_tool_argument_resolver.py tests/application/llm/test_tool_command_mapper.py tests/application/llm/test_llm_wiring.py -x -k "awakened or skill"`
- **Phase gate:** `uv run pytest`

### Wave 0 Gaps
- [ ] `tests/application/skill/services/test_player_skill_tool_service.py` — awakened facade が server-side defaults を埋めるテストが不足
- [ ] `tests/application/llm/services/executors/test_world_executor.py` — awakened handler と成功/失敗 result のテストが不足
- [ ] `tests/application/llm/test_tool_command_mapper.py` — awakened tool の mapper 経路回帰が不足
- [ ] `tests/application/llm/test_llm_wiring.py` — default wiring 上で awakened tool が skill family に含まれる統合証明が不足
- [ ] `tests/application/world/services/test_player_supplemental_context_builder.py` — resource insufficiency を hidden にする current-state テストが不足

## Sources

### Primary (HIGH confidence)
- Local repo source: `.planning/ROADMAP.md`, `.planning/REQUIREMENTS.md`, `.planning/STATE.md`, `.planning/phases/10-awakened-mode-tooling-and-runtime-proof/10-CONTEXT.md`
- Local repo source: `src/ai_rpg_world/application/skill/services/player_skill_tool_service.py`, `src/ai_rpg_world/application/skill/services/skill_command_service.py`, `src/ai_rpg_world/application/skill/contracts/commands.py`
- Local repo source: `src/ai_rpg_world/application/llm/services/tool_argument_resolver.py`, `src/ai_rpg_world/application/llm/services/tool_definitions.py`, `src/ai_rpg_world/application/llm/services/availability_resolvers.py`, `src/ai_rpg_world/application/llm/services/executors/world_executor.py`, `src/ai_rpg_world/application/llm/services/tool_command_mapper.py`, `src/ai_rpg_world/application/llm/wiring/__init__.py`
- Local repo tests: `tests/application/world/services/test_player_supplemental_context_builder.py`, `tests/application/skill/services/test_skill_command_service.py`, `tests/application/llm/test_available_tools_provider.py`, `tests/application/llm/test_tool_argument_resolver.py`, `tests/application/llm/services/executors/test_world_executor.py`, `tests/application/llm/test_tool_command_mapper.py`, `tests/application/llm/test_llm_wiring.py`
- Local project config: `pyproject.toml`, `pytest.ini`, `uv run pytest --version`

### Secondary (MEDIUM confidence)
- None. Local repo sources were sufficient for this phase.

### Tertiary (LOW confidence)
- None.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - versions and tools are directly declared in `pyproject.toml` and confirmed via `uv run`
- Architecture: HIGH - phase10 seams are visible in local source and follow the established skill tool pattern
- Pitfalls: HIGH - all listed pitfalls arise from gaps or asymmetries directly observable in current code/tests

**Research date:** 2026-03-13
**Valid until:** 2026-04-12
