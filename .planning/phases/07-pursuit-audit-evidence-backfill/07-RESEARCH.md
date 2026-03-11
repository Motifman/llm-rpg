# Phase 7 Research: Pursuit Audit Evidence Backfill

**Phase:** 07-pursuit-audit-evidence-backfill  
**Researched:** 2026-03-11  
**Focus:** planner guidance for PURS-02, OUTC-03, RUNT-03, OBSV-01, plus audit-traceability closure

## フェーズの位置づけ

Phase 7 は新機能実装フェーズではなく、監査受け入れを止めている証跡欠落を埋める是正フェーズである。実コードの主要ギャップは Phase 6 で閉じており、Phase 7 の中心は以下の 3 点に集約される。

1. Phase 3 / 4 / 5 に `VERIFICATION.md` を追加し、現在コードベースに対する受け入れ証跡を成立させる。
2. Phase 4 の `04-VALIDATION.md` を Nyquist compliant な状態へ更新する。
3. `REQUIREMENTS.md` の Traceability を、監査後の実際の受け入れ状態へ同期する。

重要なのは、単に欠けている Markdown を埋めることではない。監査はすでに「計画と summary はあるが、verification がないため partial/missing 扱い」と判定しているため、Phase 7 では「どの要件がどの phase で最終的に accept されるか」を文書レベルで再確定する必要がある。

## 監査ギャップの確定

`.planning/v1.0-MILESTONE-AUDIT.md` から、Phase 7 が直接閉じるべきギャップは次のとおり。

### 成果物欠落

- Phase 3 に `VERIFICATION.md` がない。
- Phase 4 に `VERIFICATION.md` がない。
- Phase 5 に `VERIFICATION.md` がない。
- Phase 4 の `04-VALIDATION.md` は `status: draft`, `nyquist_compliant: false`, `wave_0_complete: false` のまま。

### 要件トレース不整合

`REQUIREMENTS.md` の Traceability は現状の証跡と一致していない。特に以下がズレている。

- `PURS-02` が `Phase 7 / Pending` のままだが、実際の実装責務は Phase 5。
- `OUTC-03`, `RUNT-03`, `OBSV-01` が `Phase 7 / Pending` のままだが、実際の実装責務は Phase 4。
- Phase 6 完了後も `PURS-03`, `PURS-04`, `PURS-05`, `RUNT-01`, `OBSV-02` が Pending のまま。
- 監査 tech debt にある通り、Phase 1 の `OUTC-01`, `OUTC-02`, `RUNT-02` も未反映。

Planner への示唆: 成功条件は 4 ID だけを触れば足りるように見えるが、`Traceability` 全体を同期しないと監査テーブルと `REQUIREMENTS.md` が再び不一致になる。

## 現在の成果物状況

### Phase 3

- 研究、3 本の plan、3 本の summary、Nyquist compliant な `03-VALIDATION.md`、`03-UAT.md` は存在する。
- `VERIFICATION.md` だけが欠落している。
- ただし監査時点では `PURS-03`, `PURS-04`, `RUNT-01` が runtime assembly 欠落のため unsatisfied 扱いだった。
- この runtime assembly ギャップは Phase 6 の `VERIFICATION.md` で解消済み。

結論: Phase 3 の verification は「Phase 3 実装自体の証跡」だけでは不十分で、Phase 6 の runtime closure を current-codebase evidence として参照する必要がある。

### Phase 4

- 研究、3 本の plan、3 本の summary は存在する。
- `04-VALIDATION.md` はあるが Nyquist 未準拠。
- `VERIFICATION.md` が欠落している。
- 監査では `OUTC-03`, `RUNT-03`, `OBSV-01` が partial、`OBSV-02` が unsatisfied。
- `OBSV-02` の unsatisfied 理由は observation 側より upstream の player runtime assembly 欠落であり、これも Phase 6 で閉じている。

結論: Phase 4 は validation 修復と verification 追加を同じストリームで扱うべきで、verification は formatter/handler テストだけでなく Phase 6 の live runtime evidence も参照する必要がある。

### Phase 5

- 研究、2 本の plan、2 本の summary、Nyquist compliant な `05-VALIDATION.md` は存在する。
- `VERIFICATION.md` だけが欠落している。
- 監査では `PURS-02` が partial 扱いで、理由は verification 欠落のみ。

結論: Phase 5 は本質的に verification backfill 単体作業で閉じる。

## 要件ごとの受け入れ先

Phase 7 の planning では、「どの要件をどの phase の verification で accept するか」を先に固定したほうがよい。

| Requirement | 受け入れ先 | 理由 |
|-------------|------------|------|
| PURS-02 | Phase 5 `VERIFICATION.md` | モンスター pursuit 整合は Phase 5 の責務で、監査 gap も verification 欠落のみ。 |
| OUTC-03 | Phase 4 `VERIFICATION.md` | failure_reason を含む observation payload の責務は Phase 4。 |
| RUNT-03 | Phase 4 `VERIFICATION.md` | movement interruption と pursuit interruption の区別は Phase 4 observation semantics の責務。 |
| OBSV-01 | Phase 4 `VERIFICATION.md` | pursuit event の observation pipeline 接続は Phase 4 の責務。 |
| OBSV-02 | Phase 6 `VERIFICATION.md` を最終根拠、Traceability は Phase 6 | Phase 4 実装は必要条件だが、player live path の成立は Phase 6 で閉じた。 |
| PURS-03 | Phase 6 `VERIFICATION.md` を含む current-codebase evidence、Traceability は Phase 6 | Phase 3 の continuation 実装に加え、非テスト runtime assembly が最終受け入れ条件。 |
| PURS-04 | Phase 6 `VERIFICATION.md` を含む current-codebase evidence、Traceability は Phase 6 | 上と同じ。 |
| PURS-05 | Phase 6 `VERIFICATION.md` を最終根拠、Traceability は Phase 6 | cancel 自体は Phase 2 だが live runtime exposure は Phase 6 で閉じた。 |
| RUNT-01 | Phase 6 `VERIFICATION.md` | runtime composition の最終 closure は明確に Phase 6。 |

Planner への示唆: Phase 3/4 の verification を書くときに、元 phase の達成内容と current codebase の受け入れ条件を分けて記述しないと、Phase 6 との責務境界が曖昧になる。

## 使うべき既存証拠

### Phase 3 verification の根拠

- `03-01-SUMMARY.md`, `03-02-SUMMARY.md`, `03-03-SUMMARY.md`
- `03-UAT.md`
- `03-VALIDATION.md`
- Phase 3 plan 群に列挙された targeted pytest commands
- Phase 6 `VERIFICATION.md`
- Phase 6 `06-VALIDATION.md`

実務上は、Phase 3 verification を書く前に Phase 3 validation の quick/full commands と Phase 6 runtime integration commands を再実行し、現在コードベースで再確認した結果を書くのが安全である。

### Phase 4 verification / validation 修復の根拠

- `04-01-SUMMARY.md`, `04-02-SUMMARY.md`, `04-03-SUMMARY.md`
- `04-01-PLAN.md`, `04-02-PLAN.md`, `04-03-PLAN.md`
- 現在の `04-VALIDATION.md` 草案
- Phase 6 `VERIFICATION.md`
- Phase 6 `06-VALIDATION.md`

特に Phase 4 は、validation 修復時に以下を埋め直す必要がある。

- frontmatter を `status: approved`, `nyquist_compliant: true`, `wave_0_complete: true` 相当に更新
- quick/full commands を `.venv/bin/python -m pytest ...` へ統一
- per-task verification map を 04-01 / 04-02 / 04-03 の task 粒度に拡張
- feedback latency を現実的な値へ縮める
- Wave 0 と manual-only verifications を明示

### Phase 5 verification の根拠

- `05-01-SUMMARY.md`, `05-02-SUMMARY.md`
- `05-VALIDATION.md`
- Phase 5 plan 群にある regression commands

Phase 5 は追加依存が少なく、Phase 3/4 より先に固めやすい。

## 計画可能なワークストリーム

### Workstream A: 監査受け入れマトリクス確定

目的:
- audit gap を requirement / phase / artifact 単位で固定する。
- `REQUIREMENTS.md` の更新方針を事前に決める。

含めること:
- audit の partial / unsatisfied / missing を一覧化
- current-codebase acceptance でどの phase を最終根拠にするか決定
- `REQUIREMENTS.md` の行ごとの更新先を決定

成果物:
- Phase 7 plan 内の acceptance matrix

### Workstream B: Phase 3 / 5 verification backfill

目的:
- Nyquist compliant validation が既にある phase から順に `VERIFICATION.md` を追加する。

含めること:
- validation commands の再実行
- verdict / evidence / requirement checks / commands を持つ verification 生成
- Phase 3 では Phase 6 runtime closure 参照を明記

非目的:
- code change
- validation architecture の再設計

### Workstream C: Phase 4 validation repair + verification

目的:
- 監査上もっとも弱い成果物セットを修復する。

含めること:
- `04-VALIDATION.md` の Nyquist 化
- Phase 4 verification 作成
- `OUTC-03`, `RUNT-03`, `OBSV-01` を accept できる根拠整理
- `OBSV-02` は Phase 6 に最終帰属させるか、Phase 4 verification 内で dependency として扱うかを明示

依存:
- Workstream A

### Workstream D: REQUIREMENTS traceability sync

目的:
- `REQUIREMENTS.md` を監査後の accepted state に合わせる。

最低限更新が必要な行:
- `PURS-02` -> `Phase 5 | Completed`
- `OUTC-03` -> `Phase 4 | Completed`
- `RUNT-03` -> `Phase 4 | Completed`
- `OBSV-01` -> `Phase 4 | Completed`

監査整合のため同時に更新すべき行:
- `PURS-03`, `PURS-04`, `PURS-05`, `RUNT-01`, `OBSV-02` -> `Phase 6 | Completed`
- `OUTC-01`, `OUTC-02`, `RUNT-02` -> `Phase 1 | Completed`

Planner への示唆: 4 ID だけ更新すると `REQUIREMENTS.md` は依然として audit notes と矛盾する。

## 推奨 Wave 順序

### Wave 1

- Workstream A を実施する。
- 受け入れマトリクスを固定する。
- `REQUIREMENTS.md` の最終状態を先に決める。

理由:
- verification を書いた後に traceability 方針を変えると、受け入れ先がぶれる。

### Wave 2

- Workstream B のうち Phase 5 `VERIFICATION.md`
- Workstream B のうち Phase 3 `VERIFICATION.md`

理由:
- どちらも validation が既に Nyquist compliant。
- Phase 5 は単独で閉じやすく、Phase 3 は Phase 6 を参照すれば current-codebase verification を書ける。

### Wave 3

- Workstream C として `04-VALIDATION.md` 修復
- 続けて Phase 4 `VERIFICATION.md`

理由:
- Phase 4 だけ validation が未整備。
- verification より前に validation を fix したほうが根拠コマンドを再利用しやすい。

### Wave 4

- Workstream D として `REQUIREMENTS.md` 同期
- Phase 7 completion review

理由:
- traceability は verification verdict が揃ってから最後に更新するほうが安全。

## 依存関係

- Phase 3 verification は Phase 6 verification を current-codebase runtime evidence として参照する必要がある。
- Phase 4 verification は Phase 4 validation 修復に依存する。
- `REQUIREMENTS.md` 更新は、少なくとも Phase 3/4/5 verification の verdict 固定後に行うべき。
- すべての verification 文書は、summary の自己申告ではなく targeted test command 再実行結果に基づくべき。

## リスク

### リスク 1: summary の書き換え写しで verification を作る

これは監査上もっとも弱い。summary は完了申告であって受け入れ判定ではないため、verification では command と requirement-level verdict が必要。

### リスク 2: Phase 3 の requirement 帰属を誤る

現在コードベースでは `PURS-03`, `PURS-04`, `RUNT-01` の最終受け入れ根拠は Phase 6 runtime closure を含む。Phase 3 verification だけで完結しているように書くと、監査 reasoning と衝突する。

### リスク 3: Phase 4 で `OBSV-02` の扱いを曖昧にする

Phase 4 は observation wiring を実装したが、player path の live runtime closure は Phase 6。verification と traceability の責務境界を明文化しないと、再度 partial 判定が起こり得る。

### リスク 4: REQUIREMENTS を部分更新にとどめる

Phase 7 の required IDs だけを Completed にしても、Phase 1 と Phase 6 の stale rows が残る。監査差分は減るが、整合性 debt は残る。

## Planner が先に決めるべきこと

1. `REQUIREMENTS.md` を required IDs だけでなく全 stale row まで同期するか。
2. Phase 4 `VERIFICATION.md` で `OBSV-02` を dependency note に留めるか、補足 requirement check として触れるか。
3. verification 作成前に targeted pytest commands をすべて再実行するか。

推奨:
- 1 は「全 stale row を同期」にする。
- 2 は「最終 acceptance は Phase 6、Phase 4 verification では prerequisite/partial closure を説明」にする。
- 3 は「再実行する」にする。

## Validation Architecture

Phase 7 自体のために `07-VALIDATION.md` を新設する必要性は低い。

理由:
- Phase 7 の主成果物は verification/validation/traceability の文書修復であり、新しい実行時挙動を導入しない。
- Nyquist の主眼である「実装中の継続的フィードバック sampling」は、Phase 7 では既存 phase の validation commands を再実行することで代替できる。
- 新しい validation 文書を作るより、Phase 4 validation を正しく直し、Phase 3/4/5 verification に再実行コマンドと verdict を残すほうが監査価値が高い。

したがって planner は `07-VALIDATION.md` を前提にせず、各 workstream の verify step に以下を持たせれば十分である。

- Phase 3 targeted verification commands の再実行
- Phase 4 targeted verification commands の再実行
- Phase 5 targeted verification commands の再実行
- `REQUIREMENTS.md` の差分レビュー

例外:
- もし orchestrator が doc-only phase にも Nyquist frontmatter を要求する運用であれば、最小限の document-audit validation を作ってもよい。ただし本 phase の成功可否には必須ではない。

## 推奨 Plan 分割

### 07-01: Phase 3 / 5 verification evidence を再構築する

狙い:
- 欠落している verification を、既存 validation と再実行結果に基づいて埋める。

Done 条件:
- Phase 3 `VERIFICATION.md` が current codebase と Phase 6 dependency を反映している。
- Phase 5 `VERIFICATION.md` が `PURS-02` を受け入れている。

### 07-02: Phase 4 の verification / validation artifacts を完了させる

狙い:
- Phase 4 を監査可能な状態にする。

Done 条件:
- `04-VALIDATION.md` が Nyquist compliant。
- Phase 4 `VERIFICATION.md` が `OUTC-03`, `RUNT-03`, `OBSV-01` を current codebase basis で accept している。

### 07-03: requirements traceability を監査結果に合わせて同期する

狙い:
- `REQUIREMENTS.md` を最終受け入れ台帳として成立させる。

Done 条件:
- required IDs の行が正しい phase / status を指す。
- stale rows が残っていない。

## まとめ

Phase 7 の難所は実装ではなく、責務帰属の整理である。Phase 3/4/5 の verification backfill は単独ではなく、Phase 6 runtime closure と監査 verdict を前提に書く必要がある。最も安全な進め方は、先に受け入れマトリクスを固定し、Phase 5 と Phase 3 の verification を先行、次に Phase 4 validation/verification を修復し、最後に `REQUIREMENTS.md` を一括同期する流れである。
