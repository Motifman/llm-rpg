# エージェント連続性ロードマップ

> このディレクトリは、「AI エージェントをゲーム世界の中で連続的な存在にする」という
> 長期ビジョンに対し、漂流島サバイバルデモを駆動シナリオとしてどんな基盤を順番に
> 育てていくかを整理した運用ドキュメント群。
>
> **更新方針**: PR がマージされたら「完了済み」セクションに移し、Phase 1 で
> 新しく出てきたギャップは「未着手の TODO」に追記する。LLM 実験で判明した
> 知見も適宜記録。

---

## 1. 長期ビジョン

### 連続的存在とは

**「時間が経った後のエージェントが、本人と外から見て同じ存在として認識される」**
ことを目標にする。これは外から見れば一貫した人格・記憶・関係性が観測でき、
内から見れば過去の自分の判断と現在の判断が連続的につながっている状態を指す。

これを支えるのは大きく 3 層:

1. **記憶**: 経験を物語として保ち、現在の判断に滲ませる
2. **連続性のある世界**: エージェントが居なくても時間が進み、戻ってきた時に
   差分が観測できる (OS カーネル的に「時間がループし続ける中でタスクが
   割り込んでくる」イメージ)
3. **観測の非対称性 (witness)**: 「同じ世界に居て、それぞれが見たもの・聞いた
   ものだけを信じる」という現実世界的な制約。これがあって初めて「信頼」
   「裏切り」「秘密」が成立する

### 駆動シナリオ: 漂流島サバイバル

3 人が無人島に漂着し 14 日 (140 tick) 以内に救助される。詳細は
[demos/survival_island/README.md](../../demos/survival_island/README.md) 参照。

- 22 spot / 17 item / 5 event / 15 reactive binding
- 階層計画・長期記憶・協力・動的環境の 4 軸を同時に検証
- 「3 人協力で焚き火着火」が成立しないと進めない構造で**協力プリミティブの
  価値**が定量的に測れる
- 毒キノコ識別 (片方の player に偽情報を持たせる) が**裏切りシナリオの種**
  として組み込み済み

---

## 2. 完了済みの仕事

### 漂流島 Phase 1 MVP (PR #274)
- 22 spot のシナリオ JSON
- スモークランナー (`demos/survival_island/`)
- 既存 primitive (Effect / Trigger / reactive_bindings) だけで構築
- Phase 2 着手候補のギャップ報告

### Spot-graph 世界の drop / pickup ドメイン + アプリ (PR #277)
- タイルマップ時代の `world_drop_item` が**完全に死コード**であることを確認
- `SpotInterior.with_ground_item()` / `find_ground_item()` を追加
- `SpotGraphItemTransferService` を新設 (drop / pickup / list_ground_items)
- `EscapeGameRuntime.do_drop_item` / `do_pickup_item` を runtime に配線
- 島デモで 3 人協力の焚き火着火が機械的に成立することを確認

### Drop / pickup の LLM ツール公開 (PR #281)
- `spot_graph_drop_item` / `spot_graph_pickup_item` を tool catalog に追加
- 所持アイテム = `I1, I2...`、地面アイテム = `G1, G2...` ラベル
- LLM プロンプトに「地面に落ちているもの」セクションが出る
- argument resolver / executor / wiring 完備
- `ToolRuntimeTargetDto.real_item_instance_id` を新設し旧 use_item の慣習との
  整合を維持

### Drop / pickup の witness 最小実装 (PR #284)
- `PlayerDroppedItemEvent` / `PlayerPickedUpItemEvent` をドメイン定義
- `SpotGraphItemTransferService` から event 発火 (`event_publisher` 注入)
- `SpotGraphRecipientStrategy` で「同室・行為者除外」配信
- `SpotGraphObjectHandler` で「Xが流木を地面に置いた」prose 生成
- 別スポット player には届かない / 行為者本人には届かない を unit test で保証

---

## 3. 未着手の TODO (優先度順)

### 🔴 重大 (シナリオ進行に直結 / 体験を変える)

#### give: 同室の特定プレイヤーに直接渡す
- 現状の drop → pickup は経由が冗長。同室なら直接「Xに流木を渡す」が自然
- `spot_graph_give_item` ツール + `target_player_label` 解決
- transfer_service に `give_item(from_player, to_player, slot_id)` を追加
- 観測: 「ミラがトマに流木を渡した」(両者+第三者に届く)
- 規模: ~250 行

#### Hunger / Fatigue の自動進行
- `AgentNeeds` ドメインは既存。tick 毎の自動 increment が未配線
- シナリオ JSON で `environment.needs.{hunger,fatigue}.increment_per_tick` 設定
- 閾値 (80%) で「腹が鳴る」観測注入、100% で HP ダメージ
- これが入って初めて**「食わないと死ぬ」が回り、時間圧が出る**
- 規模: ~150 行 (runtime 側に NeedsAutoIncrementer ステージを追加)

#### Visibility / Witness の拡張 (`witness_policy`)
- 現状の同室観測は「同スポットなら全員に見える」一律ルール
- 拡張案:
  - `witness_policy: SAME_SPOT (現状) | EXPLICIT_TARGETS | ACTOR_ONLY`
  - `ACTOR_ONLY` → 「コソコソ落とす」「こっそり食う」が成立
  - `EXPLICIT_TARGETS` → 「Xに耳打ち」「Xだけに見せる」
- ActionResult / Event レベルで policy フィールドを追加
- 観測パイプラインの recipient resolution を policy 駆動に切り替え
- 規模: ~300 行 (基盤拡張)

### 🟡 中 (基盤として汎用性が高い)

#### 確率トリガ / ランダムハプニング
- 新 condition_type: `PROBABILITY` (chance=0.1 等)
- 新 trigger: `ON_TICK_RANDOM` (毎 tick 評価)
- 「20% の確率で岩崩れ」「沖で釣ると 10% でサメ」が書ける
- これが入ると動的環境の不確実性が出る
- 規模: ~200 行
- 関連: 天候のランダム遷移 (現状は scenario_events で固定 tick)

#### アイテム合成 (Craft) の実行ツール
- `RecipeAggregate` は domain に既存だが execute する path が無い
- 新サービス `CraftApplicationService` + `spot_graph_craft` ツール
- 「木の枝＋蔓→簡易釣竿」「魚＋火→焼き魚」が動く
- 既存の build_fire / cook_fish は interaction で書いてあるが、汎用 craft で
  シナリオ作家の手数を減らせる
- 規模: ~250 行

#### 罠 / 毒 / 遅延効果 (Effect の Triggered / Delayed)
- 現状の Effect は Immediate のみ
- 新 timing: `Triggered(condition)` `Delayed(ticks=N)`
- 罠: `spot に EnterSpot トリガで damage effect を仕掛ける`
- 毒: 「飲んだ tick から N tick 後に HP 減少」
- これと witness_policy: ACTOR_ONLY が組み合わさると**毒殺シナリオが成立**
- 規模: ~400 行 (Effect 抽象の格上げ)

#### Player-to-Player の攻撃 (PvP)
- 既存 `SpotAttackOrchestrator` はモンスター target のみ
- player target に拡張すれば直接攻撃が成立
- `spot_graph_attack_player` ツール
- アイテム強奪 (`steal`) も同じ拡張で可能
- 規模: ~200 行

### 🟢 低 (品質改善 / 痒い所)

#### `FLAG_NOT_SET` を InteractionConditionTypeEnum に追加
- 現状はある事象の「不在」を precondition で表せない
- Phase 1 で「満潮時の貝採集禁止」を諦めた経緯あり
- もしくは `NOT(FLAG_SET)` をネスト可能に
- 規模: ~30 行

#### `RECORD_OBJECT_STATE_TICK` の警告調査
- 「caller did not provide current_tick」が島デモで出続けている
- 再生は動くが内部で tick 未渡しのパスがある (silent failure 一歩手前)
- 規模: 調査 + 修正

#### 天候のランダム遷移
- 現状 `weather.update_interval_ticks` を設定しても transition table が無く
  実質変化しない
- `weather.transitions: [{from: CLEAR, to: STORM, chance: 0.2}, ...]` を載せる
- 確率トリガと組み合わせて使う
- 規模: ~100 行

#### Evidence (痕跡)
- witness_policy 拡張の続編
- 行為後に spot / object に残る「痕跡」値オブジェクト
- 「ミラが箱を開けた跡」を後から来た player が観測可能
- 「アリバイ」「目撃証言」が成立する
- 規模: ~250 行

---

## 4. シナリオ拡張アイデア (基盤が揃ってから着手)

### 漂流島 v2 (4人ペルソナ × 動的連合)
- 詳細: [`survival_v2_design.md`](./survival_v2_design.md)
- ペルソナ: エイダ (医師) / ノア (元自衛官) / リオ (建築技師) / カイ (留学生)
- 6 周期のライフサイクル + プレイヤー個別の勝敗判定
- Phase A〜E で順次実装。基盤先行

### 漂流島 v3 候補 (構想のみ)
- 救助船到達後に「島で起きたこと」を陸で証言するフェーズ
- 観測の食い違いから真相が見えてくる (記憶 × witness × evidence の総合演習)

### 商隊の道 (候補 A、未着手)
- 5〜7 街を巡る交易キャラバン、30 日 (30〜60 tick)
- 階層計画 (長期目標→中期戦略→短期行動) の最強テスト台
- 信頼/裏切りが**経済的に意味を持つ**
- shop / trade / world(weather) / conversation コンテキスト再利用

### ギルド連続クエスト (候補 C、未着手)
- 連続する依頼で NPC が再登場
- 「1 日目に助けた人が 3 日目にヒントをくれる」エピソード記憶の検証
- 既存 `quest` / `guild` 資産を活用

### 廃病院 拡張版 (候補 D、未着手)
- 既存 8 spot を 3 倍に拡張
- 「闇」が時間で広がり通路封鎖
- 1 回死んだ仲間が幽霊として情報を残す (記憶継承の演習)

### 間接妨害メニュー (witness_policy 完成後)

| 妨害手段 | 必要基盤 |
|---|---|
| 共有食料を密かに食う/隠す | inventory + witness_policy(ACTOR_ONLY) |
| メモ/地図に虚偽を書く | 書き込み可能アイテム |
| 道具を壊す/隠す | アイテム破壊 + ACTOR_ONLY |
| 水源/食料を汚染 (毒) | Delayed Effect + ACTOR_ONLY |
| 罠を設置 | Triggered Effect |
| モンスター誘導 | モンスター AI に「誘引」概念 |
| 通路を塞ぐ | 既存 passage 操作 + ACTOR_ONLY |
| SNS 的な噂で評判操作 | 既存 sns + 島と接続 |
| 眠っている間に荷物を漁る | ステルス状態 + ACTOR_ONLY |

---

## 5. 並走する大きなテーマ

これらは本ロードマップとは半独立に進むが、最終的に統合される。

### Memory システム
- `docs/memory_system/` 配下で別管理
- エピソード → 意味記憶への昇格
- リフレクション (recall on cue)
- 連続性の本丸

### MCP Bridge (cross-instance interaction)
- 別プロセス / 別世界のエージェントとの相互作用
- 過去のセッション要約で議論された (filesystem MCP / hardcode で spike 予定)
- 「Slack の alice と裏切られたゲーム世界の alice が同一視されない」設計
- スレッドモデル (タスク割り込み) も同テーマ

### 観測 trace / リプレイ
- PR #278 で trace に observation を記録
- 後追いでセッションを再現する基盤
- ABテスト・LLM 比較実験の前提

---

## 6. 進捗管理のルール

### PR のサイズ
- CLAUDE.md の方針通り、1 PR = 1 目的、~200〜400 行を目安
- それ以上になる場合は **必ず分割の検討** をする
- 「ドメイン → アプリ → 配線 → 観測」のような自然な層単位で割ると分割しやすい

### Worktree の使い方
- 大型シナリオ作業 (本ロードマップ全般) は `llm-rpg-wt-survival-island` で進行中
- main を頻繁に取り込み、衝突を最小化
- マージされたら最新 main で次の作業ブランチを切り直す

### ドキュメントの場所
- 本ロードマップ: 全体俯瞰
- `demos/survival_island/README.md`: シナリオ単位の Phase 1 ギャップ報告
- `docs/memory_system/`: 記憶系の別線
- `docs/game/DESIGN.md`: 元設計

新しい未着手 TODO が発見されたら本ファイルに追記。完了したら「完了済み」に
昇格 + PR 番号を残す。

---

## 7. 「とりあえず次に何をやるか」の判断指針

完了済みの drop/pickup/witness の上で、シナリオの体験を一段引き上げるなら:

1. **give ツール** (~250 行): 同室なら drop → pickup より自然。即効性高い
2. **Hunger 自動進行** (~150 行): 14 日生き延びる圧が初めて出る
3. **witness_policy: ACTOR_ONLY** (~300 行): 裏切りの本丸

基盤として汎用性を取るなら:

1. **確率トリガ** (~200 行): 天候・ハプニング・モンスター遭遇全てに効く
2. **Delayed / Triggered Effect** (~400 行): 罠・毒・呪い・契約罰すべての土台
3. **Visibility/Witness 拡張** (~300 行): witness の汎用基盤

**両方ほしいなら**: give → Hunger → 確率トリガ → witness_policy → Delayed Effect
の順で進めるとシナリオ体験と基盤拡張のバランスが取りやすい。

LLM 実験で得られる発見によって順序は変わるので、まず**今動くもので実モデルを
走らせる** (PR #284 までを通したセッションで survival_island を 1 度回す) のが
直近の最短手。
