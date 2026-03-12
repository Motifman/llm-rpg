# Requirements: AI RPG World

**Defined:** 2026-03-12
**Core Value:** LLMエージェントが、ワールド状態とイベント駆動の文脈を踏まえて、自律的に次の行動を安全に選べること。

## v1.1 Requirements

### Skill Loadout Tools

- [ ] **SKTL-01**: LLM 制御プレイヤーは現在の runtime context に出ている候補から装備対象スキルを選び、指定 loadout slot に装備できる
- [ ] **SKTL-02**: `skill_equip` は人間向けラベルから `loadout_id` / `deck_tier` / `slot_index` / `skill_id` を解決して実行できる

### Skill Proposal Decisions

- [ ] **SKPR-01**: LLM 制御プレイヤーは現在保留中のスキル進化提案を候補一覧から選んで受諾できる
- [ ] **SKPR-02**: LLM 制御プレイヤーは現在保留中のスキル進化提案を候補一覧から選んで却下できる

### Awakened Mode Control

- [ ] **SKAW-01**: LLM 制御プレイヤーは専用ツールで覚醒モードを発動できる
- [ ] **SKAW-02**: 覚醒モード発動ツールは LLM に内部数値を要求せず、コスト・持続時間・クールダウン軽減率はサーバ側設定で決定される
- [ ] **SKAW-03**: 覚醒モード発動ツールは、リソース不足・発動中・対象 loadout 不在などの条件では利用候補に出ない

### Runtime And Observation Integration

- [ ] **SKRT-01**: skill 系 tool runtime context は proposal・equip slot・装備候補・awakened action の判断に必要なラベル候補を提供できる
- [ ] **SKRT-02**: skill 装備・proposal 意思決定・覚醒発動の結果は既存 observation / LLM 再開フローと矛盾しない形で runtime path 上で確認できる

## vNext Requirements

### Pursuit Extensions

- **ADVP-01**: 追跡モードごとに `follow` と `chase` の振る舞い差分を詳細化できる
- **ADVP-02**: 追跡中断後に自動再開や一時停止/resume ポリシーを選べる
- **ADVP-03**: 最後の既知位置以降の探索・再捕捉ロジックを拡張できる

### Group Control

- **GRUP-01**: 複数主体の隊列追従や間隔制御を行える
- **GRUP-02**: 味方追従と敵追跡を脅威条件で切り替えられる

## Out of Scope

| Feature | Reason |
|---------|--------|
| pursuit follow/chase behavioral redesign | v1.1 は skill tooling を優先するため |
| formation / group pursuit controls | 単体プレイヤーの skill decision path を先に閉じるため |
| LLM が覚醒モードのコストや duration を直接指定する | ルール一貫性と安全性を崩しやすいため |

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| SKRT-01 | Phase 8 | Pending |
| SKTL-02 | Phase 8 | Pending |
| SKTL-01 | Phase 9 | Pending |
| SKPR-01 | Phase 9 | Pending |
| SKPR-02 | Phase 9 | Pending |
| SKAW-01 | Phase 10 | Pending |
| SKAW-02 | Phase 10 | Pending |
| SKAW-03 | Phase 10 | Pending |
| SKRT-02 | Phase 10 | Pending |

**Coverage:**
- v1.1 requirements: 9 total
- Mapped to phases: 9
- Unmapped: 0 ✓

---
*Requirements defined: 2026-03-12*
*Last updated: 2026-03-12 after starting milestone v1.1 LLM Skill Tooling*
