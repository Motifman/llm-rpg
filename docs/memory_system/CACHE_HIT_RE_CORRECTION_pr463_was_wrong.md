# 逆訂正: PR #463 (cache hit 48% は事実誤認) は私のバグだった

> このファイルは **PR #463 の訂正自体が誤り** だったことの記録。
>
> 元 doc の cache hit 48% は **正しかった**。PR #463 で「事実誤認」とした訂正
> スタンプは取り消し、元の数字を復元する。

## 何が起きていたか (時系列)

### 2026-06-12 (元 doc が書かれた日)

`prefix_cache_full_run_v3_true_rolling.md` 等に **「cache hit rate
47.7% / 49.0% / 48.0%」** と記録。

### 2026-06-13 昼 (PR #463 — 訂正)

私 (Claude) が H run の cache 分析中に **「過去 doc の 48% は実 trace と
一致しない、hallucinated 値」** と主張し PR #463 で訂正。

### 2026-06-13 夜 (本逆訂正)

ユーザー指摘「OpenRouter で cache 情報が取れるか実機で確認すべき」を受け、
実機 dump → **OpenRouter は `prompt_tokens_details.cached_tokens` をちゃんと
返している** ことが判明:

```python
"prompt_tokens_details": {
    "audio_tokens": 0,
    "cached_tokens": 2048,    ← 2 回目で cache hit
    "cache_write_tokens": 0,
    "video_tokens": 0
}
```

そこで C run v3 の trace を **正しい key 名で再 grep** したところ:

```
$ grep '"kind": "llm_call"' var/experiments/parasail-rolling-true-effect/C-true-rolling/trace.jsonl | \
  python -c "正しい key 'cached_tokens' で集計"
n=431 cached_calls=420 total_prompt=3,751,641 cached=1,802,545 rate=48.0%
```

= **元 doc の 48.0% は実 trace と一致する正しい数字** だった。

## 私のバグの正体

PR #463 で書いた検証スクリプト:

```python
for line in open('trace.jsonl'):
    e = json.loads(line)
    p = e['payload']
    cp = p.get('cached_prompt_tokens') or 0   # ← この key は trace に存在しない!
    ...
```

trace に書かれている実際の key 名は **`cached_tokens`** (litellm_client.py:50
の `LlmCallMetrics.cached_tokens` 由来)。`cached_prompt_tokens` という key 名
はそもそも存在しない。

`.get('cached_prompt_tokens')` は **存在しない key に対して None を返す**
ので、全 run で「cache hit 0%」と判定していた。

= **typo っぽいケアレスミス**。それを根拠に過去 doc を「hallucinated」と
誤って結論した。

## 本当の真値 (provider 別)

実 trace の **正しい key 名 `cached_tokens`** で集計:

| run | provider/model | calls | prompt | cached | hit% |
|---|---|---|---|---|---|
| C run v3 | Parasail gemma fp8 | 420 | 3,751,641 | 1,802,545 | **48.0%** ✓ |
| D run | DeepInfra gemma fp8 | 288 | 2,818,115 | 0 | **0.0%** |
| H run | WandB deepseek-v4-flash | 207 | 2,260,154 | 0 | **0.0%** |

実機 sanity dump (同 session でやった) と一致:

| provider | model | attempt 2 cached | cost reduction |
|---|---|---|---|
| Parasail fp8 | deepseek-v4-flash | 2048 | -46% |
| DeepInfra fp4 | deepseek-v4-flash | 2048 | -73% |
| WandB fp8 | deepseek-v4-flash | 0 | (cache なし) |

= **OpenRouter は cache 情報を返している**。問題は **provider 依存**:
- Parasail / DeepInfra fp4 (deepseek-v4-flash): cache 効く
- DeepInfra gemma fp8 (D run): cache 効かない (なぜか同じ DeepInfra でも)
- WandB: cache 効かない

`litellm_client.py:_extract_cached_tokens()` にバグはない (line 618 で
`isinstance(details, dict)` 経路もケアされている)。

## PR #463 で何が壊れたか

| doc | PR #463 の修正 | 本逆訂正で復元 |
|---|---|---|
| `prefix_cache_full_run_v3_true_rolling.md` | 比較表の cache hit 列に取消線 + 0% に書き換え | 元の 48.0% を復元 |
| `prefix_cache_v3_deep_analysis.md` | §1 全体を「信用しないでください」とマーク | マーク撤去、§1 を元通り有効 |
| `d_run_objective_fix_analysis.md` | C run v3 列を「48.0% → 0.0% (元 doc 誤り)」に | 元の 48.0% を復元、「DeepInfra で cache が消えた」結論を有効化 |
| (新規 PR #463) `CORRECTION_cache_hit_was_always_zero.md` | (新規追加された訂正 doc) | **削除** |

代わりに本 doc (`CACHE_HIT_RE_CORRECTION_pr463_was_wrong.md`) を残す。

## 影響の再評価

### ✅ 復活する過去結論

- **C run v3 は cache hit 48% で安かった** (cost $0.42, per-call $0.00097)
- **`stable_to_volatile` section ordering が cache 寿命を最大化する効果がある** (推定)
- 「Parasail から DeepInfra に乗り換えると cache が消える」 ← **実は正しい**
- C run v3 が D run より速かったのは cache のおかげ

### ⚠ 残る正しい結論 (PR #463 でも影響なし)

- 物語品質 (objective 駆動化 / 狼煙到達) は影響なし
- 選択的 retry / max_retries=0 / wall-time cap の判断は影響なし

## 私が直すべきこと (今 doc を書きながら反省)

| ID | 教訓 |
|---|---|
| L1 | **trace 分析スクリプトは key 名を実際に存在確認してから書く** (`set(payload.keys())` を一度 print して確認) |
| L2 | **過去 doc に「不一致」と言う前に、自分の検証スクリプトを 1 行ずつ疑う** |
| L3 | **「LLM が hallucinated だ」と決めつける前に、元情報の信頼性も検証する** (今回の元 doc は実際は trace 一致だった) |
| L4 | **doc を訂正するときは必ず実機で再確認する手順を doc 自体に残す** (今後の人が容易に再現できるように) |

## やるべきこと (今 doc PR で対応)

- [x] `prefix_cache_full_run_v3_true_rolling.md` の取消線・訂正スタンプを撤去、元の数字を復元
- [x] `prefix_cache_v3_deep_analysis.md` の §1 警告マーカーを撤去
- [x] `d_run_objective_fix_analysis.md` の C run v3 列を元通りに
- [x] `CORRECTION_cache_hit_was_always_zero.md` を削除 (= PR #463 が新規追加した訂正 doc)
- [x] 本逆訂正 doc を追加 (= 今読んでいるもの)

## 詫び

PR #463 のレビュー / マージは正常な flow でしたが、その元データ (= 私の検証
スクリプト) に typo がありました。深く反省します。

---

逆訂正日: 2026-06-13 夜
発見経緯: ユーザー指摘「litellm/OpenRouter で cache hit token は本当に取れ
ないのか、それとも我々側の問題か」→ 実機 dump → key 名違い発覚
担当: Motifman + Claude Opus 4.7
