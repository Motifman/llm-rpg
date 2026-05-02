# Episodic Memory System Specification

この文書は、LLM エージェントに「人間らしい連続性のある記憶」を持たせるための、エピソード記憶システム仕様の叩き台である。

**関連**: 実装フェーズとコード移行順は [episodic_memory_implementation_plan.md](./episodic_memory_implementation_plan.md)。長文の補足・Tool schema 詳細は [episodic_memory_reimplementation_plan.md](./episodic_memory_reimplementation_plan.md)。

目的は、過去ログを検索できるようにすることではない。過去の体験が、現在の注意、予測、感情、行動選択、他者理解、自己物語に影響する状態を作ることである。

## 1. 基本方針

記憶は攻略情報 DB ではない。

このシステムでは、記憶を以下の循環として扱う。

```text
現在状況
  -> 行動前予測
  -> 行動 / 観測
  -> 予測誤差
  -> 主観エピソード化
  -> 関連記憶との連想形成
  -> 想起
  -> 現在文脈での再解釈
  -> 固定化 / 意味化
  -> 次の注意・予測・行動に影響
```

明示的な `PredictionModel` コンポーネントは作らない。

予測モデル的な振る舞いは、過去の似た体験、予測誤差、再解釈、固定化された意味が想起され、次の `expected_result` / `attention` / `intention` に影響することで創発的に現れる。

つまり、予測は独立したモデルから出るのではなく、記憶が現在の認知を変えることで発生する。

## 2. 中核概念

### 2.1 Experience Trace

`ExperienceTrace` は、エピソードを作る前の一次材料である。

Trace は神視点ログではない。その agent が実際にアクセスできた材料として扱う。

#### ActionExperienceTrace

能動的な tool 実行から作る体験材料。

主な要素:

- 行動前の `inner_thought`
- `intention`
- `expected_result`
- `attention`
- `emotion_hint`
- tool 名・引数
- tool result
- success / error
- current state snapshot
- goals / beliefs / identity snapshot

#### ObservationExperienceTrace

受動的な観測から作る体験材料。

主な要素:

- 自分が知覚した出来事
- 他者の行動
- 発話
- 環境変化
- 自分への介入
- perceived salience
- location / visible context

### 2.2 Subjective Episode

`SubjectiveEpisode` は、複数の trace から生成される主観的なエピソード記憶である。

主な要素:

- `observed`: 実際に知覚したこと
- `interpreted`: 当時どう意味づけたか
- `felt`: 当時の感情
- `intended`: その後どうしようと思ったか
- `expected`: 行動前に予測していたこと
- `prediction_error`: 予測と結果のズレ
- `cue_keys`: 想起の手がかり（正規化済み文字列。LLM 由来・移行期レガシー）
- `cues`: 型付き想起手がかり（`EpisodicCue`: axis / value / source）。ルールベース生成の主たる置き場
- `source_trace_ids`: 元 trace への参照
- `importance`
- `salience_reasons`
- `memory_reflection_journal`

`observed` と `source_trace_ids` は不変とする。

後から変わるのは、現在から見た意味づけ、感情トーン、他の記憶との関係、semantic / identity への反映候補である。

### 2.3 Cue Index

**索引の受け皿**

- **`cues` (`EpisodicCue`)**: ルール・将来の validator が扱う**型付き**の主フィールド。`axis` と `value` から `to_canonical()` で `axis:value` 形式の 1 文字列に落とせる。
- **`cue_keys`**: 移行期および LLM JSON 出力との互換用の **`tuple[str, ...]`**。徐々に `cues` へ寄せ、重複は保存前または索引化時に整理する。
- **想起・重複判定での統合**: アプリケーション側では `subjective_episode_index_strings(ep)` のように、`cue_keys` と `cues` の canonical を**マージ（重複除去）**して使う。単一 Dict に「すべて」を詰めるより、構造化と互換の二本立ての方が安全である。

`cue_keys` を単独で LLM に自由生成させることは索引として危うい（下記）。最終的には **ルール生成を `cues` に載せ、LLM は補助（`source=llm`）に限定**する。

`cue_keys` は、LLM に自由生成させるタグではなく、検索・関連づけに使う正規化済みの索引キーとして扱う（上記の統合関数経由でも同じ意味）。

#### 空間系 cue の prefix 語彙の適用範囲

`tile_area:` / `sub_loc:` / `place:spot:` のような **名前空間付きの最終語彙**は、主に **二系統の空間 id（タイル側 `LocationAreaId` とグラフ側 `SubLocationId`）を混同しないための空間軸**を指す。`entity:` や `object:` など **別軸の prefix 規約とは独立**であり、「全 cue をこの語彙だけで名付ける」という意味ではない。

既存検証では、LLM 生成の `cue_keys` は以下の問題を起こしやすい。

- 表記が標準化されない。
- 1 単語や短いキーにならず、文章に近くなる。
- 同じ対象が別表記で保存される。
- 感情、場所、人物、物体、行動などの種類が混ざる。
- 後続の検索や関連リンク生成に使いにくい。

そのため、初期実装では `cue_keys` を LLM の主生成物にしない。

基本方針:

- ルールベース抽出を主とする。
- LLM は `cue_key_suggestions` のような補助提案に留める。
- 保存前に正規化・分類・上限数制限を行う。
- 自由文タグではなく、型付き cue として扱う。

#### Cue の種類

初期は以下の型で十分である。

- `entity`: 人物、NPC、モンスター、組織
- `place`: 場所、領域、部屋、地形
- `object`: アイテム、装置、環境オブジェクト
- `action`: 調べる、話す、開ける、戦う、待つなど
- `goal`: 現在目的、未解決問い
- `emotion`: 正規化済み emotion enum
- `outcome`: 失敗、成功、発見、危険、報酬など
- `schema_hint`: 罠、約束、裏切り、助け、鍵、認証などの抽象手がかり

内部表現は、単なる文字列配列ではなく、以下のような正規化済み構造を想定する。

```text
type: entity
key: alice
label: Alice
source: rule
confidence: high
```

ただし既存 DTO との互換や初期実装の軽さを優先する場合は、保存形式を文字列にしてもよい。

その場合も、文字列は以下の形式に正規化する。

```text
entity:alice
place:spot:12
area:area:3
location:location:5
object:old_box
action:open
emotion:regret
outcome:failure
schema_hint:trap
```

#### Cue 抽出の責務分担

ルール側:

- stable id がある人物、場所、物体を抽出する。
- tool 名から action cue を抽出する。
- `emotion_hint` から emotion cue を抽出する。
- success / error / high salience / prediction error から outcome cue を抽出する。
- current goals / unresolved questions から goal cue を抽出する。
- 表記ゆれを正規化する。

LLM 側:

- trace からルールでは拾いにくい抽象 cue を提案する。
- 例: `schema_hint:trap`, `schema_hint:promise`, `schema_hint:betrayal`
- ただし提案は validator を通し、長すぎるものや曖昧なものは捨てる。

Validator 側:

- 型 prefix がない cue を拒否または補正する。
- 空白を含む長文 cue を拒否する。
- 1 episode あたりの cue 数を制限する。
- 同義語辞書や stable id で canonical key に寄せる。

この設計により、cue は「自然言語の飾り」ではなく、関連記憶取得のための安定した index になる。

#### Prompt 生成元オブジェクトからの Cue 生成

cue は、完成した prompt 文字列から後処理で抽出するのではなく、prompt を作る元になった構造化オブジェクトから生成する。

理由:

- prompt 文字列は人間・LLM 向けに整形されており、安定した索引元ではない。
- 表示名や自然文は変わりやすい。
- stable id、場所 id、tool 名、structured event type は、prompt 文字列化の前に失われやすい。
- cue は検索用 index なので、表示用テキストではなく構造化データから作る方がよい。

主な入力元:

- `ActionExperienceTrace.tool_name`
- `ActionExperienceTrace.tool_args`
- `ActionExperienceTrace.emotion_hint`
- `ActionExperienceTrace.result_success`
- `ActionExperienceTrace.error_code`
- `ActionExperienceTrace.current_state_snapshot`
- `ActionExperienceTrace.current_goals_snapshot`
- `ObservationExperienceTrace.structured`
- `ObservationExperienceTrace.observation_kind`
- `ObservationExperienceTrace.perceived_salience`
- `ObservationExperienceTrace.world_event_refs`
- `ObservationExperienceTrace.visible_agents`
- `ToolRuntimeContextDto`
- `CurrentStateDto` 相当の現在地・周囲・可視対象情報

たとえば tool 実行からは以下の cue を作れる。

```text
tool_name = spot_graph_interact
tool_args = { "target_label": "古い箱", "world_object_id": 42 }
emotion_hint = caution
result_success = false
error_code = TRAP_TRIGGERED

=> action:spot_graph_interact
=> object:world_object:42
=> emotion:caution
=> outcome:failure
=> error:trap_triggered
=> schema_hint:trap
```

観測 trace からは以下の cue を作れる。

```text
structured = {
  "type": "spot_object_state_changed",
  "spot_id_value": 12,
  "world_object_id_value": 42,
  "actor": "Alice"
}
observation_kind = environment_change
perceived_salience = high

=> event_type:spot_object_state_changed
=> place:spot:12
=> object:world_object:42
=> entity:alice
=> observation_kind:environment_change
=> salience:high
```

LLM は、このルール抽出結果を補完するだけでよい。

### 2.4 Structured Location Context

エピソード記憶において、場所は最重要 cue の一つである。

人間の記憶でも「どこで起きたか」は想起の強い手がかりになる。ゲーム内でも、同じ場所、近い場所、同じエリア、以前危険だった地点に戻った時に、関連記憶が自然に想起される必要がある。

そのため、trace には自然文の `location_snapshot` だけでなく、構造化された location context を残す。

初期 schema 候補:

```text
current_spot_id: int | None
current_area_ids: tuple[int, ...]
current_location_id: int | None
current_x: int | None
current_y: int | None
current_z: int | None
place_labels: tuple[str, ...]
```

生成する cue:

```text
place:spot:12
area:area:3
location:location:5
coord:10:4:0
place_label:地下倉庫
```

#### 現状コードとの差分（仕様は目標・実装は移行中）

以下は査読（コード突合）に基づく **2026 時点の実情**である。仕様の schema は最終形の候補として残す。

- `ToolRuntimeContextDto` は **タイル経路**で `current_spot_id` / `current_area_ids` / `current_x|y|z` を保持する。**スポットグラフ経路**では `SpotGraphPlayerSnapshotDto.current_spot_id` を立て、`SpotGraphUiContextBuilder` が `ToolRuntimeContextDto.current_spot_id` に渡す（従来の `None` は是正）。
- `ActionExperienceTrace` / `ObservationExperienceTrace` に、上記の構造化フィールドを **そのままコピーして保存する処理は未着手**（文字列 snapshot のみの箇所が多い）。
- `SubjectiveEpisode` に **`cues: Tuple[EpisodicCue, ...]`** を追加済み。索引は `subjective_episode_index_strings` で `cue_keys` とマージ。**ルールベース抽出の本実装・validator 一括**は未着手。v2 Encoder は依然 **LLM 生成の `cue_keys`（および JSON の `cues` 枠）** に依存しうる。
- `episode_cues` / `memory_links` テーブル相当は **コード上未実装**（SQLite にはレガシー episodic 用の別 schema がある）。
- `DefaultPredictiveMemoryRetriever` は **レガシー `EpisodeMemoryEntry` 経路**。v2 `SubjectiveEpisode` の Passive Recall とは**別経路**である。

実装方針:


- `ToolRuntimeContextDto` や current state builder が持つ現在地情報を trace 作成時に渡す。
- `ObservationExperienceTrace` にも、観測時点の agent の現在地を構造化して保存する。
- `location_snapshot` は表示・LLM 入力用の自然文として残すが、検索 index の主材料にはしない。
- `place_labels` は補助情報とし、主要な照合は stable id で行う。

場所 cue は以下で使う。

- Passive Recall: 同じ spot / area に戻った時に記憶を想起する。
- Memory Context Pack: 現在地に関係する episode を `temporal_neighbors` / `associative_neighbors` に入れる。
- Consolidation: 「この場所は危険」「この場所では Alice と会いやすい」などの semantic / schema を作る。
- 忘却制御: 場所に強く結びついた記憶は、その場所に戻った時だけ再浮上しやすくする。

### 2.5 Associative Memory Graph

`Associative Memory Graph` は、記憶同士の関係を扱うための概念である。

ただし、初期実装から厳密なグラフ DB や一般グラフ探索エンジンを作る必要はない。最初は、episode や semantic memory に付随する「関連リンクの集合」として実装してよい。

また、新しい episode が追加されるたびに全 episode と比較してリンクを作る設計にはしない。

関連候補は、cue / scene / entity / place / recent sequence の逆引き index から限定して取得する。Graph は全件比較で作るものではなく、索引により候補を絞ったうえで少数のリンクを更新するものとする。

重要なのは、記憶を単体のイベントとして保存するだけでなく、他の記憶、人物、場所、目的、感情、未解決問い、意味記憶と結びつけることである。

#### ノードの候補

- subjective episode
- semantic memory
- identity fragment
- person
- place
- object
- goal
- emotion
- unresolved question
- schema
- commitment

#### リンクの候補

- `temporal`: 時系列的に近い
- `entity`: 同じ人物・物体に関係する
- `spatial`: 同じ場所に関係する
- `goal`: 同じ目的・問いに関係する
- `emotion`: 同じ感情に関係する
- `co_recalled`: 同時に想起された
- `supports`: 同じ理解を補強する
- `contradicts`: 既存理解と食い違う

`prediction_error` は、独立したリンク種別として初期から強く扱う必要はない。

予測誤差は salience や importance を高める重要な要素だが、「似た予測誤差だった」という理由だけで記憶同士を強く結ぶと、意味のない失敗記憶のまとまりができやすい。

予測誤差に基づく関連づけは、以下のように他の cue と組み合わせる場合に有効である。

- 同じ対象に対して予測が外れた
- 同じ場所で何度も予測が外れた
- 同じ行動カテゴリで失敗した
- 同じ人物への期待が裏切られた
- 同じ schema の例外になった

したがって、`prediction_error` はリンク種別というより、リンク強度や salience を補正する特徴量として扱うのがよい。

#### 形成タイミング

Associative Memory Graph は一度に完成するものではない。

以下のタイミングで少しずつ形成・更新される。

1. `SubjectiveEpisode` 生成時
   - 正規化済み cue を cue index に登録する。
   - cue index から同じ cue を持つ近傍 episode だけを取得し、弱い関連リンク候補にする。
   - scene / chunk index から同じ scene / chunk の episode だけを取得し、`temporal` または `scene_neighbor` リンク候補にする。
   - recent sequence index から直前・直後の episode を取得し、時系列リンクを作る。

2. Passive Recall 時
   - 一緒に想起された episode 間に `co_recalled` リンクを弱く作る。
   - その想起が行動判断に使われた場合、リンクを少し強める。

3. Memory Reflection 時
   - 現在文脈で再解釈した結果、supports / contradicts / related_to の候補を作る。
   - ただし source trace や initial episode は書き換えない。

4. Consolidation 時
   - 複数 episode / reflection / semantic memory を見て、安定した関係だけを強める。
   - 一時的な共起や偶然の関連は弱める、または放置する。

5. 時間経過
   - 使われないリンクは減衰する。
   - 高 salience、未解決問い、強い感情、重要な関係に紐づくリンクは残りやすい。

#### 初期実装の index

全件比較を避けるため、初期実装では以下の index を持つ。

- `cue_index`: `cue_key -> episode_id[]`
- `scene_index`: `scene_id/chunk_id -> episode_id[]`
- `entity_index`: `entity_key -> episode_id[]`
- `place_index`: `place_key -> episode_id[]`
- `recent_episode_index`: `agent_id -> recent episode_id[]`
- `semantic_subject_index`: `subject_key -> semantic_memory_id[]`

新しい episode が追加されたら、以下の順で処理する。

1. episode から正規化済み cue を抽出する。
2. 各 index から候補 episode を取得する。
3. 候補を `max_candidates` 件まで絞る。
4. cue overlap、recency、importance、同一 scene、同一 entity などで軽量スコアリングする。
5. 上位 `max_links_per_episode` 件だけリンクとして保存する。
6. episode 自身を各 index に登録する。

このため、計算量は全 episode 数に比例させない。

Graph 更新は以下のような局所処理でよい。

```text
new_episode
  -> normalized cues
  -> index lookup
  -> small candidate set
  -> lightweight scoring
  -> store top links
```

厳密な graph traversal やクラスタリングは、必要になるまで導入しない。

#### RDB / Index としての実装イメージ

初期実装では、Associative Memory Graph は RDB 的に考えるのがよい。

物理的な graph database ではなく、episode 本体、cue index、link table の組み合わせとして扱う。

```text
subjective_episodes
  - episode_id
  - agent_id
  - observed
  - interpreted
  - importance
  - created_at
  - candidate_id

episode_cues
  - agent_id
  - episode_id
  - cue_type
  - cue_key
  - confidence

memory_links
  - agent_id
  - source_id
  - target_id
  - link_type
  - strength
  - evidence_count
  - last_reinforced_at
  - created_reason
```

新しい episode が以下の cue を持つとする。

```text
entity:alice
place:spot:12
object:world_object:42
action:open
emotion:regret
outcome:failure
schema_hint:trap
```

このとき、既存 episode 全体とは比較しない。

まず `episode_cues` を使い、同じ cue を持つ episode だけを取得する。

```sql
SELECT episode_id
FROM episode_cues
WHERE agent_id = :agent_id
  AND cue_key IN (
    'entity:alice',
    'place:spot:12',
    'object:world_object:42',
    'action:open',
    'schema_hint:trap'
  )
ORDER BY episode_id DESC
LIMIT 100;
```

次に、その候補だけを軽量スコアリングする。

```text
同じ entity がある: +30
同じ place がある: +30
同じ object がある: +25
同じ action がある: +10
同じ schema_hint がある: +20
同じ scene/chunk: +40
最近の episode: +0〜15
high importance: +20
```

最後に、上位だけを `memory_links` に保存する。

```text
new_episode -> old_episode_A: entity + place, strength 0.62
new_episode -> old_episode_B: object + schema_hint, strength 0.51
new_episode -> old_episode_C: same scene, strength 0.75
```

これが「Graph を形成する」の実体である。

Graph は全体を毎回再構築するものではなく、新しい episode の周辺にだけ局所的にリンクを張る。

scene / chunk についても同様に、全 episode に「同じ scene か」を聞かない。

episode に `candidate_id`, `scene_id`, `chunk_id` などを持たせ、index で取得する。

```sql
SELECT episode_id
FROM subjective_episodes
WHERE agent_id = :agent_id
  AND scene_id = :scene_id
ORDER BY created_at DESC
LIMIT 20;
```

このため、Associative Memory Graph は「様々な観点で query できる記憶 DB」に近い。

グラフという名前は、記憶同士の関連が link として残り、想起時にその link が利用されることを表している。

### 2.6 Episode Cluster

`EpisodeCluster` は、Associative Memory Graph 上で自然にまとまった episode 群である。

Cluster は初期段階では明示的な永続オブジェクトでなくてよい。

たとえば以下のようなまとまりを、検索・想起・固定化の過程で一時的に見つけられればよい。

- Alice を信頼するようになった一連の記憶
- 地下施設で罠に警戒するようになった経験群
- 同じ失敗を繰り返して慎重になった記憶群
- ある場所に対する嫌な印象を形成した記憶群

Cluster は「記憶のまとまり」であり、現在の処理に渡す入力そのものではない。

将来的に必要になった場合のみ、cluster summary や cluster id を保存する。

### 2.7 Memory Context Pack

`Memory Context Pack` は、想起、再解釈、固定化、能動検索のたびに、その場で組み立てる作業用パッケージである。

Cluster が記憶のまとまりであるのに対して、Context Pack は処理の入力である。

含めるもの:

- `current_situation`: 現在地、周囲、直近 N ターン、現在行動可能なもの
- `current_goals`: 現在の目的
- `current_attention`: 注意対象
- `current_emotional_state`: 将来的に HP など身体状態導入後に拡張
- `focus_episode`: 想起対象の中心 episode
- `temporal_neighbors`: 直前・直後・同じ場面の episode
- `associative_neighbors`: cue 的に近い episode
- `semantic_context`: 関連する意味記憶
- `identity_context`: 自己物語、約束、恐れ、信頼、未解決問い
- `contradictions`: 食い違う記憶や信念
- `co_recalled_memories`: 最近一緒に想起された記憶

Context Pack は保存物ではない。

同じ focus episode でも、現在地、目的、感情、直近の出来事が変われば、異なる Context Pack が作られる。

### 2.8 学習と予測への使われ方

このシステムでは、明示的な `PredictionModel` を作らない。

学習や予測は、以下のような記憶処理の結果として現れる。

```text
現在状況
  -> cue 生成
  -> 関連 episode / semantic / identity を検索
  -> Memory Context Pack を構築
  -> prompt に短い想起・再解釈・注意への影響を入れる
  -> LLM が次の tool call の intention / expected_result / attention を書く
  -> 行動結果との prediction_error が次の episode になる
```

たとえば、キャラクターが以前 `place:spot:12` で `object:world_object:42` を急いで開け、罠で失敗していたとする。

その後、似た場所や似た箱に出会うと、cue index から以下が取得される。

```text
place:spot:12
object:world_object:42
action:open
outcome:failure
schema_hint:trap
```

Memory Context Pack には、過去の失敗 episode、同じ場所の近傍 episode、罠に関係する semantic / schema、当時の後悔や警戒が入る。

Prompt には、攻略ルールではなく、次のような短い影響として渡す。

```text
以前、似た箱を急いで開けた時に罠で失敗した記憶がある。
今は箱そのものだけでなく、床や周囲の仕掛けにも注意が向きそうだ。
```

すると LLM は次の行動前主観で、たとえば以下のように書きやすくなる。

```text
intention: 箱を開ける前に、周囲に罠や仕掛けがないか確かめる。
expected_result: 箱に触れる前に、危険な仕掛けや不自然な床の沈み込みが分かるかもしれない。
attention: 箱の鍵穴、床、壁際の細い隙間。
```

この振る舞いが、予測モデルが更新されたように見える効果である。

実際には「罠予測モデル」を直接更新したわけではない。

過去の episode と cue link が現在状況で想起され、その想起が `attention` と `expected_result` を変えたのである。

#### 学習の単位

学習は以下のレイヤで起きる。

1. Episode level
   - 予測と結果のズレが強い episode は importance が上がる。
   - 似た cue で再想起されやすくなる。

2. Link level
   - 一緒に想起された episode の `co_recalled` が少し強まる。
   - 同じ場所、同じ対象、同じ失敗が繰り返されるとリンクが安定する。

3. Semantic / Schema level
   - 複数 episode から「この場所では罠に注意する」「Alice は助けてくれることが多い」などの意味が生まれる。
   - これは行動を強制するルールではなく、注意と予測を傾ける記憶である。

4. Identity level
   - 繰り返しの失敗や成功から「自分は危険な場所では慎重になる」「Alice には恩がある」などの自己物語が育つ。

#### 予測への影響

予測への影響は、直接的な数値モデルではなく prompt context として現れる。

Memory Context Pack から prompt に出すべきなのは、過去 episode の全文ではなく、以下である。

- なぜ今その記憶が想起されたか。
- 当時、何を予測してどう外れたか。
- 今の状況では、どこに注意が向きそうか。
- 今の `expected_result` が慎重になるべき理由は何か。
- ただし、世界の真実として断定しない。

例:

```text
以前、鍵だけで扉が開くと予測したが、実際には認証端末も必要だった。
今回も扉を開けようとするなら、鍵穴だけでなく周辺装置に注意が向きそうだ。
```

これにより、キャラクターは同じ失敗を避けやすくなる。

ただし、予測は固定ルールではないため、別状況では外れることもある。

その外れがまた新しい episode となり、記憶システム全体を更新する。

## 3. 処理フロー

### 3.1 Trace Capture

行動または観測が起きたら trace を保存する。

目的:

- episode 化前の根拠を残す
- 後から `observed` の正当性を検証できるようにする
- 主観生成と材料を分離する

### 3.2 Episode Encoding

複数 trace を意味的なまとまりにして `SubjectiveEpisode` を生成する。

Chunk boundary の候補:

- 場所が変わった
- 目的が変わった
- 感情が大きく変わった
- 予測誤差が大きい
- 失敗・危険・報酬・発見があった
- 他者との関係が動いた
- scene / day / chapter が切れた

Encoding は LLM を使ってよい。

ただし、`observed` に source trace にない事実を混ぜてはいけない。

### 3.3 Associative Link Update

`SubjectiveEpisode` が作られたら、関連リンクを更新する。

初期実装では以下でよい。

- 正規化済み cue を index に登録する。
- cue index から同じ cue を持つ episode を少数取得する。
- scene / chunk index から同じ scene / chunk の episode を取得する。
- recent episode index から直近時系列の episode を取得する。
- entity / place index から同じ人物・場所・物体を含む episode を取得する。
- semantic subject index から類似した semantic memory を取得し、必要なら弱く接続する。

新規 episode 追加時に、全 episode を走査して関連判定してはいけない。

関連候補は index lookup で取得し、候補数に上限を設ける。

リンクは以下の情報を持つ。

- `source_id`
- `target_id`
- `link_type`
- `strength`
- `evidence_count`
- `last_reinforced_at`
- `created_reason`

初期は in-memory または episode store 内の補助 index でよい。

厳密な graph traversal が必要になるまでは、`list_related(episode_id, link_type, limit)` 程度の API で十分である。

推奨パラメータ:

- `max_candidates`: 30-100 件程度
- `max_links_per_episode`: 5-12 件程度
- `max_recent_episodes`: 20-50 件程度

これにより、記憶数が増えても、追加時の処理は全件比較ではなく局所的な関連更新に留まる。

### 3.4 Passive Recall

毎ターン、現在状況から自然に想起されそうな記憶を選ぶ。

検索要素:

- cue overlap
- recency
- importance
- current goal relevance
- unresolved question relevance
- graph link strength
- semantic / identity relevance

出力は episode 全文ではなく、短い想起ブロックである。

重要:

- 単一 episode だけでなく、Memory Context Pack を組み立てる
- 一緒に想起された episode 間に `co_recalled` を記録する
- prompt に入れる件数は制限する
- 高重要な想起だけ reflection 対象にする

### 3.5 Memory Reflection

想起された episode を、現在文脈から再解釈する。

入力:

- focus episode
- Memory Context Pack
- current goals
- current situation
- current identity
- related semantic memories
- contradictions

出力:

- `recall_trigger`
- `current_interpretation`
- `effect_on_attention`
- `effect_on_prediction`
- `effect_on_decision`
- `episode_patch`
- `semantic_update_candidates`
- `identity_update_candidates`
- `link_update_candidates`

`effect_on_prediction` は、明示的な予測モデル更新ではない。

次の行動前予測に影響するための自然文ヒントとして扱う。

### 3.6 Consolidation

複数 episode / reflection / co_recall / contradiction から、より安定した意味を作る。

タイミング:

- 日次
- 章・場面の区切り
- 高 importance episode 発生後
- 同じ episode が複数回想起された時
- 未解決問いが解決した時
- 矛盾が発生した時

出力:

- semantic memory
- schema memory
- identity memory
- relationship memory
- open question 更新
- confidence 更新
- link strength 更新

Consolidation は「世界の真実」を断定する処理ではない。

その agent にとって安定しつつある意味を作る処理である。

## 4. Semantic / Schema / Identity

### 4.1 Semantic Memory

世界、場所、物、他者、行動傾向についての理解。

例:

- この施設の扉は、鍵以外の認証を要求することがある。
- Alice は困った時に助けてくれることが多いかもしれない。

`confidence` と evidence episode を持つ。

### 4.2 Schema Memory

複数体験から形成された「状況の型」。

例:

- 暗い場所で急いで物に触れると、見落としや罠が起きやすい。
- 相手が警戒している時は、直接聞くより周囲の状況を確認した方がよい。

Schema は行動ルールではない。

注意と予測を傾ける記憶である。

### 4.3 Identity Memory

自分が何を経験し、何を恐れ、何を守ろうとしているか。

例:

- 急いで失敗した経験から、危険な場所では慎重になりやすい。
- Alice への不信は、後の出来事によって少し弱まっている。
- 地下施設の奥に何があるのかをまだ知りたい。

## 5. 忘却と干渉

忘却は削除ではなく、想起されにくさとして表現する。

- recall weight が下がる
- cluster summary に吸収される
- semantic memory 経由でのみ影響する
- cue link が減衰する
- detail は出ず印象だけ残る

干渉は、似た記憶が複数存在し、prompt に入る記憶が制限されることで自然に発生する。

ただし、元 episode は壊さない。

混ざるのは recall / reflection / consolidation の段階だけである。

## 6. 期待するゲーム内現象

- 過去に罠で失敗したキャラが、似た箱を見た時に床や壁を先に調べる。
- 一度助けられただけでは信頼しないが、複数の episode が重なって Alice への信頼が育つ。
- 後から事情を知ることで、昔の「裏切られた」という記憶が再解釈される。
- 未解決の問いが残っている場所に戻ると、以前の疑問を思い出す。
- 強い失敗体験があると、似た状況で `expected_result` が慎重になる。
- 古い細部は忘れるが、「あそこは嫌な感じがする」という印象は残る。
- キャラごとに同じ出来事から違う schema / identity が育つ。

## 7. 初期実装での優先順位

初期実装では、すべてを厳密なグラフとして作らない。

優先する順序:

1. Memory Context Pack を導入し、Reflection / Passive Recall の入力を豊かにする。
2. episode 間の簡易 link store を作る。
3. `co_recalled` と `temporal` と `entity/spatial/goal` 程度のリンクから始める。
4. Consolidation で semantic / schema / identity への更新候補を採用できるようにする。
5. リンク強度の減衰と強化を入れる。
6. 必要になったら EpisodeCluster の summary を永続化する。

最初から完全な graph DB を作るより、記憶が現在の判断に影響する最短経路を優先する。

---

## 8. 想起軸（Recall Axis）と索引キー

**想起軸**は「なぜその記憶を引くか」という観点である。**索引キー**は、その軸で index を引くときの正規化値（例: `place:spot:12`, `object_category:container`）。同じ episode に複数種類のキーが載ることは普通である。

### 8.1 軸の候補

| 想起軸 | ざっくりした理由で思い出す | 主な索引の例 |
|--------|---------------------------|--------------|
| 個体一致 | あの時のあの対象 | `object:world_object:42`, `entity:...` |
| 型・カテゴリ | 別 instance だが同種（別の箱でも箱として） | `object_category:...`, `object_affordance:...`, ドメインの `SpotObject` 型 |
| 空間 | 同じ・近い場所にいる | `place:spot:*`, タイルの `tile_location_area_id`（`LocationAreaId`）, グラフの `sub_location_id`（後述） |
| 時間的近傍 | 続きの場面・直前直後 | `created_at`, tick, temporal link, recent リスト（cue というより専用 index） |
| 出来 event の骨格 | 罠・戦闘・会話など | `action:*`, `event_type:*`, `outcome:*`, `schema_hint:*` |
| 目的・作業意図 | いま調べていることと関連 | 現状は WM 文字列／将来 `goal:*` 正規化 key |
| 関係・タスク束ね | クエスト・会話文脈 | `scope_keys` 系（`quest:...` 等） |

軸ごとに **候補集合を取り、和集合にマージし、必要なら二次スコア**する方針とする。能動的な検索（`memory_query` 等）は Passive より優先度を低めてよい。

### 8.2 解像度とスコア

同一軸内では **instance 完全一致を最優先**とし、抽象化された階層（型・カテゴリ）に降りるほどスコアを下げるイメージでよい。物体と人物で key の namespace が違うことは問題ではなく、**prefix（entity / object / …）で並列**に扱う。

### 8.3 cue を増やすことと embedding の違い

cue を「意味的類似」の特徴量として無制限に増やすと手作り embedding に寄る。増やす場合は **ゲーム由来・検証可能な次元**に限定し、cue の役割は **類似度ベクトルではなく、出来事の構造を保つ索引**に置く（時空間の「すべて」は cue 列だけでは保持できない：本文・trace・temporal link・Context Pack が担う）。

---

## 9. 空間：階層と命名（コードベース準拠）

一般的な「location が一番細かい」イメージとは **必ずしも一致しない**。本リポジトリでは次の二系統がある。

1. **タイル／物理マップ**: `SpotId` 配下の **`LocationAreaId`**（`ToolRuntimeContextDto.current_area_ids` 等）。座標 `current_x/y/z` もある。
2. **スポットグラフ**: ノード＝ `SpotNode`。スポット**内部**の区画は **`SubLocation`**（`PlayerSpotNavigationState.current_sub_location_id`）。

**粒度の目安（細かい方から粗い方へ）**

1. 座標（タイルモード）
2. 区画 id：`LocationAreaId`（タイル）または **`SubLocationId`（グラフ）**
3. `spot_id`（意味的な場所ノード）
4. （あれば）`Spot.parent_id` に相当する粗い地域

**`ToolRuntimeTargetDto` の空間フィールド（是正済み）**

- **`tile_location_area_id`**: タイル／物理マップの `LocationAreaId`。
- **`sub_location_id`**: スポットグラフの `SubLocationId`（いわゆる spot 内部区画）。旧 `location_area_id` への誤格納は廃止した。
- `SpotGraphPlayerSnapshotDto.current_spot_id` から `ToolRuntimeContextDto.current_spot_id` へ渡す経路は追加済み（2026）。**ExperienceTrace へのコピー**は未着手。

空間 cue の prefix 例として **`tile_area:...` / `sub_loc:...` / `place:spot:...`** のように役割を字面で区別できるとよい（§2.3 のとおり、これは主に空間軸の名前空間である）。

---

## 10. 目的（goal）軸：意味とデータソース

仕様上の「goal」は **クエスト進行フラグの同期テーブルだけを指すものではない**。

| レイヤ | 意味 | 実装での主な出所（現状） |
|--------|------|---------------------------|
| 作業ゴール | いま確かめたい・調べたいこと | `IWorkingMemoryStore` の短文。`EpisodeEncodingContextDto.current_goals` に直近行を連結した文字列として載る |
| エピソード時点のゴール | 当時のプロンプト文脈のスナップショット | `ActionExperienceTrace.current_goals_snapshot` |
| 関係・タスク | クエスト・会話など | `EpisodeMemoryEntry.scope_keys` 等（既存 extractor 経路） |
| 信念・自己物語 | 「自分はこうしたい」 | 長期 facts / identity。goal 軸の隣接入力として Context Pack に載せうる |

**Passive Recall** では現状、`current_goals_hint` をトークン化し `observed`/`interpreted` との部分一致で加点している。将来は **`goal:stable_id`** 等の正規化 cue へ移行し、表記ゆれに強くする。

**未解決問い**は専用ストアが薄い。WM・長期・`scope_keys`・将来の `open_question` id から供給する想定とする。

---

## 11. 出来事の骨格（イベントフレーム）

「誰が・どこで・何に・どう作用し・何が起き・自分にどう影響したか」を検索・リンクで保つための cue 群を **骨格**と呼ぶ。例:

- `action:`（tool 名または正規化カテゴリ）
- `event_type:`（観測 `structured.type` 等）
- `outcome:` / `error:`
- `schema_hint:`（罠・約束など抽象型）
- **視点**（将来）: `perspective:self_action` 等

シナリオ検証では、代表フロー（罠箱・会話・戦闘・移動失敗）ごとに「最低限必要な骨格 cue」を列挙してよい。

---

## 12. 関連ドキュメント

- **実装フェーズ・タスク分解**: [episodic_memory_implementation_plan.md](./episodic_memory_implementation_plan.md)
- 歴史的・詳細な再設計メモ（Tool schema 等）: [episodic_memory_reimplementation_plan.md](./episodic_memory_reimplementation_plan.md)
