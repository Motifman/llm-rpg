# 全機能 ON 実験 (memory_full_001〜003) — 予測→学習ループの初回実走

> 2026-07-05。予測→学習ループ (PR0〜PR3, #540-#544) と記憶階層の全フラグを
> 初めて同時に ON にして実走した記録。survival_island_v2 / 140 tick / 4 players /
> DeepSeek V4 Flash (openrouter, provider=DeepSeek)。
> run: `var/runs/memory_full_001` (tick 62 で死亡) / `002` (完走・学び 0 件) /
> `003` (完走・ループ初閉鎖)。

## 実行条件

```
LLM_EXPECTED_RESULT_POLICY=required
LLM_EPISODIC_ENABLED=1 (+ 慣化 / slot / afterglow は Makefile default ON)
LLM_EPISODIC_REINTERPRETATION_ENABLED=1
SEMANTIC_PASSIVE_TOP_K=3 / SEMANTIC_LLM_GIST_ENABLED=1 / SEMANTIC_SEARCH_ENABLED=1
EPISODIC_RECALL_ENABLED=1 / EPISODIC_EXPLORE_RELATED_ENABLED=1
make experiment-with-snapshot SCENARIO=data/scenarios/survival_island_v2.json \
  MAX_WORLD_TICKS=140 WORKERS=4 EPISODIC=1 PYTHON="uv run python"
```

`LLM_EXPECTED_RESULT_POLICY` はこの実験まで、リポジトリ内のどのシナリオ /
Makefile / スクリプトからも設定されていなかった (= 予測ループは本番経路で
一度も動いたことがなかった)。

## 見つかった静かな失敗 3 件

全て「単機能では踏めず、機能の組合せで初めて顕在化する」型だった。

### 1. loop_guard の naive datetime が run を殺す (001, 修正済み)

`tool_call_loop_guard.py` の既定 clock が `datetime.utcnow` (naive)。警告観測が
sliding window に入った瞬間、`get_oldest_entry_datetime` の `min()` (naive/aware
直接比較) が TypeError → prompt 構築ごと失敗 → post-tick hook 例外で run 全体が
死亡。episodic 想起 ON (PR5 R1 の時間下限フィルタ) × loop_guard 発火 の組合せ
でのみ踏む。

修正: 既定 clock を aware (UTC) に + `get_oldest_entry_datetime` を
`get_recent` と同じ timestamp() キー比較に堅牢化。テスト 2 件追加。

### 2. 想起→強化の link service が prompt builder に未配線 (002, 修正済み)

`build_episodic_stack` 内の `link_service` はローカル変数で chunk_coordinator
(TEMPORAL リンク) にだけ渡され、`EpisodicStack` の公開フィールドに存在しなかった。
`world_runtime` の `EpisodicRecallConfig` は `memory_link_service` を渡せず常に
None → `on_passive_recall_candidates` が一度も呼ばれない。

帰結 (002 実測): 想起は 262 prompt 中 80 回成立していたのに、全 81 episode の
recall_count が 0、CO_RECALL リンク 0、ヘブ則強化 0。**昇格ゲート
(recall_count>=3) は構造的に到達不能で、semantic (学び) は全フラグ ON でも
1 件も生まれ得なかった**。

修正: `EpisodicStack.link_service` を公開し `EpisodicRecallConfig` に配線。
テスト追加 (`test_link_service_wired_to_prompt_builder_for_recall_strengthening`)。

なお同型の配線漏れは過去にもある (慣化 store の prompt_builder 側 ctor 漏れ、
PR #565)。「stack には作ったが prompt builder に渡し忘れる」が繰り返し起きて
おり、個別 field の手渡しという構造自体の問題 (後述の改善案 #1)。

### 3. slot / afterglow / 慣化の snapshot 追従漏れ (003 で発見, 未修正)

trace 上は 3 サイドカーとも稼働しているのに、Being snapshot では
`recall_slot_entries` / `afterglow_entries` / `recall_habituation_last_recalled`
が全員空。`scripts/run_scenario_experiment.py` の
`_wiring_stub_from_world_runtime` が semantic / link / journal は stack から
拾うのに、この 3 store を拾っておらず空 fallback になる。save→resume で
想起階層の状態だけ静かに消える (CLAUDE.md checklist #27 のパターン)。

## ループ実測 (003 = 配線修正後)

| 段 | 実測 | 評価 |
|---|---|---|
| 予測入力 (`expected_result`) | ほぼ全 world-action に付与 | ○ |
| 段0 突き合わせ (【前回の予測と実際】) | 287 prompt 中 ~250 回出現 (平均 288 字) | ○ 動作 |
| episode 永続 (`expected`) | 81 episode 中 61 件 (002) | ○ |
| 質的乖離 (`prediction_error`) | 48/81 件。「ツール成功だが期待外れ」を正しく言語化 | ○ 質が高い |
| 想起→強化 | recall_count 最大 21、rc>=3 が 21 episode | ○ (修正後) |
| 再解釈 (段1) | journal 28 件。時点更新・現在文脈への接続あり | ○ だが誤差を名指ししない |
| 学び生成 (段2) | **4 件 (p1: 3, p3: 1)。全て予測誤差由来** | △ 初成立、ただし偏り |
| 学びの戻り (【関連する学び】) | 20/287 prompt | △ 薄い |
| 学び→次の予測 | p1 後半の予測が過去の失敗を明示引用し較正される | ○ 質感が出た |

### 生まれた学び (全 4 件)

- p1 [imp8, conf1.00, evid6] 「思った場所に資源はないことが多い」
- p1 [imp7, conf0.80, evid4] 「拠点や浜の探索は資源を期待するほど実りがない」
- p1 [imp6, conf0.70, evid3] 「探索の見積もりは過信しがちだ」
- p3 [imp8, conf0.70, evid3] 「gather ツールは使えず、interact で流木を拾う必要がある。」

gist prompt の予測誤差重視の指示 (semantic_gist_service) は機能している。
一方で **p1 の 3 件はほぼ同一教訓の変奏**で、belief revision 不在
(`existing_related_semantic=None` ハードコード) が初回実走で即実体化した。
confidence はクラスタサイズの機械値 (0.4+0.1n) で、conf=1.00 が「多く数えた」
以上の意味を持たない。

### 予測の質的変化 (p1)

前半: 「〜が見つかるかもしれない」の素朴な楽観が連発。
後半: 「探索はもう 2 回失敗している」「流木が足りないので火はつかないだろう」
と、過去の失敗を明示的に引用した反実仮想混じりの予測へ変化。
副作用として、後半の `expected_result` に計画・逡巡 (「〜すべきだ。が、ここでは
まだ試す」) が混入し、フィールドの規律 (予測 vs 意図) がドリフトする。

### その他の観察

- **memo が明示的学習チャネルとして既に機能**: 「岩礁海岸は山方面に通じず×」
  「カニは素手で倒すのは困難」など、予測が外れて得た世界知識がエージェント
  自身の手で memo に書かれている。自動の semantic が死んでいた 002 でも
  こちらは動いていた。
- **能動想起ツールの発見性**: p3 が幻覚ツール `remember` に失敗
  (UNSUPPORTED_TOOL) した後、正しい `memory_recall_episodes` に辿り着けず
  記憶ツール自体を放棄。`memory_search_semantic` / `memory_explore_related`
  は 4 人 × 140 tick で使用 0 回。
- **観測性の穴**: semantic 昇格と再解釈に TraceEventKind が無く、「学びがいつ
  何件生まれたか」は snapshot の事後解析でしか分からない。
- 教材の供給は自然に豊富: survival シナリオでは「探索すれば見つかるはず→
  何もなかった」という同型の予測誤差が反復し、段2 の一般化の素材になる。

## 設計改善 (実験フィードバック反映)

[prediction_error_correction_design.md](./prediction_error_correction_design.md)
(3 段のはしご) を土台に、実走で得た証拠で更新する。

1. **配線の構造対策**: EpisodicRecallConfig への個別 field 手渡しは配線漏れを
   繰り返し生む (#565 慣化、今回 link_service)。stack→prompt builder は
   「stack を丸ごと渡す」か、EXPECTED_PAYLOAD_KEYS と同様の起動時整合チェック
   (stack が持つ store と prompt builder が受けた store の同一性検証) を足す。
2. **belief revision を段2 の中核に昇格**: 重複学びが初回実走で出た。
   (a) 昇格時に `existing_related_semantic` を実際に渡す (現在 None
   ハードコード)、(b) semantic store に supersede 操作を足し(再解釈 journal
   方式)、既存学びの改訂として書く、(c) 機械値 confidence は廃止するか
   「反証で下がる」値に再定義する。学びが prompt に出たターンの
   PredictionOutcome に belief_id を紐づければ (3 段のはしごの
   prediction_context_id と同じ土台)、「学び自体が外れた」を反証 evidence
   として流せる。
3. **誤差駆動の昇格 (PR3.5 / 段2) の価値は実証された**: 003 で学びが生まれた
   のは「想起が偶然重なった」p1/p3 のみで、p2/p4 は 0 件。同じ cue signature で
   non-empty prediction_error が k 回反復したら、recall_count/cluster ゲートを
   バイパスして直接 gist 候補にする経路を足す (段0 台帳がそのまま証拠台帳に
   なる)。
4. **memo→semantic の合流**: エージェントが memo に書く世界知識は実質
   belief。memo_done / memo 溢れの時点で「これは世界についての持続的な学びか」
   を既存 LLM 呼び出しに相乗りで判定し、semantic へ蒸留する経路を検討。
   明示的学習 (memo) と暗黙的学習 (昇格) の二重化ではなく合流として設計する。
5. **観測性**: `SEMANTIC_PROMOTED` / `REINTERPRETATION_APPLIED` の trace
   イベントを足す。実験の feedback loop 速度に直結する。
6. **段0 の既定計画は据え置きで妥当**: 最新 1 件→N 件台帳 (PR-A) の必要性は
   実走でも確認 (複数 action chunk で前半の予測が消える)。加えて「結果が
   まだ出ていない予測」の保持 (数 tick 後に結果が出る待ち型予測) を台帳仕様に
   含める。
7. **snapshot 追従**: 発見 #3 の修正 (stub に 3 store を追加)。
   per-Being store checklist (#27) を experiment スクリプトの stub にも適用する
   運用を明文化。

## 再現手順

```
# 修正 2 件 (naive datetime / link_service 配線) を含む working tree で:
LLM_CLIENT=litellm LLM_EXPECTED_RESULT_POLICY=required \
LLM_EPISODIC_REINTERPRETATION_ENABLED=1 SEMANTIC_PASSIVE_TOP_K=3 \
SEMANTIC_LLM_GIST_ENABLED=1 SEMANTIC_SEARCH_ENABLED=1 \
EPISODIC_RECALL_ENABLED=1 EPISODIC_EXPLORE_RELATED_ENABLED=1 \
make experiment-with-snapshot PYTHON="uv run python" \
  SCENARIO=data/scenarios/survival_island_v2.json \
  OUT=var/runs/memory_full_XXX MAX_WORLD_TICKS=140 WORKERS=4 EPISODIC=1
```

1 run 約 8.5 分 / LLM 呼び出し ~290 回 (プロンプト 10-12k tokens)。
