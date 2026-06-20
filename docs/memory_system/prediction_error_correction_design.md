# 予測誤差駆動の修正学習 設計メモ (3段のはしご)

> Issue #526 不在#3「予測 / 期待値の不在」の続き。PR0〜PR3 で予測の器とループの
> 配線はできたが、「**同じ予測が繰り返し外れたら、次の予測を当てに行く**」という
> 修正学習として見ると、固着の引き金が意図とずれていた。その再設計。
> claude × codex × ユーザーの議論をまとめた確定版。
>
> 既存メモ [prediction_learning_loop_design.md](./prediction_learning_loop_design.md)
> (PR0〜PR3) の上に乗る。

## なぜ書くか

PR3 までで「予測誤差を学びの根拠にする」配線は入ったが、**昇格の引き金は
依然 generic な recall_count / cluster** だった。つまり予測ミスが学びになるのは
「たまたま想起・リンク条件も満たしたとき」で、意図的ではない。

ユーザーの問い：「予測誤差による学習」と「複数エピソードから意味記憶を作る固着」は
別物か。どう調和させるか。本当にやりたいのは**予測誤差のずれを修正する方向の学習**
＝次に予測が当たるようにすること。

## 人間モデルの整理 (未解明前提)

予測誤差学習と episode→意味記憶の固着は、**別の機構だが独立ではない**。

- **予測誤差学習** (予測符号化 / 強化学習): 予測と結果のずれを学習信号にして、予測
  モデルを更新する。本質は「予測モデルの更新」
- **固着** (補完学習系: 海馬↔新皮質): 多数の経験から統計的規則性を抽出して
  意味知識にする。本質は「汎化・圧縮」

人間では予測誤差が**橋渡し**をする: 驚いた出来事ほど強くタグ付けされ優先的に固着
される。同時に強い予測誤差は一撃で期待を更新する (一度痛い目を見たら警戒)。
→ 少なくとも 2 つのタイムスケール (速い誤差駆動の更新 / 遅い統計的固着) があり、
予測誤差はその両方を駆動する顕著性信号。

現状システムの不調和の正体: **遅い統計経路 (episode→semantic) しか持たず、予測誤差を
駆動信号として速い経路に流す配線が無い**。

## LLM エージェントへの翻訳

LLM 本体の重みは更新できない。予測を生むのは「LLM × プロンプト」で、可変なのは
プロンプトだけ。

> **「予測モデルの更新」＝「次に同じ状況が来たとき、プロンプトに載る内容を変えること」**

予測は毎回プロンプトから新規生成されるので、修正情報を**次回の該当状況のプロンプトに、
予測を動かす形で・確実に retrieve される形で・知識として重みづけされる段に**載せる
ことが学習の実体。これは深層学習の**信用割り当て (credit assignment)** と同型の問題:
ずれの責任を記憶階層のどこに帰属させ、どう更新するか。

## 何を根拠に予測するか (プロンプト構成要素)

`expected_result` は以下の合成で生まれる。修正情報の置き場の候補でもある:

| section | 予測への効き方 | 修正の置き場 |
|---|---|---|
| 【ペルソナ】(system) | 予測の気質 (楽観/慎重) | 固定。触らない |
| 【自己像と世界観】(L5) | 「世界はこういうもの」= 世界モデル | 深い・安定した信念 |
| 【関連する学び】(semantic) | 汎化知識「祭壇は反応しない」 | 安定した規則性 |
| 【関連する記憶】(episodic) | 具体例「前に触ったら何も起きなかった」 | 短期・反復 |
| 【前回の予測と実際】(PR1) | 直前の予測 vs 現実 | 即時・1ターン |
| 【直近の出来事】【現在地】 | 今の状況 | 予測の前提 |

## 設計の背骨: 予測誤差が駆動する「3段のはしご」

予測誤差を**駆動信号**とし、修正は記憶階層の段を、証拠が溜まるほど上へ登る。
重要なのは **3 つの別機能ではなく、1 つの `PredictionOutcome` が 3 つの表れ方を
持つ** と定義すること (設計原則#3)。`PredictionOutcome` =
{expected_result, actual_result, tool_name, action fingerprint, prediction_error,
予測時に想起されていた recall_ids}。

| 段 | 機構 | 何が更新されるか | 既存資産 |
|---|---|---|---|
| **段0 即時/文脈内学習(ICL)** | 直近 N 件の予測→結果を構造化台帳 (ledger) で明示 | プロンプト内文脈 (重み更新なし、純 ICL) | `ActionResultStore` + `build_prediction_feedback_text` を最新1件→N件に拡張 |
| **段1 episodic** | 予測誤差をトリガに、予測時に想起されていた episode を「これらから X を予測したが Y だった」と再解釈。信用割り当ては LLM に委ねる | その episode の含み (色づけ) | `reinterpretation coordinator` |
| **段2 semantic** | 安定した規則性を学びに固着 | 汎化知識 | `promotion` / `gist` の priority/evidence 底上げ |

**予測誤差の判定は単一の source に統一する** (重複実装しない)。PR2b の LLM 補完が
埋める `prediction_error` を唯一の判定結果とする。段2 で別の文字列一致カウンタを
作ると、却下済みの決定論 baseline に逆戻りするので禁止。

## 現状の事実 (実コードで確認済み)

- 【直近の出来事】の行動ログは `_format_action_summary` が `json.dumps(arguments)`
  で `expected_result`/`inner_thought`/`intention`/`emotion_hint` を**生 JSON で
  dump**。= 予測+結果が「汚い形」で既に積まれている
- 【前回の予測と実際】(PR1) は `ActionResultEntry.expected_result` (構造化) を読み
  **最新1件だけ**。= 予測情報が二重に出ており、片方はノイズだらけ
- `recall_buffer` は「そのターンで何を想起したか」(current_state/recent_events/
  persona/situation_cues/turn_index) を記録しているが、「その想起がどの予測→結果に
  結びついたか」は明示されていない → 段1 の信用割り当てが turn_index 推定では曖昧
  (複数 prompt / 再スケジュール / no tool / 例外経路で崩れる)

## 確定した設計判断 (codex レビュー反映)

1. **`action_summary` の表示整理は「表示のみ」に限定**: 共有 formatter
   `format_action_summary_for_display(tool_name, args)` を作り、結果に効く引数だけ
   表示し `NARRATIVE_ARG_FIELDS` (主観入力) を落とす。**raw args / canonical args /
   `argument_fingerprint` は変えない** (loop_guard 不変)。生 args は trace ACTION に
   残し監査可能
2. **段0 台帳は新ストア不要**: `ActionResultStore` が source of truth。
   `build_prediction_feedback_text` を最新1件→直近 N 件 (まず 3、char cap 付き) に
   拡張。各行は tool / 予測 / 実際 / 必要なら後続観測1件。`intention`/`emotion_hint`
   は段0 では出しすぎない
3. **段1 の前に信用割り当ての土台**: prompt build ごとに `prediction_context_id`
   (decision_id) を発行し `recall_buffer` observation と `ActionResultEntry` の両方に
   持たせる。または軽量な `PredictionOutcome` 値オブジェクトを導入。reinterpretation
   には「外れた予測 X→Y」を渡す専用入口を追加し、generic な再解釈と混ぜすぎない
4. **段2 は既存 promotion/gist の priority/evidence 底上げ**として入れる
   (recall_count/cluster の置き換えではなく)。再発判定は「同じ予測文の文字列一致」
   ではなく「**同じ cue signature で non-empty な prediction_error が繰り返される**」
   を基本にする

## 経路統一の位置づけ

段1 に必要なのは **full runtime の完全統合ではなく、`recall_buffer` /
`reinterpretation coordinator` を escape_game に共有配線すること** (#547 で semantic を
フラグ配線したのと同じ、的を絞った拡張)。各段が必要とする部品だけを段の手前で共有
配線する。完全な runtime 一本化は別テーマ (後回し可)。

## 実装順 (PR 分割)

| PR | 内容 | 統一の要否 |
|---|---|---|
| **A** | `action_summary` 表示 sanitizer + 段0 N 件台帳。テスト厚め | 不要 (共有 formatter で両経路に効き経路差を減らす) |
| **B** | `prediction_context_id` / `PredictionOutcome` の最小導入 + trace | 不要 |
| **C** | escape_game に `recall_buffer`/`reinterpretation` を共有配線 (or full path で実験する方針確定) | 的を絞った共有配線 |
| **D** | 段1: 予測誤差駆動の reinterpretation | C の後 |
| **E** | 段2: semantic 固着 (priority/evidence 追加) | 最後 |

段0(A) は統一を待たず着手でき、即効で価値が出る (実験の観測難も解消)。

## 現在の動作を維持する制約 (重要)

別 PR で実験が走っているため、**現在の動作を壊さない**ことを最優先する。特に PR-A:

- `action_summary` 表示の整理は **chunk episode の `observed`/`what`/`episode_id`、
  passive recall の cue、memo hint への波及に注意**。これらが今の挙動から変わると
  実験の episodic 挙動・episode_id が変わる
- 方針: **表示用 (プロンプトの【直近の出来事】) と、episode 派生 / cue / fingerprint に
  使う source を分離**する。表示だけ sanitize し、episode 派生は現状の動作を維持する
  (または sanitize した形に寄せる場合は episode_id 変化の影響を明示し、実験 PR と
  調整してから入れる)
- 必要テスト: 表示に生 JSON が出ない / `ActionResultEntry` の構造化フィールドは保持 /
  `argument_fingerprint`・loop_guard 不変 / chunk observed/what / passive cue / memo
  hint の代表ケースが落ちない

## 未決・次

- 段0 の section 名 (【前回の予測と実際】維持 か 【直近の予測と実際】) と N の最終値
- `prediction_context_id` か `PredictionOutcome` VO か (B で確定)
- 段1 の reinterpretation 入口の API 形 (D で確定)
- 実験 (real LLM 観測) は段0 完了後に再開: rig した最小シナリオ + 段0 台帳で
  短期 ICL を観測 → 段1/2 で中長期を観測

## 関連

- Issue #526 不在#3 / [prediction_learning_loop_design.md](./prediction_learning_loop_design.md)
- PR0〜PR3 (#540-#544) / 質感シナリオ #546 / escape_game semantic flag #547 /
  runtime contract tests #548
