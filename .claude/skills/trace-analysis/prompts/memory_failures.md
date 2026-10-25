あなたは LLM 駆動 RPG (= llm-rpg) の実験 trace を分析するアナリストです。
**記憶システム + 失敗モード** 軸で人間が読む Markdown レポートを返してください。

## 対象ファイル

- 解析対象: `{{RUN_DIR}}/trace.jsonl`
- 比較 baseline: `{{BASELINE_DIR}}/trace.jsonl` (指定がなければ比較なしで OK)

## 着目すべき event

- `episodic_recall`: passive recall の結果。`payload.recalled_episodes` / `payload.candidates` 等。受動想起は #1631 で消したので、それより後の trace には出ない (出ないのが正常)
- `episodic_chunk_written`: 新しい episode の生成。古いエピソードは #1631 で消したので、それより後の trace には出ない (出ないのが正常)
- `episodic_subjective_filled`: subjective field (= chunk の意味付け) の埋め込み。同じく #1631 前の trace のみ
- `short_term_summary_generated`: L4 short-term summary 更新
- `short_term_long_summary_generated`: L5 long summary 生成。L5 は #1824 で消したので、それより後の trace には出ない (出ないのが正常)
- `being_memo`: メモ帳への書き込み。`payload.applied` / `payload.rejected`
- `episode_writing`: 目次つきのエピソードの書き起こし。`payload.trigger` (compaction / leaving / fold) / `payload.outcome` (written / failed / skipped) / `payload.episodes`。fold (Being の短期記憶が古いターンのいきさつを頼んだとき) は `player_id` を持たず `payload.being_id` で引く。fold で書けなかったときは `outcome: failed` ではなく `async_event_delivery_failed` (`payload.event_type` が `FoldRequested`) に残る
- `episode_index_shown`: 毎ターンのプロンプトに出した目次。`payload.shown_handles` / `payload.total_count`
- `episode_recall`: 呼び名でエピソードを呼び出した。`payload.outcome` (recalled / rejected / failed) / `payload.results`
- `episode_index_revision`: 本人が目次を直した。`payload.before` / `payload.after`
- `action_result` の `success=false` + `error_code`: 失敗分析
- `loop_guard_warning`: 同 intent loop 検出
- `prompt_section_breakdown`: prompt 各 section のサイズ (cache 観測の補助)

## 担当軸

### D. 記憶システム
- **D-25 episodic_recall の K 分布と質** (#1631 前の trace のみ): 1 call で何件出したか分布 + 3-5 件サンプリングして役に立っていたか
- **D-26 recall habituation の効果** (#1631 前の trace のみ): 同じ episode が連続採用されてないか
- **D-27 recall slot 動作** (#1631 前の trace のみ): working memory の保持 / 入れ替わり
- **D-28 afterglow / score 構造** (afterglow は #1631 前の trace のみ): 採用候補・非採用候補のスコア構造が観測できるか
- **D-29 episodic_chunk_written と subjective_filled の 1:1 整合** (#1631 前の trace のみ): episode_id ベースで diff
- **D-30 short / long summary クオリティ**: 1-2 件の中身評価
- **D-31 メモ帳の重複と消し忘れ**: 同じやることを何度も書いていないか、済んだやることを消しているか
- **D-32 失敗の記憶化** (#1631 前の trace のみ): recall に失敗エピソードが出ているか (= 学習する記憶か)
- **D-32b 目次つきのエピソード**: 書き起こしの written / failed / skipped の内訳、目次に出た呼び名のうち呼び出されたものの割合、目次を直した例を 1-2 件 (直す前と後)

### E. 失敗・loop_guard・異常
- **E-33 error_code 全分布**: 上位 5 (baseline 指定なら差分)
- **E-34 loop_guard_warning 詳細**: 誰が何 tick で何 loop に引っかかり、その後どうなったか
- **E-35 silent failure 兆候**: success=true だが効果ゼロ / 同じ行動を 2-3 連続している例
- **E-36 INVALID_TARGET / INTERACTION_PRECONDITION_FAILED の breakdown**: 具体例 3-5 件

## prefix cache 観測 (おまけ)

`prompt_section_breakdown` の `system_chars` / `objective_chars` / `recent_events_chars` 等 (`recall_chars` は #1631 で受動想起を消す前の trace にだけある)のばらつきから「cache 効きそう / 効かなさそう」を所感。深追い不要。

## 守るべきこと

- 具体例なしの「だいたい良い」レポートは却下。必ず引用 (tick, player_id, error_code, memo 内容) を伴う
- 5000 字程度の本格レポート、Markdown 整形

## 出力形式

Markdown レポート。セクション見出しは `## D-25 ...` / `## E-33 ...` のように軸番号付き。最後に `## 総合所感 (記憶 + 失敗モード)` を 200-400 字で。
