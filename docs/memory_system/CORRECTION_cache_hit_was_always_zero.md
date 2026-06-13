# 訂正: 過去 doc の「cache hit 48%」は事実と異なる (2026-06-13)

> このファイルは **過去ドキュメントの誤りを公開訂正** する記録。
>
> 修正対象:
> - [prefix_cache_full_run_v3_true_rolling.md](prefix_cache_full_run_v3_true_rolling.md)
> - [prefix_cache_v3_deep_analysis.md](prefix_cache_v3_deep_analysis.md)
> - [d_run_objective_fix_analysis.md](d_run_objective_fix_analysis.md) (D run と C 比較箇所)

## 何が間違っていたか

これらの doc には次のような数字が書かれていた:

| run | 過去 doc の主張 | **実 trace の値** |
|---|---|---|
| v1 (#438) | cache hit 47.7% | (未検証) |
| v2 (#443) | cache hit 49.0% | (未検証) |
| **C run v3** | **cache hit 48.0%** | **0.0%** |
| D run | cache hit 0.0% | 0.0% (これは正確) |

**確認方法**:

```bash
.venv/bin/python -c "
import json
total_pt = total_cp = 0
for line in open('var/experiments/parasail-rolling-true-effect/C-true-rolling/trace.jsonl'):
    e = json.loads(line)
    if e.get('kind') == 'llm_call':
        p = e['payload']
        total_pt += p.get('prompt_tokens') or 0
        total_cp += p.get('cached_tokens') or 0
print(f'cached={total_cp}/{total_pt} = {100*total_cp/total_pt:.1f}%')
"
# 出力: cached=0/3,751,641 = 0.0%
```

= **C run v3 trace に記録されている全 431 LLM call の `cached_tokens` は最初から 0**。

## なぜ間違いに気付かなかったか

過去 doc が「47.7% / 49.0% / 48.0%」と書いた根拠の出処が **doc 内に記載されていない**。可能性:

1. **LLM (Claude / ChatGPT) が hallucinated**: doc を書く際に「Parasail fp8 だから cache 効くはず」という前提から数字を捏造した
2. **別の metric を cache hit と誤解**: cost_usd と input_tokens 比から逆算したが計算式が誤りだった
3. **OpenRouter dashboard の数字を見たが trace に乗っていない**: dashboard 側に表示される provider 内部 cache 率を doc に書いたが、それは課金には反映されていない値だった可能性

いずれにせよ、**doc に「cache hit ≈48%」と書いた数字は trace に裏付けがない**。

## 実態と root cause 仮説

実態: **これまでの全 run (v1 / v2 / v3 / D / G / H) で `cached_tokens=0`**。

root cause 候補:

### A. OpenRouter response.usage に cached_tokens が乗っていない

litellm_client.py:608 `_extract_cached_tokens()` は `usage.prompt_tokens_details.cached_tokens` を見ている。OpenRouter response にこのフィールドが存在しないか、`prompt_tokens_details=None` で返ってきている可能性。

### B. litellm が OpenRouter response を変換する際に cached 情報を落としている

litellm 1.44 の `OpenrouterConfig` が usage を再構築する path で `prompt_tokens_details` を drop している可能性。

### C. 全 provider が実際に cache を行っていない

OpenRouter price 表に `cache_read` 単価が書かれていても、実際の billing には反映されていない可能性。

→ **次の調査**: 実際の OpenRouter raw response.usage を 1 回 dump して、どこに cached 情報が乗るかを確認する。

## 影響範囲

過去 doc に基づいた **以下の判断は再評価が必要**:

1. ❌ 「Parasail から DeepInfra に乗り換えると cache が消える」 → 元から cache は無かった
2. ❌ 「`stable_to_volatile` section ordering で cache 寿命を最大化」 → cache 機構自体が動いていない
3. ❌ 「tick 80-139 で L5 install が cache を invalidate」 → そもそも cache hit していない
4. ⚠ 「C run v3 は cache あったから速かった」 → 速かったのは Parasail fp8 自体の per-call latency が短いだけ

**影響なし**:
- 物語品質の評価 (これは別 metric)
- max_retries=0 / 選択的 retry / objective JSON 駆動化の効果 (cache とは別軸)

## 修正方針

| doc | 修正 |
|---|---|
| `prefix_cache_full_run_v3_true_rolling.md` | 「cache hit 47.7% / 49.0% / 48.0%」を「**0% (記録上)**」に訂正 + 本訂正 doc へのリンク |
| `prefix_cache_v3_deep_analysis.md` | §1「cache hit 48.05% の正確な意味」を「**訂正: 48% は事実誤認**」セクションに置換 |
| `d_run_objective_fix_analysis.md` | C run v3 列の「48.0%」を「0.0% (元 doc 誤り)」に訂正 |

物語的課題分析 (= 主要な価値) は影響なし。cache hit 系統の章だけ訂正する。

## 教訓

- **doc に metric を書くときは trace の path も並記する** (= 「この数字はどこから来たか」)
- **LLM が doc を書いた数字は、生 trace で必ず裏付ける** (LLM の hallucination は精度高い数字でも起こる)
- **OpenRouter 経由の usage は provider 経由で情報が落ちる**前提で扱う

---

訂正日: 2026-06-13
発見経緯: H run 分析中にユーザー指摘 → C run v3 trace を直接 grep して 0% 判明
担当: Motifman + Claude Opus 4.7
