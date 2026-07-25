# 対人インタラクション基盤 — 効果の対象を行為者から解放する

> 検証の的: シナリオ JSON だけで Among Us が近似できること。
> ただし Among Us 固有の概念 (インポスター・緊急ボタン・タスクバー) は
> コードに入れない。表現力の到達度を測る的として使うだけ。

## 0. この doc は 2 度目である

初版は「Among Us に足りないのはキルだけ」と書いたが、レビューで前提が 3 つ
崩れた。ベントもサボタージュも「既に書ける」と書いていたが、実装が末端まで
届いていなかった。土台が壊れたまま上物を設計していたことになる。

そこで先に 3 つ埋めた。

| PR | 埋めた穴 |
|---|---|
| #812 | `WitnessPolicy.ACTOR_ONLY` が同スポットの第三者に貫通していた。ついでに **すべての interact で目撃が二重計上** されていたのも判明 |
| #814 | `TELEPORT_ENTITY` が spec を作るだけの dead code だった |
| #815 | `CHANGE_ATMOSPHERE` が同じく dead code だった (interaction / scenario_events 両方) |

本 doc の記述はすべて main (7cefa095) を読んで確認した。

## 1. 現在地

動くことを確認したもの。

| 要素 | 手段 | 状態 |
|---|---|---|
| 役割 | `players[].initial_state` + `PLAYER_STATE_IS` | 動く |
| 非対称な目的 | `players[].objective` / `goal_locked` | 動く (#809) |
| 死体がその場に残る | `is_dead` の同スポット表示 | 動く |
| 死体発見で人が動く | 目撃者の起床 | 動く (#803) |
| 秘匿行為 | `WitnessPolicy.ACTOR_ONLY` | 動く (#812) |
| ベント | `TELEPORT_ENTITY` + `ACTOR_ONLY` | 動く (#814) |
| 照明サボタージュ | `CHANGE_ATMOSPHERE` | 動く (#815) |
| 通路封鎖サボタージュ | `CHANGE_PASSAGE_STATE` | 動く |
| タスク | `interaction_def` + `quest` | 動く |
| **対人行為** | — | **書けない。本 doc の対象** |
| 陣営の勝敗 | — | 書けない (集計述語。別 doc) |
| 会議・投票 | — | 書けない (優先度低) |

素材は揃っている。`InteractionConditionType` が **19 種**、
`InteractionEffectType` が **28 種**、`WitnessPolicy` と `EffectVisibility` で
可視性を宣言でき、`players[].initial_state` で役割を持てる。

**効果の対象を選べないことだけが、対人行為を塞いでいる。**

## 2. どこで行為者に固定されているか

**層を取り違えると実装量を読み違える。** 初版はここで失敗した。固定は
「効果の種類」ではなく「**適用が起きる層**」で 2 つに分かれる。

### 2.1 application 層で `player_id` から引き直している (多数派)

`WorldGraphEffectService.apply_effects` は spec を組み立てるだけで、**何も
適用しない**。実際に行為者へ固定しているのは `SpotInteractionApplicationService`
で、しかも `player_id` から aggregate を引き直している。

| 効果 | 固定箇所 |
|---|---|
| `APPLY_DAMAGE` | `self._player_status_repository.find_by_id(player_id)` |
| `APPLY_STATUS_EFFECT` | 同上 |
| `SATISFY_NEED` | 同上 |
| `GIVE_ITEM` | `grant_item_specs_to_inventory(player_id, ...)` |
| `REMOVE_ITEM` | 同上のインベントリ |
| `TELEPORT_ENTITY` | `graph.teleport_entity(entity_id, ...)` |

### 2.2 domain 層で aggregate を in-place mutate している (少数派)

`CHANGE_PLAYER_STATE` と `RECORD_PLAYER_STATE_TICK` の 2 つだけ。spec を作らず、
`apply_effects` に渡された `acting_player_status` を直接 `merge_state` する。

**この 2 つは必ずセットで扱う。** 片方だけ対象化すると「対象に印を付けたのに
刻んだ時刻は行為者側に書かれる」という捻れが起きる。

### 2.3 観測も行為者に固定されている

`AppliedEffectSummary` は対象を持たず、`SpotPlayerStateChangedInSpotEvent` は
`entity_id=actor_entity_id` で発火する。**対象に適用したのに「行為者の状態が
変わった」と第三者に流れる**ので、対象を足すなら観測側も対で直す。

### 2.4 行為者が存在しない呼び出し元が 3 つある

`apply_effects` の呼び出し元は 3 箇所。うち 2 つには行為者が居ない。

| 呼び出し元 | 行為者 |
|---|---|
| `SpotInteractionService` (interact) | 居る |
| `SpotGraphScenarioEventStageService` | **居ない** |
| `SynchronizedActionResolverStageService` | **居ない** |

3 つ目は協力アクションの `on_complete` / `on_timeout` で、これもシナリオ JSON
から書ける入口である。`TARGET_PLAYER` のガードは 3 箇所すべてに要る。

## 3. 設計

### 3.1 target バケットを並置する

`EffectTarget` は JSON の語彙としては 1 つに保つが、実装は 2 つの機構になる。
**「対象 aggregate を渡すだけ」では 2.1 に届かない** (spec が消費されるのは
application 層であり、`apply_effects` はインベントリ aggregate を引数として
受け取ってすらいない)。

1. `WorldGraphEffectResult` に `target_damage_specs` /
   `target_status_effect_specs` / `target_satisfy_need_specs` /
   `target_item_spec_ids_to_grant` / `target_item_spec_ids_to_remove` /
   `target_teleport_specs` を **並置する** (spec 型自体は変えない = 波及最小)
2. `target_player_status` は 2.2 のためだけに `apply_effects` へ渡す
3. application 層が `target_player_id` を解決し、既存の適用ブロックを target
   側にももう 1 回まわす

これは既存の前例と同型である。`acting_item_aggregate` /
`target_item_aggregate`、`item_instance_state_changed` /
`target_item_instance_state_changed` が同じ「acting_ / target_ 並置」を
採っている。

**domain 層で対象に damage を当てる案は採らない。** `cross_domain_effect_spec`
の冒頭が「world_graph は combat/player の型に直接依存しない、application 層が
適用する」と明記した層の分離を壊すし、後述 H-1 の `PlayerDownedEvent` 回収を
domain へ持ち込むことになる。

**署名変更の波及**: `apply_effects` の呼び出し元は 3 箇所だけで、すべて
keyword-only なので既定値付き追加は非破壊。ただし中間 DTO が 2 段ある —
`WorldGraphEffectResult` と `InteractionExecutionResult` の両方に同じ
フィールドを生やす必要がある (後者は `hidden_effects` を落とすなど単なる転送
ではない)。**署名 → 結果 VO → 中間 VO → app 層の 4 段**と見積もる。

### 3.2 `InteractionEffect.target`

`visibility` と同じく first-class 属性にする (`parameters` dict に混ぜない)。

```python
class EffectTarget(Enum):
    ACTOR = "ACTOR"                  # 既定。従来の挙動
    TARGET_PLAYER = "TARGET_PLAYER"
```

**未知の値は `ScenarioLoadError` で落とす。** `visibility` の既存パースは不正値を
黙って既定へ倒すが、その書き方を踏襲してはいけない。`"TARGET_PLAYERS"` の
綴り間違いが `ACTOR` に落ちると**自分に致死ダメージ**が入る。#814 / #815 で
同じ方針を取った。

### 3.3 対人行為は専用ツールにする — 理由は自由文字列の削減ではない

初版は「`interact` の失敗率 54% だから自由文字列を増やすと悪化する」と書いたが、
**根拠の出し方が誤っていた**。内訳を正しく読む。

| コード | 件数 | 性質 |
|---|---|---|
| `INTERACTION_PRECONDITION_FAILED` | 68 | **世界が正しく拒否した**。schema とは無関係 |
| `INVALID_TARGET_LABEL` | 15 | ラベルの取り違え |
| `INTERACTION_ACTION_NOT_FOUND` | 13 | action 名の推測ミス |

schema 誤用は 28/179 = **16%**、ラベル誤りに限れば **8%** である。54% を根拠に
するのは誇張だった。

さらに、`interact` の外に出しても引数は減らない。§3.5 で対人行為も object を
経由すると決めるので、`act_on_player` の引数は
`object_label` × `action_name` × `target_player_label` の**自由文字列 3 つ**に
なる。初版が却下した構成そのものである。

**それでも分ける。理由は 2 つ。**

1. **description を専有できる。** `interact` の説明文は物体操作の作法
   (「オブジェクト行末尾の `[gather, examine]` から選べ」) で埋まっている。
   対人行為の作法をそこに足すと双方が薄まる
2. **`target_player_label` を `required` にできる。** 任意引数だと「書き忘れて
   実行 → 失敗 → 学習」の 1 往復が毎回入る。必須化すれば schema が構造で防ぐ

自由文字列の数は減らない。そこは正直に書いておく。

### 3.4 ツール生成の段階 — シナリオ定義ツールへの布石

「ワールドごとに露出ツールを変える」構想がある。設計判断 #1 (tool list は
tick 間で byte 不変) はプレフィックスキャッシュのための制約で、**run 内で
不変なら run をまたいで違ってよい**。実際 spot_graph / tile_map モードで既に
露出ツールを変えている。破れるのは「tick ごとに動的に絞る」だけである。

| 案 | ツール数 | キャッシュ |
|---|---|---|
| **A. 汎用の対人ツール 1 個 (`act_on_player`)** | +1 | 影響なし |
| B. シナリオの対人 action ごとに専用ツールを生成 | +N | run 内固定なら効く |
| C. spot ごとに動的に絞る | 可変 | **壊れる。不可** |

**v1 は A。** B は独立した大テーマ (ツール数の上限、同名 action の衝突、
「今この spot に無い action のツールも一覧に出る」問題) で、A の実測を持って
判断する。A→B の移行は tool catalog の生成方法を変えるだけで、ドメイン設計は
変わらない。

**A の既知の弱点 2 つを明記する。**

- **発見可能性**: 対人 action を現在状況のどこに表示するか。物体行に混ぜると
  LLM はまず `interact` を呼ぶ (description がそう指示しているため)。別
  セクションが要り、これは現在状況ビルダの改修になる。**「ツールは生えたが
  一度も呼ばれない」はこのプロジェクトが繰り返し踏んでいる型**なので、PR 2 の
  受け入れ条件に含める
- **常時露出**: 対人 action が 0 件のシナリオでも `act_on_player` は出る。
  「呼べるが必ず失敗するツール」になる。シナリオ由来の availability resolver を
  作ると案 B に片足を踏み入れるので、v1 では description で「このシナリオに
  対人行為が無ければ使えない」と書くに留める

### 3.5 対人行為は spot object に紐づけたまま宣言する

```json
{
  "id": "dark_corridor_shadow",
  "name": "暗がり",
  "interactions": [
    {
      "action_name": "strike_down",
      "display_label": "背後から襲う",
      "witness_policy": "ACTOR_ONLY",
      "notify_target": true,
      "preconditions": [
        {"condition_type": "PLAYER_STATE_IS", "required_state": {"role": "hunter"}},
        {"condition_type": "HAS_ITEM", "required_item": "knife"},
        {"condition_type": "TARGET_PLAYER_STATE_IS", "required_state": {"role": "crew"}}
      ],
      "effects": [
        {"effect_type": "APPLY_DAMAGE", "target": "TARGET_PLAYER",
         "parameters": {"damage": 999}}
      ]
    }
  ]
}
```

> 初版の JSON 例は `state_key` / `value` / `item_spec_id` と書いており、**loader が
> 一切読まないので常に precondition 失敗する**代物だった。正しくは
> `required_state` (dict) と `required_item` (文字列 id)。動かない例を載せるのは
> この doc で最もやってはいけないことなので記録しておく。

**棄却**: シナリオ直下に `player_interaction_defs` を作る案。対人行為を
「どこでもできる」ものにすると場所の意味が消える。暗がりでしか襲えない、
診療所でしか手当てできない、という**場所への紐付けが物語を作る**。実装上も
`execute_interaction` は `object_id` を起点に interior → interaction_def を引き、
失敗観測の dedup キーにも `object_id` を使う。

帰結として **v1 では対人行為も必ず object を経由する**。「相手に直接話しかけて
殴る」は書けない。

### 3.6 対象側の前提条件を v1 に含める

初版は「v1 では書けない既知の制約」としたが、**撤回する**。これが無いと
Among Us の中核ルールが 2 つ書けない。

- 「生きている相手だけ殺せる」
- 「crew だけ殺せる」(インポスターが仲間を殺せてしまう)

`TARGET_PLAYER_STATE_IS` を 1 種だけ足す。`PLAYER_STATE_IS` の鏡像で、
`can_interact` に `target_player_status` を渡して評価する。2.2 の経路でどのみち
対象 aggregate は渡すので、それを precondition 側でも読むだけである。

他の条件 (`TARGET_HAS_ITEM` など) は要求が出てから足す。

### 3.7 可視性は 3 軸、ただし interaction 単位

`WitnessPolicy` と `EffectVisibility` の 2 軸では、「毒を盛られた本人が即座に
気づく」か「殴られた本人に因果が届かない」かのどちらかになる。3 軸目が要る。

| 軸 | 何を決めるか | 粒度 |
|---|---|---|
| `WitnessPolicy` | 第三者に行為が届くか | interaction |
| `EffectVisibility` | 第三者に効果が届くか | effect |
| **`notify_target`** | **対象本人に行為が届くか** | **interaction** |

**効果ごとではなく interaction 単位にする。** 初版は effect 単位としたが、
`EffectVisibility` の既定は「安全側 (`ACTOR_DIRECT`)」という哲学で決まっており、
そこに「身体の外形に現れるか」という別の哲学の軸を同じ粒度で足すと、作家が
同じ effect について 2 つの基準で推論することになる。組み合わせの意味も未定義に
なる (`notify_target=true` + `HIDDEN` は HIDDEN の定義を上書きしてしまう)。

`witness_policy` は既に `InteractionDef` に載っているので、同じ層に置けば
「この行為は誰に届くか」を 1 回で決められる。1 interaction 内で notify を
分けたい要求が実測で出たら、そのとき effect 単位に降ろす (YAGNI)。

**何が問題なのかを正確に書く。** 「殴られた本人が HP だけ減って何も知らない」は
言い過ぎだった。`HIDDEN` の定義は「本人プロンプトの現在状態にのみ反映」なので、
HP が減ったこと自体は本人に見える。欠けているのは因果である。実在する問題は
3 点に絞られる。

1. 致死打では対象のターンが回らないので何も読めない
2. 因果不明のダメージは推論を歪める (環境ダメージは意図的にそうしているが、
   対人行為で同じ扱いにすると「誰にやられたか分からない」が常態化する)
3. `hidden_state_keys` に入る state 変化は本人からも見えない

### 3.8 対象への配信 — 新 event が要るのは 1 組み合わせだけ

`ObservedEventRegistry` は event 型 → strategy の 1 対 1 写像で、しかも
`is_observed` は `type(event) in ...` の**完全一致**判定である。継承で逃げる手も
無いので、新しい strategy を足す形は取れない。

ただし**新 event が本当に要るのは `ACTOR_ONLY` かつ `notify_target=true` の
組み合わせだけ**である。

- 公然の対人行為 (`SAME_SPOT` + notify) は `MonsterAttackedPlayerInSpotEvent` と
  同じ「被害者本人を含む同スポット全員」パターンで足りる。既存 strategy に
  同型の前例があり、コメントにも「被害者にも観測として通知して『自分が
  襲われている』と認識させる必要がある」と書かれている
- 対象 1 人だけへの配信も既に実装がある。`SpotSoundHeardEvent` 用の
  `_resolve_known_player_entity` が「この entity_id 1 人だけに届ける」を
  やっており、新 event の分岐はこれの再利用で済む

**実装上の注意 2 つ。**

- 新 event は `_EVENT_TO_STRATEGY` に**明示登録が必須**。完全型一致判定なので、
  登録漏れは例外もログも出さず配信 0 件になる
- `is_down` 除外は分岐ではなく `resolve()` の最終行での一括後処理である。
  対象通知を例外にするなら、分岐側ではなくその行を変える必要がある

### 3.9 対象が解決できないときは明示的に失敗させる

対象なし / 同スポットに居ない / 自分自身 / 対象が倒れている、のいずれも
**明示的な失敗として本人に返す**。効果を黙って捨てたり行為者に適用したり
しない。`give_item` の既存語彙 (`GIVE_ITEM_TARGET_NOT_IN_SAME_SPOT` /
`GIVE_ITEM_TARGET_IS_SELF`) と揃える。

同スポット判定の情報源は `give_item` の resolver と揃える。別々の判定にすると
「give_item では渡せるのに act_on_player では届かない」という説明不能な差が
出る。

## 4. v1 で書けるようになるもの

| 行為 | 使う効果 | 経路 |
|---|---|---|
| 口封じ・洗脳・教える・印を刻む | `CHANGE_PLAYER_STATE` + `RECORD_PLAYER_STATE_TICK` (target) | 2.2 |
| **殺害** | `APPLY_DAMAGE` (target) + `ACTOR_ONLY` + 役割ゲート | 2.1 |
| 毒を盛る | `APPLY_STATUS_EFFECT` (target, 非 notify) | 2.1 |
| 手当て | `SATISFY_NEED` (target) + `PUBLIC_OBSERVABLE` | 2.1 |
| 突き落とす・射出する・監禁する | `TELEPORT_ENTITY` (target) | 2.1 |
| 盗み | `REMOVE_ITEM` (target) + `GIVE_ITEM` (actor) | 2.1 (**H-3 の解決が前提**) |

`TELEPORT_ENTITY` の対象化は初版が見落としていた。観測経路
(`EntityLeft/EnteredSpotEvent`) が既にあるので**最も安く実装できる対人行為**で、
最初の質感確認に向いている。

## 5. 非目標

- `attack` のプレイヤー対応。`attack` はモンスター戦闘のままにする
- 戦闘バランス・命中判定・クールダウン (シナリオが `preconditions` と
  `RECORD_PLAYER_STATE_TICK` で表現する)
- 陣営・勝敗判定 (集計述語の別 doc)
- 会議・投票
- `TARGET_PLAYER_STATE_IS` 以外の対象側条件
- 回復系 effect の新設 (`InteractionEffectType` に HP 回復が無いことは確認済み)

## 6. 実装順 — 経路ごとに縦に切る

初版の「宣言 → 適用 → 観測」という横割りは、PR 2 が 3 つの独立した機構の改修に
なって 200〜400 行の規約を確実に超える。**経路ごとに縦に切り、各 PR が対人行為を
1 つずつ動かせる形にする。**

| PR | 内容 | 動くもの |
|---|---|---|
| 1 | `EffectTarget` + `InteractionEffect.target` + loader の厳格パース + **actor 不在の 3 呼び出し元すべてで `TARGET_PLAYER` を弾く** | なし (極小) |
| 2 | `act_on_player` + 同スポット解決 + 失敗語彙 + `TARGET_PLAYER_STATE_IS` + **経路 2.2 のみ** | 口封じ・印を刻む。**対象 aggregate を渡すだけで済む唯一の経路**なので、ツールから保存・観測までの縦の配線を最小コストで通せる |
| 3 | 経路 2.1 のうち `TELEPORT_ENTITY` (target) | 突き落とす・射出する |
| 4 | 経路 2.1 のうち damage / status / need + **対象の `PlayerDownedEvent` 回収** | **殺害・毒・手当て** |
| 5 | 経路 2.1 のうちアイテム + 対象 `REMOVE_ITEM` の soft fail | 盗み |
| 6 | `notify_target` + 新 event + formatter + `is_down` 例外 | 秘匿対人行為の当事者通知 |
| 7 | 観測 event への target field 追加 + prose の `{target}` 展開 | 「A が B を〜した」 |
| 8 | 質感確認シナリオ | 密室・役割ゲート・秘匿の 3 点 |

PR 1 は振る舞いの変化がゼロである。「各 PR は単独で動く」を満たしていないが、
loader ガードで中途半端な宣言を起動時に弾くことで、少なくとも**静かに壊れた
状態にはならない**。

PR 7 は formatter だけの作業ではない。`SpotObjectInteractedEvent` 自体に対象を
運ぶ field が無いので **event schema の変更を含む**。

## 7. 見落としやすい罠 (実装時のチェックリスト)

### H-1. 対象の `PlayerDownedEvent` を回収する — キル経路の最大の罠

`apply_damage` で HP 0 になると aggregate が `PlayerDownedEvent` を内部に積み、
これを `publish_all` に流さないと `PlayerDownedOutcomeHandler` が走らず
**DEAD outcome が確定しない**。さらに save→clear の順序を誤ると陳腐化イベントが
後の `find` で再放出される。

現在このドレイン処理は**行為者の status についてしか書かれていない**。対象にも
同じ「publisher ガード内で clear してから save」が要る。PR 4 の受け入れ条件に
**「対象を殺したとき DEAD outcome が確定する」を明示テスト**として入れる。

### H-2. 同一プレイヤーの aggregate が二重に生きる

app 層は `acting_player_status` を読んだ後、damage 用に**別インスタンスとして
引き直している**。行為者 = 対象になった瞬間に同じ player の copy が複数生き、
後勝ちで state が消える。

item 側には防御が 2 段入っている (domain 側の `is` 同一性チェックと、app 側の
値等価チェック)。**player 側にも同じ 2 段が要る。** §3.9 の「自分自身は失敗」を
ツール層だけで守ると item と同じ抜け方をする。

### H-3. 盗みは soft fail 経路を作らないと書けない

`REMOVE_ITEM` の消費失敗は `ApplicationException` を raise する。「precondition で
count を確認している前提なので、ここで失敗するのは何かが致命的に壊れている
状態」という設計だが、対象側の所持を確認する条件が無い (§3.6 では
`TARGET_PLAYER_STATE_IS` しか足さない)。**空のポケットを狙った瞬間に例外が
飛ぶ。** PR 5 で対象側 `REMOVE_ITEM` の soft fail を作るまで、盗みは書けない。

### H-4. 死体を狙えるのか決める

設計判断 #2 に「dead player に対するアクションは全部 silent にする」とある。
Among Us は死体がその場に残り発見されることが核なので、「狙えないが見える」を
両立させる必要がある。`TARGET_IS_DOWN` / `TARGET_IS_DEAD` の失敗語彙を用意し、
**死体から盗めるかを明示的に決める**。決めないと silent 規則に飲まれて静かに
何も起きない。

### H-5. 同スポット判定の情報源を揃える

`presence_at(spot_id).present_entity_ids` と `give_item` の resolver、どちらを
使うか決める。別々だと説明不能な差が出る。

## 8. 検証の的

v1 (PR 1〜8) 完了時点で、Among Us の残りが **陣営の勝敗** と **会議・投票** だけに
なっているかで測る。§3.6 で対象側条件を v1 に引き上げたのは、これを成立させる
ためである。

## 関連

- [goal_per_player_objective_design.md](./goal_per_player_objective_design.md) — 目的層 G6
- [../design_decisions.md](../design_decisions.md) — #1 プレフィックスキャッシュ不変、#2 取れる手段の質、#31 テレポートの秘匿性、#32 環境変化の部分更新
- [../agent_design_principles.md](../agent_design_principles.md) — 静かな失敗の回避、他者からの可視性
