# Phase 10: Awakened Mode Tooling And Runtime Proof - Context

**Gathered:** 2026-03-13
**Status:** Ready for planning

<domain>
## Phase Boundary

LLM が `skill_activate_awakened_mode` を使って覚醒モードを安全に発動できるようにし、その結果が runtime path と observation 上で確認できる状態まで閉じる。ここで決めるのは「発動結果を user-facing にどう返すか」「どの条件で tool を hidden / reject に振り分けるか」「何をもって runtime proof 完了とするか」であり、覚醒中の効果詳細や追加の強化表現そのものを拡張することは扱わない。

</domain>

<decisions>
## Implementation Decisions

### Success result messaging
- `skill_activate_awakened_mode` の成功文面は短く確定的にし、発動者本人への即時フィードバックとして返す
- tool 結果では「覚醒モードを発動した」という完了事実を主に伝え、周辺への伝播や追加の描写は observation 側へ委ねる
- コスト・duration・cooldown 軽減率などの内部数値は、通常の成功結果では user-facing に出さない
- user-facing の成立時点は tool 実行成功時点とみなし、observation は追認・周辺共有の役割で扱う

### Availability expectations
- リソース不足や既に覚醒中など、通常の発動不能条件は tool 候補自体を出さない方針にする
- 特に「覚醒中」は現在の `awakened_action` builder 方針どおり action label を出さない
- loadout owner mismatch や stale runtime label など、事前に完全には防げない整合性崩れは実行時失敗で扱う
- 実行時失敗の文面は覚醒専用に盛り込みすぎず、既存の `exception_result(...)` と service 例外ハンドリングを基本とする

### Runtime proof expectations
- Phase 10 の完了証明には、LLM wiring 経由の実行 path と observation / runtime 反映の両方を必要とする
- ただし observation 側は「覚醒発動が確認できること」を主眼とし、周辺効果の詳細検証までは必須にしない
- 既存 skill 系 tool との共存確認は最低限の回帰でよく、equip / proposal まで含めた大規模シナリオ証明は必須にしない
- テスト方針は unit と integration を半々にし、builder / resolver / executor の局所確認と wiring 経由の結線確認を両立する

### Claude's Discretion
- 成功メッセージの最終文面と語尾
- 発動不能条件のうち、どこまで current state builder 側で hidden 判定し、どこから service 側拒否へ委ねるかの実装配分
- runtime proof で使う統合テストの具体シナリオ構成

</decisions>

<specifics>
## Specific Ideas

- 成功文面は「覚醒モードを発動しました。」のように短く閉じる
- 発動者本人には tool 結果で即時に返し、周辺プレイヤーや後続の見え方は既存 observation flow に載せる
- `awakened_action` は hidden-first を維持し、通常の発動不能状態を LLM が不用意に触れないようにする
- runtime proof では「tool が公開される -> resolver が `loadout_id` に解決する -> executor / service が発動する -> 観測に表れる」の一本線を確認できれば十分とする

</specifics>

<code_context>
## Existing Code Insights

### Reusable Assets
- `src/ai_rpg_world/application/world/services/player_supplemental_context_builder.py`: `build_awakened_action(...)` が既に単一 action label を返し、覚醒中は `None` を返す
- `src/ai_rpg_world/application/llm/services/ui_context_builder.py`: `AW1` 形式の awakened action label と runtime target を組み立てる既存パターンがある
- `src/ai_rpg_world/application/llm/services/availability_resolvers.py`: `context.awakened_action is not None` を用いた presence-based availability が既にある
- `src/ai_rpg_world/application/llm/services/tool_argument_resolver.py`: awakened action label から `loadout_id` だけを解決し、内部数値を LLM に要求しない contract が既にある
- `src/ai_rpg_world/application/skill/services/skill_command_service.py`: `activate_player_awakened_mode(...)` と server-side 数値パラメータ付き実行経路が既に存在する

### Established Patterns
- Phase 8 までで tool definition / runtime target / argument resolution は整っているため、Phase 10 の主戦場は executor wiring、availability の具体化、runtime proof になる
- skill 系 tool は成功時に簡潔な `LlmCommandResultDto` を返し、失敗時は `exception_result(...)` へ寄せる流儀がある
- hidden-first の availability と stale-label 時の実行時拒否は、他の tool 群でも使いやすい安全側パターンである

### Integration Points
- `src/ai_rpg_world/application/llm/services/executors/world_executor.py` に `skill_activate_awakened_mode` の handler を追加する必要がある
- wiring 側で `SkillCommandService.activate_player_awakened_mode(...)` へ接続し、server-side defaults を供給する経路を閉じる必要がある
- current state / observation 側で、覚醒発動結果が runtime path から確認できることを統合テストで証明する必要がある

</code_context>

<deferred>
## Deferred Ideas

- 覚醒中の効果詳細や数値を user-facing に豊富表示すること
- 覚醒発動後の後続行動ボーナスまで含めた高粒度 observation 検証
- equip / proposal / awakened をすべて同一長尺シナリオで証明する重い E2E
- v1.1 外の pursuit / group control 拡張

</deferred>

---

*Phase: 10-awakened-mode-tooling-and-runtime-proof*
*Context gathered: 2026-03-13*
