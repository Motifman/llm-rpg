# Phase 8: Skill Runtime Context And Tool Contracts - Context

**Gathered:** 2026-03-12
**Status:** Ready for planning

<domain>
## Phase Boundary

skill 系ツールを LLM に安全に見せるための runtime target・tool definition・argument resolution を整える。ここで決めるのは「候補をどう見せるか」「どのラベルを canonical args に解決するか」「どの条件で tool を公開するか」であり、実際の equip / proposal accept-reject / awakened 発動処理そのものは後続フェーズで閉じる。

</domain>

<decisions>
## Implementation Decisions

### Label shape
- 装備系は action-first とし、装備候補スキルラベルと装備先 slot ラベルを分けて出す
- `skill_equip` は分離されたラベル同士を組み合わせて canonical args へ解決する
- 進化提案は proposal 1件につき 1 ラベルを出し、`accept` / `reject` の両方から同じ proposal label を使う
- slot は通常デッキと覚醒デッキを分けた tiered slot として見せる
- 覚醒モードは発動可能時のみ単一 action label を出す

### Tool contract expectations
- 既存の `combat_use_skill` と同じく、人間向けラベルから内部 ID を解決する contract を維持する
- LLM には raw `skill_id` や `slot_index` を直接選ばせない
- 覚醒モードは「発動するか」の意思決定のみを tool contract に含め、数値パラメータは含めない

### Availability expectations
- Phase 8 の段階で availability 設計の土台を入れ、後続フェーズで具象化しやすいようにする
- proposal・slot・awakened action は runtime context に存在しない場合、対応 tool は候補に出せない前提で設計する

### Claude's Discretion
- proposal / slot / awakened action 用の label prefix 命名
- UI context 上での補助文言や並び順
- 既存 `ToolRuntimeTargetDto` を拡張するか、専用 DTO を足すかの実装方針

</decisions>

<specifics>
## Specific Ideas

- 既存の `K1` のような skill ラベル流儀を踏襲しつつ、equip は「スキル候補」と「装備先」を別々に選ばせたい
- 進化提案は accept / reject で別ラベルにせず、同じ提案候補を見て意思決定だけ分けたい
- 覚醒モードは loadout ごとの複雑な選択ではなく、まずは「今発動できるなら 1 action」として見せたい

</specifics>

<code_context>
## Existing Code Insights

### Reusable Assets
- `src/ai_rpg_world/application/llm/services/ui_context_builder.py`: 既存の skill / quest / conversation label 列挙パターンを再利用できる
- `src/ai_rpg_world/application/llm/contracts/dtos.py`: `ToolRuntimeTargetDto` と `SkillToolRuntimeTargetDto` を起点に新しい runtime target を表現できる
- `src/ai_rpg_world/application/llm/services/tool_argument_resolver.py`: tool 名ごとに label を canonical args に変換する既存の分岐点
- `src/ai_rpg_world/application/llm/services/tool_definitions.py`: 新規 tool definition と availability resolver の登録点
- `src/ai_rpg_world/application/llm/services/availability_resolvers.py`: `CombatUseSkillAvailabilityResolver` などの単純な公開条件パターンがある

### Established Patterns
- UI context builder が label 一覧と runtime target 辞書を同時に組み立てる
- argument resolver が label kind を検証し、不正な組み合わせを `ToolArgumentResolutionException` で拒否する
- world executor が tool 成功時のメッセージを整形し、例外は `exception_result(...)` に寄せる
- 新規 tool は `tool_constants.py`、`tool_definitions.py`、`tool_argument_resolver.py`、executor の 4 点セットで増える

### Integration Points
- `ToolRuntimeContextDto.targets` に proposal / slot / awakened action を追加する必要がある
- `register_default_tools(...)` と wiring 側の `combat_enabled` 周辺が skill tool 群の公開条件に関わる
- 後続フェーズで `SkillCommandService` の `equip_player_skill(...)`、`accept_skill_proposal(...)`、`reject_skill_proposal(...)`、`activate_player_awakened_mode(...)` へ接続される

</code_context>

<deferred>
## Deferred Ideas

- equip 候補を「スキルと slot の組み合わせ済みラベル」で見せる案
- 覚醒モードを loadout ごとに選ばせる案
- pursuit follow/chase 差分や group control など v1.1 外の機能拡張

</deferred>

---

*Phase: 08-skill-runtime-context-and-tool-contracts*
*Context gathered: 2026-03-12*
