# Asset Sources

このディレクトリに配置した素材の出典とライセンスを記録する。

## 1. Character

### `player_default.png`

- 配置先: `/assets/actors/players/player_default.png`
- 元ファイル: `/assets/sources/actors/base_32x48_cc0.png`
- 出典: OpenGameArt
- URL: `https://opengameart.org/content/simple-32x48-base-sprite`
- 直接取得元: `https://opengameart.org/sites/default/files/Base.png`
- ライセンス: CC0
- 備考:
  - 画像サイズは `96x192`
  - 現在は `32x48` の 3 コマ歩行 spritesheet として扱っている
  - Phase 10 で `player_default` の最初の差し替え候補として使用する

## 2. Tileset

### `sbs_tiny_top_down_pack`

- 配置先: `/assets/tilesets/sbs_tiny_top_down_pack/`
- 元ファイル: `/assets/sources/tilesets/sbs_tiny_top_down_pack_cc0.zip`
- 出典: OpenGameArt
- URL: `https://opengameart.org/content/tiny-top-down-pack`
- 直接取得元: `https://opengameart.org/sites/default/files/sbs_-_tiny_top_down_pack.zip`
- ライセンス: CC0 / Public Domain
- ライセンス本文: `/assets/tilesets/sbs_tiny_top_down_pack/License.txt`
- 内容:
  - `Tiny Top Down 32x32.png`
  - `Tiled Tsx/Tiny Top Down Tiles 32x32.tsx`
  - `Example.tmx`
- 備考:
  - タイルは `32x32`
  - プロトタイプ用の Starter Town / dungeon / gate 周辺の試作に使いやすい

## 3. Monster

### `blob_move.png`

- 配置先: `/assets/monsters/blob_move.png`
- 元ファイル: `/assets/sources/monsters/blob_move_cc0.png`
- 出典: OpenGameArt
- URL: `https://opengameart.org/content/blobs`
- 直接取得元: `https://opengameart.org/sites/default/files/blob%20move.png`
- ライセンス: CC0
- 備考:
  - 画像サイズは `640x80`
  - 現在は `80x80` の 8 フレーム歩行アニメーションとして扱っている
  - Phase 10 の仮モンスター表示候補

## 4. Object

### `object_chest_closed.png`

- 配置先: `/assets/objects/object_chest_closed.png`
- 元ファイル: `/assets/sources/objects/chest_topdown_cc0.png`
- 出典: OpenGameArt
- URL: `https://opengameart.org/content/chest-2`
- 直接取得元: `https://opengameart.org/sites/default/files/chest_2.png`
- ライセンス: CC0
- 備考:
  - 画像サイズは `64x64`
  - Starter Town の固定オブジェクト表示の試作用

## 5. UI

### `character-select-ui-atlas.png`

- 配置先: `/assets/ui/character-select-ui-atlas.png`
- 生成元: OpenAI imagegen built-in tool
- 用途: キャラクター選択画面のボタン、パネル、HUDフレーム向け質感オーバーレイ
- プロンプト要約:
  - 暗い和風ホラーRPG向けのUIテクスチャアトラス
  - 琥珀色の擦れた金属ボタン面、真鍮コーナーブラケット、暗いガラスパネル、走査線、微細なグリッチ片
  - 文字、ロゴ、キャラクター、背景シーンなし
- 備考:
  - CSSの `background-image` としてクロップせずに使用する
  - レイアウトやテキストはReact/CSS側で制御する

## 6. 運用ルール

- 外部素材を追加したら必ずこのファイルに追記する
- ライセンス URL と直接取得元 URL を両方残す
- `sources/` 配下には原本を残す
- 実際にゲームで使うファイルは `actors/`, `tilesets/`, `objects/` などへコピーまたは整理して置く
