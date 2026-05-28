# 漂流島サバイバル ―― 14日後の救助

長期サバイバルシナリオのデモ。22スポット × 3エージェント × 動的環境(天候/潮汐) で構築した
Phase 1 MVP。階層計画・長期記憶・協力・動的環境の4軸を同時に検証する。

## 実行

```bash
cd <repo_root>
python3 -m demos.survival_island.run_survival_island
```

LLM は呼ばずに、シナリオロードと happy path をスクリプトで動かしてプロンプト構築と
状態遷移を可視化するスモークテスト。本番運用には別途 LLM ランナーを書く。

## シナリオ概要

- **島の構造**: 浜辺ゾーン(5) / 森ゾーン(6) / 淡水・丘陵ゾーン(4) / 山岳ゾーン(5) / 特殊(2)
- **エージェント**: ミラ(隊長) / レン(偵察) / トマ(工作) ― 全員 難破船の浜から開始
- **勝利**: 山頂で狼煙を上げ、3人揃って救助船を待つ (tick 100 か 125 のチェックポイントで救助来訪)
- **敗北**: 140 tick 以内に救助されない
- **動的環境**:
  - 嵐 (STORM) ― 岩礁海岸と崖の見張り台への接続を封鎖
  - 満潮 (FLAG: `high_tide`) ― 洞窟内部への通路を封鎖
  - 干潮 (tick 85) ― 通れるようになる

## Phase 1 で活用した既存primitive

| 機能 | 使用例 |
|---|---|
| `GIVE_ITEM` / `REMOVE_ITEM` | 採取・拾得・消費 |
| `CHANGE_OBJECT_STATE` / `RECORD_OBJECT_STATE_TICK` | 採取後のクールダウン |
| `reactive_bindings.objects` + `OBJECT_STATE_TICK_AT_LEAST` | 12箇所の自動再生 |
| `reactive_bindings.passages` + `WEATHER_IS` / `FLAG_SET` | 嵐と満潮で通路封鎖 |
| `scenario_events` + `TICK_AT_LEAST` | 嵐の到来・潮汐の切替 |
| `PLAYER_AT_SPOT` / `FLAG_SET` (event condition) | 救助到達判定 |
| `HAS_ITEM` precondition | 焚き火・狼煙の燃料チェック |
| 階層型インタラクション (object → action → effects) | 焚き火台での build_fire と cook_fish |

## Phase 1 で判明したギャップ (= Phase 2 の作業候補)

### 🔴 [重大] 協力プリミティブの不足

**現象**: ミラが流木を、トマが火打ち石と枯れ葉を持っているが、**焚き火を起こすには3つを
同一人物が持つ必要がある**。アイテム受け渡し手段がなく、speech_speak で口頭依頼するしか
ない (=合意できてもアイテムは動かない)。

**影響**: 「協力」の本質的部分が成立しない。Phase 1 シナリオは「全アイテムを1人が集める」
シングルプレイ近似でしかクリアできない。

**提案**: `give_item` / `drop_item` / `pickup_item` ツールを追加。インベントリ間移動と
スポット内アイテム置きを両方サポート。Effect として `TRANSFER_ITEM` (target_player or
target_spot) を作っても良い。

### 🔴 [重大] Visibility / Witness の不在

**現象**: 観測ログに「ミラが**何かを**操作した」「**何かの**available が変わった」と出る。
これは現状の観測パイプラインが「同一スポット内のプレイヤーには行動者と対象がぼかされる」
仕様 (Issue #別件で扱われている可能性) で、つまり**witnessing は粗いが存在する**。

しかし以下は表現できない:
- 同室者が見ているのに「何かを操作した」止まりで、対象オブジェクト名が出ない (=witness 詳細度が一律)
- スポットを離れた後に「何が起きたか痕跡を見つける」ができない (`evidence`概念がない)
- 「意図的な隠蔽」(同室者がいないタイミングで盗む) と「公然の行為」が区別できない

**提案**: ActionResult に `witness_policy` と `evidence` を導入。
- `witness_policy`: `EVERYONE_IN_SPOT` / `ACTOR_ONLY` / `EXPLICIT_TARGETS`
- `evidence`: 行為後にspotオブジェクトに残る痕跡。後発見可能

### 🟡 [中] Hunger / Fatigue の自動進行が無い

**現象**: 20 tick 経過後も全員の空腹/疲労が 0/100 のまま。`AgentNeeds` ドメインは存在
するが、scenario event で明示的に `CHANGE_PLAYER_STATE` するか、heartbeat に乗せるかが
必要。

**提案**: シナリオ側の設定で `needs_autoincrement` を宣言できるようにする。
```json
"environment": {
  "needs": {
    "hunger": {"increment_per_tick": 0.5, "damage_threshold": 80},
    "fatigue": {"increment_per_tick": 0.3, "damage_threshold": 90}
  }
}
```
runtime が tick advance 時に自動で increase_need を呼ぶ。これは小さく、汎用性は高い。

### 🟡 [中] 確率的トリガが無い

**現象**: 全ての scenario_event が `TICK_AT_LEAST` で決定論的。「20%の確率で岩崩れ」
「沖で釣ると10%でサメに襲われる」が書けない。

**提案**: 新しい condition_type `PROBABILITY` (parameters: chance=0.1) と
`ON_TICK_RANDOM` トリガ (各tickで条件評価) を追加。
Effect 側に `WITH_PROBABILITY(p, effect)` を入れても良い。

### 🟡 [中] `FLAG_NOT_SET` がインタラクション precondition で使えない

**現象**: `InteractionConditionTypeEnum` に `FLAG_NOT_SET` が無い (scenario_event 側には
ある)。MVP では「満潮時に貝採集を禁止」が表現できず、precondition を外した。

**提案**: 既存 `FLAG_SET` の隣に `FLAG_NOT_SET` を追加。あるいは `NOT(FLAG_SET)` をネスト
可能にする (実装はやや大きい)。

### 🟢 [低] `RECORD_OBJECT_STATE_TICK` の警告

**現象**: 実行時に `RECORD_OBJECT_STATE_TICK: caller did not provide current_tick;
skipping write to state['last_harvest_tick']` が出る。実際の再生は動いているので致命的
ではないが、メッセージが示唆する通り内部で tick が渡らないパスがある。

**提案**: 別件 (issue) で原因調査。MVP の挙動には影響なし。

### 🟢 [低] 天候のランダム遷移

**現象**: `environment.weather.enabled: true` で `update_interval_ticks: 25` を設定したが、
ロード時に "WEATHER_TRANSITIONS が定義されてないので変化しない" 趣旨の警告が出る (推測)。
明示的な遷移確率表が必要そう。

**提案**: 天候モデルが既に存在するなら、scenario JSON に
`weather.transitions: [{from: CLEAR, to: STORM, chance: 0.2}, ...]` を書けるようにする。

## Phase 2 ロードマップ (推奨順序)

1. **協力プリミティブ** (give/drop/pickup) ― 既存シナリオの「3人協力で焚き火」が成立する
2. **Hunger 自動進行** ― 「食わないと死ぬ」が動き、シナリオに本物の時間圧が生まれる
3. **Visibility/Witness 最小版** (`witness_policy: ACTOR_ONLY` 1 種類だけでも) ―
   「こっそり盗む」が成立する
4. **確率トリガ + 天候ランダム遷移** ― 動的環境の不確実性が出る
5. **Evidence (痕跡)** ― 「Aliceが箱を開けた跡」が後で発見できる、推理が成立
6. **`FLAG_NOT_SET` 等の precondition 拡充** ― 軽い

## ファイル

- `data/scenarios/survival_island.json` ― シナリオ定義 (22 spot / 17 item / 5 event / 15 binding)
- `demos/survival_island/run_survival_island.py` ― ロード確認 + happy path スモークテスト
- 既存 `demos/escape_game/escape_game_runtime.py` をそのまま使用 (シナリオ非依存)
