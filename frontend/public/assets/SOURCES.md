# Asset Sources

このディレクトリに配置した素材の出典とライセンスを記録する。

## 1. Character

### `player_default.png`

- 配置先: `/assets/actors/players/player_default.png`
- 元ファイル: `/assets/sources/actors/player_41_cc0.png`
- 出典: OpenGameArt
- URL: `https://opengameart.org/content/player-character-free-sprite`
- 直接取得元: `https://opengameart.org/sites/default/files/player_41.png`
- ライセンス: CC0
- 備考:
  - 画像サイズは `160x192`
  - 現状の規約どおり `32x48` フレームとして扱える
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

## 3. 運用ルール

- 外部素材を追加したら必ずこのファイルに追記する
- ライセンス URL と直接取得元 URL を両方残す
- `sources/` 配下には原本を残す
- 実際にゲームで使うファイルは `actors/`, `tilesets/`, `objects/` などへコピーまたは整理して置く
