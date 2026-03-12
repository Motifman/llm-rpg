# Phase 9: Skill Equip And Proposal Decision Tools - Research

**Researched:** 2026-03-13
**Domain:** LLM skill equip / proposal decision execution, executor wiring, and result messaging
**Confidence:** HIGH

## User Constraints

### Locked Decisions
- 成功メッセージは操作対象の具体名まで返す
- `skill_equip` は装備したスキル名と装備先スロット名が一文で分かる結果にする
- `skill_accept_proposal` は受諾と loadout 反映を同じ成功結果として扱う
- `skill_reject_proposal` は却下した提案名が分かる文面にする
- 提案理由や `proposal_type` は成功メッセージへ含めない
- `skill_equip` のスロット上書きは通常の装備変更として許容する
- 候補一覧の更新は次ターンの runtime context 再取得で見せる

### Failure Expectations
- 失敗時は既存の `exception_result(...)` を基本とする
- equip / proposal 専用の厚いガイド文は不要
- stale label / target mismatch など Phase 8 起点の不整合を優先して検証する

### Architecture Guardrails
- Phase 8 で確定した label-driven contract を崩さない
- raw `skill_id` / `slot_index` / `proposal_id` を public schema に露出しない
- executor で label 文字列を再解釈しない
- 覚醒モードの実行は Phase 10 に送る

### Deferred Ideas (OUT OF SCOPE)
- 覚醒モード実行結果の user-facing ルール
- proposal accept 時に置換前スキル名まで必須表示する高詳細結果
- 操作後候補差分をその場で全文返す richer result payload
- proposal observation formatter の改善

## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| SKTL-01 | LLM 制御プレイヤーは現在の runtime context に出ている候補から装備対象スキルを選び、指定 loadout slot に装備できる | `skill_equip` の canonical args を既存 resolver から executor へ流し、world executor から skill tool facade を呼び出す |
| SKPR-01 | LLM 制御プレイヤーは現在保留中のスキル進化提案を候補一覧から選んで受諾できる | proposal label から解決済みの `progress_id` / `proposal_id` を facade 経由で command service に接続し、成功時は受諾 + 装備反映を 1 結果として返す |
| SKPR-02 | LLM 制御プレイヤーは現在保留中のスキル進化提案を候補一覧から選んで却下できる | proposal label から解決済みの canonical args を使い、proposal reject を facade / executor から実行する |

## Summary

Phase 9 は新しい skill decision label を作るフェーズではなく、Phase 8 で確立した `tool definitions -> argument resolver -> executor -> application service` の最後の 2 段を閉じるフェーズです。現状は `skill_tool_service` が `use_skill(...)` しか持たず、`WorldToolExecutor` も `combat_use_skill` しか処理しないため、公開済みの `skill_equip` / `skill_accept_proposal` / `skill_reject_proposal` は contract だけ存在して execution path が未接続です。

既存パターンを見ると、表示用の情報は service 戻り値で返すより、resolver が canonical args に display 用フィールドを添えて executor がそのまま成功メッセージを組む方が整合的です。`combat_use_skill` はすでに `skill_display_name` / `target_display_name` を canonical args に載せており、同じ手法を equip / proposal に拡張すれば、application service を read-model や UI 文言責務で汚さずに済みます。

**Primary recommendation:** `PlayerSkillToolApplicationService` を Phase 9 用 facade として拡張し、`WorldToolExecutor` に 3 つの handler を追加する。表示名は `DefaultToolArgumentResolver` が runtime target から canonical args へ display-only fields として引き継ぎ、executor が既存 `LlmCommandResultDto` 成功文面を構築する。

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Python | >=3.10 | 実装言語 | 既存コードベース全体が Python dataclass / service 構成 |
| pytest | 8.4.1 | テスト実行 | application/llm、application/skill、wiring テストが既存で揃っている |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| unittest.mock | stdlib | facade / executor / wiring 差し替えテスト | mapper / executor unit test で使用 |
| coverage | 7.9.2 | 変更影響確認 | フェーズ完了時の回帰確認 |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| resolver が display 名を canonical args に添付 | service から result DTO を返す | application service が UI 向け責務を持ち始め、既存 `use_skill()` の void-style facade と不整合 |
| `PlayerSkillToolApplicationService` 拡張 | executor から `SkillCommandService` を直接呼ぶ | wiring とテスト境界が増え、`combat_use_skill` だけ facade 経由という非対称な構成になる |
| world executor に 3 handler 追加 | 別 skill executor を新設 | world/combat 系 skill ツールが分散し、既存 mapper の構造メリットが薄れる |

## Architecture Patterns

### Recommended Project Structure
```text
src/ai_rpg_world/
├── application/skill/services/player_skill_tool_service.py   # equip / accept / reject facade を追加
├── application/llm/services/executors/world_executor.py      # 新規 skill handlers を追加
├── application/llm/services/tool_argument_resolver.py        # display-only fields を canonical args へ含める
├── application/llm/services/tool_command_mapper.py           # 既存 world executor wiring をそのまま活用
└── application/llm/wiring/__init__.py                        # facade 拡張に追随する wiring テスト対象
```

### Pattern 1: Facade Keeps LLM-Facing Skill API Cohesive
**What:** `PlayerSkillToolApplicationService` を LLM 向け skill API の入口として維持し、`use_skill` に加えて `equip_skill` / `accept_skill_proposal` / `reject_skill_proposal` を持たせる。  
**Why:** `ToolCommandMapper` と `WorldToolExecutor` は「skill tool service があるか」で combat-enabled skill tools をまとめて扱っているため、facade の責務を広げる方が最小変更。  
**Example anchor:** `src/ai_rpg_world/application/skill/services/player_skill_tool_service.py`

### Pattern 2: Resolver Carries Display-Only Fields
**What:** canonical args は command service に必要な numeric fields に加え、executor の成功文面に使う `*_display_name` を含めてもよい。  
**Why:** `combat_use_skill` がすでにこの形を採用しており、executor は repository 再読込なしで文面を返せる。  
**Example anchor:** `src/ai_rpg_world/application/llm/services/tool_argument_resolver.py::_resolve_combat_use_skill`

### Pattern 3: Executor Owns User-Facing Success Messages
**What:** application service は domain/action の完了だけを担い、`LlmCommandResultDto(success=True, message=...)` は executor が作る。  
**Why:** 既存 world executor 群と一貫し、例外はそのまま `exception_result(...)` に流せる。  
**Example anchor:** `src/ai_rpg_world/application/llm/services/executors/world_executor.py::_execute_combat_use_skill`

### Pattern 4: Observation Is Follow-Through, Not Primary Tool Result
**What:** equip/proposal 操作後の observation はドメインイベント経由で届くが、ツール成功結果そのものは executor が即時に返す。  
**Why:** `ObservationFormatter` には `skill_equipped` はあるが proposal accept/reject 専用 formatter は見当たらず、Phase 9 の要件を observation 修正に依存させるべきではない。  
**Example anchors:** `src/ai_rpg_world/application/observation/services/observation_formatter.py`, `src/ai_rpg_world/domain/skill/event/skill_events.py`

## Concrete Findings

### Finding 1: Public tool contracts already exist, execution path is the missing seam
- `TOOL_NAME_SKILL_EQUIP`, `TOOL_NAME_SKILL_ACCEPT_PROPOSAL`, `TOOL_NAME_SKILL_REJECT_PROPOSAL` は定義済み
- tool definitions と availability resolver も登録済み
- argument resolver も equip / proposal canonical payload を返せる
- つまり Phase 9 の本体は executor + facade + tests であり、schema を触りすぎる必要はない

### Finding 2: `PlayerSkillToolApplicationService` is intentionally thin and ready to expand
- 現在は `use_skill(...)` しか持たない
- `SkillCommandService` には equip / accept / reject 実装が既にある
- facade 側に command 生成を寄せれば world executor は facade API だけ知っていればよい

### Finding 3: Success display names should come from runtime labels, not post-hoc repository reads
- equip は skill label / slot label の双方が `display_name` を持っている
- proposal も label が `display_name` を持っている
- executor 実行後に repository から名前を引き直すと、Phase 9 の範囲外で query 責務が増える
- 既存 `combat_use_skill` と同様、resolver で `skill_display_name`, `slot_display_name`, `proposal_display_name` を乗せるのが自然

### Finding 4: Proposal accept is already atomic at service layer
- `SkillCommandService.accept_skill_proposal(...)` は progress 更新後に loadout を取得し、そのまま提案スキルを装備する
- 途中で spec/loadout が見つからなければ例外になるため、user decision どおり「装備反映込みで成功」が service の現実と一致する
- 逆に言えば、Phase 9 で partial success UI を作るべきではない

### Finding 5: Proposal accept/reject observation coverage is weaker than equip coverage
- `skill_equipped` formatter はある
- `SkillProposalGeneratedEvent` formatter はあるが accept / reject 専用イベント・formatter は明示的に確認できない
- したがって Phase 9 の runtime proof は、まず tool result と aggregate state 変化を主証拠にすべき

## Recommended Plan Split

### Plan 09-01: Extend skill tool facade and world executor
Scope:
- `PlayerSkillToolApplicationService` に equip / accept / reject API を追加
- `WorldToolExecutor` に 3 handler を追加
- `WorldToolExecutor` の service validation を update
- executor unit tests を追加

Why first:
- 公開済み tool contract を実際に動かす最短経路
- mapper / wiring は既存 seam を使えるため、まず executor 成功系を閉じる価値が高い

### Plan 09-02: Carry display names through resolver and lock user-facing messages
Scope:
- resolver が equip / proposal canonical args に display-only fields を含める
- equip / accept / reject の成功メッセージを context decision どおり固定
- stale label / invalid kind failure tests を増やす

Why second:
- 実行は 09-01 で通るが、Phase 9 のユーザー決定は「何を成功として見せるか」にある
- display path を分けると message changes が isolated になる

### Plan 09-03: Wiring and runtime regression coverage
Scope:
- `ToolCommandMapper` / wiring integration を更新
- available tools から canonical execution までの回帰テストを追加
- `skill_equip`, `skill_accept_proposal`, `skill_reject_proposal` が LLM path で共存することを証明

Why third:
- end-to-end 風の回帰は最後にまとめる方が安定
- Phase 10 の awakened mode 導入前に、Phase 9 の 3 tool が壊れない基盤を固められる

## Anti-Patterns to Avoid

- executor が label prefix を見て文字列分解すること
- equip/proposal 成功文面のためだけに query repository を大量注入すること
- proposal accept を「受諾成功だが装備失敗ありうる」UI にすること
- observation formatter の改善を Phase 9 の必須経路へ混ぜること
- `skill_tool_service` の callable validation を更新せずに handler だけ足すこと

## Common Pitfalls

### Pitfall 1: Extending handlers without updating service validation
`WorldToolExecutor._validate_world_services(...)` は `use_skill` callable だけを前提にしている。新 API を追加したのに validation を更新しないと、偽 service を許して実行時に落ちる。

### Pitfall 2: Losing display names after argument resolution
resolver が numeric canonical args だけ返すと、executor は成功時に generic 文言しか出せなくなる。Phase 9 の locked decision に反する。

### Pitfall 3: Over-testing observation instead of execution seam
proposal accept/reject は observation coverage が薄い。まず tool result と aggregate 更新を主に検証し、observation 依存の flaky な plan にしない。

### Pitfall 4: Forgetting mapper-level regression tests
`WorldToolExecutor` だけ通っても、`ToolCommandMapper` から handler が引けなければ LLM path は完結しない。

## Validation Architecture

### Test Framework
- `pytest`
- 既存 unit テスト中心
- LLM path は mapper / resolver / available tools / wiring を結ぶ application テストでカバー

### Phase Requirements → Test Map
| Requirement | Primary Tests | Secondary Tests |
|-------------|---------------|-----------------|
| SKTL-01 | `tests/application/llm/test_tool_command_mapper.py`, world executor tests, facade tests | wiring / available-tools integration that proves `skill_equip` is exposed and executable |
| SKPR-01 | `tests/application/llm/test_tool_command_mapper.py`, facade tests, `tests/application/skill/services/test_skill_command_service.py` accept coverage | resolver tests ensuring proposal labels stay valid and display names survive |
| SKPR-02 | `tests/application/llm/test_tool_command_mapper.py`, facade tests | resolver tests + mapper failure path for invalid proposal labels |

### Recommended New / Extended Test Files
- `tests/application/skill/services/test_player_skill_tool_service.py`
  Purpose: facade methods build the correct commands and delegate to `SkillCommandService`
- `tests/application/llm/test_tool_command_mapper.py`
  Purpose: mapper exposes equip / accept / reject through world executor and returns user-facing success messages
- `tests/application/llm/test_tool_argument_resolver.py`
  Purpose: equip/proposal canonical payload now includes display-only fields without weakening invalid-kind rejection
- `tests/application/llm/wiring/test_*` or nearest existing wiring test module
  Purpose: default wiring with `skill_tool_service` still registers and routes all Phase 9 tools

### Sampling Rate
- 100% of new public skill tool names in mapper/executor path
- 100% of new facade methods
- At least one stale-label / invalid-kind regression for equip and proposal labels
- At least one integration test that exercises `available tools -> resolver -> mapper execute` for a Phase 9 tool

### Wave 0 Gaps
- No separate Wave 0 is required for Phase 9; Phase 8 already created the relevant LLM/world test anchors
- Reuse and extend existing test modules rather than creating broad new scaffolding unless facade tests need a dedicated file

## Sources

### Primary (HIGH confidence)
- `src/ai_rpg_world/application/skill/services/player_skill_tool_service.py`
- `src/ai_rpg_world/application/skill/services/skill_command_service.py`
- `src/ai_rpg_world/application/llm/services/executors/world_executor.py`
- `src/ai_rpg_world/application/llm/services/tool_command_mapper.py`
- `src/ai_rpg_world/application/llm/services/tool_argument_resolver.py`
- `src/ai_rpg_world/application/llm/wiring/__init__.py`
- `src/ai_rpg_world/application/observation/services/observation_formatter.py`
- `tests/application/llm/test_tool_command_mapper.py`
- `tests/application/skill/services/test_skill_command_service.py`

### Secondary (MEDIUM confidence)
- `src/ai_rpg_world/application/llm/services/tool_definitions.py`
- `src/ai_rpg_world/application/llm/services/availability_resolvers.py`
- `src/ai_rpg_world/application/world/services/player_supplemental_context_builder.py`

## Metadata

- Research method: repository source inspection only
- Web used: no
- Ready for planning: yes
