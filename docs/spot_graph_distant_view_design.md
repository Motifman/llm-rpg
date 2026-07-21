# spot グラフの遠景知覚設計

## 目的

`survival_island_v4_coop` から spot は `position{x,y}` を持てるようになった。これにより、エージェントは現在地の直接接続だけでなく、「遠くに山が見える」「東に湿地が広がる」といった地形からの方向づけを受け取れる。

この文書は、完全な視線遮蔽計算を入れずに、質感としての遠景知覚を実装するための設計を定める。実装はこの文書の承認後に段階的に行う。

## 設計方針

- 遠景の対象は個々の spot ではなく area とする。
- area は新しい集約にしない。scenario の top-level `areas` と `spot.area_id` による軽い定義表として扱う。
- 常時見える遠景は現在状態の一部として prompt に織り込み、episode には流さない。
- 動的な煙・光・火災などの兆候は、汎用の `distant_cues` 宣言で表現する。
- prompt には `visible_name` / `name` だけを出し、`area_id` や内部 ID は出さない。
- 視認性は「見られる側の目立ち度」と「見る側の見晴らし」の 2 ダイヤルで表現し、レイキャストはしない。

## 既存アーキテクチャとの接続

この設計は、既存の「現在状態」と「観測イベント」の区別に乗せる。

- 現在状態: `prompt_builder` が毎回組み直す現在地・周囲・同席者・状態など。常時の遠景はここに入る。episode には入らない。
- 観測イベント: ドメインイベントから観測が作られ、必要に応じて episode 記憶へ流れる。動的兆候の出現はここに入る。

場所専用の `seen_landmarks` のような記憶ストアは作らない。場所だけを特別扱いすると、記憶機構がシナリオ構造に密結合するためである。

## area の役割

area は次の 3 つを兼ねる。

1. 大まかな位置の同一性
2. 遠景の知覚単位
3. 汎用シナリオ次元

例えば「山頂」「山道」「高地の泉」は別 spot だが、遠景では「北東の山岳エリアの高み」として見せる方が自然である。spot をそのまま遠望対象にすると、候補が増えすぎ、prompt が「北東に山頂、山道、泉、崖、森が見える」のように汚れる。

### 集約にしない理由

area は初期設計では状態を持たない。実行中に HP や inventory のような mutable state を持たないため、world_graph の新集約にする必要はない。

初期実装では value object 的な `AreaDef` として扱う。将来、area 自体が支配状況・火災範囲・汚染度・勢力圏などの状態を持つ場合に、集約化を再検討する。

## 最小スキーマ案

top-level に `areas` を置き、各 spot に `area_id` を任意で持たせる。

```json
{
  "areas": [
    {
      "id": "mountain",
      "name": "山岳エリア",
      "visible_name": "切り立った山影",
      "prominence": 0.95,
      "position": {"x": 7.0, "y": 8.0},
      "description": "島の北東にそびえる高地。",
      "distant_descriptions": {
        "far": "北東の遠くに切り立った山影が見える。",
        "middle": "北東に山岳エリアの高みが見える。"
      }
    }
  ],
  "spots": [
    {
      "id": "summit",
      "name": "山頂",
      "area_id": "mountain",
      "position": {"x": 7.2, "y": 8.4}
    }
  ]
}
```

必須:

- `areas[].id`
- `areas[].name`
- `areas[].visible_name`
- `areas[].prominence`
- `spots[].area_id`

任意:

- `areas[].position`
- `areas[].description`
- `areas[].distant_descriptions`
- `spots[].visibility_range`
- `areas[].visibility_range`

`area_id` は prompt に出さない。trace / structured payload / validator のみで使う。

## area 位置の決定

area の位置は次の順で決める。

1. `area.position` が宣言されていれば、それを使う。
2. 宣言が無ければ、所属 spot の `position` の重心を自動計算する。
3. 所属 spot が無い、または所属 spot の `position` が足りず重心が作れない場合は validator で検出する。

`area.position` override は、重心では地理的な見え方と合わない場合に使う。例えば山岳エリアが広く、遠景としては山頂側を代表点にしたい場合がある。

## 遠景の膨張を防ぐ 4 段の絞り込み

遠景は prompt を汚しやすい。実装では候補生成後に必ず 4 段で絞る。

### 1. 目立ち度の閾値

`area.prominence` が低い area は遠景候補にしない。

森・沼・浜・小屋など大半の area は `prominence` を 0 付近に置く。作者が「遠くから見えるべきもの」だけを入口で指定する。

### 2. 距離減衰

現在地から area 代表点までの距離で減衰させる。

概念式:

```text
score = area.prominence * distance_decay(distance) * visibility_modifier
```

`score` が閾値未満なら表示しない。

現在地の area と隣接 area は遠景から除外する。そこは現在地説明や出口説明の領分であり、「遠くに見えるもの」として出すと局所情報と混ざるためである。

### 3. 方角ごとに 1 つへ集約

同じ方角に複数候補がある場合、基本は最も `score` が高い 1 件だけを出す。

必要なら、複数候補を 1 文にまとめる。

```text
北東に山と森が重なって見える。
```

次のような列挙は構造的に起きないようにする。

```text
北東に山岳エリア、北東に高地の泉、北東に山道、北東に崖が見える。
```

### 4. 件数上限

最終表示は 2〜3 件で打ち切る。既定は 2 件、見晴らしが良い場所だけ 3 件を許す程度にする。

## 視認性モデル

視線遮蔽は入れない。代わりに 2 つの値で見え方を作る。

### 見られる側: `area.prominence`

遠くから目立つ度合い。

例:

- 山岳エリア: 高い
- 灯台や煙を出す地点: 高い
- 森の奥: 低い
- 沼地: 低い
- 浜辺: 低い

### 見る側: `visibility_range`

現在地からどれだけ遠くまで見えるか。

宣言先は `spot.visibility_range` を優先し、無ければ `area.visibility_range` を使う。両方無ければ category から既定値を与える。

例:

- 屋内・洞窟: 0
- 森の奥: 短い
- 浜: 長い
- 崖・山頂・見張り台: とても長い

見える条件:

```text
現在地が屋外
かつ
area.prominence * distance_decay(distance, visibility_range) が閾値以上
```

## prompt への出し方

常時の遠景は独立ブロックにしない。現在地説明の直後、出口一覧より前に 1〜2 文で織り込む。

例:

```text
あなたは浜辺の拠点にいる。風が強く、波の音が近い。
北東の遠くに切り立った山影が見える。
```

制約:

- 方角と `visible_name` だけを書く。
- 「東へ行ける」「山へ向かうには東に進め」とは書かない。
- `area_id` や spot ID は出さない。
- 出口一覧とは混ぜない。
- 常時の遠景は episode に流さない。

遠景は方向づけであり、経路案内ではない。実際にどの接続を使えるかは出口説明と行動結果で学ばせる。

## 記憶への流し方

### 常時の遠景

常時の遠景は現在状態なので、episode には流さない。毎ターン再生成される。

これにより、「山が見えている」という環境情報が episode を埋め尽くすことを防ぐ。

### 静的 area の初回発見

初期実装では、静的 area の「初回発見イベント」は作らない。

理由:

- player ごとの既見判定が必要になる。
- 場所専用ストアを作ると、記憶基盤が場所概念に密結合する。
- 常時遠景だけでも方向づけの質感は得られる。

将来どうしても player ごとの初回発見が必要になった場合は、場所専用ストアではなく、汎用の観測重複排除キーを導入する。

```text
dedup_key = player_id + semantic_key
```

この汎用 dedup state は snapshot 対象にする。snapshot から漏れると、再開後に初回発見が再発するためである。

### 動的兆候の出現

動的兆候の false→true は「世界状態の変化イベント」として扱う。

例:

- 狼煙が上がる。
- 灯台に明かりが灯る。
- 森で火災の煙が上がる。
- 火山の噴煙が増える。

これは「初めてその場所を見た」ではなく「世界が変化した」なので、場所専用ストアなしで既存の observation → episode 経路に乗せられる。

## 汎用 `distant_cues`

`distant_cues` は、オブジェクト状態やフラグ条件から、遠くから見える兆候を宣言する仕組みである。

engine に `signal_fire` を埋め込まない。狼煙は `distant_cues` の一例に過ぎない。

### スキーマ案

```json
{
  "distant_cues": [
    {
      "id": "summit_signal_smoke",
      "source": {
        "kind": "object_state",
        "object_id": "signal_fire_pit",
        "state_key": "lit",
        "equals": true
      },
      "origin": {
        "area_id": "mountain"
      },
      "visible_name": "細い煙",
      "prominence": 0.9,
      "appear_event_message": "山の方から細い煙が立ち上った。",
      "ambient_descriptions": {
        "far": "北東の山の方に細い煙が見える。",
        "middle": "山の高みから細い煙が上がっている。"
      }
    }
  ]
}
```

`source.kind` の初期候補:

- `object_state`
- `world_flag`
- `scenario_flag`

`origin` は `area_id` を基本とする。必要なら将来 `spot_id` や object の現在位置から解決するが、prompt にはそれらの ID を出さない。

### 常時表示と出現イベント

`distant_cues` には 2 つの出口がある。

1. 条件が true の間、ambient 遠景に混ぜる。
2. 条件が false→true に変わったとき、通常のドメインイベントとして観測を出す。

出現イベントは既存の記憶経路へ流れる。常時表示は流れない。

## 静かな失敗ガード

### validator 検査

| 対象 | 検査 | 重大度案 | 目的 |
|---|---|---:|---|
| area 定義 | `areas[].id` の重複 | error | 参照先の曖昧化を防ぐ |
| area 定義 | `visible_name` 空 | error | prompt に空文が出るのを防ぐ |
| area 定義 | `prominence` が数値でない / 範囲外 | error | 遠景候補の計算不能を防ぐ |
| spot | `spot.area_id` が存在しない area を参照 | error | area の重心計算と表示不能を防ぐ |
| spot | `area_id` 未設定 spot がある | warning | 段階0では許容しつつ、v4 適用時に発見可能にする |
| area 位置 | `area.position` が無く、所属 spot から重心を作れない | error | 遠景方向の計算不能を防ぐ |
| visibility | 屋外 spot なのに `visibility_range` が解決不能 | warning | 常時遠景が出ない理由を見える化する |
| prompt | `area_id` が本文に混入 | error 相当のテスト | 過去のラベル漏れ再発を防ぐ |
| `distant_cues` | `source` が存在しない object / flag を参照 | error | 兆候が一度も発火しない事故を防ぐ |
| `distant_cues` | `origin.area_id` が存在しない | error | 方角計算不能を防ぐ |
| `distant_cues` | 条件 true なのに可視対象者が 0 の場合 | trace warning | 仕様通りか設定ミスかを後から判断できるようにする |

### trace 観測点

trace は実験後に「見えていたはずの遠景が本当に prompt に入ったか」「兆候が誰にも届かず消えていないか」を確認するために使う。

候補:

- `DISTANT_VIEW_RENDERED`
  - `player_id`
  - `spot_id`
  - `area_id` 一覧
  - `cue_id` 一覧
  - `candidate_count`
  - `rendered_count`
  - `suppressed_reasons`
- `DISTANT_VIEW_SKIPPED`
  - `player_id`
  - `spot_id`
  - `reason`
  - 例: `indoor`, `no_area_positions`, `visibility_range_zero`, `all_below_threshold`
- `DISTANT_CUE_STATE_CHANGED`
  - `cue_id`
  - `old_active`
  - `new_active`
  - `origin_area_id`
  - `source_kind`
- `DISTANT_CUE_DELIVERED`
  - `cue_id`
  - `player_id`
  - `spot_id`
  - `direction`
  - `distance_band`

prompt 本文には ID を出さないが、trace には ID を残す。分析とデバッグのためである。

## 表示文の作り方

遠景文は、area / cue ごとに作者が宣言した文を優先する。

優先順:

1. `distant_descriptions[distance_band]`
2. `visible_name` から生成した定型文

距離帯の例:

- `near`: 隣接ではないが近い
- `middle`: 中距離
- `far`: 遠距離

方角は `position` から計算し、日本語の 8 方位に丸める。

```text
北東の遠くに切り立った山影が見える。
西の中ほどに白い灯りがまたたいている。
```

## 段階案

| 段階 | 何ができるようになるか | 内容 |
|---:|---|---|
| 0 | シナリオに大まかな地理単位を持てる | top-level `areas` と `spot.area_id` を追加し、重心計算・validator・viewer の area 色分けを入れる。v4 に area を付ける。実行系は変えない。 |
| 1 | エージェントが遠くの地形から方向の見当をつけられる | 常時の遠景を現在地説明に織り込む。episode には流さない。 |
| 2 | 煙・光・噴煙などをシナリオ宣言だけで遠景に出せる | 汎用 `distant_cues` を追加し、条件が true の間は ambient 表示する。 |
| 3 | 世界の変化としての兆候が記憶に残る | `distant_cues` の false→true をドメインイベントにし、既存 observation → episode 経路へ流す。 |
| 4 | 必要なら初回発見も扱える | 場所専用ストアではなく、汎用 dedup_key による初回観測を追加する。snapshot 対象にする。 |
| 5 | 高台・浜・森・洞窟で見える範囲が変わる | `visibility_range` を本格化し、`map_revealed` 的な二値の見晴らしを連続的な見晴らしへ一般化する。 |

## 実装時の注意

- 段階0は実行系を変えない。validator と viewer だけで area のデータ品質を固める。
- 段階1では prompt 露出テストを必ず作り、`area_id` が本文に漏れないことを固定する。
- 段階2では `distant_cues` が有効なのに候補 0 になった理由を trace で残す。
- 段階3では状態変化イベントの重複発火を避ける。false→true の境界だけがイベントで、true の間の常時表示は ambient に留める。
- 段階4を入れる場合、dedup state は snapshot 対象にする。途中再開で初回発見が再発すると実験が汚れる。
- 段階5では `visibility_range` を強くしすぎない。見えすぎると全容地図を与えるのと同じになり、探索と空間学習の意味が薄くなる。

## 未決事項

- `prominence` と `visibility_range` の数値範囲を 0〜1 にするか、距離単位に近い値にするか。
- 既定の表示上限を 2 件にするか 3 件にするか。
- `distance_decay` の式を線形にするか、しきい値つきの段階関数にするか。
- `distant_cues` の `source.kind` 初期実装を `object_state` だけに絞るか、flag も同時に入れるか。
- trace event 名を既存命名規約に合わせて最終決定する。
