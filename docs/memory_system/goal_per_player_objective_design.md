# 目的の入口をプレイヤーごとに開く (目的層 G6)

> 前提: [goal_layer_design_active_inference.md](./goal_layer_design_active_inference.md)
> の G1 (goal store) は実装済み。本 doc はその **入口** だけを扱う。

## 0. 要約

目的 (goal) は既に per-Being の journal として保管されている。器は完成して
いる。しかし入口が「シナリオ全体で 1 本の文字列」しかなく、さらに勝敗条件を
持つシナリオでは目的が locked で固定されるため、**本命 run では目的層が一度も
動いていない**。

本 doc は入口を 2 つ開く。

1. `players[].objective` — プレイヤーごとの初期目的をシナリオで宣言できる
2. `players[].goal_locked` — 改訂可否をプレイヤーごとに決められる

新しいドメイン概念は追加しない。`GoalEntry` / `GoalJournalRepository` /
【現在の目的】の描画 / snapshot 追従はすべて既存のものをそのまま使う。

## 1. 実測 — いま目的層は本命 run で死んでいる

`belief_goal_full` 系 profile は `GOAL_STORE_ENABLED` と
`GOAL_REVISION_ENABLED` を両方 true にしている。つまり目的の見直し (G2) は
配線されている。それでも既存 run の trace は次のとおり。

| run | tick | `goal_revision_rejected` | 内 `reason=locked` | `goal_resolution` (成功) |
|---|---|---|---|---|
| v4coop_reasonfirst_001 | 184 | 1 | 1 | 0 |
| v4coop_distant_001 | 200 | 6 | 6 | 0 |
| v3coop_postrefactor_001 | 200 | 10 | 10 | 0 |
| v3coop_stagnation_003 | 200 | 2 | 2 | 0 |
| **合計** | **784** | **19** | **19** | **0** |

エージェントは 19 回「目的を立て直したい」と意思表示している。その全部が
locked で拒否され、成功は 1 件もない。拒否された文面は具体的で真っ当なものだ。

```
being_w1_p3 / tick 145 / reason=locked
attempted_goal_text: "まず食料を確保してHPと空腹を回復させる。その後に山頂ルートを進む。"
```

これは不具合ではなく、設計どおりの帰結である。`locked` の初期値は
`_scenario_has_goal(scenario)` に連動しており (`world_runtime.py:1397`)、
`game_end_conditions` か `outcome_resolution` を持つシナリオは locked=True に
なる。survival_island 系は `outcome_resolution` を持つので、**本命シナリオは
定義上すべて locked** である。

結果として、G2 (意識的な更新) / G3 (監査の接続) / G4 (目的の予測化) は、
`persistent_world_demo` のような勝敗条件なしのシナリオでしか到達できない。
目的層への投資が、本命の観察 run に一切還元されていない状態が続いている。

## 2. いまの構造と、2 つの塞がり

### 3 層

| 層 | 実体 | 状態 |
|---|---|---|
| 入口 | `scenario.metadata.llm_objective_text` | **シナリオ全体で 1 本の文字列** |
| 保管 | `GoalJournalRepository` (per-Being journal) | 完成。supersede / 清算 / 履歴 / snapshot 済み |
| 描画 | 【現在の目的】section | `objective_text_provider` 経由。完成 |

### 塞がり A — 入口が 1 本

`_resolve_objective_via_goal_store` は Being ごとに遅延 seed するが、seed する
text は全員同じ `fallback_text` (= `llm_objective_text`) である。コード中の
コメントも「描画結果は従来の静的テキストと同一 = 既存シナリオの挙動不変」と
明記している。つまり **goal store を ON にしても初期状態は全員同じ目的**。

非対称な目的を書く手段は現状 `persona_prompt` に文章で埋め込むことだけで、
これは goal store にも勝敗判定にも繋がらない。

### 塞がり B — locked がシナリオ単位

`locked` はシナリオ全体の性質から導出され、プレイヤーごとに変えられない。
「この 3 人の目的は固定、この 1 人だけは自分で立て直してよい」が書けない。

## 3. 設計

### 3.1 `players[].objective`

`PlayerSpawnConfig` に `objective: Optional[str]` を足す。`persona_prompt` と
まったく同じ扱い (省略可、文字列以外は loader で拒否、前後の空白のみ除去して
内側の改行は保持)。

```json
{
  "id": "ada",
  "name": "エイダ",
  "spawn_spot": "shipwreck_beach",
  "objective": "- 山頂の狼煙台で火を上げ、救助船を待つ\n- 手当てを約束した相手を見捨てない",
  "persona_prompt": "..."
}
```

解決順は `persona_prompt` の既存ルールと揃える。

1. `players[].objective` があればそれ
2. なければ `metadata.llm_objective_text`

これにより既存シナリオは 1 行も変えずに挙動不変になる。

### 3.2 `players[].goal_locked`

`Optional[bool]`。省略時は現行どおり `_scenario_has_goal(scenario)` に従う。
明示されていればそれを優先する。

「勝敗条件のあるシナリオでも、この 1 人だけは目的を立て直せる」が書ける。
逆に open world で特定の 1 人だけ執着を固定することもできる。

### 3.3 fail-fast の扱い

`_require_llm_objective_text` は `metadata.llm_objective_text` が空だと起動時に
例外を投げる。意図は「シナリオ作者に目的文を明示させる強制力」であり、これは
維持する価値がある。判定を次のように緩める。

> `metadata.llm_objective_text` が空でも、**全プレイヤーに `objective` が
> 揃っている** なら通す。どちらも欠けているプレイヤーが 1 人でもいれば
> 従来どおり例外。

「一部の人だけ目的があり、残りは無言で目的なしになる」という静かな失敗を
構造で塞ぐ。

### 3.4 描画は変えない

【現在の目的】section の書式・位置・語彙は一切変えない。プレフィックス
キャッシュの不変条件 (設計判断 #1) にも影響しない — 変わるのは section の
中身の文字列だけで、tool list も section の並びも不変である。

### 3.5 新しい store は作らない

per-Being の store は増えないので、`BeingMemorySnapshotService` への追従
(checklist #27) は **不要**。goal store は既に配線済みで、seed される中身が
変わるだけである。

## 4. 何が書けるようになるか

Among Us の裏切り者はこの表現力の 1 事例にすぎない。もっと日常的なものが
書けるようになる。

| 書けるもの | 例 |
|---|---|
| 非対称な目的 | 4 人漂流のうち 1 人だけ「救助ボートは 2 人分。何としても自分が乗る」 |
| 役割の分担 | 「食料班」「狼煙班」で初期目的が違う。合流と交渉が発生する |
| 職能に紐づく目的 | 医師は「怪我人を死なせない」、猟師は「日に 1 度は獲物を獲る」 |
| 執着の個体差 | 同じ目的でも 1 人だけ `goal_locked: true` にして「諦められない人」を作る |
| 目的の欠落 | 1 人だけ `objective` を空にし、「(まだ定まっていない)」から始めさせる (P6 の需要信号を意図的に作る) |
| 長期の生活世界 | 全員 unlocked + 各自の目的。本命の MMO 世界の最小形がこれ |

そして最も重要なのは、**本命シナリオで G2 / G3 / G4 が初めて到達可能になる**
ことである。19 回の拒否が、19 回の観察対象に変わる。

## 5. 残る食い違い — 勝敗条件と個人の目的

`locked` が `_scenario_has_goal` に連動していた事実が示すとおり、現状のコードは
「目的 = シナリオの勝利条件」を前提に書かれている。プレイヤーごとの目的を
入れると、この前提が崩れる。

裏切り者が「自分だけ助かる」を目的に持ったとき、シナリオの
`game_end_conditions` はそれを判定できない。`GameEndCondition` は
`condition_type` / `target_spot_id` / `target_flag` / `tick_limit` の
4 フィールドしかなく、`GameEndConditionTypeEnum` も `ALL_AT_SPOT` /
`ANY_AT_SPOT` / `FLAG_SET` / `TICK_LIMIT` の 4 種のみである。一方
`InteractionConditionType` は 20 種以上ある。**同じ「条件」なのに語彙が
3 系統に分裂している**。

本 doc はこれを扱わない。ただし本 doc の変更を入れると、この食い違いが具体的な
形で表面化する。条件式の統一と「プレイヤー集合への集計述語」(生存数、特定
`initial_state` を持つ人数、特定 spot にいる人数) は別 doc で扱う。

### 既知の未対応 — system prompt の勝敗フレーミングは per-player でない

`create_world_runtime` は `_scenario_has_goal(scenario)` を 1 度だけ評価し、
その `has_goal` を system prompt のナラティブ (`safe_world_intro_text` /
`build_world_system_prompt`) に渡している。これはシナリオ全体で共有される。

結果として「勝敗条件つきシナリオで `goal_locked: false` を宣言した 1 人」は、
`GoalEntry.locked=False` なので目的を書き換えられるのに、本人が読む system
prompt の語りは `has_goal=True` 前提の勝敗フレームのままになる。**目的層の状態と
本人が読む物語が食い違う。**

本 doc のスコープ外として意図的に残す。理由は 2 つある。system prompt は
プレフィックスキャッシュの不変対象なので、per-player に分岐させると
キャッシュ設計への影響を別途評価する必要があること。そして「勝敗フレームを
読みながら自分の目的だけは動かせる」状態が実際にどう振る舞うかは、まず
観察してから決めたいこと。PR 4 の質感確認で、この食い違いが実際に不自然さと
して出るかを見る。

### 検証しているのは「有無」であって「中身」ではない

fail-fast の緩和 (§3.3) は `players[].objective` の **有無** しか見ない。中身が
勝敗条件と整合しているか、コピペミスで別シナリオの目的文になっていないかは
検証しない。これは共通目的文 `metadata.llm_objective_text` に対する既存の
チェックと同じ水準 (空かどうかしか見ない) なので後退ではないが、入力経路が
増えた分だけ「形式的には通るが中身が誤っている」余地は広がっている。

## 6. 非目標

- 陣営 (faction) という概念の新設。**しない。**「同じ目的を持つ人が複数いる」
  で足りる。陣営を第一級にするのは、集計述語が要ると分かってからでよい
- 初期知識・初期信念の seed。目的とは別物 (belief journal / 意味記憶の管轄)
  であり、入口も別に開ける。本 doc に混ぜない
- 目的の達成判定を個人単位にすること。`PlayerOutcomeEnum` は触らない
- 投票・追放などの集団意思決定

## 7. 実装順とテストリスト

1 サイクル 1 振る舞いで進める。

**PR 1 — loader**

- [ ] `players[].objective` を省略すると `PlayerSpawnConfig.objective` は None になる
- [ ] `players[].objective` に文字列を渡すと前後の空白だけ除去され、内側の改行は保持される
- [ ] `players[].objective` に文字列以外を渡すと ValueError を投げ、どの player かがメッセージに含まれる
- [ ] `players[].objective` が空白のみのとき None に正規化される
- [ ] `players[].goal_locked` を省略すると None になる
- [ ] `players[].goal_locked` に bool 以外を渡すと ValueError を投げる

**PR 2 — seed の解決**

- [ ] `objective` を持つプレイヤーは、その文字列で goal store に seed される
- [ ] `objective` を持たないプレイヤーは `metadata.llm_objective_text` で seed される
- [ ] 既存シナリオ (全員 `objective` なし) では seed 内容が変更前と一致する
- [ ] `goal_locked: true` のプレイヤーの `GoalEntry.locked` が True になる
- [ ] `goal_locked` 省略時は `_scenario_has_goal(scenario)` の値が使われる
- [ ] `goal_locked: false` を勝敗条件つきシナリオで指定すると、そのプレイヤーだけ goal_update が通る

**PR 3 — fail-fast の緩和**

- [ ] `metadata.llm_objective_text` が空でも全員に `objective` があれば起動する
- [ ] `metadata.llm_objective_text` が空で `objective` を欠くプレイヤーが 1 人でもいると、その player id を含む例外で起動に失敗する

**PR 4 — 質感確認シナリオ**

- [ ] 非対称な目的を持つ 4 人シナリオを 1 本追加し、`smoke_stub` で seed が
      プレイヤーごとに異なることを確認する

## 8. trace 観測性

新しい trace event は追加しない。既存の `goal_resolution` /
`goal_revision_rejected` で足りる。ただし run 後に次を確認できることを
PR 4 の受け入れ条件にする。

- `experiment.config.resolved.json` から、各プレイヤーの初期目的が読めること
- `goal_revision_rejected` の `reason=locked` が、`goal_locked: false` の
  プレイヤーでは出ないこと
- `goal_resolution` が 1 件以上出ること (= 目的層が本命 run で初めて生きる)

最後の 1 点が本 doc の成否そのものである。784 tick 回して成功 0 だった値が、
1 以上になるかどうかで判定する。

## 関連

- [goal_layer_design_active_inference.md](./goal_layer_design_active_inference.md) — 目的層の全体設計 (G1〜G5)
- [../design_decisions.md](../design_decisions.md) — #1 プレフィックスキャッシュ不変、#27 per-Being store の snapshot 追従
- [../trace_observability_review.md](../trace_observability_review.md) — trace 観測性のレビュー観点
