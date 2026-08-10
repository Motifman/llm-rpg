# P2-① 意味記憶 passive recall の relevance 修正(語彙の噛み合わせ)

## なぜ

v4coop_reasonfirst_002 分析で、意味記憶の**獲得**は世界側改善でほぼ解けたが、**想起(retrieval)**が弱いと判明。
`SemanticPassiveRecallService` の score = α·recency + β·importance + γ·relevance(現状 α=β=γ=1.0)。ところが
**relevance が候補の約89%で 0** になり、score が実質 recency+importance に退化 → **状況に関係なく高importance の
belief が常時 surface**する(例: 床板の前で刃物が無いのに「床板は刃物が要る」が出ず、「救助には狼煙」が出続ける)。

### 根本原因: cue と belief が別の語彙
- **situation cue = ID/コード**(`episodic_cue_rules.build_situation_episodic_cues`): `place_spot=<spot ID 数値>` /
  `object=<object_id>` / `entity="spot_graph_player_N"` / `action=<tool名>`。
- **belief = 自然言語**(consolidation が付ける `tags: ["火","流木"]`、text「狼煙には流木が3本必要だ」)。
- relevance(`semantic_passive_recall_service._relevance`)は `cue.value == tag` か `cue.value in text` の**字面一致**。
  ID 値と日本語の語は一致しないので relevance≈0。

## 制約(重要): situation_cues は episodic と共有

`prompt_builder.py:1322` で `situation_cues = build_situation_episodic_cues(...)` を **1 回**生成し、
**episodic recall(:1372/:1473)と semantic recall(unconscious_context_provider 経由)の両方**に流している。
episodic recall は「マッチした cue canonical(`axis:value`)の数 = multi_cue_score」でスコアする
(`episodic_recall_slot_store.py:59-60`)。**よって既存 axis に値を足すと episodic 側のスコアが動く**。

## 方針: 新 axis `topic` で"意味語 cue"を追加(episodic には inert)

`build_situation_episodic_cues` に、既存の ID cue は残したまま、**新しい axis `topic`(または `keyword`)で
日本語の意味語 cue を追加**する。

- **episodic recall は不変**: 既存 episode は `topic` cue を持たないので `topic:火` は既存 episode の cue と
  マッチせず multi_cue_score に寄与しない(= 追加のみ・inert)。回帰テストで「新 axis 追加で episodic のスコア/
  順位が変わらない」を固定する。
- **semantic relevance が立つ**: `_relevance` は `cue.value` を axis 非依存で走査するので、`topic:火` の value
  「火」が belief tag「火」や text「狼煙には…火…」にマッチして relevance が上がる。

### 何を意味語 cue にするか(現在の状況から抽出)
- 現在地: spot の**名前/種別語**(「干潟」「山頂」「拠点」)
- 見えているオブジェクト: **名前**(「狼煙台」「緩んだ床板」「流木の山」)
- 現在の欲求: 閾値越えの need を語に(空腹高→「空腹」「食料」、HP 低→「負傷」等)
- 所持品: **アイテム名**(「火打ち石」「流木」)

すべて既にプロンプトの現在状態に日本語文字列として存在する情報。cue value は語そのもの(ID でなく)。

### マッチ規則
既存 `_relevance`(cue==tag or cue in text、hits/RELEVANCE_SATURATION_HITS 上限1.0)をそのまま使う。
belief の **text にも当たる**ので、LLM が付ける tag の語彙揺れ(火/焚き火/狼煙)に対して text マッチが緩衝になる。

### MAX_EPISODIC_CUES との関係(silent starvation 回避・重要)
`MAX_EPISODIC_CUES=32`(`episodic_cue_rules.py:43`)。実 run 002 の situation cue 数は最大19・大半11-16。
topic cue(5〜13個)を足すと rich な spot では 32 に到達し、既存 cue を押し出さない方針だと **topic が
truncate されて、情報が豊富な局面ほど relevance 修正が効かない silent starvation**になる。
→ **原則: topic cue は MAX_EPISODIC_CUES の budget 対象外にする**。cap の目的は episodic マッチのコスト
上限で、topic は episodic に inert なので episodic budget に数える必要がない。truncation(:574)は ID cue
(episodic 参加分)だけに適用し、topic cue はその後に append(cap 非対象)。回帰テストに「rich な状況
(cue 30個超相当)でも topic cue が落ちない」を1本入れる。

## 非目標 / 後段
- **embedding(A2)は今回やらない**。まず語 cue マッチ(A1)で効果を見る。コード注記の「将来 embedding」は後段。
- **importance rubric の変更はしない**。自己評価の belief 化は既に reflect 経路(P4)で分離済みで、②は概ね解決。
  relevance が立てば高importance belief も「関連する時だけ」出るようになり、②の追加調整はほぼ不要。
- 重み(γ)調整は、relevance が機能し始めたのを確認してから別途検討(今回は等重みのまま)。

## 成功条件(次 run / テストで測る)
- semantic_passive_recall の trace で **relevance>0 の比率が上がる**(現状 ~11%)。
- 状況関連 belief が surface する具体例(床板前で「刃物が要る」/ 山頂前に「流木3本・2人」)。
- **episodic recall のスコア/順位が新 axis 追加で不変**(回帰)。

## テスト
1. 現在状況(spot 名 / 可視オブジェクト名 / 高 need / 所持品名)から `topic` axis の意味語 cue が生成される。
2. その意味語が belief の tag/text にマッチして relevance>0 になる(ID cue のみだった従来は 0)。
3. `topic` cue を足しても episodic recall の multi_cue_score / 順位が変わらない(inert 回帰)。
4. 意味語 cue ゼロ(閾値未満・可視物なし)のとき従来どおり relevance=0 で fail-safe。

## 記憶系ワークフロー
本 PR は `docs/memory_system/memory_feature_workflow.md` に従う(専用 git worktree / 機能単位ブランチ /
PR 作成前レビュー)。関連: [[semantic_learning_consolidation_design]]。
