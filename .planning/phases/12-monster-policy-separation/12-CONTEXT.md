# Phase 12: Monster Policy Separation - Context

**Gathered:** 2026-03-14
**Status:** Ready for planning

<domain>
## Phase Boundary

`WorldSimulationService` facade と Phase 11 で導入した stage 境界を保ったまま、monster lifecycle / behavior 周辺の業務ルールを、より小さく読みやすい policy / 協調オブジェクトへ分離する。Phase 12 では monster rule の読みやすさと responsibility boundary を改善するのであり、tick 順序の再設計や新しい monster capability の追加は扱わない。

</domain>

<decisions>
## Implementation Decisions

### Monster behavior の読み口
- monster behavior は「観測を作る → 状態を決める → 失敗を確定する → 行動を解く → 記録する」という一本道 coordinator として上から読める形を優先する。
- ただし coordinator が全判定を抱え込まないよう、pursuit failure と foraging は専任ルールとして coordinator から読める位置に分離する。
- `WorldSimulationService` facade は order coordinator のまま残し、Phase 12 の分離先は facade の外側で読める monster behavior 協調オブジェクト群とする。

### Survival / lifecycle の境界
- 飢餓死と老衰判定は behavior 側の gate から外し、spawn / respawn と同じ lifecycle 側の「生存進行」文脈へ寄せる。
- lifecycle は大きく `spawn系` と `survival系` の 2 つの読み口に分けたい。
- spawn と respawn は完全分離ではなく、同じ coordinator 内で「新規 spawn」と「既存個体の respawn」の分岐が見える形にする。
- survival では「生き延びる / 死ぬ / 餌を求めて移る」を近い文脈で読めるようにする。

### Pursuit failure の責務
- monster pursuit の失敗確定は action resolver の内部責務に吸収せず、behavior coordinator の前後から呼べる専任ルールとして分離する。
- `selected_target` 不在、`last_known` 到達、`TARGET_MISSING` / `VISION_LOST_AT_LAST_KNOWN` など、Phase 5 で固定した pursuit の意味づけを壊さない。
- Phase 12 では「どこで failure を確定するか」を読みやすくすることが主目的であり、monster pursuit の語彙自体は既存方針を引き継ぐ。

### Foraging の責務
- 餌の観測と選択は target context へ吸収せず、monster behavior から読める独立 foraging ルールとして切り出す。
- foraging は pursuit / combat と別の意図として読めることを優先する。
- behavior coordinator からは「foraging facts を作る」「foraging rule が target を返す」という関係が見える形を望む。

### Hunger migration policy の形
- Phase 12 の hunger migration policy は「候補選定ロジック」が単独で読めることを最優先にする。
- policy は repository 非依存とし、「飢餓が閾値以上」「嗜好する餌がない」「spot に餌がない」といった facts を入力として受け取る。
- 1 tick に 1 体、最も飢餓が高い個体を選ぶ判定を policy に閉じ込める。
- 同率時は新しい複雑な優先順位を増やさず、入力順や既存順を尊重する扱いでよい。
- 接続先の選び方は policy の主責務に含めず、Phase 12 では「誰を移住させるか」を中心に切り出す。

### Dependency boundary
- 判定は repository 非依存、適用だけ application 側依存、を Phase 12 の基本方針にする。
- map / repository / transition service を触る保存・配置変更は application / stage 側に残してよい。
- 完全な dependency inversion を目的化せず、「業務ルールが単体で読める」状態を優先する。

### Claude's Discretion
- coordinator / policy / rule / evaluator など最終命名
- foraging facts と pursuit facts を別 DTO にするか、より薄い値の束にするか
- lifecycle の中で starvation / old age / migration を 1 つの survival collaborator にまとめるか、近接した複数 rule にするか

</decisions>

<specifics>
## Specific Ideas

- Phase 12 は「monster behavior を読むときに private helper を飛び回らなくてよい状態」に近づけたい。
- monster behavior は大きな分岐木よりも、一本道 coordinator と専任 rule の組み合わせで理解できる方がよい。
- hunger migration は接続先決定より前に、「誰が移住候補で、誰が選ばれるのか」を独立に読めるのが大事。
- 新しい monster capability を足すのではなく、既存ルールの責務境界を見える化したい。

</specifics>

<code_context>
## Existing Code Insights

### Reusable Assets
- `src/ai_rpg_world/application/world/services/world_simulation_monster_behavior_stage_service.py`: 現在は actor 行動可否判定と `_process_single_actor_behavior()` 呼び出しを束ねており、behavior coordinator への移行起点になる。
- `src/ai_rpg_world/application/world/services/world_simulation_monster_lifecycle_stage_service.py`: spawn / respawn / hunger migration を束ねているため、Phase 12 の spawn系 / survival系 分離の入口として使える。
- `src/ai_rpg_world/application/world/services/world_simulation_service.py`: `_process_spawn_and_respawn_by_slots()`, `_process_respawn_legacy()`, `_process_single_actor_behavior()`, `_process_hunger_migration_for_spot()` が rule 抽出の元になる。
- `src/ai_rpg_world/application/world/services/monster_action_resolver.py`: action resolver は chase / search / flee / forage の最終アクション解決点として残っており、pursuit failure の責務分離境界を考える基準になる。

### Established Patterns
- Phase 11 で `WorldSimulationService` は facade / order coordinator として残す方針が固定している。
- Phase 5 で monster pursuit は `CHASE` / `SEARCH` を active pursuit とみなし、`last-known` 到達時の failure semantics を既に決めている。
- 現在の world simulation は callback で既存 helper を再利用する incremental リファクタ方針を取っており、Phase 12 でも behavior-safe な段階分離が前提になる。
- repository や map 依存を完全に消すより、判定ロジックを facts ベースで外へ出す方がこの milestone の目的に合う。

### Integration Points
- hunger / old-age 判定は現在 `WorldSimulationMonsterBehaviorStageService._can_actor_act()` にあり、Phase 12 の lifecycle 側へ移す主要候補。
- pursuit failure は `_resolve_monster_pursuit_failure_reason()` と `_should_fail_monster_search_at_last_known()` に散っており、専任ルール化の統合点になる。
- foraging は `_build_feed_observation()` と `_spot_has_feed_for_monster()` に分かれており、behavior と migration の双方で再利用できる facts/evaluator 境界がありそう。
- hunger migration の適用は `_process_hunger_migration_for_spot()` で map transition と save を行っているため、Phase 12 では候補選定 policy と適用 orchestration の分割が自然。

</code_context>

<deferred>
## Deferred Ideas

- 飢餓移住の接続先選択ルールを賢くする改善
- monster action resolver 自体の大型再設計
- stage service / policy 単位テストの厚み付け全般
- 新しい monster behavior state や capability の追加

</deferred>

---

*Phase: 12-monster-policy-separation*
*Context gathered: 2026-03-14*
