# Roadmap: AI RPG World

## Overview

このロードマップは、既存のイベント駆動型 RPG ワールドに対して、動的な主体を追う追跡機能を段階的に導入するためのものです。まず追跡の語彙と状態を明確化し、その上でプレイヤー追跡、継続追跡、LLM 連携、モンスター整合へと進めることで、既存の移動・観測・イベント基盤を崩さずに機能追加します。

## Phases

- [x] **Phase 1: Pursuit Domain Vocabulary** - 追跡状態、終了理由、ライフサイクルイベントの基盤を定義する
- [x] **Phase 2: Player Pursuit Commands** - プレイヤーが追跡開始/中断できるアプリケーション入口を整える (completed 2026-03-11)
- [x] **Phase 3: Pursuit Continuation Loop** - 最新既知位置に基づく継続追跡をワールド tick に統合する (completed 2026-03-11)
- [x] **Phase 4: Observation And LLM Delivery** - 追跡結果を観測/LLM 再駆動パイプラインへ接続する (completed 2026-03-11)
- [x] **Phase 5: Monster Pursuit Alignment** - モンスター側の追跡語彙と状態遷移を新しい基盤に整合させる (completed 2026-03-11)
- [x] **Phase 6: Player Pursuit Runtime Assembly Closure** - プレイヤー追跡の開始から継続・再開までを非テスト実行経路に組み込む (completed 2026-03-11)
- [ ] **Phase 7: Pursuit Audit Evidence Backfill** - 監査を止めている検証成果物とトレーサビリティの欠落を解消する

## Phase Details

### Phase 1: Pursuit Domain Vocabulary
**Goal**: 追跡を静的移動と分離した明示的なドメイン概念として定義する
**Depends on**: Nothing (first phase)
**Requirements**: OUTC-01, OUTC-02, RUNT-02
**Success Criteria** (what must be TRUE):
1. 追跡状態が通常の移動先/path 情報とは独立して保持される
2. 追跡終了理由が構造化された enum/値として表現される
3. 追跡開始・更新・失敗・中断を表すドメインイベントが存在する
**Plans**: TBD

Plans:
- [x] 01-01: 追跡状態と失敗理由のドメイン型を定義する
- [x] 01-02: 追跡ライフサイクルイベントを定義する
- [x] 01-03: プレイヤー/モンスターの既存状態モデルへの組み込み方針を整える

### Phase 2: Player Pursuit Commands
**Goal**: プレイヤーが追跡開始/中断を明示的に行えるようにする
**Depends on**: Phase 1
**Requirements**: PURS-01, PURS-05
**Success Criteria** (what must be TRUE):
1. LLM 制御プレイヤーがプレイヤーまたはモンスターを追跡対象に指定できる
2. 明示コマンドまたは明示状態変更で追跡を止められる
3. 追跡開始/中断がドメイン状態とイベントに正しく反映される
**Plans**: TBD

Plans:
- [x] 02-01: プレイヤー追跡コマンドとバリデーションを追加する
- [x] 02-02: 中断コマンドと追跡状態クリアを実装する

### Phase 3: Pursuit Continuation Loop
**Goal**: 最新既知位置に基づく継続追跡を既存移動フローの中で成立させる
**Depends on**: Phase 2
**Requirements**: PURS-03, PURS-04, RUNT-01
**Success Criteria** (what must be TRUE):
1. 追跡中の主体が対象可視時に最新既知位置へ向かって移動を継続できる
2. 対象を見失っても最後の既知位置までは追跡を続けられる
3. 追跡継続は `MovementApplicationService` とワールド tick の流れに統合される
**Plans**: TBD

Plans:
- [x] 03-01: tick 時の追跡継続/再計画ロジックを追加する
- [x] 03-02: 最後の既知位置の更新と可視喪失ハンドリングを実装する
- [x] 03-03: 継続追跡の回帰テストを追加する

### Phase 4: Observation And LLM Delivery
**Goal**: 追跡の終了理由と中断結果を observation/LLM パイプラインへ接続する
**Depends on**: Phase 3
**Requirements**: OUTC-03, RUNT-03, OBSV-01, OBSV-02
**Success Criteria** (what must be TRUE):
1. 追跡関連イベントが observation パイプラインに接続される
2. 追跡失敗イベントに LLM が判断できる失敗理由が含まれる
3. 移動中断と追跡中断が区別され、観測イベントからも扱いが明示される
4. 追跡失敗または中断後に必要なら既存イベント駆動で LLM ターン再開へつながる
**Plans**: TBD

Plans:
- [x] 04-01: pursuit イベントの recipient/formatter/registry wiring を追加する
- [x] 04-02: LLM 再駆動に必要な structured payload を整える
- [x] 04-03: interruption と outcome の統合テストを追加する

### Phase 5: Monster Pursuit Alignment
**Goal**: モンスター側の追跡表現を新しい追跡基盤と整合させる
**Depends on**: Phase 4
**Requirements**: PURS-02
**Success Criteria** (what must be TRUE):
1. モンスターが既存行動文脈の中で追跡対象を保持し追跡開始状態へ遷移できる
2. モンスター追跡の理由語彙がプレイヤー追跡と基本的に揃う
3. 可視喪失時の last-known-position の扱いが明確にテストされる
**Plans**: TBD

Plans:
- [x] 05-01: モンスター側の追跡状態/理由語彙を整合させる
- [x] 05-02: モンスター追跡回帰テストを追加する

### Phase 6: Player Pursuit Runtime Assembly Closure
**Goal**: プレイヤー追跡の live runtime 配線を完成させ、追跡開始から継続・観測再開までを実行経路上で成立させる
**Depends on**: Phase 5
**Requirements**: PURS-03, PURS-04, PURS-05, RUNT-01, OBSV-02
**Gap Closure**: Closes audit gaps from v1.0 milestone audit
**Success Criteria** (what must be TRUE):
1. 非テストの composition path で `pursuit_command_service` と `pursuit_continuation_service` がともに配線される
2. プレイヤーの追跡開始が aggregate state 更新と world tick 継続へ接続される
3. 追跡失敗/中断が observation パイプライン経由で LLM turn resumption に届く
**Plans**: TBD

Plans:
- [x] 06-01: live runtime で pursuit command/continuation services を組み立てる
- [x] 06-02: player pursuit の start -> tick continuation -> observation resumption を接続する
- [x] 06-03: 非テスト bootstrap を通る回帰テストを追加する

### Phase 7: Pursuit Audit Evidence Backfill
**Goal**: 監査を阻害している verification/validation 成果物と要件トレースの欠落を解消する
**Depends on**: Phase 6
**Requirements**: PURS-02, OUTC-03, RUNT-03, OBSV-01
**Gap Closure**: Closes audit gaps from v1.0 milestone audit
**Success Criteria** (what must be TRUE):
1. Phase 3, 4, 5 に現在コードベースに対応した `VERIFICATION.md` が存在する
2. Phase 4 の `VALIDATION.md` が Nyquist compliant な状態に更新される
3. `REQUIREMENTS.md` のトレーサビリティが監査後の受け入れ状態と一致する
**Plans**: TBD

Plans:
- [x] 07-01: Phase 3 と Phase 5 の verification evidence を再構築する (completed 2026-03-11)
- [x] 07-02: Phase 4 の verification/validation artifacts を完了させる (completed 2026-03-12)
- [ ] 07-03: requirements traceability を監査結果に合わせて同期する

## Progress

**Execution Order:**
Phases execute in numeric order: 1 → 2 → 3 → 4 → 5 → 6 → 7

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Pursuit Domain Vocabulary | 3/3 | Completed | 2026-03-11 |
| 2. Player Pursuit Commands | 2/2 | Completed | 2026-03-11 |
| 3. Pursuit Continuation Loop | 3/3 | Complete   | 2026-03-11 |
| 4. Observation And LLM Delivery | 3/3 | Completed | 2026-03-11 |
| 5. Monster Pursuit Alignment | 2/2 | Completed | 2026-03-11 |
| 6. Player Pursuit Runtime Assembly Closure | 3/3 | Completed | 2026-03-11 |
| 7. Pursuit Audit Evidence Backfill | 2/3 | In Progress | - |
