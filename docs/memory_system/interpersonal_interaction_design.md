# 対人インタラクション基盤 — 効果の対象を行為者から解放する

> 検証の的: シナリオ JSON だけで Among Us が近似できること。
> ただし Among Us 固有の概念 (インポスター・緊急ボタン・タスクバー) は
> コードに入れない。表現力の到達度を測る的として使うだけ。

## 0. この doc は 3 度目である

初版は「Among Us に足りないのはキルだけ」と書いたが、前提が 3 つ崩れた。
ベントもサボタージュも「既に書ける」と書いていたのに、実装が末端まで届いて
いなかった。そこで先に埋めた。

| PR | 埋めた穴 |
|---|---|
| #812 | `WitnessPolicy.ACTOR_ONLY` の貫通 + 全 interact での目撃の二重計上 |
| #814 | `TELEPORT_ENTITY` が dead code |
| #815 | `CHANGE_ATMOSPHERE` が dead code |

**そして 4 件目が見つかった。** `execute_interaction` は
`acting_item_instance_id` / `target_item_instance_id` を受け取るのに、**本番の
呼び出し元がどちらも渡していない** (`application/llm` 配下に
`target_item_instance_id` の出現は 0 件)。結果として Phase 4-A/4-B の item
instance 層 6 種 (`ITEM_INSTANCE_STATE` / `TARGET_ITEM_INSTANCE_STATE` /
`CHANGE_*` / `RECORD_*_TICK`) が**エージェントの行動から一切到達できない**。
本 doc のスコープ外だが、「装備を壊す」がこれに依存するので §4 に反映する。

2 版目は「対人行為を spot object にぶら下げ、専用ツール `act_on_player` を
足す」設計だったが、これも棄却した。理由は §3 に書く。**この doc で最も
時間を使ったのは「LLM とシナリオ作者の両方にとって自然な形」を見つける
ところ**で、2 度作り直している。

記述はすべて main (7cefa095) を読んで確認した。

## 1. 現在地

| 要素 | 状態 |
|---|---|
| 役割 (`initial_state` + `PLAYER_STATE_IS`) | 動く |
| 非対称な目的 (`players[].objective`) | 動く (#809) |
| 死体がその場に残る / 発見で人が動く | 動く (#803) |
| 秘匿行為 (`ACTOR_ONLY`) | 動く (#812) |
| ベント (`TELEPORT_ENTITY`) | 動く (#814) |
| 照明サボタージュ (`CHANGE_ATMOSPHERE`) | 動く (#815) |
| 通路封鎖 (`CHANGE_PASSAGE_STATE`) | 動く |
| **対人行為** | **書けない。本 doc の対象** |
| 陣営の勝敗 | 書けない (集計述語。別 doc) |
| 会議・投票 | 書けない (優先度低) |

`InteractionConditionType` が **19 種**、`InteractionEffectType` が **28 種**
あり、可視性も役割も宣言できる。**効果の対象を選べないことだけが対人行為を
塞いでいる。**

## 2. どこで行為者に固定されているか

**層を取り違えると実装量を読み違える。** 初版はここで失敗した。固定は
「効果の種類」ではなく「適用が起きる層」で 2 つに分かれる。

### 2.1 application 層で `player_id` から引き直している (多数派)

`apply_effects` は spec を組み立てるだけで**何も適用しない**。実際に固定して
いるのは `SpotInteractionApplicationService` で、`player_id` から aggregate を
引き直している。`APPLY_DAMAGE` / `APPLY_STATUS_EFFECT` / `SATISFY_NEED` /
`GIVE_ITEM` / `REMOVE_ITEM` / `TELEPORT_ENTITY` の 6 つ。加えて
`COMBINE_ITEMS` / `GIVE_FROM_LOOT_TABLE` も同じ id リスト経由で行為者に固定
される。**どの effect_type が `TARGET_PLAYER` を受け付けるかは loader で
列挙する** (`COMBINE_ITEMS` に対象は無意味)。

### 2.2 domain 層で aggregate を in-place mutate している (少数派)

`CHANGE_PLAYER_STATE` と `RECORD_PLAYER_STATE_TICK` の 2 つだけ。spec を作らず、
渡された `acting_player_status` を直接 `merge_state` する。**この 2 つは必ず
セットで扱う** — 片方だけ対象化すると「対象に印を付けたのに刻んだ時刻は
行為者側に書かれる」という捻れが起きる。

### 2.3 観測も行為者に固定されている

`AppliedEffectSummary` は表示用の `target_ref: str` しか持たず (構造化 ID では
ない)、`SpotPlayerStateChangedInSpotEvent` は
`entity_id=actor_entity_id` で発火する。対象に適用したのに「行為者の状態が
変わった」と第三者に流れる。

### 2.4 行為者が存在しない呼び出し元が 3 つある

`apply_effects` の呼び出し元は 3 箇所。うち 2 つには行為者が居ない
(`SpotGraphScenarioEventStageService` と
`SynchronizedActionResolverStageService`)。どちらもシナリオ JSON から書ける
入口なので、`TARGET_PLAYER` のガードは 3 箇所すべてに要る。

## 3. LLM とシナリオ作者から見た形 (2 度作り直した部分)

### 3.1 棄却した 2 つの案

**案 A: `interact` に `target_player_label` を足す。**
初版。`interact` の失敗率 54% を根拠に撤回したが、**その根拠が誤っていた**。
内訳を読むと 68/96 は `INTERACTION_PRECONDITION_FAILED` = 世界が正しく拒否した
ケースで、schema とは無関係である。schema 誤用は 16%、ラベル誤りは 8%。

> 数値の出所: `var/runs/` の `v4coop_reasonfirst_001` / `v4coop_distant_001` /
> `v3coop_postrefactor_001` の `trace.jsonl` を `action` / `action_result` で
> 突き合わせて集計した (計 179 interact)。初版の撤回はこの数値の読み違いが
> 原因だったので、再導出できるよう run id を残す。

**案 B: 対人 action を spot object にぶら下げ、専用ツール `act_on_player` を
足す。** 2 版目。2 つの理由で棄却した。

1. **object の役割が変質する。** `interact` では object が「行為の対象」
   (流木の山を採る) なのに、対人行為では「行為の文脈」(暗がりを使って人を
   襲う) になる。**同じ引数名に違う役割**をやらせることになり、
   `object_label` × `action_name` × `target_player_label` の自由文字列 3 つを
   LLM に当てさせる形になる
2. **同じ action を複数の場所で使うには複数回定義が要る。** 「暗い場所なら
   どこでも襲える」が書けない。紐付けを「成立条件の代用品」として使っていた

### 3.2 採用 — 対象は 1 本、定義はシナリオに 1 回、場所は条件で書く

対人 action には分離できる 2 つの側面がある。ここを混ぜたのが案 B の失敗
だった。

| | 置き場所 |
|---|---|
| **定義** (名前・効果・可視性) | シナリオに 1 回 |
| **成立条件** (どこで・いつ・誰が・何を持てば) | 前提条件 |

**紐付けより条件の方が厳密に表現力が高い。** 場所は条件のひとつにすぎない。

```json
"player_interactions": [
  {
    "action_name": "strike_down",
    "display_label": "背後から襲う",
    "witness_policy": "ACTOR_ONLY",
    "notify_target": true,
    "preconditions": [
      {"condition_type": "PLAYER_STATE_IS", "required_state": {"role": "hunter"},
       "failure_message": "あなたにそんな真似はできない。"},
      {"condition_type": "HAS_ITEM", "required_item": "knife",
       "failure_message": "素手では無理だ。"},
      {"condition_type": "SPOT_LIGHTING_IS", "lighting": ["DARK", "PITCH_BLACK"],
       "failure_message": "明るすぎる。誰かに見られる。"},
      {"condition_type": "TARGET_PLAYER_STATE_IS", "required_state": {"role": "crew"},
       "failure_message": "その相手は同じ側の人間だ。"}
    ],
    "effects": [{"effect_type": "APPLY_DAMAGE", "target": "TARGET_PLAYER",
                 "parameters": {"damage": 999}}]
  }
]
```

「暗い場所ならどこでも襲える」が 1 回の宣言で書ける。特定の部屋に限りたければ
`AT_SPOT_IS` を足すだけで、**選択肢は減るのではなく増える**。#815 で照明が
実際に変わるようになったので、`SPOT_LIGHTING_IS` は動的な条件として機能する。

必要な新条件は 3 つで、いずれも対人行為に限らず汎用である。

| 条件 | 用途 |
|---|---|
| `TARGET_PLAYER_STATE_IS` | 「crew だけ殺せる」「まだ印が無い相手だけ」 |
| `SPOT_LIGHTING_IS` | 暗所限定の行為全般 |
| `AT_SPOT_IS` | 場所限定の行為全般 |

既存の `PLAYERS_AT_SPOT` (人数) / `TIME_OF_DAY_IS` / `WEATHER_IS` / `FLAG_SET` /
`HAS_ITEM` と組み合わせれば「夜に」「二人きりのときだけ」「停電中に」が書ける。

### 3.3 ツールは `interact` 1 本、対象は `target_label` に統一

```
interact(target_label, action_name, parameters?, say_inline?, inner_thought)
```

`target_label` には object でも player でも入る。現在の状況では既に両方が
`""` 付きで列挙されているので、LLM は**行為したいものの名前を書くだけ**。

```
オブジェクト:
  - "焚き火跡"(available=true) — 消えかけた焚き火の跡 [gather, examine]

同じ場所にいるプレイヤー:
  - "リン"（疲れて見える） [strike_down(暗い場所・ナイフが要る), tend, mark]
  - "カイト" [strike_down(暗い場所・ナイフが要る), tend, mark]
```

行末の `[...]` に条件ヒントを添える形式は**既存の仕組みがそのまま使える**
(`_format_action_name_with_condition_hints`)。物体行で
`gather(備蓄が足りない)` と出しているのと同じである。

この形が解くもの。

- 自由文字列が 3 つから **2 つ**に減る (案 B では減らなかった)
- ツールを分ける / 分けないの議論が消える。**対象名の指定作法が物体と人で
  揃う**

  ただし「誤用が構造的に起きない」とまでは言えない。§4 で「既存ツールに手を
  触れない」と決めた以上 `give_item` / `tend_to_player` / `whisper` / `attack`
  は残るので、`interact("リン", "give_item")` のような**新しい誤用クラス**が
  生まれる。同席者行には既に `(give_item で所持アイテムを直接渡せる相手)` の
  注記が付いており、同じ 1 行が「別ツールで渡せる相手」と「interact の action
  リスト」を同時に広告することになる。ここは実測で見る
- 物体と人で作法が同じになる
- `(要 target_player_label)` のような注記が不要になる

> 表示形式について: 各 action に `action_name="gather"` を添える冗長形は
> PR-EE で一度試され、「認知負荷が高く action 誤発明を招く」として戻されて
> いる。節見出しで 1 度だけツール名と引数名を示す案は有望だが、プロンプト
> 文言の変更は実測で確かめるべき類なので、まず現行形式のまま出し、
> `INTERACTION_ACTION_NOT_FOUND` の比率で判断する。

**リネームの範囲 (実施済み)**: 当初「100 箇所 / 29 ファイル」と見積もったが、
これは過大だった。実際は `src` に 29 箇所 / 7 ファイル、`tests` に 62 箇所 /
17 ファイルで、うち**引数を実際に読み書きしている箇所は 6 つ**しかなく、
残りはコメントと docstring だった。

書き換えが必要だった実質的な箇所:

| 箇所 | 内容 |
|---|---|
| `tool_catalog/spot_graph.py` | schema の property 名と `required` |
| `spot_graph_resolver._resolve_interact` | `args.get(...)` |
| `runtime_manager._build_interact_invalid_label_failure` | `arguments.get(...)` と文面 |
| `spot_graph_tool_executor` | explore 空振り時の「interact するには〜」ヒント |
| `tool_call_loop_guard._TARGET_ARG_KEYS` | 旧 key を削除 (`target_label` は既にあった) |

`_list_object_labels` は**名前を変えていない**。この関数は実際に物体だけを
列挙しており、本 PR の時点でも対象種別は物体だけなので、名前は事実に合って
いる。プレイヤーを列挙するようになる PR で改名する。

旧名で呼ばれたときは「対象の名前が見つかりません: (空)」という何も伝えない
文面になるので、`_build_interact_invalid_label_failure` に**引数名違いを名指し
する分岐**を足した。

プレフィックスキャッシュ (設計判断 #1) には抵触しない (tick 間の不変性の話で
あり、リネームは 1 回きりの静的変更) が、過去 run との prompt 比較可能性は
切れる。

### 3.4 ID 解決を 1 本にまとめる (前提となるリファクタリング)

`target_label` に object と player が混ざるので、解決ロジックの統一が前提に
なる。現状は重複しているうえ、**エラー意味論が食い違っている**。

**プレイヤー解決だけで 3 本ある。** object を入れると 4 本。

| 関数 | 実装 | 見つからないとき |
|---|---|---|
| `resolve_object_target` | 共通ヘルパ | 例外 |
| `_resolve_tend_to_player` | **共通ヘルパを player kind で既に使っている** | 例外 |
| `resolve_player_target` | 手書きループ | **`None`** |
| `_resolve_speech` (world_resolver) | `require_target_type` | 例外 |

4 本目は `_normalize_label_candidates` も display_name fallback も通らない。
つまり **「本家 resolver の whisper は名前直書きに弱く、runtime_manager 側の
whisper は強い」というねじれ**が今ある。

**1 本にまとめる。**

```
resolve_target(
    label, runtime_context, *,
    accept_kinds=("spot_graph_object", "spot_graph_player"),
    label_name="対象の名前",
) -> ToolRuntimeTargetDto
```

- 見つからない → `INVALID_TARGET_LABEL`
- 見つかったが種別が違う → `INVALID_TARGET_KIND` (「その名前はプレイヤーです。
  この action は物体が対象です」のように**期待した種別を明示**する)
- `None` を返す経路は無くす

**「振る舞い不変」にはならない。** `resolve_player_target` の呼び出し元 2 つの
うち、`_resolve_single_give_entry` は None を受けて例外に変換しているので安全
だが、**whisper 経路 (`runtime_manager._resolve_whisper_target`) が壊れる**。
`_handle_speech` は resolver 例外を `LlmCommandResultDto` に変換するアダプタを
通さず生で登録されているため、例外は広い `except Exception` に落ち、現在の

- `INVALID_WHISPER` + 有効な target_label 一覧 + remediation

が

- `LLM_TOOL_EXECUTION_FAILED` + 汎用文言 + スタックトレース

に**劣化する**。`tests/presentation/spot_graph_game/test_whisper_target_resolution.py`
も `is None` を assert している。

したがって PR 1 は「振る舞い不変」ではなく **「失敗の返し方を揃える」** と
位置づけ、whisper 呼び出し元の書き換えとテスト更新を含める。

`accept_kinds` は文字列 `kind` で受ける。object は基底 `ToolRuntimeTargetDto`、
player は `PlayerToolRuntimeTargetDto` で登録されており非対称なので、
`expected_types` (isinstance) より素直である。

### 3.5 同名衝突

**「種別を足すだけ」では済まない。** `build_ordinal_disambiguator` は
objects / players / monsters の**セクションごとに別々の名前リスト**へ適用
されているので、物体「リン」とプレイヤー「リン」は両方とも `"リン"` のまま
出力され `#N` が付かない。種別横断の衝突は現状の仕組みで検出できない。

さらに `_find_target_by_display_name` は単一 kind で絞って `matches[0]` を
返し、複数一致は warning だけ。`accept_kinds` で 2 種別を許すと**警告すら
出ない静かな誤解決**が起こりうる。

対処にはラベル割り当て前に object + player の名前を合併して 1 回で
disambiguate する構造変更が要る。**実装量は §3.4 のリファクタリングと同程度**
と見積もる。

### 3.6 可視性は 3 軸、`notify_target` は interaction 単位

`WitnessPolicy` と `EffectVisibility` の 2 軸では、「毒を盛られた本人が即座に
気づく」か「殴られた本人に因果が届かない」かのどちらかになる。

| 軸 | 何を決めるか | 粒度 |
|---|---|---|
| `WitnessPolicy` | 第三者に行為が届くか | interaction |
| `EffectVisibility` | 第三者に効果が届くか | effect |
| **`notify_target`** | **対象本人に行為が届くか** | **interaction** |

**effect 単位にしない。** `EffectVisibility` の既定は「安全側」という哲学で
決まっており、そこに「身体の外形に現れるか」という別の哲学の軸を同じ粒度で
足すと、作家が同じ effect について 2 つの基準で推論することになる。組み合わせ
の意味も未定義になる (`notify_target=true` + `HIDDEN` は HIDDEN の定義を
上書きしてしまう)。1 interaction 内で分けたい要求が実測で出たら降ろす。

**何が問題なのかを正確に書く。** 「殴られた本人が HP だけ減って何も知らない」
は言い過ぎだった。`HIDDEN` でも HP 自体は本人の現在状態に見える。欠けている
のは因果である。実在する問題は 3 点。

0. `WitnessPolicy` の docstring には **`EXPLICIT_TARGETS` が将来拡張として
   既に予告されている**。`notify_target` はこれと同じ問題を解こうとしている。
   直交している分こちらが良いと判断するが、**採用する PR でその予告コメントを
   消す**。1 つの問題に 2 つの仕組みの計画が残るのが最悪の状態である
1. 致死打では対象のターンが回らないので何も読めない
2. 因果不明のダメージは推論を歪める
3. `hidden_state_keys` に入る state 変化は本人からも見えない

### 3.7 対象への配信 — 新 event が要るのは 1 組み合わせだけ

`ObservedEventRegistry` は event 型 → strategy の 1 対 1 写像で、
`is_observed` は完全型一致判定である。継承で逃げる手も無い。

ただし**新 event が本当に要るのは `ACTOR_ONLY` かつ `notify_target=true` の
組み合わせだけ**。

- 公然の対人行為 (`SAME_SPOT` + notify) は `MonsterAttackedPlayerInSpotEvent`
  と同じ「被害者本人を含む同スポット全員」パターンで足りる
- 対象 1 人だけへの配信も `SpotSoundHeardEvent` 用の
  `_resolve_known_player_entity` に前例がある

**致死打には原理的に届かない。** `is_down` の player は recipient から
構造的に除外されるので、`notify_target=true` でも致死打では対象に何も届かない。
「死んだ本人に自分の死の観測を届けるか」を H-4 とあわせて明示的に決める
(私は届けない方に賛成だが、決めないと silent 規則に飲まれる)。

**実装上の注意 2 つ。** 新 event は `_EVENT_TO_STRATEGY` に**明示登録が必須**
(完全型一致なので登録漏れは例外もログも出さず配信 0 件)。`is_down` 除外は
分岐ではなく `resolve()` 最終行の一括後処理なので、例外を作るならその行を
変える。

### 3.8 対象が解決できないときは明示的に失敗させる

対象なし / 同スポットに居ない / 自分自身 / 対象が倒れている、のいずれも
**明示的な失敗として本人に返す**。効果を黙って捨てたり行為者に適用したり
しない。`give_item` の既存語彙 (`GIVE_ITEM_TARGET_NOT_IN_SAME_SPOT` /
`GIVE_ITEM_TARGET_IS_SELF`) と揃え、同スポット判定の情報源も揃える。

## 4. 対人 interact で扱う行為の全体像

| 行為 | 使う効果 | 経路 | v1 | 備考 |
|---|---|---|---|---|
| 殺害 | `APPLY_DAMAGE` | 2.1 | ○ | H-1 の DEAD 確定が必須 |
| 殴る・傷つける | `APPLY_DAMAGE` (小) | 2.1 | ○ | |
| 毒を盛る | `APPLY_STATUS_EFFECT` (非 notify) | 2.1 | ○ | 隠し毒 |
| 麻痺・拘束 | `APPLY_STATUS_EFFECT` | 2.1 | ○ | |
| 脅す | `APPLY_STATUS_EFFECT` + 公開 | 2.1 | △ | `StatusEffectType` は 13 種で恐怖・沈黙・失明が無い。`ATTACK_DOWN` 等の読み替え止まり |
| 食べさせる・飲ませる | `SATISFY_NEED` | 2.1 | ○ | |
| 手当て | `APPLY_STATUS_EFFECT` (`REGENERATION`) | 2.1 | ○ | **漸進回復なら可能**。ただし即時回復の effect が無く、回復量もシナリオから指定できない (グローバル定数) |
| 突き落とす・射出する | `TELEPORT_ENTITY` | 2.1 | ○ | **最も安い**。観測経路が既にある |
| 監禁する | `TELEPORT_ENTITY` + 通路封鎖 | 2.1 | ○ | |
| **盗む** | `REMOVE_ITEM` + `GIVE_ITEM` | 2.1 | **△** | **H-3**。対象の所持を確認できず空振りで例外。soft fail 経路が要る |
| 押し付ける・持たせる | `GIVE_ITEM` | 2.1 | ○ | 既存 `give_item` と重複 |
| 印を刻む | `CHANGE_PLAYER_STATE` + `RECORD_..._TICK` | 2.2 | ○ | **最初に動かす経路**。既定 visibility が `HIDDEN` なので、シナリオ側で明示しないと第三者に何も届かない |
| 教える・知識を渡す | `CHANGE_PLAYER_STATE` | 2.2 | ○ | |
| 洗脳・役割を書き換える | `CHANGE_PLAYER_STATE` | 2.2 | ○ | |
| **口封じ** | `CHANGE_PLAYER_STATE` | 2.2 | **✕** | 状態は付けられるが**発話を実際に止める仕組みが無い** |
| **装備を壊す** | `CHANGE_TARGET_ITEM_INSTANCE_STATE` | 2.1 | **✕** | §0 の 4 件目の dead code。**item instance 層そのものが行動から到達不能**。配線の新設が前提 |
| 起こす | — | — | — | 既存 `tend_to_player` |

○ 11 / △ 3 / ✕ 2。**△ と ✕ を隠さない。**

初版・2 版目で「手当ては HP を回復できない」と書いたのは**誤り**だった。
`APPLY_STATUS_EFFECT` の `REGENERATION` が `heal_hp` を呼ぶ経路が既にある。
正確には「漸進回復はできるが、即時回復と回復量の指定ができない」。

逆に「装備を壊す」は過小評価で、実態は dead code 4 件目に依存している。

**loader の fail-fast が要る**: 未知の `effect_type_name` (status effect 名) は
warning + skip で **interaction 自体は成功として返る**。`witness_policy` の
typo には fail-fast するのに status effect 名には何もしていない。毒・麻痺を
○ と言うなら、この fail-fast を PR で足す。

### 既存の対人ツールとの関係

`give_item` / `tend_to_player` / `whisper` は既に対人ツールとして存在し、機能が
重複する。**v1 では既存ツールに手を触れない。** 動いているものを壊すリスクを
負う理由がない。シナリオ定義の対人行為が実運用に耐えると分かってから統合を
検討する。

## 5. 非目標

- `attack` のプレイヤー対応 (`attack` はモンスター戦闘のまま)
- 戦闘バランス・命中判定・クールダウン
- 即時 HP 回復 effect の新設と回復量のシナリオ指定 (漸進回復は `REGENERATION` で可能)
- 発話を止める仕組み (口封じの実効化)
- item instance 層の配線 (装備破壊の前提。dead code 4 件目)
- 陣営・勝敗判定 (集計述語の別 doc) / 会議・投票
- 既存対人ツールの統合

## 6. 実装順

| PR | 内容 | 動くもの |
|---|---|---|
| 1 | **ID 解決の集約** (`resolve_target` 一本化、`None` 返しの廃止、whisper 呼び出し元の移行) + `EffectTarget` + loader の厳格パース + **actor 不在の 3 呼び出し元すべてでガード** | なし (失敗の返し方が揃う) |
| 2 | シナリオ直下 `player_interactions` + `target_label` の種別統一 + 名前の種別横断 disambiguate + **経路 2.2** + **最小の観測 event** | 印を刻む・教える・洗脳 |
| 3 | 新条件 3 種 (`TARGET_PLAYER_STATE_IS` / `SPOT_LIGHTING_IS` / `AT_SPOT_IS`) | 役割ゲート・暗所限定 |
| 4 | 経路 2.1 の対象化 (`TELEPORT_ENTITY` + damage / status / need) + **プレイヤー aggregate のロード一元化** | 突き落とす・毒・手当て |
| 5 | **H-1** (対象の `PlayerDownedEvent` 回収 → DEAD 確定) | **殺害** |
| 6 | `TARGET_HAS_ITEM` + アイテムの対象化 | 盗み |
| 7 | `notify_target` + 新 event + `is_down` の扱い決定 | 秘匿対人行為の当事者通知 |
| 8 | 質感確認シナリオ | 密室・役割ゲート・秘匿 |

**PR 2 に観測を含める理由**: `CHANGE_PLAYER_STATE` の既定 visibility は
`HIDDEN` で観測 event も出ない。観測を後回しにすると PR 2 は「誰にも何も
見えないまま state だけ変わる」状態になり、trace からも効果を確認できない。

**PR 4 と 5 を分ける理由**: H-2 (aggregate 二重生存) は単体で証明できる正しさの
修正で、H-1 の event 配線をその上に載せる前に固めたい。受け入れ条件も 8 個
あるので 1 PR に混ぜない。

**PR 2 の受け入れ条件に必ず入れるもの**:

- 対人観測が `schedules_turn=True` を持つ (**被害者も目撃者も起きる**)。
  MEMORY に残した「行動密度の親原因は `schedules_turn`」を一度踏んでいる
- 失敗観測の dedup キーが対象を含む
  (`(entity_id, target_kind, target_int_id, action_name, reason)`)。
  object 用の現在のキーは `object_id` を含むので、対人でセンチネルを入れると
  **「リンを襲おうとして失敗」と「カイトを襲おうとして失敗」が同一キーに潰れ、
  24 tick 間 2 件目が出ない**
- interior が変化しない (後から object 系 effect が混入したときに気づける)

**PR 2 の設計判断**: `SpotObjectInteractedEvent.object_id` は Optional でない。
対人 interaction には object が無いので、Optional 化するのではなく
**専用の event 型を新設する** (`_EVENT_TO_STRATEGY` への明示登録が必須)。
Optional 化は `_resolve_object_name` と `_build_public_observable_events` に
分岐を増やす。

**PR 3 で必ず決めること**: `SPOT_LIGHTING_IS` が **raw か effective か**。
raw (spot の atmosphere そのまま) なら #815 の停電は効くが松明を持った同席者は
無視される。effective (`SpotPerceptionService.compute_effective_lighting`) なら
屋外・昼夜・天候・光源持ちまで合成されるが、光源持ち判定は
`spot_attack_orchestrator` が「inventory 解決のコストが高い」として TODO で
放置している。**「明るすぎる。誰かに見られる」という意図を満たすには
effective が要る。** 決めずに出すと宣言したのに効かない静かな失敗になる。

また `"lighting": ["DARK", "PITCH_BLACK"]` の配列形は既存条件 (すべて単一値 +
`_IS_NOT` 対) と揃っていない。`SPOT_LIGHTING_IS` / `SPOT_LIGHTING_IS_NOT` の
単一値に揃えるか、配列形を意図的に導入するか決める。

**PR 3 に入れるテスト**: `_evaluate_condition` の最終行は未対応の条件を
`return False` で落とす。enum に値を足して分岐を書き忘れると**その条件を使う
interaction が永久に実行不能**になる。「全 `InteractionConditionTypeEnum`
メンバに分岐があること」を assert するテストを入れる。

**永続化**: `player_interactions` は静的なのでシナリオ再読込で復元でき、
SQLite codec の変更は不要。per-Being store も増えないので checklist #27 の
追従も不要。

## 7. 実装時のチェックリスト

### H-1. 対象の `PlayerDownedEvent` を回収する — キル経路の最大の罠

`apply_damage` で HP 0 になると aggregate が `PlayerDownedEvent` を**内部に積む
だけ**で、`publish_all` に流さないと `PlayerDownedOutcomeHandler` が走らず
**DEAD outcome が確定しない**。さらに save→clear の順序を誤ると陳腐化イベントが
後の `find` で再放出される (`tend_to_player` で実際に起きた前例がある)。

現在このドレイン処理は**行為者についてしか書かれていない**。対象にも同じ
「回収 → clear → save」の 3 手が要る。

これは既存のバグではなく、**対人ダメージを実装するときに踏む罠**である。
LLM から見ると「攻撃は成功したと言われたのに相手が普通に歩いている」という、
因果が壊れて見える最悪の形になる。例外もログも出ない。

**PR 6 の受け入れ条件 (すべて自動テストで固定する):**

1. 対象の HP を 0 にしたとき、**対象の outcome が `DEAD` に確定する**
2. 対象の `PlayerDownedEvent` が publish される。件数は **ちょうど 1 件**
3. 保存後に対象 aggregate を `find` し直して `get_events()` が **空である**
4. 同スポットの第三者に「倒れた」観測が届く
5. 対象の `is_dead` が他プレイヤーの「同じ場所にいるプレイヤー」行に
   「(死亡している)」として反映される
6. 致死でないダメージでは outcome が `UNRESOLVED` のままである
7. `target=ACTOR` の既存挙動 (環境ダメージ等) が変わらない
8. 行為者と対象が同一 player になった場合は、効果を適用せず明示的に失敗する

3 と 6 が抜けやすい。

**実装後に判明した追加の注意点** (対人ダメージ PR):

- **昏倒させた一撃を「倒れている間にされたこと」に混ぜない。** 対人行為の
  記録側が「いま倒れているか」を集約に問い合わせると、致死の一撃は必ず
  「倒れている相手への行為」に化ける。倒された事実は `PlayerDownedEvent`
  由来の観測で本人に即座に届くので、目覚めの申し送りにも入れると同じ一撃が
  二重に語られる。判定は **行為が始まった時点の状態** で行う
  (`PlayerInteractedWithPlayerEvent.target_was_down`)。
- **倒れている相手への追撃が DEAD 確定を無限に先延ばしできる。**
  `apply_damage` は HP 0 の相手にも毎回 `PlayerDownedEvent` を積み、
  `PlayerDeathGraceTimer.register` は `downed_at_tick` を上書きする
  (down → revive → 再 down の猶予リセットを意図した仕様)。したがって猶予
  (既定 30 tick) が切れる前に殴り続ければ、DEAD を確定させずに相手を倒した
  ままにできる。物体 / 環境ダメージにも同じ性質があるが、対人行為が入って
  初めてシナリオ作者の手で意図的に到達できるようになった。

  現時点では engine 側で塞いでいない。塞ぐと「猶予リセット」の既存意図を
  壊すため、まずシナリオ作法として **致死性のある対人行為には
  「相手が倒れていないこと」を前提条件に書く** ことを推奨する。engine 側で
  区別する場合は「再 down か、down 中の追撃か」を分けて扱う必要がある。

### H-2. 同一プレイヤーの aggregate が二重に生きる

app 層は同じプレイヤーの aggregate を **4 回**引いている (precondition 用 /
damage 用 / status effect 用 / need 用)。今は各ブロックが load → 変更 → save を
順に完結させ、in-memory repo が clone を返すので偶然無事だが、対象が加わると
**6 回 load + 交互 save** になる。

対処は「item と同じ 2 段ガードを player 側にも」ではなく、**「1 プレイヤーに
つき 1 インスタンスを load して使い回す」** である。受け入れ条件もそう書く。

### H-3. 盗みは soft fail 経路を作らないと書けない

`REMOVE_ITEM` の消費失敗は `ApplicationException` を raise する。対象側の所持を
確認する条件が無い (v1 で足すのは `TARGET_PLAYER_STATE_IS` だけ) ので、**空の
ポケットを狙った瞬間に例外が飛ぶ**。

**soft fail 化より安い解がある。** `TARGET_HAS_ITEM` 条件を足す方が良い。
`HAS_ITEM` の鏡像で十数行、しかも §3.2 の「紐付けより条件の方が表現力が高い」
の直接の応用である。soft fail 化は「precondition を通ったのに消費されない
状態を作らない」という既存の不変条件を弱める。

### H-4. 死体を狙えるのか決める

設計判断 #2 に「dead player に対するアクションは全部 silent にする」とある。
Among Us は死体がその場に残り発見されることが核なので、「狙えないが見える」を
両立させる。`TARGET_IS_DOWN` / `TARGET_IS_DEAD` の失敗語彙を用意し、**死体から
盗めるかを明示的に決める**。決めないと silent 規則に飲まれて静かに何も起きない。

### H-5. 同スポット判定の情報源を揃える

`presence_at(spot_id).present_entity_ids` と `give_item` の resolver、どちらを
使うか決める。別々だと「give_item では渡せるのに interact では届かない」という
説明不能な差が出る。

## 8. 検証の的

v1 完了時点で、Among Us の残りが **陣営の勝敗** と **会議・投票** だけに
なっているかで測る。§4 の △ 3 件 (脅す・手当ての即時回復・盗みの所持確認) と ✕ 2 件 (口封じ・
装備破壊) は残るので、それらを使わない形で近似できるかを見る。

## 関連

- [goal_per_player_objective_design.md](./goal_per_player_objective_design.md) — 目的層 G6
- [../design_decisions.md](../design_decisions.md) — #1 プレフィックスキャッシュ不変、#2 取れる手段の質、#31 テレポートの秘匿性、#32 環境変化の部分更新
- [../agent_design_principles.md](../agent_design_principles.md) — 静かな失敗の回避、他者からの可視性
