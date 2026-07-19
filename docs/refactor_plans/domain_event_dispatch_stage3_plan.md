# Stage 3 — emission サイトの手動 drain 撤去 (方針、codex レビュー反映)

> 状態: **改訂版**。codex レビュー (2026-07-20) の HIGH×3 / MEDIUM×3 / LOW を反映。
> 親計画: [domain_event_dispatch_refactor_plan.md](./domain_event_dispatch_refactor_plan.md)
> 前提: Stage 0 (#747) / Stage 1+2 (#748) マージ済み。
> Stage 1 契約: [stage1_contract.md](./domain_event_dispatch_stage1_contract.md)
> 棚卸し: [stage0a_inventory.md](./domain_event_dispatch_stage0a_inventory.md)

## 0. 最重要の再認識 (codex HIGH×3 で判明)

改訂前は「Stage 3a = 相② だから低リスク、item_transfer helper を横展開」と書いた。
これは**危険**だった。裏取りの結果:

- **swallow しているのは item_transfer (C3) だけ**。他サイトは publisher 例外を
  握らず伝播する。item_transfer の `_flush_events` (None no-op + 例外握り) を横展開
  すると、他サイトの現行例外方針を**静かに変えてしまう** (挙動変更)。
- **相② には 2 種ある**: 「その場生成 (create)」は drain footgun が**そもそも無い**
  (exploration/conversation/prepare/failure)。footgun があるのは「集約 drain」
  サイトだけ (speech/harvest/use_item/tick 系)。
- **harvest (C4) は意図的に clear しない**。`get_events → publish → (clear せず) save` で、
  save の `_register_aggregate` に UoW 経路への供給を委ねる二重経路設計。collector で
  「add → clear → save」にすると spot_graph 以外 (UoW 配線テスト/別 runtime) で挙動が変わる。

→ **一律ヘルパーは作れない。各サイトの (publisher 必須性 / 例外方針 / clear 有無 /
batch 粒度) を保存する per-site 移行が必須。** これが Stage 3 全体の前提。

## 1. Stage 3 の線引き (codex P1: 妥当と確認)

- Stage 3 = **手動 drain footgun の撤去のみ**。各サイトの外部挙動 (dispatch 先/順序/
  例外方針/clear の有無) は保存する。
- 相①a の **swallow → 伝播** (Stage 1 契約の目標) は **Stage 3X として分離**。挙動変更
  なので trace 可視化つきで独立に行う (§6)。混ぜると「構造移行で壊れた」のか「例外
  方針変更で見えた」のか切り分け不能になる (codex P1 追認)。

## 2. 相①a の即時性 (codex P2 反映: 「stage-local batch」であって「per-event」ではない)

`PlayerDownedEvent` は同 tick の death_grace_stage が走る前に grace 登録を終える必要が
ある。ただし現状は「apply_damage ごと即 publish」ではなく、**stage が全 player を走査し
events を貯めて save_all 後に stage 末尾で一括 publish_all** している
(`needs_decay_stage:109-164` / `status_effects_tick_stage:92-101`)。

→ 相①a サイトは collector を **stage-local batch** として使い、**stage 末尾で dispatch**
する (tick 末尾へは寄せない)。「emission-local (damage ごと即時)」ではない。これが
現状挙動の忠実な保存。

## 3. per-site 方針表 (実装 PR の事故防止・必読)

| ID | サイト | 相 | drain/create | publisher | 例外 | clear | batch 粒度 |
|---|---|---|---|---|---|---|---|
| C3 | item_transfer | ② | create | 任意 | **握る** | — | 単一 (移行済み #748) |
| C5 | exploration | ② | create | 任意 | 伝播 | — | 単一 |
| C6/C7 | conversation | ② | create | **必須** | 伝播 | — | 単一 |
| B4 | prepare | ② | create | 任意(早return) | 伝播 | — | group 複数 |
| C2 | interaction failure | ② | create | 任意(早return) | 伝播 | — | 単一 |
| C4 | harvest | ② | drain | 任意 | 伝播 | **しない** | batch |
| C9 | speech | ② | drain | **必須** | 伝播 | する | status batch |
| B1 | use_item 正常 | ② | drain | 任意 | 伝播 | する | `_use_item` 内 (B2/B3 と同居) |
| A1 | needs_decay | ①a+② | drain | 任意 | 伝播 | する | stage-local batch |
| A2 | status_effects | ①a+② | drain | 任意 | 伝播 | する | stage-local batch |
| A3 | attack_orchestrator | ①a+② | drain | 任意 | 伝播 | する | batch |
| C1 | interaction 接触ダメージ | ①a+② | drain | 任意 | 伝播 | する | batch |
| B5 | tend_to_player revive | ①c+①a+② | drain | 任意 | 伝播 | する | 単一 |
| B3/C8 | consumable | ①a/② | create+drain | 任意 | 伝播 | する | nested |

**create サイト (C5/C6/C7/B4/C2) は drain footgun が無い** → Stage 3 の主対象では
ない。統一 dispatcher (相ごとの振り分け) が入る Stage 3X 以降で扱う。Stage 3 で無理に
collector 化しても churn になる (単一イベント create を collector に通すだけ)。

## 4. サブステージ分割 (改訂)

### Stage 3a — 「クリーンな drain サイト」の footgun 撤去 (behavior-preserving)
現行の (publisher/例外/clear/batch) を**そのまま保存**しつつ、`get_events→clear→publish`
の並びを collector 経由の「原本から collect → dispatch → clear」helper に寄せる。
**item_transfer の swallow helper は使わない**。各サイトの例外方針を保つ専用経路。

- **C9 speech** (publisher 必須・伝播・clear する・単一集約): 最もクリーン。先頭候補。
- **B1+B2+B3 use_item** (`_use_item` 一括): codex HIGH2。B1 だけ切り出さない。
  `_use_item` 全体の publish 順序テストを厚く張ってから、メソッド単位で 1 PR。
  B2 は相①a、B3 は相①a (consumable 効果) を含むので、実質 3b 相当の慎重さ。

### Stage 3b — 相①a を含む tick / interaction サイト (behavior-preserving: swallow 維持)
stage-local batch collector + stage 末尾 dispatch。dispatch 先/順序/例外は不変。

- A1 needs_decay / A2 status_effects (stage-local batch)。
- A3 attack_orchestrator / C1 interaction 接触ダメージ。
- B5 revive (①c PostHoc direct append → ①a cancel の登録順が load-bearing。最慎重)。
- 各 PR は Stage 0b の順序不変条件を回帰網に。1 PR = 1 サイト。

### Stage 3c — harvest (C4) 単独 (codex HIGH3: clear しないのが挙動保存条件)
- **collector に add しても original を clear しない**。canonical 汚染は save の clone
  drain (#746) が防ぐ。「両経路供給」コメントの意図 (UoW + Pipeline) を壊さない。
- spot_graph では UoW 経路は実効でないが、service 単体/別 runtime の挙動を変えないため
  clear 撤去を Stage 3 に含めない。UoW 経路を切るなら独立の挙動変更 PR。

### Stage 3X — 相①a の例外方針を swallow→伝播へ (挙動変更・別イニシアチブ)
- PhasedEventDispatcher を導入し、相①a=伝播 / 相①b=握って警告 / 相②=現状維持 に振り分け。
- **前段として観測 PR** (codex LOW): `PipelineEventPublisher` の side handler 例外を
  **trace event に落とす** (現状は log のみで実験 run 集計に乗らない)。これで伝播化の
  影響 (相①a handler がどれだけ失敗しているか) を run から見積もれる。
- create サイト (C5/C6/C7/B4/C2) の統一 dispatcher 化もこの段以降で検討。

## 5. codex 指摘の反映済み事項
- **HIGH1**: item_transfer helper 横展開を撤回。per-site 方針表 (§3) を新設。
- **HIGH2**: B1 を単独 3a にしない。B2/B3 と同じ `_use_item` PR、順序テスト先行。
- **HIGH3**: harvest は clear しない (§4 Stage 3c 独立)。
- **MEDIUM (C9 漏れ)**: speech を §3/§4 に明記。
- **MEDIUM (P2)**: 「emission-local」→「stage-local batch + stage 末尾 dispatch」に修正 (§2)。
- **MEDIUM (dedup 可視化)**: Stage 3b の helper で dedup drop 件数を trace/debug 可能にし、
  **「別 player の同種 PlayerDownedEvent は両方 publish される」テスト**を追加 (偶発 coalesce 防止)。
- **LOW**: Stage 3X 前に side handler 例外の trace 化 観測 PR を挟む (§4 Stage 3X)。

## 6. 進め方の原則
- 1 PR = 1 サイト (相① / use_item は特に)。200〜400 行目安。
- **各サイトの現行 (publisher/例外/clear/batch) を保存**。共通 swallow helper を作らない。
- 相①a の即時性 (stage 末尾 dispatch、tick 末尾に寄せない) を絶対に壊さない。
- 収集は原本から (save 前)。#746 不変条件を維持。harvest は clear しない。
- Stage 0b + 各 PR の特性化テストを回帰網に、behavior-preserving を最優先。

## 7. 未解決 (次に詰める)
- Stage 3 で collector を通す実利 (footgun 撤去) が、per-site 方針保存の制約下で
  create サイトには薄い。drain サイト中心に絞るのが妥当か、最終確認する。
- harvest の「両経路供給」を将来どう畳むか (UoW 経路を正式に切るか) は別計画。
