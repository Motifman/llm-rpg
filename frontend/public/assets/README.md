# Frontend Asset Rules

## 1. 目的

このディレクトリは、Web viewer / 将来のゲーム UI で使用する 2D アセットの正本置き場とする。

この文書では以下を固定する。

- 置き場所
- 命名規則
- 画像サイズと基準
- spritesheet 規約
- animation catalog 規約
- Tiled 用 tileset / map との対応
- こちらで先に用意すべき素材


## 2. 現時点の前提

- ゲームは 2D 見下ろし RPG 風
- タイル座標は backend / game logic の正本
- frontend は tile 単位の論理位置を補間して描画する
- マップは Tiled JSON
- フロントは React + Phaser
- スポットごとに scene が分かれる


## 3. 推奨方針

おすすめ:

- タイルサイズは `32x32`
- キャラクターの 1 フレームは `32x48`
- 透過 PNG
- 4 方向歩行
- 3 コマ歩行 + 1 コマ静止
- 背景やオブジェクトも pixel-art 寄りで統一

理由:

- 現在の viewer 実装と相性が良い
- Tiled / Phaser で扱いやすい
- 見下ろし RPG らしく見せやすい
- 無料アセットや生成アセットの流用がしやすい


## 4. ディレクトリ構成

```text
frontend/public/assets/
  README.md
  actors/
    players/
    npcs/
  monsters/
  tilesets/
  objects/
  weather/
  ui/
  catalogs/
```

補足:

- `actors/players/`: 手動プレイヤーや LLM プレイヤー
- `actors/npcs/`: 商人、門番、村人など
- `monsters/`: 非戦闘モンスター、巡回モンスター
- `tilesets/`: 地面、壁、建物、装飾
- `objects/`: 宝箱、看板、樽、採取ポイントなど
- `weather/`: 雨、霧、雪の overlay 素材
- `ui/`: パネル、アイコン、カーソル、ボタン
- `catalogs/`: asset catalog / animation catalog JSON


## 5. 命名規則

ファイル名は ASCII / snake_case を使う。

例:

- `hero_knight_blue.png`
- `npc_guard_town_a.png`
- `monster_slime_green.png`
- `tileset_starter_town_ground.png`
- `object_wooden_sign_a.png`
- `weather_rain_light.png`

sprite key は backend / frontend をまたいで共通で使う。

例:

- `player_default`
- `player_hero_knight_blue`
- `npc_guard_town_a`
- `monster_slime_green`
- `object_sign_wood_a`


## 6. キャラクター規約

### 6.1 フレームサイズ

推奨:

- フレームサイズ: `32x48`
- 足元の接地点: フレーム下端中央
- 原点: 足元中央を基準

理由:

- `32x32` タイル上で頭が少し上にはみ出し、RPG らしく見える
- 奥行き感が出しやすい

### 6.2 向き

最低限必要:

- `down`
- `left`
- `right`
- `up`

### 6.3 アニメーション

最低限必要:

- `idle_down`
- `idle_left`
- `idle_right`
- `idle_up`
- `walk_down`
- `walk_left`
- `walk_right`
- `walk_up`

推奨歩行フレーム数:

- 1 方向につき `3` コマ

推奨 idle:

- 1 コマ

### 6.4 配置ルール

- trim しない
- すべて同じフレームサイズでそろえる
- 背景は完全透過
- 影は spritesheet 側に焼き込まない

影は frontend 側の描画で足元に出す。


## 7. Monster 規約

最初は戦闘なしなので、必要なのは次だけでよい。

- `idle`
- `walk`
- 向きがあるなら 4 方向、なければ 1 方向でも可

推奨:

- スライム系は 1 方向でも可
- 獣系や humanoid 系は 4 方向


## 8. Object 規約

インタラクション可能オブジェクトは spritesheet ではなく単体 PNG でもよい。

最初に用意したいもの:

- 看板
- 宝箱
- 樽
- 草むら
- 鉱石 or 採取ポイント
- ゲート風オブジェクト

必要なら状態差分を別画像で持つ。

例:

- `object_chest_closed.png`
- `object_chest_open.png`


## 9. Tileset 規約

### 9.1 タイルサイズ

固定:

- `32x32`

### 9.2 最初に欲しいタイル種

Starter Town 向けの最小構成として以下を推奨する。

- 草
- 土
- 石畳
- 木床
- 壁
- 屋根
- 水
- 柵
- 花壇
- 門

### 9.3 レイヤー

Tiled では最低限以下を使う。

- `ground`
- `decoration`
- `collision`
- `gateways`
- `areas`

必要なら追加:

- `above_player`
- `shadows`
- `spawn_points`


## 10. Weather 規約

weather は最初は frontend overlay だけでもよい。

必要なキー:

- `clear`
- `rain_light`
- `rain_heavy`
- `fog_light`

最初の素材は画像でも良いが、できれば code-driven overlay を優先する。

理由:

- 色味や強度を後で調整しやすい
- 量産しやすい


## 11. Animation Catalog 規約

`frontend/public/assets/catalogs/animation_catalog.json` を作り、以下の形にそろえる。

```json
{
  "player_default": {
    "image": "/assets/actors/players/player_default.png",
    "frame_width": 32,
    "frame_height": 48,
    "anchor": { "x": 0.5, "y": 0.9 },
    "animations": {
      "idle_down": { "frames": [0], "frame_rate": 1, "repeat": -1 },
      "walk_down": { "frames": [0, 1, 2], "frame_rate": 8, "repeat": -1 },
      "idle_left": { "frames": [3], "frame_rate": 1, "repeat": -1 },
      "walk_left": { "frames": [3, 4, 5], "frame_rate": 8, "repeat": -1 },
      "idle_right": { "frames": [6], "frame_rate": 1, "repeat": -1 },
      "walk_right": { "frames": [6, 7, 8], "frame_rate": 8, "repeat": -1 },
      "idle_up": { "frames": [9], "frame_rate": 1, "repeat": -1 },
      "walk_up": { "frames": [9, 10, 11], "frame_rate": 8, "repeat": -1 }
    }
  }
}
```

ルール:

- backend は `sprite_key` だけを返す
- frontend は `sprite_key` から catalog を引く
- image path は public 配下の絶対パスにする


## 12. Asset Catalog 規約

animation を持たない object / weather / UI も含めて、別 catalog を用意してよい。

例:

```json
{
  "objects": {
    "object_sign_wood_a": {
      "image": "/assets/objects/object_sign_wood_a.png",
      "width": 32,
      "height": 32
    }
  },
  "weather": {
    "rain_light": {
      "mode": "shader_or_overlay",
      "tint": "#89a6c8",
      "alpha": 0.14
    }
  }
}
```


## 13. こちらで先に用意するべきもの

優先順は次の通り。

### 13.1 Hero

最優先:

- `player_default` 置き換え用 spritesheet 1 枚
- 4 方向
- idle + walk

### 13.2 Starter Town の tileset

次点:

- 草
- 石畳
- 建物外壁
- 屋根
- 柵
- 門
- 看板

### 13.3 NPC

最低限:

- 門番
- 村人
- 商人

### 13.4 モンスター

戦闘抜きで最初に置くなら:

- スライム
- 小動物 or 狼

### 13.5 オブジェクト

- 看板
- 宝箱
- 樽
- 採取ポイント


## 14. Starter Town 向けのおすすめ

画作りのおすすめ:

- 地面は草 + 石畳
- 建物は 2 軒程度
- 門を 1 つ
- 看板と樽で生活感を出す
- 雨演出が映える配色にする

最初の 1 スポットで十分見栄えする構成:

- 中央広場
- 宿屋前
- 南門
- 看板
- 門番 NPC
- スライム 1 種


## 15. 受け入れ基準

Phase 10 着手前のアセット受け入れ基準:

- `player_default` を実 spritesheet に差し替え可能
- 1 つの spot 用 tileset がそろっている
- object を最低 3 種置ける
- Tiled 上で破綻なく配置できる
- 背景透過、サイズ、命名規則が統一されている


## 16. 今後の実装順

おすすめ:

1. `player_default` を本物の spritesheet に置き換える
2. animation catalog を実装する
3. Starter Town の tileset を入れる
4. object / NPC / monster を順に追加する
5. UI をゲームらしく再設計する


## 17. 未確定項目

現時点では以下を推奨として仮置きしている。

- キャラのフレームサイズ: `32x48`
- タイルサイズ: `32x32`
- 画風: pixel-art 寄りの見下ろし RPG

もし変更するなら、Phase 10 に入る前にここを更新する。
