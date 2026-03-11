# Requirements: AI RPG World

**Defined:** 2026-03-11
**Core Value:** LLMエージェントが、静的な目的地指定だけでなく、動的に移動する主体に対しても一貫した状態遷移とイベント駆動で行動を継続できること

## v1 Requirements

### Pursuit Core

- [x] **PURS-01**: LLM 制御プレイヤーはプレイヤーまたはモンスターを追跡対象として指定できる
- [ ] **PURS-02**: モンスターは既存の行動文脈の中で追跡対象を保持し、追跡開始状態へ遷移できる
- [ ] **PURS-03**: 追跡中の主体は、対象が見えている間、対象の最新既知位置に向けて既存の移動ルールで移動を継続できる
- [ ] **PURS-04**: 追跡対象が視界から外れた場合、主体は最後の既知位置まで追跡を継続できる
- [ ] **PURS-05**: 主体は明示コマンドまたは明示状態変更によって追跡を中断できる

### Pursuit Outcomes

- [x] **OUTC-01**: 追跡は `cancelled`、`target_missing`、`path_unreachable`、`vision_lost_at_last_known` のような構造化された理由で終了できる
- [x] **OUTC-02**: 追跡の開始、更新、失敗、中断はドメインイベントとして発行される
- [ ] **OUTC-03**: 追跡失敗イベントは LLM エージェントが次行動を判断できるだけの失敗理由を含む

### Runtime Integration

- [ ] **RUNT-01**: プレイヤー追跡は既存の `MovementApplicationService` とワールド tick の流れに統合される
- [x] **RUNT-02**: 追跡状態は静的な移動先/path 状態とは別に保持される
- [ ] **RUNT-03**: 追跡中の移動中断と追跡中断は区別して扱われ、観測イベントで移動が止まっても追跡状態の扱いを明示できる

### Observation And LLM

- [ ] **OBSV-01**: 追跡関連イベントは既存の observation パイプラインに接続される
- [ ] **OBSV-02**: 追跡失敗または中断後に、必要な場合は既存のイベント駆動で LLM ターン再開につなげられる

## v2 Requirements

### Advanced Pursuit

- **ADVP-01**: 追跡モードごとに `follow` と `chase` の振る舞い差分を詳細化できる
- **ADVP-02**: 追跡中断後に自動再開や一時停止/resume ポリシーを選べる
- **ADVP-03**: 最後の既知位置以降の探索・再捕捉ロジックを拡張できる

### Group Behavior

- **GRUP-01**: 複数主体の隊列追従や間隔制御を行える
- **GRUP-02**: 味方追従と敵追跡を脅威条件で切り替えられる

## Out of Scope

| Feature | Reason |
|---------|--------|
| 必ず追いつく保証 | 同速主体では不自然で、v1 の完了条件とも一致しない |
| NPC 一般対応 | 現時点ではプレイヤーとモンスターに絞る方がスコープが明確 |
| 連続ステアリング/物理ベース追従 | 現在の経路ベース移動モデルと合わず、過剰実装になる |
| 隊列・護衛・編隊行動 | まず単一対象への追跡基盤を成立させるべき |

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| PURS-01 | Phase 2 | Completed |
| PURS-02 | Phase 7 | Pending |
| PURS-03 | Phase 6 | Pending |
| PURS-04 | Phase 6 | Pending |
| PURS-05 | Phase 6 | Pending |
| OUTC-01 | Phase 1 | Completed |
| OUTC-02 | Phase 1 | Completed |
| OUTC-03 | Phase 7 | Pending |
| RUNT-01 | Phase 6 | Pending |
| RUNT-02 | Phase 1 | Completed |
| RUNT-03 | Phase 7 | Pending |
| OBSV-01 | Phase 7 | Pending |
| OBSV-02 | Phase 6 | Pending |

**Coverage:**
- v1 requirements: 13 total
- Mapped to phases: 13
- Unmapped: 0 ✓

---
*Requirements defined: 2026-03-11*
*Last updated: 2026-03-11 after milestone gap planning*
