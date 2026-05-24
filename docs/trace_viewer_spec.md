# 専用 Trace Viewer 仕様

## 背景と動機

Issue #205 第11回実験で生成した trace を [PR #211 の gist publish] 経由で共有しようとしたところ、以下の問題が判明:

1. **htmlpreview.github.io が Mermaid CDN をブロック** — シーケンス図がページ上で描画されない
   - mermaid.live に手でコピペすれば見えるが、共有ハードルが高い
2. **シーケンス図そのものが読みにくい** — 30 tick × 2 player × 平均 2 event/tick = 100+ メッセージで圧倒される
3. **空間移動が見えない** — どのスポットからどのスポットに動いたかが分からない (現状の sequence 図には `travel_to` ツール名しか出ない)

研究上知りたいのは「**いつ・どこで・誰が・何をして・何が起きたか**」だが、現状の Mermaid 図は時系列の一部しか伝えていない。

## ゴール

> trace を開いて再生ボタンを押すと、世界の地図上でカイト/リンが時間とともに動き、各 tick で起きたイベント (action / observation / memo) がタイムラインに流れる viewer を作る。

## 非ゴール

- ゲームのリアルタイム監視 (web フロントエンドの既存 Phaser/React 系がカバー)
- 編集 / 介入 (read-only な可視化に絞る)
- スマホ最適化 (デスクトップ前提)

## 必須要件

| # | 要件 | 根拠 |
|---|---|---|
| R1 | **外部 CDN ゼロ**で動く self-contained HTML | htmlpreview.github.io でも見える / オフラインでも見える |
| R2 | gist で共有可能 (~1MB 以内、できれば 500KB) | 既存の `publish_experiment_gist.py` フロー再利用 |
| R3 | 任意のシナリオで動く (relay_puzzle 専用ではない) | 第12回以降の長尺シナリオでも使える |
| R4 | 地図上のプレイヤー位置をアニメーション再生できる | ユーザー要望 |
| R5 | 現在 tick で起きた event 一覧を表示 | タイムライン |
| R6 | 任意の tick にシーク (jump / scrub) できる | デバッグ用 |
| R7 | memo 状態を現在 tick で表示 | memo system の効果検証用 |

## 入力データ

| ファイル | 既存 | 役割 |
|---|---|---|
| `trace.jsonl` | ✅ | 全 event の時系列 |
| `scenario.json` | ✅ (gist 同梱) | spot graph topology + 初期配置 |

### データ拡張が必要な点

現状の trace に**プレイヤーの spot 位置の時系列が直接含まれていない**。`observation` payload に位置情報があるが、抽出ロジックが脆い。

→ **trace schema に `position_change` event を追加** (PR α で対応):

```json
{
  "kind": "position_change",
  "tick": 5,
  "player_id": 1,
  "payload": {
    "from_spot_id": "control_room",
    "to_spot_id": "corridor",
    "spot_name": "廊下"
  }
}
```

emit 元: `EscapeGameRuntime` の `advance_tick` 後フック (各プレイヤーの現位置を前 tick と比較して差分を出す)。

## 画面レイアウト

```
┌────────────────────────────────────────────────────────────────┐
│ relay_puzzle / 第11回 R1 / WIN tick=25 / 31 actions             │
├────────────────────────────────────────────────────────────────┤
│  ⏮ ⏯ ▶ ⏭   [====●================]  tick 10/25   速度 1x ▼      │
├──────────────────────────────────┬─────────────────────────────┤
│                                  │ 現在 tick のイベント         │
│       ┌───────┐                  │ • t10 カイト: press          │
│       │ 制御室 │ 🟦 カイト          │   ─ power_on=true            │
│       └───┬───┘                  │ • t10 リン: travel_to vault  │
│           │                      │   ─ 移動完了                  │
│       ┌───┴───┐                  ├─────────────────────────────┤
│       │ 廊下  │                  │ active memo                  │
│       └───┬───┘                  │ ▸ カイト「制御室に残る」(+8) │
│           │                      │ ▸ リン「扉固定する」(+5)     │
│       ┌───┴───┐                  ├─────────────────────────────┤
│       │ 金庫室 │ 🟧 リン           │ event ヒート (tick × kind)   │
│       └───────┘                  │ obs ▁▁▂▂▁▁▃▂▁▃▁           │
│                                  │ act ▁▂▁▁▃▃▁▂▂▁▁           │
│                                  │ memo ▁▁▂▁▁▁▁▁▁▁▁          │
└──────────────────────────────────┴─────────────────────────────┘
```

### 構成要素

| 領域 | 内容 |
|---|---|
| **header** | scenario 名 / outcome / total ticks / 総 action 数 |
| **playback bar** | 再生 ⏯ / 前後 ⏮⏭ / scrub slider / 速度 (0.5x/1x/2x/4x) |
| **map** | SVG。spot を node (円 or 矩形)、connection を edge。プレイヤーは色分けされた dot + ラベル |
| **event log** | 現在 tick の event を時系列で。kind 別アイコン (action/observation/memo) |
| **memo panel** | 現在 tick で active な memo + 経過 tick + `[STALE]` 表示 |
| **heatmap** | 簡易 sparkline で全 tick の event 分布 (obs/act/memo 別) |

## 機能仕様

### F1. Playback

- 既定状態: tick=0 で一時停止
- ▶ で再生開始、1 tick = 500ms (1x 速度)
- 速度切替: 0.5x / 1x / 2x / 4x → 250ms / 500ms / 1000ms / 2000ms per tick
- 再生中も scrub 可能 (drag で任意位置に飛ぶ)
- 矢印キー: ← / → で 1 tick 戻る / 進める、Space で play/pause

### F2. Map 描画

- spot graph topology は scenario.json の `spot_graph.spots` / `spot_graph.connections` から取得
- レイアウトアルゴリズム: **シンプル force-directed (~50 行)** か事前計算座標
  - 第一版: 各 spot に手動座標 (or scenario.json に optional `view_coord` field) 推奨
  - 第二版: force-directed 自動配置
- プレイヤーは spot の中心 + オフセット (複数プレイヤーが同 spot にいるとき重ならないように)
- 位置変化は SVG `transform: translate()` の CSS transition で滑らかにアニメーション (300ms ease)

### F3. Event Log

- 現在 tick で発生した event を時系列で表示
- kind 別アイコン: 👁 obs / ⚡ action / 📝 memo_add / ✅ memo_done / 💡 memo_hint / ❌ action_failed
- action_result は対応する action にネストして表示 (`└ result_summary`)
- 表示件数が多い時は折りたたみ

### F4. Memo State Panel

- 現在 tick 時点での active memo 一覧
- 各 memo に `[STALE]` フラグ (>=20 tick 経過なら) と経過 tick を表示
- 完了した memo は薄くグレーアウトして「t=X で完了」付き

### F5. Heatmap (簡易)

- 横軸 tick、縦軸 kind (obs/act/memo) の sparkline
- 現在 tick 位置を vertical line で示す

## 技術スタック

### 採用

- **Cytoscape.js (inline 埋め込み)** — グラフ描画 + 自動レイアウト + interaction
- **vanilla JavaScript (ES2020+)** — それ以外の UI ロジック
- **CSS Grid / Flexbox** — layout

### Cytoscape.js を採用する理由

| 項目 | vanilla SVG 自作 | Cytoscape.js inline |
|---|---|---|
| 自前コード量 | ~700 行 (layout / pan/zoom / drag / animation) | ~200 行 (設定 + イベント) |
| 描画品質 | 標準的 | 綺麗 (force-directed / dagre 等の優れたレイアウト) |
| pan / zoom / drag | 全自作 | built-in |
| アニメーション API | 自作 (CSS transition) | built-in (`ele.animate()`) |
| HTML サイズ | ~50KB | ~500KB (Cytoscape min ~400KB を inline) |
| 外部 CDN 依存 | なし | **なし (inline 埋め込み)** |

**inline 埋め込みで htmlpreview 互換を確保**しつつ、自前 700 行を削れるのが大きい。gist の 1 ファイル上限は 10MB なので 500KB は全然余裕。

### 不採用とその理由

| 候補 | 不採用理由 |
|---|---|
| **Cytoscape.js (CDN 経由)** | htmlpreview の CSP/CORS で同じ問題に当たる可能性。**inline ならOK** |
| D3 / vis.js | 学習コストが高い割に Cytoscape より得が少ない |
| React / Vue | build step が増える / 学習コスト |
| Phaser (既存) | runtime 表示用に重い / build 統合が複雑 |
| Mermaid | 空間表現できない (PR #212 で sequence 図のバグは修正したが用途が違う) |

### Cytoscape プラグインの選択

第一版で使うもの:
- `cytoscape-dagre` (directed graph layout) — spot graph が階層的なら有用
- `cytoscape-cose-bilkent` (force-directed) — 任意トポロジで綺麗

第一版は `dagre` で十分。シナリオによっては `cose-bilkent` に切り替え。プラグインも inline する (追加 ~50KB)。

### 配布形式

`scripts/build_trace_viewer.py` が以下を生成:
- 単一 `viewer.html` ファイル
- 中に Cytoscape.js (minified) + plugin + 自作 JS + CSS + trace.jsonl + scenario.json を **すべて inline** で埋め込み
- ファイルサイズ: ~500KB (event 数による微変動)
- 外部リソース参照ゼロ → gist + htmlpreview で確実に動く

## CLI / Makefile 連携

```bash
# 既存の trace 出力に viewer.html を追加生成
python scripts/build_trace_viewer.py var/runs/exp11_r1/

# 出力: var/runs/exp11_r1/viewer.html
```

publish_experiment_gist.py との接続:
- `run_dir` 内に viewer.html があれば gist に含める
- `00_summary.md / 01_report.md / 02_trace.jsonl / 03_trace.html / 04_scenario.json / 06_viewer.html` の構成
- `[viewer]` URL も終了時に出力

## 実装プラン (PR 分割)

| PR | 内容 | 規模 | 依存 |
|---|---|---|---|
| **α** | trace schema 拡張 (`position_change` event) + escape_game_runtime での自動 emit + tests | 中 (~400 行) | なし |
| **β** | `scripts/build_trace_viewer.py` 雛形 + viewer template (HTML/CSS/JS) + **Cytoscape.js inline 埋め込み機構** + 静的 map 描画 + event log | 中 (~400 行) | α |
| **γ** | playback animation (Cytoscape `animate()`) + memo state + heatmap + scrub | 小 (~250 行) | β |
| **δ** | `publish_experiment_gist.py` への接続 + docs + `trace_to_html.py` と併存 | 小 (~100 行) | γ |

合計: **~1150 行** (vanilla SVG 版より 450 行削減)。

### Cytoscape.js の取得経路

`scripts/build_trace_viewer.py` が初回実行時に:
1. `~/.cache/llm-rpg/cytoscape.min.js` (またはプロジェクト内 `vendor/`) にダウンロード
2. SHA256 を `vendor/cytoscape.sha256` で検証 (供給チェーン攻撃対策)
3. 以降は cache から読み込み

ダウンロード URL: `https://unpkg.com/cytoscape@3.30.x/dist/cytoscape.min.js` (具体的なバージョンは pin)
プラグイン: `https://unpkg.com/cytoscape-dagre@2.5.0/cytoscape-dagre.js`

vendor file はリポジトリにコミットせず、`.gitignore` 対象。初回ビルド時に DL する。CI で問題なら vendor/ 配下に commit する選択も可。

## 段階的提供価値

| PR 完了時点 | 何ができるか |
|---|---|
| α | trace に位置情報が乗る (まだ視覚化なし) |
| β | 静的 map に最終位置を表示 (再生はまだなし) |
| γ | 再生 + memo + heatmap (完成形) |
| δ | gist に自動同梱、すぐ共有可能 |

## 既存 `trace_to_html.py` との関係

- **共存させる**。Mermaid sequence + per-tick details は今でも有用 (jq / grep ユース)
- 新 viewer は「空間 + アニメーション」担当
- 同じ gist に両方含める (`03_trace.html` = Mermaid 版 / `06_viewer.html` = 新版)

## 検証計画

| 試験 | 内容 |
|---|---|
| 単体テスト | `build_trace_viewer.py` のレイアウト / event grouping ロジック |
| ブラウザ手動 | Chrome / Safari / Firefox で開いて再生確認 |
| htmlpreview 確認 | gist + htmlpreview で正常描画されること (CDN 依存ゼロなので原理上問題ないが必ず実機確認) |
| 第12回実験で使う | 長尺シナリオで体験し、追加要望を集める |

## 未解決の論点

- **scenario.json に座標フィールドを追加するか?** spot graph に座標を持たせれば手動レイアウト指定可能。なければ force-directed 自動配置。第一版は座標フィールド optional で受け取り、無ければ自動配置で誤魔化す
- **複数プレイヤーが同 spot にいる時の重ね表示** 円周上にオフセット (3 人以内ならわかりやすい)
- **長尺シナリオでの event 数** 500+ event でも描画が重くならないか (SVG の DOM 数 + イベント log のレンダリング戦略)

## 受け入れ条件

PR γ 完了時に以下すべてを満たす:

- [ ] 第11回 R1 の trace を viewer.html 化し、htmlpreview で開いて再生できる
- [ ] カイトとリンが地図上で実際に動くアニメーションが見える
- [ ] 任意の tick にシークでき、その tick の event log / memo state が表示される
- [ ] viewer.html のファイルサイズが 1MB 以下 (目標 500KB)
- [ ] CDN ロード失敗の心配がない (外部リソース参照ゼロ — Cytoscape は inline)
- [ ] Cytoscape の SHA256 検証が `build_trace_viewer.py` で行われる (供給チェーン攻撃対策)

## 関連

- Issue #205 (第11回実験)
- PR #199 (trace schema 基盤)
- PR #203 (trace 自動配線)
- PR #204 (`scripts/run_scenario_experiment.py`)
- PR #211 (gist publish)
- PR #212 (Mermaid 描画修正 — 経緯)
- `docs/trace_format.md` (trace スキーマ)
