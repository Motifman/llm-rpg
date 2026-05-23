# 観測モデル設計の 4 軸 (Observation Model Axes)

> Issue #154 の relay_puzzle デモ実走 (第 4-7 回) で発見した観測モデルの
> 構造的問題を整理した結果、4 つの直交する設計軸として確立した。本文書は
> 将来の formatter / event / recipient_strategy 追加時の指針として残す。

## 背景: なぜこの設計を立てたか

LLM agent が他者の行動 / 環境変化を観測して因果を組み立てるとき、
「何を / 誰に / どう見せるか」を分解しないと、設計が容易に破綻する。
具体的には:

- **観測者が本来知り得ない情報** を prose に焼き込むと、別 spot にいる人にも
  漏れる (cause-in-prose 問題、PR #182 で発見)
- **連鎖イベント** で起点 actor が逐次失われると、観測者が因果を結びつける
  手がかりが失われる (Issue #154 第 5 回 R2 LOSE の主因)
- 観測者の **位置 / 視界** が prose 生成と配信判定に反映されないと、
  「同 spot だけが詳細を見える」のような自然な観測モデルが崩れる

これらを 4 つの軸として整理した。

## 軸の全体像

```
              事実の記録                  観測の選別                  表現の差分
            ────────────              ──────────                ──────────
            軸 1: event                  軸 3: recipient            軸 2: prose
               structure                    strategy                    rendering
               (情報を残す)                  (誰に届けるか?)              (どう表現?)
                    ↑                                                      ↑
                    └──────── 軸 4: cascade attribution ─────────────────┘
                                (連鎖中も actor を保つ)
```

| 軸 | 内容 | 関連 PR |
|---|---|---|
| **軸 1** | 事実は event に全部載せる (主体 / 場所 / 状態を捨てない) | #186 (`original_actor_entity_id`) |
| **軸 2** | prose は事実だけ。観測者が知り得ない情報を文体に焼き込まない | #182, #189 |
| **軸 3** | 観測者の位置で prose / 配信を分岐 | #187 (`lookup_recipient_spot` + 隣接配信), #189 |
| **軸 4** | 連鎖中も主体を保つ (interaction → reactive で actor を引き継ぐ) | #186 |

## 軸 1: 事実の完全性 (Event Structure)

### 原則

ドメインイベントには、**今わかっている情報をできる限り全部** 載せる。
観測者の都合で間引かない。

### なぜ

イベントは「世界で起きた事実の記録」であって、観測者ごとの見え方は
formatter で調整するレイヤーの仕事。捨てた情報は後から復元できない。

### 適用例

`ConnectionStateChangedEvent`:
- 旧: `from_spot_id`, `to_spot_id`, `traversable` のみ
- 新: 上記 + `cause: PassageChangeCauseEnum`, `original_actor_entity_id: Optional[EntityId]`

```python
@dataclass(frozen=True)
class ConnectionStateChangedEvent(BaseDomainEvent):
    connection_id: ConnectionId
    from_spot_id: SpotId
    to_spot_id: SpotId
    traversable: bool
    cause: PassageChangeCauseEnum = PassageChangeCauseEnum.UNKNOWN
    original_actor_entity_id: Optional[EntityId] = None  # 連鎖の起点
```

### チェックリスト (新 event 追加時)

- [ ] 主体 (actor_entity_id) を含めたか? 該当しないなら明示的に Optional + None
- [ ] 場所 (spot_id) を含めたか?
- [ ] 因果カテゴリ (cause / reason / 等) を含めたか?
- [ ] 時刻 / tick が必要なら含めたか?
- [ ] **default 値を None / UNKNOWN にして後方互換** にしたか?

## 軸 2: 事実だけの prose (Prose Faithfulness)

### 原則

formatter が LLM に流す prose には、**観測者が本来知り得ない情報を漏らさない**。
オノマトペや因果表現で「能動 / 自動」の質感を匂わせるのも禁止。

### なぜ

`cause` のような structured metadata は、機械可読の補助情報としては有用だが、
prose に焼き込むと **観測者の位置に関係なく** その情報が伝わってしまう。
「ガチャッと閉まった」は actor の能動行動を匂わせるが、隣の spot にいる人
には本来「ガチャッ」と聞こえる根拠がない。

### 適用例

```python
# ❌ NG (PR #182 でやってしまった例、後で revert)
if event.cause == PassageChangeCauseEnum.ACTOR_ACTION:
    prose = f"{conn_name}がガチャッと{base}。"
elif event.cause == PassageChangeCauseEnum.REACTIVE:
    prose = f"{conn_name}がひとりでに{base}。"

# ✅ OK
prose = f"{conn_name}が{base}。"  # 事実だけ
structured["cause"] = event.cause.value  # 機械可読 metadata は残す
```

同種の問題:
- `monster_abandoned_chase`: `reason` (target_lost / no_path / 等) を prose に焼き込まない (PR #189)
- `player_downed`: killer 名を観測者位置を見ずに出さない (PR #189)

### チェックリスト (新 formatter / prose 追加時)

- [ ] event に乗っている情報のうち、観測者が **位置 / 視界 / 関係性で
      推測不能** なものを prose に出していないか?
- [ ] オノマトペ / 程度表現 / 因果接続詞で「観測者が知り得ない事情」を
      匂わせていないか?
- [ ] structured payload には残してよい (機械可読、解析、将来の位置分岐用)

## 軸 3: 観測者位置による prose / 配信差分化 (Position-Aware Observation)

### 原則

`recipient_strategy` で **誰に届けるか** を決め、formatter で
**recipient の位置に応じた prose** を作る。同じ event でも、観測者の位置
によって prose / 詳細レベル / 配信有無が変わる。

### なぜ

人間の世界でも同じ。同じ「ドアが閉まる」イベントでも:
- ドアの前にいる人 → 「Aさんが扉を閉めた」と見える
- 隣の部屋にいる人 → 「ガチャッという音が聞こえた」だけ
- 遠くにいる人 → 何も気付かない

これは event の属性ではなく **観測者の位置と感覚範囲** が決めること。

### 適用例: `ConnectionStateChangedEvent`

**recipient_strategy (PR #187)**:
- 両端 spot 内 → 直接観測 (常時配信)
- 隣接 spot + `sound_permeability >= 0.1` → 間接観測 (音だけ)
- 完全遮音 / 遠方 → 配信なし

**formatter (PR #187)**:
- `at_from` / `at_to` → 「{conn}が通行可能/不能になった」(事実)
- `adjacent` → 「遠くで{conn}が動く音がした」(音だけ、状態確定はしない)
- `unknown` (graph 未注入) → 直接観測の prose に fallback (安全側)

```python
def _format_connection_changed(self, event, recipient_id):
    recipient_spot = self._context.lookup_recipient_spot(recipient_id)
    is_direct = recipient_spot in (event.from_spot_id, event.to_spot_id)
    is_neighbor = recipient_spot is not None and not is_direct
    if is_neighbor:
        prose = f"遠くで{conn_name}が動く音がした。"
    else:
        prose = f"{conn_name}が{base}。"
```

### 既存の良い先例

軸 3 を満たす先例:
- `player_formatter::_format_player_spoke`: `sound_propagation_service` で
  CLEAR / MUFFLED / FAINT を切り替え。FAINT 時には content を空に上書き
- `_spot_graph_sound_handler`: `is_adjacent` 判定で「隣の spot から」と
  「同 spot」を分岐
- `_spot_graph_monster_handler`: `target_visible` 分岐

### チェックリスト (新 formatter / recipient_strategy 追加時)

- [ ] formatter は `recipient_id` を引数で受け取り、位置を引いて分岐したか?
- [ ] `recipient_strategy` で「同 spot」「隣接」「遠方」の 3 階層を意識した
      配信判定をしたか?
- [ ] 位置が引けない fallback ケース (graph 未注入 / entity 未配置) は
      **安全側** (詳細を出さない or 配信しない) に倒したか?
- [ ] `sound_permeability` / `view_distance` のような propagation 属性が
      既に存在するか確認。あれば再利用する

## 軸 4: 連鎖中の主体追跡 (Cascade Attribution)

### 原則

`interaction → reactive_binding → passage_change` のような **イベント連鎖** で、
最終 event にも **起点 actor** を引き継ぐ。連鎖の途中で主体が逐次失われない
ように、各層が actor 情報を伝播する責任を持つ。

### なぜ

連鎖の末端だけ観測した recipient は、起点 actor が分からない。同 spot に
いて actor を視認できる recipient なら、actor 情報と連鎖の結果を **同 tick**
で受け取り、因果を組み立てられる。

### 適用例

`SpotGraphAggregate.set_connection_passage` のシグネチャ拡張 (PR #186):

```python
def set_connection_passage(
    self,
    connection_id: ConnectionId,
    new_passage: Passage,
    *,
    cause: PassageChangeCauseEnum = PassageChangeCauseEnum.UNKNOWN,
    actor_entity_id: Optional[EntityId] = None,
) -> None:
    ...
    self.add_event(
        ConnectionStateChangedEvent.create(
            ...,
            cause=cause,
            original_actor_entity_id=actor_entity_id,
        )
    )
```

caller 別の actor:
- `spot_interaction_application_service`: `actor_entity_id=entity_id` (interaction の起点)
- `reactive_passage_binding_stage_service`: `actor_entity_id=None` (世界 tick 由来、actor 不在を明示)
- `spot_graph_scenario_event_stage_service`: `actor_entity_id=None` (scripted)
- `synchronized_action_resolver_stage_service`: `actor_entity_id=None` (一旦、複数 actor を縮約しないため)

### 連鎖の解釈

- **actor あり連鎖**: interaction で actor が明示 → そのまま reactive を経由
  しても actor を伝える (将来実装)
- **actor なし連鎖**: reactive / scenario_event 由来 → 起点 actor は本当に
  存在しない。観測者は「環境変化」として受け取る

### チェックリスト (新連鎖メカニズム追加時)

- [ ] 起点 actor が存在するか? あれば末端 event まで伝播するか?
- [ ] 「actor なし」を明示的に表現できるか? (default None で OK)
- [ ] 連鎖の各層 (aggregate メソッド / stage_service) が `actor_entity_id`
      kwarg を受け取っているか?
- [ ] reactive 系は **明示的に `None` を渡す** (default 依存ではなく、
      意図を call site に残す)

## 軸の関係性と設計原則

### 軸間の依存

- **軸 1 → 軸 3**: 軸 1 で記録した情報を軸 3 が選択的に提示する。軸 1 が
  サボると軸 3 が判断材料を失う
- **軸 4 → 軸 1 + 軸 3**: 軸 4 が連鎖中の actor を保つことで、軸 1 は事実を
  完全に記録でき、軸 3 は「actor を視認できる recipient だけ richer prose」
  のような判定ができる
- **軸 2 ← 軸 1 + 軸 3**: 軸 1 で機械可読な情報を残し、軸 3 で位置で選別する
  ことで、軸 2 (prose は事実だけ) を自然に守れる

### 落とし穴: 軸 2 違反のパターン

「観測者が知り得ない情報を漏らす」例:
- ❌ `cause` を prose のオノマトペで出す (PR #182 の最初の実装、revert 済み)
- ❌ `reason` (monster's internal state) を prose で説明する (PR #189 で修正)
- ❌ `killer_player_id` を観測者の位置に関係なく出す (PR #189 で修正)
- ❌ 連鎖の起点 actor を、recipient が actor の spot にいなくても prose で
  名指しする (軸 4 + 軸 3 を破る)

### 推奨: 新 event / formatter / strategy を追加するフロー

1. **軸 1**: event の構造を決める。何を記録するか、default 値は何か
2. **軸 4**: 連鎖がある場合、各層で actor を伝播するシグネチャに整える
3. **軸 3**: recipient_strategy で配信判定を書く (同 spot / 隣接 / 遠方)
4. **軸 2**: formatter で prose を書く。**位置で分岐する前提で**、何を出して
   何を出さないか整理する
5. **テスト**:
   - 各軸の不変条件 (位置不明 fallback、actor なし伝播、prose に漏れない語)
   - 静的走査テスト (`assert "ガチャッ" not in result.prose` のような
     回帰防止) を入れる

## 関連 Issue / PR

- Issue #182 (cause enum 導入、軸 2 確立の元)
- Issue #183 / PR #186 (軸 1 + 4: `original_actor_entity_id`)
- Issue #184 / PR #187 (軸 3: 位置ベース prose 差分化、隣接配信)
- Issue #185 / PR #189 (軸 2 の徹底: 他 formatter の audit と修正)
- Issue #188 (relay_puzzle 実験で発見された問題群、本軸の動機)

## 現状の網羅状況

| Event | 軸 1 | 軸 2 | 軸 3 | 軸 4 |
|---|---|---|---|---|
| `ConnectionStateChangedEvent` | ✅ (cause + actor) | ✅ | ✅ (隣接配信) | ✅ |
| `SpotObjectStateChangedEvent` | ✅ (actor_entity_id) | ✅ | ⚠️ (同 spot 配信のみ、隣接拡張は未対応) | ✅ (interaction 経由) |
| `SpotObjectInteractedEvent` | ✅ | ✅ | ✅ (同 spot、actor 除外) | n/a (起点) |
| `PlayerSpokeEvent` | ✅ | ✅ | ✅ (sound_propagation で clarity 切替) | n/a |
| `MonsterAbandonedChaseInSpotEvent` | ✅ (reason in structured) | ✅ (PR #189) | ⚠️ (将来は「障害物が見える場合」分岐の余地) | n/a |
| `PlayerDownedEvent` | ✅ (killer_player_id) | ✅ (PR #189) | ✅ (killer 視認チェック) | n/a |
| `SpotSoundHeardEvent` | ✅ | ✅ | ✅ (intensity / is_adjacent) | n/a |

`⚠️` は将来の拡張余地で、当面は破綻していない箇所。
