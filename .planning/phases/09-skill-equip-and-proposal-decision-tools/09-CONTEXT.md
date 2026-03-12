# Phase 9: Skill Equip And Proposal Decision Tools - Context

**Gathered:** 2026-03-13
**Status:** Ready for planning

<domain>
## Phase Boundary

LLM が `skill_equip`、`skill_accept_proposal`、`skill_reject_proposal` を使って skill loadout の装備変更と進化提案の意思決定を完了できるようにする。ここで決めるのは「実行後に何を成功として見せるか」「提案受諾と loadout 反映をどう一体として扱うか」「境界ケースを user-facing にどう返すか」であり、覚醒モード発動や追加の runtime target 設計は扱わない。

</domain>

<decisions>
## Implementation Decisions

### Success result messaging
- 成功メッセージは操作対象の具体名まで返す
- `skill_equip` は装備したスキル名と装備先スロット名が一文で分かる結果にする
- `skill_accept_proposal` は「提案を受諾した」だけで終わらせず、loadout 反映まで完了したことを同じ成功メッセージで明記する
- `skill_reject_proposal` は却下した提案名が分かる文面にする
- 提案理由や proposal type は成功メッセージへ含めず、判断時に見えている runtime context に委ねる

### Failure result messaging
- 失敗時は既存の `exception_result(...)` と例外メッセージ整形を基本とする
- equip / proposal 専用の過度な誘導文は足さず、`INVALID_TARGET_LABEL` / `INVALID_TARGET_KIND` と service 側例外を主に使う
- stale label や target mismatch のような Phase 8 起点の不整合を優先して検証対象にする

### Proposal acceptance semantics
- 提案受諾は「progress 更新」と「loadout 反映」を切り離さず、装備まで完了して初めて成功とみなす
- 受諾成功時は新しく反映されたスキル名と装備先スロットを返す
- 既存スロットが置き換わる場合でも、成功メッセージは新しく反映された側を主に伝え、置換前スキル名は必須にしない
- 受諾後の loadout 反映で失敗した場合は部分成功を user-facing に出さず、ツール全体を失敗として扱う

### Equip / conflict semantics
- `skill_equip` で埋まっているスロットを選んだ場合は通常の装備変更として許容する
- 操作後に equip 候補や proposal 候補が変わることは、今回のツール結果ではなく次ターンの runtime context 再取得で見せる
- 操作完了時に「候補一覧が更新される」などの補助文言は必須にしない

### Claude's Discretion
- 成功メッセージの具体文面と語尾
- executor 内でどこまで表示名を組み立てるか、service 戻り値 DTO を足すかの実装形
- 既存 observation event 文言との重複をどこまで許容するか

</decisions>

<specifics>
## Specific Ideas

- `skill_equip` 成功文面は「{skill_name} を {slot_name} に装備しました。」のように短く確定的にする
- `skill_accept_proposal` 成功文面は「{proposal_name} を受諾し、{slot_name} に装備しました。」のように受諾と反映を同じ完了結果として扱う
- `skill_reject_proposal` 成功文面は「{proposal_name} を却下しました。」のように対象が残る形にする
- 失敗時の親切さを executor で盛りすぎず、ラベル不整合とドメイン拒否が既存ハンドリング経由で読めることを優先する

</specifics>

<code_context>
## Existing Code Insights

### Reusable Assets
- `src/ai_rpg_world/application/skill/services/skill_command_service.py`: `equip_player_skill(...)`、`accept_skill_proposal(...)`、`reject_skill_proposal(...)` が既に存在し、proposal accept は内部で loadout 反映まで行う
- `src/ai_rpg_world/application/llm/services/tool_argument_resolver.py`: `skill_equip` と proposal accept/reject の canonical arg 解決が既に実装されている
- `src/ai_rpg_world/application/llm/services/tool_definitions.py`: `skill_equip`、`skill_accept_proposal`、`skill_reject_proposal` の public tool schema は登録済み
- `src/ai_rpg_world/application/llm/services/availability_resolvers.py`: equip 候補・slot・pending proposal の presence-based availability が既にある
- `src/ai_rpg_world/application/world/services/player_supplemental_context_builder.py`: equip 候補、slot、pending proposal の display_name を current state 側で組み立てている

### Established Patterns
- tool definition と argument resolver は Phase 8 で閉じているため、Phase 9 の主戦場は executor wiring と結果メッセージ整形になる
- `WorldToolExecutor` は成功時に簡潔な `LlmCommandResultDto` を返し、例外は `exception_result(...)` に寄せる
- `SkillCommandService.accept_skill_proposal(...)` は progress 更新後に loadout を取得し、offered skill を target slot に装備する一体処理になっている
- observation formatter 側には `skill_equipped` の既存イベント表現があるため、tool 結果と観測文の役割分担を意識する必要がある

### Integration Points
- `src/ai_rpg_world/application/llm/services/executors/world_executor.py` に `skill_equip` / `skill_accept_proposal` / `skill_reject_proposal` の handler 追加が必要
- `src/ai_rpg_world/application/llm/services/tool_command_mapper.py` と wiring で既存 `skill_tool_service` 経由の受け口をどう増やすかを決める必要がある
- 受諾成功メッセージ用に、proposal label から得た display name を executor が引き継ぐか、service 側で戻り値を返すかを planner が選ぶ必要がある
- Phase 10 では awakened mode と runtime proof を扱うため、このフェーズでは equip / proposal decision の execution path を先に閉じる

</code_context>

<deferred>
## Deferred Ideas

- 覚醒モード発動結果の user-facing ルール
- proposal accept 時に置換前スキル名まで必ず返す高詳細メッセージ
- 操作後候補差分をその場で全文返す richer result payload
- pursuit follow/chase 差分や group control など v1.1 外の拡張

</deferred>

---

*Phase: 09-skill-equip-and-proposal-decision-tools*
*Context gathered: 2026-03-13*
