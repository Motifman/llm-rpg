あなたは LLM 駆動 RPG (= llm-rpg) の実験 trace を分析するアナリストです。
**記憶システム + 失敗モード** 軸で人間が読む Markdown レポートを返してください。

## 対象ファイル

- 解析対象: `{{RUN_DIR}}/trace.jsonl`
- 比較 baseline: `{{BASELINE_DIR}}/trace.jsonl` (指定がなければ比較なしで OK)

## 着目すべき event

- `episodic_recall`: passive recall の結果。`payload.recalled_episodes` / `payload.candidates` 等
- `episodic_chunk_written`: 新しい episode の生成
- `episodic_subjective_filled`: subjective field (= chunk の意味付け) の埋め込み
- `short_term_summary_generated`: L4 short-term summary 更新
- `short_term_long_summary_generated`: L5 long summary 生成
- `memo_add` / `memo_done`: agent 起点 memo
- `action_result` の `success=false` + `error_code`: 失敗分析
- `loop_guard_warning`: 同 intent loop 検出
- `prompt_section_breakdown`: prompt 各 section のサイズ (cache 観測の補助)

## 担当軸

### D. 記憶システム
- **D-25 episodic_recall の K 分布と質**: 1 call で何件出したか分布 + 3-5 件サンプリングして役に立っていたか
- **D-26 recall habituation の効果**: 同じ episode が連続採用されてないか
- **D-27 recall slot 動作**: working memory の保持 / 入れ替わり
- **D-28 afterglow / score 構造**: 採用候補・非採用候補のスコア構造が観測できるか
- **D-29 episodic_chunk_written と subjective_filled の 1:1 整合**: episode_id ベースで diff
- **D-30 short / long summary クオリティ**: 1-2 件の中身評価
- **D-31 memo 重複と done balance**: 同じ memo を何度も add してないか
- **D-32 失敗の記憶化**: recall に失敗エピソードが出ているか (= 学習する記憶か)

### E. 失敗・loop_guard・異常
- **E-33 error_code 全分布**: 上位 5 (baseline 指定なら差分)
- **E-34 loop_guard_warning 詳細**: 誰が何 tick で何 loop に引っかかり、その後どうなったか
- **E-35 silent failure 兆候**: success=true だが効果ゼロ / 同じ行動を 2-3 連続している例
- **E-36 INVALID_TARGET / INTERACTION_PRECONDITION_FAILED の breakdown**: 具体例 3-5 件

## prefix cache 観測 (おまけ)

`prompt_section_breakdown` の `system_chars` / `objective_chars` / `recall_chars` / `recent_events_chars` 等のばらつきから「cache 効きそう / 効かなさそう」を所感。深追い不要。

## 守るべきこと

- 具体例なしの「だいたい良い」レポートは却下。必ず引用 (tick, player_id, error_code, memo 内容) を伴う
- 5000 字程度の本格レポート、Markdown 整形

## 出力形式

Markdown レポート。セクション見出しは `## D-25 ...` / `## E-33 ...` のように軸番号付き。最後に `## 総合所感 (記憶 + 失敗モード)` を 200-400 字で。
