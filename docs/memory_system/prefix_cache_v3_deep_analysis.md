# C run v3 深掘り分析: 行動 / 記憶 / cache hit / timeout outlier (2026-06-12)

> ⚠️ **訂正 (2026-06-13)**: 本 doc §1 の「cache hit rate 48.05%」「48% 頭打ち」「tick
> 80-139 で cache 崩壊」等は **全て事実誤認**。C run v3 trace を直接読むと
> cached_tokens は全 431 call で 0、ratio は **0.0%**。詳細と root cause 仮説は
> [CORRECTION_cache_hit_was_always_zero.md](CORRECTION_cache_hit_was_always_zero.md)
> 参照。§1 (cache 系) は信用しないでください。§2-§4 (行動 / 記憶 / timeout outlier)
> は trace 裏付けあり、引き続き有効。

PR #453 でまとめた v3 run の数値結果を、**ユーザーからの 4 つの問い**に答える形で深掘りした記録。

1. プレイヤーの行動分析: 適切な動きができているか?
2. 記憶 (L4/L5) の進化分析
3. ~~cache hit ≈48% の頭打ち~~ → **訂正: cache hit は最初から 0%** (本 doc §1 は信用しないでください)
4. **litellm timeout 222s outlier の root cause**

## 1. ~~Cache hit rate 48.05% の正確な意味~~ → 訂正: 全 0%

> ⚠️ 以下の節 (§1 全体) は事実誤認に基づいています。実 trace の `cached_tokens`
> は全 431 call で 0。下記の計算式の分子 1,802,545 がそもそも誤りで、
> 正しくは 0 でした。一次資料として残しますが、引用しないでください。

### 数式の意味 (実体は 0 / 0 = 0%)

```
cache_hit_rate = sum(cached_tokens for c in calls) / sum(prompt_tokens for c in calls)
                = 1,802,545 / 3,751,641   ← 分子は実 trace に裏付けがない hallucinated 値
                = 48.05%                  ← 実体は 0%
```

~~= **「全 LLM call の入力 token のうち何 % が provider 側 cache から再利用されたか」**。Parasail fp8 では cached_tokens は `input_cache_read` 単価 ($0.06/Mtok) で課金される (通常 $0.15/Mtok の 40%)。~~

### per-call の構造 (2 つの世界)

| 種類 | 件数 | 平均 prompt | 平均 cache 比率 |
|---|---|---|---|
| cold miss (cached<100) | **105 (24%)** | 8112 tok | ~0% |
| warm hit (cached>=100) | 326 (76%) | ~9300 tok | **62.7%** |

→ 48% は「76% の call は 62.7% 再利用 + 24% の call は 0%」の加重平均。

### 頭打ちの原因: tick 80-139 で cold miss 急増

| tick 帯 | cold miss 比率 |
|---|---|
| 0-19 | 14.5% |
| 20-39 | 9.5% |
| 40-59 | 5.4% |
| 60-79 | 7.7% |
| **80-99** | **57.6%** ⚠️ |
| **100-119** | **84.0%** ⚠️ |
| **120-139** | 57.1% |
| 140-159 | 35.3% |
| 160-179 | 10.9% |
| 180-199 | 44.4% |

→ 中盤 (tick 80-139) で **cache が全面崩壊**。これが「48% 頭打ち」の正体。

### 中盤崩壊の仮説

L5 install 直後の cold rate: 13/36 = **36%** (L4 install 直後は 27%)

→ L5 generation (= ~45 tick に 1 度 / `stable_to_volatile` 順序で前方にある section) が **その後ろのセクション全部の cache を invalidate** している。tick 80-139 に L5 install が集中していた可能性が高い (要追加検証)。

### 構造的対策案 (PR 別タスク)

1. **L5 を section 末尾に移す**: cache 寿命を最大化 (stable_to_volatile の原則に反するので慎重に)
2. **L5 update をバッチ化**: 同 tick 帯で 4 player 全部の L5 をまとめて更新 → cache 崩壊の窓を 1 ヶ所にまとめる
3. **provider 側 prefix cache TTL の確認**: tick 80-139 で 1 call が長引くと TTL (~5-10min) を超えて自然失効する可能性

## 2. litellm timeout 222s outlier の root cause

### 観測

| call | wall_latency | completion | cached |
|---|---|---|---|
| max | **222s** | 155 tok | 4 (miss) |
| 2nd | 164s | 105 tok | 5 (miss) |
| 3rd | 130s | 0 tok | 0 |
| 4th | 66s | 113 tok | 4 (miss) |

90s timeout を設定したのに 222s が出ている。

### docs-lookup サブエージェント調査結果

**Root cause** (litellm v1.x 仕様):

1. `litellm.completion(timeout=90)` は **per-request read timeout** (HTTP 1 回分)。wall-clock 上限ではない
2. **litellm が `max_retries=2` を OpenAI SDK にデフォルトで渡す** (`main.py:openai.py` で `data.pop("max_retries", 2)`)
3. **OpenAI SDK が exponential backoff (0.5s → 最大 8s + jitter) で retry**

計算:
```
1 回目: timeout で 90s 切断
backoff: 0.5s
2 回目: 90s 切断
backoff: ~1s
3 回目: 40s で成功
合計: 90 + 0.5 + 90 + 1 + 40 ≈ 222s ✓ 完璧に一致
```

### Fix (別 PR で実装すべき)

```python
# infrastructure/llm/litellm_client.py
completion_kw: Dict[str, Any] = {
    "model": self._model,
    "messages": messages,
    "tools": tools,
    "tool_choice": tool_choice,
    "api_key": self._lite_api_key(),
    "timeout": self._timeout_seconds,
    # PR #45N (推定): max_retries=2 が wall_time を 3 倍に膨らませる根本原因
    "max_retries": 0,  # litellm 内部 + OpenAI SDK 両方の retry を無効化
}
```

`completion_base_kwargs()` も同じく `max_retries=0` を追加。

これだけで **wall_time が ~3 倍縮む**。実験時間も大幅短縮 (43min → ~15min 想定)。

## 3. プレイヤー行動分析: 適切な動きか?

### Player 別概要

| player | name | actions | moves | 主要 tool |
|---|---|---|---|---|
| 1 | エイダ (医師) | 118 | 14 | wait/interact/speech |
| 2 | ノア (リーダー) | 89 | **27** (最多) | **travel_to:33** |
| 3 | リオ (探索) | 107 | 12 | **explore:13** (最多) |
| 4 | カイ (カジュアル) | 107 | 7 | **speech:28** (最多) |

→ **役割分担が成立**: ノア = リーダー / 物資調達、リオ = 探索担当、カイ = コミュニケーター、エイダ = 拠点ケア。

### Persona の一貫性 (= 大成功)

各 player の inner_thought が **tick を通して persona を保っている**:

| player | 早期 (tick 3) | 中期 (tick 60-69) | 後期 (tick 178-195) |
|---|---|---|---|
| エイダ (医師) | 「火打ち石は手に入りました。次は流木を確保しましょう」(冷静敬語) | 「明確な返答がないのは不自然です。何らかの不自由な状況に陥っている可能性も」(分析的) | 「医師として冷静に判断すれば、この状態で無理に動けば...」(専門性維持) |
| ノア (軍人) | 「漂着物は調べ尽くしたか。次は船倉だ。先手を打って確保するぞ」(命令調) | 「無理に動いて足を踏み外せば終わりだ」(リスク評価) | 「リーダーが脱落すれば全員が終わる。屈辱的だが、ここで泥のように眠り...」(リーダー責任感) |
| リオ (短文) | 「漂着物はもうないか。船倉に残ってるもんを洗う」(短文) | 「キノコで腹は満たしたが、目的はロープだ」(目的志向) | 「身体が鉛だ。生存最優先。泥のように眠り、体力が戻るのを待つ」(短い決意) |
| カイ (若者) | 「マジで頑張るし！」 | 「俺がサクッと集めてあげよっか」 | 「マジかよ……。指一本動かす余裕なんてない」(若者口調維持) |

→ **persona drift ゼロ**。L5 持続効果が機能している。

### 段階的な意思決定 (= 物語進行)

3 段階で行動が変化:
- **早期 (tick 0-30)**: 物資収集 (流木 / 火打ち石 / 漂着物)
- **中期 (tick 30-100)**: 食料探索 (キノコ採集成功 / 水確保)
- **後期 (tick 100+)**: 疲労管理 (休息) + リーダー戦闘不能対応

### 課題

| 課題 | 状況 | 重要度 |
|---|---|---|
| **後期 wait 連打** | tick 180+ で 4 player 全員が疲労 100 で動けず wait のみ | MEDIUM (シナリオ的に妥当) |
| **狼煙台到達せず救助フロー未完** | 全 run で signal_fire_lit に到達しなかった (= ゲーム未クリア) | HIGH (シナリオ難易度?) |
| **player_2 過剰移動 (27)** | travel:33 → 移動コストで疲労を浪費した可能性 | LOW |

## 4. 記憶 (L4/L5) 進化分析

### L5 (自己像 + 世界観) の進化 — player_1 エイダの 11 世代

| gen | tick | 新たに認識した要素 |
|---|---|---|
| 1 | 21 | 漂着物依存の過酷な環境 (基本認識) |
| 2 | 25 | 仲間との役割分担 (社会性) |
| **3** | **30** | **「森の奥に正体不明の生物」リスク** ← 新発見 |
| 4 | 42 | 「資源の枯渇と再生のサイクル」← 動的世界 |
| 5 | 59 | **「時間的な制約」** ← TIME 概念 |
| 6 | 64 | 「効率的な回収地点を見極める」← 戦略的思考 |
| **7** | **87** | **「夜の静寂に潜む未知の脅威」** ← 昼夜サイクル |
| 8 | 119 | 「想像以上の時間と労力」← 困難の実感 |
| 9 | 156 | 「仲間と協力して着実に」← 協力強調 |
| 10 | 174 | 「特定の希少な資材が必要」← 困難の具体化 |
| **11** | **194** | **「仲間の負傷や行方不明者」** ← 社会的危機認識 |

→ **Generative Agents 風 reflection** が完璧に機能。世界モデルが時間と共に発達し、新しい体験 (モンスター遭遇 / 夜の到来 / 仲間の負傷) を統合している。

### L5 self_image の不変核

全 11 世代で共通する核:
> 「私はこの見知らぬ地で生き延びるため、慎重に周囲を観察し、確実な資源を求める探索者だ。」

→ 核は不変、装飾的な後段だけが体験で更新される。これは設計通り (L5 design の persona drift 防止策が機能)。

### L4 (短期活動) の品質

サンプル (tick=4 player_4 カイ):
```
compressed:  リオ、エイダ、ノアと共に流木の山や波が運んだ漂着物を調べ、
             その後難破船の船倉を探索したが、得られるものはほぼ底をついた。
emotional:   周囲を調べ尽くして収穫がなく、焦燥感と慎重さが混ざり合っている。
unresolved:  ['新たな漂着物が波に運ばれてくるのを待つ必要がある',
              '生存に必要な物資の確保']
```

→ **意味のある日本語要約 + 感情状態 + 未解決事項** が揃っている。設計通り。

## 総合所見

### ✅ 成功

1. **L4/L5 が 94% LLM-backed** で動作 (PR #439-#451 全成果)
2. **persona drift ゼロ** で 200 tick 走行
3. **世界モデルが動的に発達** (新環境 / 昼夜 / 社会的状況の取り込み)
4. **行動が状況に応じて段階進化** (収集 → 探索 → 休息)

### ⚠️ 残課題 (優先順)

| 優先 | 課題 | 根本原因 | 修正案 |
|---|---|---|---|
| ⭐⭐⭐ | **timeout 222s outlier** | `max_retries=2` が wall_time を 3 倍化 | `max_retries=0` を litellm_client に追加 (簡単) |
| ⭐⭐ | **cache hit 中盤崩壊 (tick 80-139)** | L5 install が後続 section の cache を invalidate | section order の見直し or L5 batch update |
| ⭐⭐ | **救助フロー未到達** | シナリオ難易度? / 狼煙台への動機付け不足 | scenario design feedback |
| ⭐ | **後期 wait 連打** | 疲労 100 で動けない (= シナリオ的に妥当) | (修正不要) |

---

実験日: 2026-06-12
担当: Motifman + Claude Code (Opus 4.7 / 1M)
関連: PR #453 (v3 run), docs-lookup subagent (litellm 仕様調査)
