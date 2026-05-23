# TODO ツール 現状調査と能動的目標管理への改修候補

> Issue #188 第 7 回 LLM 実験で発見した「LLM の長期計画が弱い」(20 tick で
> strategy が薄れる) 問題への対策候補を整理。**受動的な episodic memory**
> ではなく **能動的に管理できる目標機能** を作る方向で評価する。

## TL;DR

- 現状の TODO ツールは **メモ機能** に留まり、能動的目標管理として不完全
- ✅ LLM が能動的に add / complete 可能、UUID で immutable 監査可
- ❌ prompt に自動表示されず、観測モデルに統合されておらず、完了条件も無く、
  達成度フィードバックも無い
- 完成形に必要な 5 改修を提案: prompt 統合 / episodic cue 統合 /
  条件ベース完了 / フィードバック / 階層化

## 1. 現状の実装

### 1.1 提供ツール

`src/ai_rpg_world/application/llm/services/tool_catalog/memory.py:21-54`

| Tool | 引数 | 効果 |
|---|---|---|
| `todo_add(content)` | `content: str` | UUID で id 採番、`added_at` 自動付与、未完了で追加 |
| `todo_list()` | なし | 未完了 (`completed=False`) のみ、追加日新しい順 |
| `todo_complete(todo_id)` | `todo_id: str` | 指定 ID を `completed=True` に |

### 1.2 内部状態

`src/ai_rpg_world/application/llm/services/in_memory_todo_store.py`:

```python
@dataclass(frozen=True)
class TodoEntry:
    id: str         # UUID
    content: str    # LLM が指定したテキスト
    added_at: datetime
    completed: bool
```

- プレイヤー ID ごとの dict で保持 (in-memory)
- **容量制限なし** (sliding_window と異なる)
- **永続性なし** (session 終了で消滅)
- 優先度 / 期限 / 完了条件 / メタ情報 **すべて無し**

### 1.3 prompt への表示

`src/ai_rpg_world/application/llm/services/prompt_builder.py:213-369`:

**TODO は prompt builder に統合されていない**。

prompt は以下の 3 セクション構成:
```
## 現在の状況
## 直近の出来事（時系列順）
## 関連する記憶
```

TODO はこれらのどこにも自動で表示されない。LLM は `todo_list` ツールを
**能動的に呼ばない限り** 自分の未完了 TODO を思い出さない。

### 1.4 escape_game / spot_graph_wiring での配線

`demos/escape_game/escape_game_runtime.py:252`:
```python
_include_todo_tools: bool = field(default=True, repr=False)
```

- デフォルト有効
- 環境変数 `LLM_TOOL_MODE=pure_spot_graph` で除外 (line 793-818)
- pure_spot_graph モードは **B-4 比較実験用** (Issue #155): 「LLM が TODO
  連打に逃げる」挙動を観察するため、TODO 系を強制的に外したモード

## 2. 実験から見える挙動

| 回 | R1 default | TODO 使用 (R1) | 備考 |
|---|---|---|---|
| 4 | WIN | 5-6 件 | signpost 直後に TODO に書き写す挙動 |
| 5-7 | LOSE | 0-3 件 | signpost が明示的だと TODO を使わなくなる |

**観察**: TODO は LLM が「自分でメモを残したい」と能動的に選んだ時だけ使われる。
**外部から再注入されない**ため、書いた直後の数 tick だけ意識される。
20+ tick の長期シナリオで「以前書いた TODO」を LLM が能動的に確認しない
限り、メモは死蔵される。

## 3. 観測モデル軸 1-4 との関係

`docs/observation_model_axes.md` の 4 軸に照らすと、TODO は **完全に軸外**:

| 軸 | TODO は? |
|---|---|
| 軸 1 (event 構造) | TODO 操作は event を発火しない (action_result のみ記録) |
| 軸 2 (prose 事実だけ) | n/a (prose に表示されないため) |
| 軸 3 (位置で差分化) | n/a (prompt 統合されないため) |
| 軸 4 (連鎖中 actor) | n/a |

つまり、TODO は **観測パイプライン外** にあり、「世界の事実 → 観測 → prompt」
の流れに乗らない。LLM の頭の中だけの個別記憶として孤立している。

## 4. 能動的目標管理として何が足りないか

### 4.1 機能ギャップ表

| 要件 | 現状 | 欠如内容 |
|---|---|---|
| ✅ LLM が能動的に add / complete | OK | - |
| ✅ ID で immutable 履歴管理 | OK | - |
| ✅ session 内永続 (容量制限なし) | OK | - |
| ❌ prompt への自動再注入 | NO | prompt_builder が参照しない |
| ❌ 観測モデル統合 | NO | episodic cue / structured payload 無し |
| ❌ 完了条件の構造化 | NO | content は自由文字列のみ |
| ❌ 達成度フィードバック | NO | 世界 state と同期しない |
| ❌ 階層化 / subtodo | NO | flat list のみ |
| ❌ 期限 / 優先度 / メタ | NO | エントリは id / content / added_at / completed のみ |
| ❌ 動的更新 | NO | content の変更手段なし (remove → re-add のみ) |

### 4.2 具体的な使われ方の問題

**問題 1: 「書いて忘れる」**
- LLM が tick=2 で TODO に「power_on を維持する」と書く
- tick=20 になっても prompt に出ないので、LLM は TODO を思い出すには
  `todo_list` を能動的に呼ぶ必要がある
- LLM は通常 1 ターン 1 ツールしか呼ばないので、`todo_list` を呼ぶ
  = 他の行動を 1 つ犠牲にする → 呼ばない傾向に

**問題 2: 完了条件が曖昧**
- 「power_on を維持する」という TODO はいつ完了か?
- LLM 自身が「達成した」と判断して `todo_complete` を呼ぶしかない
- 世界 state (例: `control_panel.power_on=true`) と紐付いていないので、
  自動完了しない

**問題 3: フィードバック不在**
- TODO を達成しようとして失敗した (例: `power_off` してしまった) ときに、
  TODO が「未達」「逆行した」と通知されない
- `action_failed` 観測 (#168) は単発の失敗には効くが、TODO 単位の進捗管理
  には繋がっていない

## 5. 改修候補 (5 案)

優先度順:

### 案 A: prompt 自動統合 (即効、最小実装)

**何を**:
- `prompt_builder` に「未完了 TODO」セクションを追加
- 毎ターンの user prompt に常時表示

**プロンプト例**:
```
## 現在の状況
...

## 進行中の目標 (未完了 TODO)
- [tick=2] power_on を維持する (id: abc-123)
- [tick=5] リンが vault に到達したら latch を engage させる (id: def-456)

## 直近の出来事
...
```

**長所**:
- LLM が能動的 `todo_list` を呼ばなくても毎ターン目があたる
- 既存実装の最小拡張で済む
- 容量制限なし (未完了の全件 or 最新 N 件)

**短所**:
- prompt が長くなる (context limit)
- LLM が「重要な目標」を選別する責任は依然残る

**実装規模**: 50-100 行

### 案 B: 条件ベース自動完了

**何を**:
- `todo_add(content, completion_condition?)` の signature 拡張
- `completion_condition` は structured (FLAG_SET / OBJECT_STATE / 等)
- 毎 tick / 関連 event で条件を評価 → 満たしたら自動 `completed=true`

**実装例**:
```python
todo_add(
    content="操作盤を起動する",
    completion_condition={
        "type": "OBJECT_STATE",
        "target_object": "control_panel",
        "required_state": {"power_on": true}
    }
)
```

**長所**:
- 世界 state と同期 → 認知負荷削減
- 「達成済みなのに勘違いで複数回追加」を防ぐ

**短所**:
- LLM が condition を正しく書けるかが鍵 (条件 schema を理解させる必要)
- 評価 stage を追加する必要 (毎 tick / event hook どちらか)

**実装規模**: 200-400 行

### 案 C: 達成度フィードバック (action_result 統合)

**何を**:
- TODO 完了条件を満たした瞬間、observation 経路で「目標達成」を通知
- 逆行 (例: `power_on=true` → `false` に戻った) も「逆行通知」として出す

**プロンプト例**:
```
[行動結果] todo_complete(id=abc-123) → 完了
[観測] 目標『power_on を維持する』が再び未達状態になりました (操作盤の電源が切れた)
```

**長所**:
- LLM が達成 / 逆行を必ず気付ける
- 案 B と組み合わせて完成度上昇

**短所**:
- observation スパムにならないようの抑制が必要

**実装規模**: 100-200 行 (案 B 上に乗せる)

### 案 D: 階層化 (subtodo / 親子関係)

**何を**:
- `todo_add(content, parent_id?)` で親子関係
- 親 TODO は子全完了で完了
- 大目標を分解する設計に対応

**長所**:
- 長期 / 多段階シナリオに対応
- LLM が「ステップを進める」感覚を持てる

**短所**:
- 設計複雑化
- 階層深さの制御 (3 段以上は乱れる?)

**実装規模**: 200-300 行

### 案 E: episodic cue 統合

**何を**:
- TODO の goal / state を `episodic_cue_rules` の cue source に追加
- 「過去にこんな目標を立てた」「似た状況で達成 / 失敗した」を受動想起の材料に

**長所**:
- 受動想起 ≠ 能動目標管理 だが、補完関係として強力
- ユーザ要件 (「episodic memory に頼らず能動管理」) と相反しないか確認要

**短所**:
- ユーザの要件「受動想起ではなく能動管理」と方向が違う
- ただし併用すれば「自分で覚えてる + 思い出させてもらえる」の二重保険

**実装規模**: 100-200 行

## 6. 推奨ロードマップ

ユーザ要件 (能動的目標管理) を踏まえると:

### Phase 1 (最小投資、最大効果): 案 A
**prompt 自動統合**だけでもかなり効果がある:
- LLM が「自分の目標を毎ターン見る」状態になる
- 「忘れる」問題が解消
- 既存 TODO ツールの活用範囲が広がる

実装は 1 PR で済む見込み。第 8 回実験のスコープ外だが、第 9 回以降の実験
で「TODO セクションが prompt に出る効果」を測定できる。

### Phase 2 (中規模): 案 B + 案 C
**条件ベース完了 + フィードバック** で「世界と同期する目標」に進化:
- LLM の認知負荷を大幅に削減
- 完了 / 逆行を能動的に把握できる
- relay_puzzle のような state 依存パズルで効果絶大

### Phase 3 (長期): 案 D + 案 E
**階層化 + episodic 統合** で長期シナリオに対応:
- 大目標 → 中目標 → 小目標の分解
- 過去の達成 / 失敗から自動的に学ぶ
- 数百 tick の規模に耐える

## 7. 次のアクション提案

ユーザの「能動管理」優先度を考えると:
1. **本ドキュメント (現調査結果) を残す** ← 今 PR で対応
2. **案 A (prompt 自動統合) を新 Issue として起票** ← 即着手可
3. 第 8 回実験結果を見てから案 B 以降の優先度を決める

## 関連

- Issue #188 第 7 回実験トレース (LLM 長期計画弱さの動機)
- Issue #154 / #155 (TODO 系の B-4 比較実験)
- `docs/observation_model_axes.md` (観測モデルとの関係性)
- `src/ai_rpg_world/application/llm/services/in_memory_todo_store.py` (実装)
- `src/ai_rpg_world/application/llm/services/executors/todo_executor.py` (ツール executor)
- `src/ai_rpg_world/application/llm/services/tool_catalog/memory.py` (tool catalog)
