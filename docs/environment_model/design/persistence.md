# 世界の状態の保存 (SQLite)

世界の状態 (集約と帳簿) は、最初から SQLite に置く。本番もテストも同じ実装を使い、テストは SQLite のメモリ上の DB (`:memory:`) で回す。メモリだけの実装は持たない。決めた経緯は #2084。

## 決まり

- 1 つの確定の範囲は 1 つのトランザクション。断られたら DB を巻き戻す
- 集約と帳簿は、1 つを 1 行の JSON で持つ。いつも ID で丸ごと読み書きし、中を SQL で検索しない。経過の分析は trace で行う
- 集約は、自分の状態を値で返す操作 (memento) と、そこから作り直す操作を持つ。JSON にするのは infrastructure で、ドメインは保存の仕方を知らない
- 行ごとに、書いたときの形の版を持つ。版が合わない行、知らないキーや足りないキーのある行は、読み捨てずにはっきり止める
- 古い形を新しい形に直す変換は、いまは作らない。ドメインモデルがおおよそ固まり、世界をコードの更新をまたいで続ける必要が出たときに作る
- ドメインイベントは保存しない。確定したら配り、経過は trace に残す

## 表

```sql
CREATE TABLE world (                       -- 1 つの DB に 1 つの世界
    world_id TEXT PRIMARY KEY,
    scenario TEXT NOT NULL,                -- 開いたシナリオのパス
    scenario_hash TEXT NOT NULL,           -- 開いたシナリオ (取り込んだ共通の部品を含む) の中身のハッシュ
    storage_version INTEGER NOT NULL       -- 表の形の版
);

CREATE TABLE world_state (                 -- 集約と帳簿。1 つを 1 行
    kind TEXT NOT NULL,                    -- "person_vitals"、"item"、"world_flags" など
    key TEXT NOT NULL,                     -- 持ち主の ID。世界に 1 つのものは world_id
    version INTEGER NOT NULL,              -- その kind の JSON の形の版
    state TEXT NOT NULL,                   -- memento を JSON にしたもの
    PRIMARY KEY (kind, key)
);
```

- 状態が変わったら、その集約の行を上書きする (行を足さない)。書き出すのは、範囲の中で引いた集約の行だけ。世界に 1 つの集約 (居場所、行為の記録、旗) は、変わるたびに世界全体の分の 1 行を書き直す。今の人数 (4〜20 人) なら数 KB で、重くなったら集約の分け方をドメインの決まりとして見直す
- 世界を開き直すとき、`scenario_hash` が今のシナリオの中身と違えば止める。集約は宣言を ID で指しているので、宣言が変わった世界を読むと、指す先がずれる
- `storage_version` が今のコードと違っても止める

## memento

```python
class PersonVitals(AggregateRoot[PersonVitalsEvent]):
    def memento(self) -> PersonVitalsMemento: ...            # 問い合わせ。値の変わらない形 (frozen dataclass) で状態を返す
    @classmethod
    def from_memento(cls, memento: PersonVitalsMemento, design: WorldDesign) -> "PersonVitals": ...
        # 宣言は memento に ID で持ち、作り直すときに design から引く (Item の spec、PassageStates の通路など)
```

- memento の中身は、値オブジェクトと、それをまとめた値の変わらない形だけ。宣言そのものは入れず、ID で持つ
- `from_memento` はイベントを出さない。作り直すことは、世界で何かが起きたことではない
- 帳簿 (`ScenarioProgress`、`MissedNotices`、`SoundsThisTick`、`MonsterSpawnRecords`) も同じ形で持つ

## 作業単位

application は保存の仕方を知らず、次の形だけを知る。

```python
class WorldStore(Protocol):
    def session(self) -> WorldSession: ...                    # 1 つの確定の範囲を始める

class WorldSession(Protocol):
    def facts(self) -> WorldFacts: ...                       # 条件に渡す読む入口
    def aggregates(self) -> WorldAggregates: ...             # 効果に渡す書き換えの入口
    def clock(self) -> WorldClock: ...                       # 効果には触らせず、ユースケースが直接扱うもの
    def scenario_progress(self) -> ScenarioProgress: ...
    def latest_actions(self) -> LatestActions: ...
    def people_register(self) -> PeopleRegister: ...
    def commit(self) -> tuple[DomainEvent, ...]: ...          # 確定し、範囲の中で出たイベントを出た順に返す
    def roll_back(self) -> None: ...
```

SQLite の実装 (`SqliteWorldSession`) は次のように動く。

1. 範囲を始めるときに、トランザクションを始める
2. 集約は、範囲の中で初めて引かれたときに行を読んで作り直し、手元に持つ。同じ範囲でもう一度引かれたら、手元のものを返す。同じ範囲の中で書き換えたものが、すぐ読める
3. 無い集約を引いたら、作らずにドメイン例外にする。宣言されたすべての場所・人・集団の決定の分は、世界を開く処理が空で入れる。読むだけの問い合わせが状態を作ると、巻き戻したときに数が合わなくなる
4. `commit` は、手元に持った集約の memento を JSON にして書き出し、世界から出た集約の行を消してから、トランザクションを確定する。範囲の中で出たイベントを、出た順に 1 つのまとまりで返す
   - 世界から出た集約 (燃え尽きた灯など) のイベントも拾う。範囲が、外した集約を覚えておく
   - まとまりは、知覚の「1 つの確定の範囲から出た刺激は 1 人に 1 つ」の単位になる
5. `roll_back` は、トランザクションを巻き戻し、手元に持った集約を捨てる。イベントは返さない

## 書き忘れを止める

- アーキテクチャのテストで、game_world のすべての集約と帳簿に、memento と JSON の変換が登録されていることを見張る。集約を足して保存を忘れると、テストが落ちる
- 集約ごとに、状態を変えたあと保存して読み戻すと、元と同じ memento になることを確かめる
- JSON にするときに知らない形の値が来たら止める (黙って捨てない)

## この先

- Being の記憶 (今は Snapshot) も同じ SQLite に移し、Snapshot をなくす。世界の保存ができてから、別の Issue で行う
- 版から版への変換は、要るときに版ごとの関数として足す
