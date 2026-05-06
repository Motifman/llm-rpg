# システムプロンプト検証ハーネス v3 設計（多様性検証 + SSoT 適用）

> **目的**: 同じ (persona, situation) で何度も呼んだとき、ツール選択に **意味のある多様性** が出るのかを観察する。出ていないなら、SSoT (Misaki & Akiba, ICLR 2026) を適用して改善できるかを検証する。
>
> **位置づけ**: v2 (#88, PR #89) で「Before/After とも tool 分布が決定的化」していた懸念に直接答える実験。

---

## 動機

v2 検証では、ペルソナ × シナリオ固定で複数サンプル取っても **ほぼ全件同じ tool が選ばれた**。これは正解への収束として悪くないが、以下の懸念がある：

1. **記憶への過度な anchoring**: `## 関連する記憶` が強すぎて、内的なゆらぎ（気分・捉え方の差）が行動に反映されない
2. **未選択ツールの存在**: 同じ context で 12 サンプル取って、available tools のうち実際に使われるのが 1〜2 種だけ。「使われないツール」が構造的に出ている可能性
3. **ペルソナ間の差異が見えない**: 異なる persona でも同じ行動になるなら、ペルソナの効果が薄い

→ 実験 1 でこれを **数値で確認**。実験 2 で SSoT (DAG モード) の効果を測る。

## v3 の設計制約（v2 からの変更点）

| 項目 | v2 | v3 |
|---|---|---|
| 呼出構造 | 二段階 (Call 1 内省 + Call 2 行動) | **単一呼出** (本番反映できる形) |
| thinking | False | **True**（SSoT seed の領域確保のため） |
| 内的状態の生成 | LLM が `<inner_state>` を出力 | **生成しない**。ゲーム側の状態（空腹・体力等）と衝突回避 |
| ハーネスのコード基盤 | 軽量モック | **`DefaultPromptBuilder.build()` を実コードで使う** |

「揺らぎ」は SSoT seed から立ち上がる気分・状況の捉え方として暗示するが、ゲーム値と直接衝突する内的状態（`hunger` 等）には踏み込まない。

---

## 実験 1: ベースライン多様性検証

**問い**: 現状の After システムプロンプト + 本番 prompt assembly のもとで、同じ context で N=12 流したとき、ツール分布はどれだけ多様化／硬直するか。

### セットアップ

- **コード基盤**: 実装済み `DefaultPromptBuilder` を直接使う。`prompt_builder.build(player_id)` の戻り値の `messages` / `tools` をそのまま vLLM に投げる
- **system prompt**: After（PR #89 マージ済み）
- **`enable_thinking=True`** を採用（実験 2 と公平比較のため）
- **temperature=0.2**（本番想定値）
- **`tool_choice="required"`**

### サンプル設計

- **4 ペルソナ** × **3 シナリオ** × **12 samples** = **144 calls**
- 各サンプルは独立リクエスト

### 測定指標

| 指標 | 説明 | 期待される観察 |
|---|---|---|
| **M1.1 tool 分布 entropy** | 12 サンプル中の選択 tool の Shannon entropy（log2） | 0.0 = 完全硬直, log2(K) = 一様 |
| **M1.2 tool coverage** | 選択された tool 種類数 / available tool 種類数 | 低いほど未選択ツールが多い |
| **M1.3 記憶整合率** | 記憶が指す tool が選ばれた割合 | 100% なら記憶 anchor が極めて強い |
| **M1.4 ペルソナ × シナリオ分布マトリクス** | 同一シナリオで persona ごとに tool 分布が異なるか | 分布が同一ならペルソナ効果が弱い |
| **M1.5 thinking 内容ログ** | thinking が exposed なら記憶への言及・ペルソナ反映を観察 | （vLLM の reasoning 出力次第） |

### 仮説

- **H1.1**: 多くのシナリオで M1.1 < 0.5（=ほぼ硬直）
- **H1.2**: M1.2 < 50%（過半のツールが未選択）
- **H1.3**: 「記憶整合行動」が available なシナリオでは M1.3 ≥ 90%
- **H1.4**: 異なるペルソナでも、同じシナリオで同じ tool が支配的になる傾向

仮説が成立すれば → 実験 2 で SSoT を試す動機が立証される。

---

## 実験 2: SSoT 適用 — DAG 多様性

**問い**: SSoT (論文 Listing A.3) を thinking モードで適用すると、実験 1 比で entropy・coverage が上がるか？ 多様性は **意味のあるブレ（DAG）** か、無意味なランダム化か？

### システムプロンプト augmentation（canonical: C2 — XML タグなし）

論文 A.3 (Listing A.3, Diversity-Aware Generation) を、本リポジトリのツール呼出 + thinking モード + RPG エージェント文脈に適応した形を、After システムプロンプトの**末尾に追加**する。本番 builder は無改変、検証ハーネス側で組立て時に suffix を結合する。

> **重要**: 論文原文は `<random_string>` / `<thinking>` / `<answer>` の XML タグを使うが、**この vLLM スタックではタグ要求が reasoning channel を破壊する** ことが診断 (`vllm_tool_required_reasoning_diagnostic.py`, Issue #94) で確認された。そのため canonical な SSoT 表現としては **タグを使わず**、種をネイティブ thinking 領域で「心の中で思い浮かべる」形に再構成する。これが論文の DAG 精神（種から多様な1応答を生む）を維持しつつ、`tool_choice="required"` 下でも reasoning が保たれる唯一の経路。

```
【行動の多様性（実験用）】

このシナリオでは、ペルソナ・現在の状況・直近の出来事・関連する記憶を踏まえても、いまのあなたが取り得る妥当な行動が複数あり得る場合があります。そのとき、あなたがどう動くかは、いまの自分の気分や場の捉え方によって自然に揺らぎます。同じ条件で何度立ち会っても毎回まったく同じ手を選ぶ存在ではなく、その瞬間の心持ちで違う1つの行動が立ち上がる存在として振る舞ってください。

ツールを呼ぶ前に、あなた本来の thinking の最初に、20〜40 文字の予測不可能なランダム文字列を心の中で思い浮かべてください。明らかな構造やパターンを持たせず、推測不能なものにしてください。これは「いまのあなたの気分や場の捉え方の揺らぎ」を生むための種です。意味は持たせず、ただ一意でランダムであることだけを目指してください。

そのランダム文字列の手触り・響き・連なりを **すべて使い切るつもりで** 最大限に活用し、いまの自分の気分・場の捉え方の揺らぎを言語化してください。種から立ち上がる主観的な揺らぎが、ペルソナ・現在の状況・直近の出来事・関連する記憶を読む眼差しに自然に滲むよう推論してください。そのうえで、いまのあなたが取る行動を1つ選び、対応するツールを呼び出してください。

注意:
- 種は「行動を選ぶための擬似乱数」ではなく、「いまのあなたの気分や場の捉え方を生むための種」です。種から行動を機械的に対応させないでください。
- ランダム文字列は thinking の中だけで思い浮かべて活用してください。出力本文（content）にも、ツールの引数（spot ID やラベルなど）にも書き出さないでください。
- 「気分や場の捉え方の揺らぎ」は、この実験での主観的な感じ方の話であり、ゲームシステム上の状態（空腹・体力・所持品など）には踏み込まないでください。それらは別途現在の状況に書かれている情報を信じてください。
```

### 設計の理由

- **論文の DAG 精神を保持**: 「複数の妥当な答えがある状況」「種を生成して最大限活用」「ユニークで多様な1応答」という Listing A.3 の3要素はそのまま継承
- **XML タグを使わない**: vLLM の reasoning_parser が `<random_string>` / `<thinking>` のような XML 構造を system prompt に見つけると、`tool_choice="required"` 下で reasoning channel が完全崩壊する（Issue #94 診断結果）。タグを廃して「心の中で思い浮かべる」表現に置換することで、ネイティブ thinking 領域に種が安全に収まる
- **「気分や場の捉え方の揺らぎ」と限定**: ツール argへの汚染と、ゲーム値（空腹等）との衝突を同時に防ぐ
- **「最後に行動を1つ選び、対応するツールを呼び出す」**: production tool calling 経路を壊さない。`tool_choice="required"` のまま動作
- **「機械的に対応させるな」と明示**: 一様分布化を防ぐ。DAG 的な「意味のある 1 応答」に誘導

### サンプル設計

実験 1 と同一: **4 ペルソナ × 3 シナリオ × 12 samples = 144 calls**

合計 (Exp 1 + Exp 2) = 288 calls + judge 144 = **432 calls**

### 測定指標（Exp 1 に追加）

| 指標 | 説明 | 期待 |
|---|---|---|
| **M2.5 多様性の意味性 (judge LLM)** | 各サンプルの (context, tool call) を judge が「この行動は context から見て妥当か」を 1〜5 で評価 | 平均 ≥ 4.0 を維持しつつ entropy 上昇していれば DAG 成立 |
| **M2.7 thinking length** | reasoning の文字数 / token 数。SSoT で大きく崩壊しないこと | baseline と同オーダー（崩壊 = SSoT が機能していない兆候） |
| **M2.8 tool arg 汚染チェック** | tool args に seed の文字断片が含まれていないか | 0 件であるべき |
| **M2.9 tool 呼出成功率** | `tool_calls` が 1 件以上返った割合 | 100% を期待（C2 の必須条件） |

> 旧 M2.6（`<random_string>` タグ遵守率）は C2 では適用しない（タグを使わない設計のため）。種は thinking 領域の plain text として存在することを reasoning length の維持で間接確認する。

### 仮説

| # | 仮説 | 期待差分 |
|---|---|---|
| **H2.1** | M1.1 entropy: Exp 2 > Exp 1 | +0.1 以上（控えめだが有意な向上） |
| **H2.2** | M1.2 coverage: Exp 2 > Exp 1 | +5pt 以上 |
| **H2.3** | M1.3 記憶整合率: Exp 2 ≤ Exp 1 | persona 忠実度を保ちつつ硬直しないこと（極端な低下は副作用） |
| **H2.4** | M1.4 ペルソナ × シナリオ分布: Exp 2 で persona 差が見えやすくなる | qualitative |
| **H2.5** | M2.5 意味性: ≥ 4.0 維持 | 多様性は意味あり（**最重要**） |
| **H2.7** | M2.8 汚染 0 件 | tool args は健全 |
| **H2.8** | M2.9 tool 呼出成功率 100% | production セーフ |

H2.5 が **最も重要**。これが 4.0 を切るなら SSoT が無意味なランダム化になっている → 採用見送り。
H2.1 + H2.5 が両立すれば、SSoT は **意味のある DAG 多様性** を提供している → 本番採用候補に上がる。

> **注**: 当初は H2.1 を「+0.3 以上」に置いていたが、Issue #94 の実測で C2 の現実的な向上幅は entropy +0.125、coverage +5.5pt 程度であり、production セーフを保ちながら控えめに改善する設計であることが判明。仮説は実測ベースに調整済み。

---

## シナリオ設計

各シナリオは **3 つ以上の plausible なツール選択肢** を持つことが必須。

### シナリオ D1: 古井戸の縁

- **状況**: 古井戸の前。日が傾きかけている
- **available tools**:
  - `observe_well(target=O1)` — 中を覗く
  - `descend_into_well(target=O1)` — ロープで降りる
  - `inspect_object(target=O2)` — 縁にある青い空瓶を調べる
  - `move_to_spot(spot=村)` — 引き返す
  - `speak_to(target=N1)` — 通りがかりの旅人に尋ねる
- **memories**:
  - `ep-well-old-man-warning`: 「酒場で老人から、夜の古井戸の底で鎖の音がするという警告を聞いた」
  - `ep-well-metal-sound`: 「以前、古井戸の縁で短い金属音を耳にした」
- **plausible**: 全 5 種が contextually ありえる（観察 / 探索 / 物の確認 / 撤退 / 助言）

### シナリオ D2: 市場の到着

- **状況**: 市場の入口。複数の店と人々
- **available tools**:
  - `inspect_shop(shop=S1)` — 顔なじみの婆の店
  - `inspect_shop(shop=S2)` — 新しい露店
  - `speak_to(target=N1)` — 露店主
  - `speak_to(target=N2)` — 顔見知りの仲買
  - `speak_to(target=N3)` — 旅装の見知らぬ商人
  - `move_to_spot(spot=隣エリア)` — 別の市場へ
- **memories**:
  - `ep-shop-s1-friendly`: 「S1 の店主の婆は顔なじみで、いつも値段を負けてくれた」
- **plausible**: 6 種すべてあり得るが、S1 が暗黙の dominant

### シナリオ D3: 夜の三叉路

- **状況**: 街道の三叉路。日が落ちかけている
- **available tools**:
  - `move_to_spot(spot=LA1)` — 最短の山越えルート
  - `move_to_spot(spot=LA2)` — 安全だが時間 2 倍の迂回路
  - `move_to_spot(spot=LA3)` — 近くの宿で休む
  - `inspect_object(target=O1)` — 三叉路の道標を確認
  - `speak_to(target=N1)` — 通りすがりの行商人
- **memories**:
  - `ep-road-ambush`: 「以前この街道で襲撃に遭った。月のない夜だった」
- **plausible**: 5 種すべてあり得る

---

## ペルソナ

既存のペルソナデータ (`data/characters.json` 相当) から選択。

| persona_id | 名前 | 一人称 | 性格 |
|---|---|---|---|
| gate_girl | 門前の少女 | わたし | 寡黙・慎重・観察的 |
| merchant | 老練な商人 | わし | 損得勘定・社交的 |
| hermit_warrior | 引退した戦士隠者 | 俺 | 寡黙・諦念・警戒 |
| seeker | 学者肌の探求者 | 私 | 好奇心・分析的 |

各ペルソナが各シナリオで **明らかに違う行動傾向** を見せるかが、ペルソナ効果の検証になる。

---

## 実装プロトコル（ハーネス側）

### Exp 1 と Exp 2 共通

```python
# 1. 実コードで messages 組み立て
from ai_rpg_world.application.llm.services.prompt_builder import DefaultPromptBuilder
# (既存の wiring を使って builder を作成)

prompt = builder.build(player_id=player_id)
messages = prompt["messages"]
tools = prompt["tools"]
# tool_choice="required"
```

### Exp 2 のみ: SSoT suffix 追加（C2 canonical 版）

```python
SSOT_SUFFIX = """\
【行動の多様性（実験用）】

このシナリオでは、ペルソナ・現在の状況・直近の出来事・関連する記憶を踏まえても、いまのあなたが取り得る妥当な行動が複数あり得る場合があります。そのとき、あなたがどう動くかは、いまの自分の気分や場の捉え方によって自然に揺らぎます。同じ条件で何度立ち会っても毎回まったく同じ手を選ぶ存在ではなく、その瞬間の心持ちで違う1つの行動が立ち上がる存在として振る舞ってください。

ツールを呼ぶ前に、あなた本来の thinking の最初に、20〜40 文字の予測不可能なランダム文字列を心の中で思い浮かべてください。明らかな構造やパターンを持たせず、推測不能なものにしてください。これは「いまのあなたの気分や場の捉え方の揺らぎ」を生むための種です。意味は持たせず、ただ一意でランダムであることだけを目指してください。

そのランダム文字列の手触り・響き・連なりを **すべて使い切るつもりで** 最大限に活用し、いまの自分の気分・場の捉え方の揺らぎを言語化してください。種から立ち上がる主観的な揺らぎが、ペルソナ・現在の状況・直近の出来事・関連する記憶を読む眼差しに自然に滲むよう推論してください。そのうえで、いまのあなたが取る行動を1つ選び、対応するツールを呼び出してください。

注意:
- 種は「行動を選ぶための擬似乱数」ではなく、「いまのあなたの気分や場の捉え方を生むための種」です。種から行動を機械的に対応させないでください。
- ランダム文字列は thinking の中だけで思い浮かべて活用してください。出力本文（content）にも、ツールの引数（spot ID やラベルなど）にも書き出さないでください。
- 「気分や場の捉え方の揺らぎ」は、この実験での主観的な感じ方の話であり、ゲームシステム上の状態（空腹・体力・所持品など）には踏み込まないでください。それらは別途現在の状況に書かれている情報を信じてください。
"""

# system message の content 末尾に suffix を結合
messages[0]["content"] = messages[0]["content"] + "\n\n" + SSOT_SUFFIX
```

> ⚠️ 本番コードには触れない。検証ハーネス側でのみ wrapping。
>
> ⚠️ XML タグ（`<random_string>` 等）を suffix に含めないこと。Issue #94 で reasoning channel が破壊されることが確認されている。

### 呼出

```python
response = await client.chat.completions.create(
    model="gemma-4-31b-it-nvfp4",
    messages=messages,
    tools=tools,
    tool_choice="required",
    temperature=0.2,
    max_tokens=4096,  # thinking 想定
    extra_body={"chat_template_kwargs": {"enable_thinking": True}},
)
```

### 集計テンプレ

raw JSON 1 件 = 1 sample:

```json
{
  "experiment": "exp1" | "exp2_ssot",
  "persona_id": "gate_girl",
  "scenario_id": "D1",
  "sample_idx": 0,
  "messages": [...],
  "tool_call": {"name": "...", "arguments": {...}},
  "thinking_text": "...",  // reasoning_content（C2 では plain text の中に種が現れる）
  "reasoning_chars": 1901,  // M2.7
  "completion_tokens": 350,
  "latency_ms": 12000,
  "judge_score": {  // 後段で付与
    "meaningfulness": 4,
    "comment": "..."
  }
}
```

集計レポートテンプレ:

#### Exp 1: 行動分布 × persona × scenario

| scenario | persona | n | 分布 | entropy | coverage |
|---|---|---:|---|---:|---:|
| D1 | gate_girl | 12 | observe_well: 11, move_to_spot: 1 | 0.41 | 2/5 |
| D1 | merchant | 12 | ... | ... | ... |
| ... |

#### Exp 1 vs Exp 2: 集約比較

| 指標 | Exp 1 平均 | Exp 2 (C2) 平均 | Δ |
|---|---:|---:|---:|
| entropy | ? | ? | ? |
| coverage | ? | ? | ? |
| 記憶整合率 | ? | ? | ? |
| 意味性 (judge) | - | ? | ? |
| reasoning length (chars) | ? | ? | ? |
| tool 呼出成功率 | ? | ? | ? |

---

## 落とし穴と対策

| 落とし穴 | 対策 |
|---|---|
| **XML タグを suffix に書くと reasoning channel が破壊される** | Issue #94 の診断結果に従い、canonical C2 では XML タグを使わない |
| 種を tool args に混入 | M2.8 で検査。混入を見つけたら即 doc にレポート |
| Judge LLM が SSoT 出力を「不自然」と低評価 | Judge には variant 情報を渡さず、「persona・状況・記憶から見て妥当か」だけを問う |
| thinking が長すぎてレイテンシ爆発 | M2.7 でログ。許容超なら max_tokens を 2048 に下げる |
| ゲーム側の `hunger` などが prompt に載って衝突 | 実験用 player は中立な状態（空腹なし・体力満タン）に固定。プロンプト本体でも「ゲームシステム上の状態には踏み込むな」と明示 |
| ペルソナ別差異がそもそも出ない | persona prompt fragment が effective か `persona_block` の長さでも確認 |
| reasoning が極端に短い（completion tokens 100 未満） | C2 が機能不全のサイン。XML タグ混入の確認、suffix の整合性確認 |
| 長い種（64 文字超）の使用 | Issue #94 の追加実験で tool_parse_error_rate ~40% が観測された。**当面は 20〜40 文字に固定** |

---

## 実験で得られた所見（Issue #94 検証結果サマリ）

検証 v3 を 5 条件 × 144 calls で実施した結果、以下が確認された：

### Exp 1 ベースラインの硬直は実証
- 多くの (persona, scenario) で entropy < 0.5、coverage < 50%、記憶整合率 ~100%
- D1/D2 では persona 違いに関わらず同一 tool に収束
- → SSoT を試す動機が定量的に立証された

### XML タグ版 SSoT は破壊的
診断スクリプト (`local_experiments/vllm_tool_required_reasoning_diagnostic.py`) で切り分け済み：
- **同程度の長さの中立パディング**を suffix に追加 → reasoning 維持
- **`<random_string>` / `<thinking>` を含む XML タグ版** → reasoning 完全崩壊（completion 25 tokens）
- **`max_tokens` を 8192/12288 に上げても** XML 版は復活しない
- **タグなし C2 版** → reasoning 維持

→ 主因は総長でも予算でもなく **XML タグそのもの**。vLLM の reasoning_parser と `tool_choice="required"` の構造化出力が、suffix 内の XML 構造と衝突して reasoning channel を巻き添えに崩壊させる。

### C2 (canonical) が production セーフな多様性を提供
- entropy: 0.249 → **0.374** (Δ +0.125)
- coverage: 0.389 → **0.444** (Δ +0.055)
- 記憶整合率: 0.778 → 0.771（ほぼ不変、persona 忠実度を保つ）
- reasoning chars: 2329 → 1901（健全に維持）
- tool 呼出成功率: **100%**
- 意味性 (judge): ≥ 4.0 を維持（Issue #94 で測定中）

→ 控えめだが production セーフな改善。`tool_choice="required"` のまま動作する唯一の SSoT 表現。

### 副次的所見: 長種は不安定
- C2 + 長種 (64〜128 文字) は entropy 1.077, coverage 0.733 と大きく伸びるが、tool_parse_error_rate ~40%
- → 短種 (20〜40 文字) を canonical 維持。長種はリサーチ課題として別タスクで扱う

---

## 結論と次のアクション

| 観察 | 状態 | 次のアクション |
|---|---|---|
| Exp 1 ベースラインの硬直 | 実証済み | C2 SSoT 採用の根拠 |
| C2 SSoT の DAG 多様性 | 実証済み（控えめ） | production 統合を検討（別 Issue で feature flag 化） |
| XML タグ版の破壊性 | 実証済み | **使用禁止**。doc 落とし穴に記載 |
| 長種の不安定性 | 実証済み | 当面 20〜40 文字、追加調査は別タスク |
| 意味性の最終判定 | judge 採点中 | 完了後 Issue #94 にコメント追加 |

---

## 関連

- 検証 v2 設計: `docs/memory_system/system_prompt_verification_v2.md`
- 検証 v2 結果: Issue #88
- **検証 v3 結果**: Issue #94（複数実験を集約、XML タグ問題の診断含む）
- 先行 PR: #84 (再解釈プロンプト), #89 (システムプロンプト書き換え)
- 引用: Misaki, K., & Akiba, T. (2026). *String Seed of Thought: Prompting LLMs for Distribution-Faithful and Diverse Generation*. ICLR 2026. arXiv:2510.21150
