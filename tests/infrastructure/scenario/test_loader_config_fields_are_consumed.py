"""loader が読み取った設定が、本番経路で誰にも使われないまま残るのを防ぐ。

## 何度も踏んでいる穴

- `initial_items` (PR #830): loader は parse し、`grant_initial_items_to_inventory`
  も存在したのに、**本番経路から一度も呼ばれていなかった**
- `initial_state` (PR #840): loader は型検証までしていたのに、
  `PlayerStatusAggregate` は常に空の state で作られていた

どちらも「シナリオに書いたのに効かない」形の静かな失敗で、しかも失敗文は
シナリオ作者が書いた文言が返るので**原因が文言の裏に隠れる**。実 run で
「なぜか一度も成功しない」としてしか現れない。

テストが通り続けていたのは、唯一の利用者が本番の配線を迂回して自前で
fixture を組んでいたため。だから「そのフィールドを使うテストがあるか」では
検出できない。**本番コード (src/) がそのフィールドを読むか**を見る。

## 名前一致だけでは足りない

同名フィールドが複数の設定クラスにあると区別できない。実際 `initial_state`
は `PlayerSpawnConfig` と `ScenarioWeatherConfig` の両方にあり、素朴に
「`.initial_state` が src/ に出現するか」を見るだけだと、**後者だけが
読まれている状態を「読まれている」と誤認**する。#840 を見逃した実際の理由が
これで、当時の走査は 0 件と報告していた。

そこで判定を 2 段にしてある。

1. 一意な名前 → 「src/ で参照が 0」なら落とす
2. 同名が複数クラスにある名前 → 受け手の変数名まで見て、そのクラス由来と
   思われる受け手が 1 つも無ければ落とす

2 の受け手推定は完全ではないので、判定できない場合は落とさず見逃す
(偽陽性でテストを不安定にするより、取りこぼしを許容する)。

## 検証

#830 の修正前のコミットで実行すると、`initial_items` と `initial_state` の
両方を検出する。当時これがあれば、どちらも出荷前に止められた。

## このテストが見ないこと (実測つき)

この網は粗い。**通ったことを「宣言が効いている」証明として読まないこと。**
2026-08-11 に反証を試みて確かめた抜け道を、規模つきで残しておく。

1. **フィールド名の衝突。これが最大の穴。** 判定は名前一致なので、`src/` の
   どこかに同名の属性アクセスがあれば通る。受け手の型は見ていない。`src/` に
   現れる属性名は 5,692 個あり、設定フィールドにありそうな名前 61 個を試すと
   **34 個 (55%) が既に衝突**していた (`enabled` `description` `name` `value`
   `state` `level` `kind` `capacity` `limit` ほか)。つまり **ありふれた名前で
   新フィールドを足すと、実装を一切書かなくてもこの検査は緑になる。**
2. **参照が生きた経路にあるかは見ない。** 到達しない分岐 (`if False:`)、型注釈
   だけの参照、デコレータ式、クラス変数の初期値、`TYPE_CHECKING` ブロックの
   中でも「読まれている」と数える。**どこからも import されないモジュール**に
   置いた参照も数える。
3. **`getattr(x, "field")` は受け手を問わない。** 動的アクセスを拾うために
   必要な緩さで、受け手が無関係なオブジェクトでも通る。
4. **一括展開は拾えない。** `sink(**asdict(cfg))` や `asdict(cfg)["field"]`、
   変数名を渡す `getattr(cfg, name)` は読み取りと数えない。本番がその形で
   読んでいると、読んでいるのに落ちる (偽陽性)。

一方、次は数えないようにしてある (数えると抜け道になる)。

- 書き込み (`cfg.field = x`) と削除 (`del cfg.field`) — `ctx` が `Load` のときだけ数える
- コメント・docstring・文字列リテラルの中の記述

宣言が実際に効くことは、シナリオを 1 本書いて歩かせる e2e が担う
(`tests/demos/test_darkened_station_scenario.py` など)。1 の穴を構造的に閉じる
には、名前一致ではなく「このフィールドを読む側」を明示登録する形が必要で、
それは別途 issue にしてある。
"""

from __future__ import annotations

import ast
from collections import defaultdict
from pathlib import Path

_SRC = Path(__file__).resolve().parents[3] / "src" / "ai_rpg_world"
_LOADER = _SRC / "infrastructure" / "scenario" / "scenario_loader.py"
_MODELS = _SRC / "infrastructure" / "scenario" / "models.py"

#: 本番経路が読まなくてよいフィールドと、その理由。
#:
#: 新しくここへ足すときは、**「読まれなくても壊れない」理由**を書くこと。
#: 「あとで使う」は理由にならない (それがまさに #830 / #840 の状態だった)。
_ALLOWED_UNCONSUMED: dict[tuple[str, str], str] = {
    ("ScenarioMetadata", "theme"): "人間向けの分類。実行時の挙動には効かせない",
    ("ScenarioMetadata", "difficulty"): "人間向けの分類。実行時の挙動には効かせない",
    ("ScenarioMetadata", "estimated_ticks"): "人間向けの目安。tick 上限は実験設定側で決める",
    ("ScenarioMetadata", "author"): "人間向けの出典表記",
    ("AreaDef", "position_source"): (
        "宣言座標か重心算出かの由来を示す派生値。シナリオ作者が書くもので"
        "はないので、読まれなくても宣言が無視されることはない"
    ),
    ("ItemSpecDefinition", "string_id"): (
        "loader 内部で文字列 id を int id へ写像するためのキー。写像後は"
        "int id だけで扱うので、runtime が読まないのが正しい"
    ),
    ("ScenarioLootTableDefinition", "string_id"): (
        "同上。loader 内部の id 写像専用"
    ),
    ("ScenarioMerchantDefinition", "string_id"): (
        "同上。loader 内部の id 写像専用で、runtime は merchant_id だけを使う"
    ),
    ("ScenarioMetadata", "description"): (
        "シナリオの解説文。**ネタバレを含み得るので LLM の初期文脈には出さない**"
        " と決めてある (world_llm_prompt.py の冒頭コメント)。公開導入は"
        " llm_public_intro が担う。読まないのが正しい"
    ),
    ("AreaDef", "description"): (
        "作者向けの覚書。設計 doc (spot_graph_distant_view_design.md) の"
        "表示文の優先順は distant_descriptions → visible_name の 2 段で、"
        "description は最初から含まれていない。metadata.description と同じ"
        "「人間向けで prompt に出さない」枠"
    ),
}

#: そのクラスの値が入っていそうな受け手変数名。同名フィールドを持つクラスを
#: 見分けるためだけに使う。ここに挙げた名前で受けていれば「読まれている」。
#:
#: 短い名前 (かつて ``PlayerSpawnConfig`` に ``"s"`` を挙げていた) は避ける。
#: ``src/`` のどこかに ``s.string_id`` があるだけで一致してしまい、見分けの
#: 役に立たない。走査が AST になってチェーンの直前の属性名まで受け手として
#: 使えるようになったので、そういう緩いヒントに頼る必要がなくなった。
_RECEIVER_HINTS: dict[str, tuple[str, ...]] = {
    "PlayerSpawnConfig": ("spawn", "player_spawn"),
    "ScenarioWeatherConfig": ("weather_config", "weather"),
    "ScenarioDayNightConfig": ("day_night_config", "day_night"),
    "AreaDef": ("area",),
    "DistantCueDef": ("cue",),
    "DistantCueAppearEventDef": ("appear_event",),
    "OngoingConditionDef": ("condition",),
    "ItemSpecDefinition": ("item_def", "spec", "definition"),
    "InitialItemSpec": ("initial", "initial_item"),
    "ScenarioLootTableDefinition": ("loot_table", "table"),
    "ScenarioMonsterTemplate": ("template", "monster_template", "st"),
    "ScenarioLootEntry": ("loot_entry",),
    "ScenarioMerchantDefinition": ("merchant",),
    "ScenarioMerchantPriceEntry": ("price_entry", "listing"),
    "ScenarioMarketInitialOrder": ("initial_order",),
}

#: まだ本番経路が読んでいないが、**続く PR で読む予定**のフィールドと、
#: それを読む PR。
#:
#: `_ALLOWED_UNCONSUMED` (= 読まれなくてよい) とは別物で、こちらは
#: 「いま読まれていないこと」を一時的に許すだけの猶予リストである。
#: `test_pending_consumers_are_removed_once_wired` が、読まれるように
#: なった項目をここに残したままにできないようにしている。つまり配線が
#: 済んだ時点で必ずこの表から消える。
#:
#: **この表に足せるのは、宣言だけを先に入れる PR が分割の理由を明示できる
#: ときだけ**。「あとで使う」を理由に無期限で積むと、#830 / #840 と同じ
#: 静かな失敗に戻る。
#: 経済統合 Phase 0 で積んだ 8 項目は、商人と所持金を prompt へ配線した PR で
#: 下の歯止めテストが落ちたため、その PR ですべて外した。
_PENDING_CONSUMERS: dict[tuple[str, str], str] = {}


def _loader_config_classes() -> dict[str, list[str]]:
    """models.py が定義する dataclass とそのフィールド名。"""
    tree = ast.parse(_MODELS.read_text(encoding="utf-8"))
    classes: dict[str, list[str]] = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue
        is_dataclass = any(
            (isinstance(d, ast.Name) and d.id == "dataclass")
            or (isinstance(d, ast.Call) and getattr(d.func, "id", "") == "dataclass")
            for d in node.decorator_list
        )
        if not is_dataclass:
            continue
        fields = [
            stmt.target.id
            for stmt in node.body
            if isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name)
        ]
        if fields:
            classes[node.name] = fields
    return classes


#: 受け手を名前で言い表せなかった属性アクセスに立てる印。
#:
#: 「読まれている」ことは示せるが、どのクラス由来かは示せない。だから
#: 同名フィールドの見分け (``_RECEIVER_HINTS``) には決して一致しない。
_UNNAMED_RECEIVER = "<式>"


def _receiver_name(value: ast.expr) -> str:
    """属性アクセスの受け手を、見分けに使える名前へ落とす。

    - ``spawn.initial_items`` → ``spawn`` (素の名前)
    - ``scenario.metadata.role_labels`` → ``metadata`` (連鎖の直前の属性名)
    - それ以外 (呼び出しや添字の結果) → ``_UNNAMED_RECEIVER``
    """
    if isinstance(value, ast.Name):
        return value.id
    if isinstance(value, ast.Attribute):
        return value.attr
    return _UNNAMED_RECEIVER


def _field_accesses() -> dict[str, set[str]]:
    """loader 以外の src/ から属性アクセスを AST で集める。

    ## なぜ正規表現をやめたか

    以前は本文を ``受け手.フィールド`` の正規表現で走査していた。``re.findall``
    は重複しない位置で走るので先頭から 2 セグメントずつ食べ、**チェーンの段数
    の偶奇で最後のフィールドが見えたり見えなかったりした**。

    - ``scenario.metadata.show_world_map`` (3 段) → ``scenario.metadata`` だけ拾い、
      ``show_world_map`` は **見えない**
    - ``self.scenario.metadata.llm_objective_text`` (4 段) → 最後のペアが揃うので
      **偶然見える**

    このため本番コードには「検査に見せるため」のローカル変数が置かれていた
    (``scenario = self.scenario`` / ``metadata = scenario.metadata``)。テストの
    実装都合が production の形に漏れていた。AST なら段数は関係ない。

    さらに、正規表現は本文をそのまま走るのでコメントや docstring 内の
    ``spawn.initial_items`` も「読まれている」と数えていた。AST にはそもそも
    入らない。

    ``getattr(x, "field")`` の動的アクセスも数える。遠景 cue 系はこの形でしか
    読まれておらず、属性アクセスだけを見ると「誰も読んでいない」と誤判定する。
    """
    accesses: dict[str, set[str]] = defaultdict(set)
    for path in _SRC.rglob("*.py"):
        if path == _LOADER:
            continue
        try:
            found = _accesses_in_source(path.read_text(encoding="utf-8"))
        except SyntaxError as exc:  # pragma: no cover - 構文エラーは別テストの領分
            raise AssertionError(f"{path} を解析できません: {exc}") from exc
        for field, receivers in found.items():
            accesses[field] |= receivers
    return accesses


def _accesses_in_source(source: str) -> dict[str, set[str]]:
    """1 ファイル分のソースから ``フィールド名 -> 受け手名の集合`` を集める。

    ``_field_accesses`` から切り出してある。走査規則そのものを、実際の
    ``src/`` に依存せず短いソースで確かめられるようにするため。
    """
    accesses: dict[str, set[str]] = defaultdict(set)
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Attribute):
            # 読み取り (Load) だけを数える。``cfg.field = x`` や
            # ``del cfg.field`` は同じ ast.Attribute になるが、**書き込みは
            # 「宣言が効いている」根拠にならない**。ctx を見ないと、代入を
            # 1 つ置くだけで検査を満足できる。
            if isinstance(node.ctx, ast.Load):
                accesses[node.attr].add(_receiver_name(node.value))
            continue
        if isinstance(node, ast.MatchClass):
            # ``case Cfg(field=v):`` の field は文字列で持たれ、ast.Attribute に
            # ならない。読んでいるのに読んでいないと判定されるので拾う。
            for attr in node.kwd_attrs:
                accesses[attr].add(_UNNAMED_RECEIVER)
            continue
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        # 組み込みの ``getattr(cfg, "field")`` だけを見る。``obj.getattr(...)``
        # は無関係なメソッドなので数えない。
        if isinstance(func, ast.Name) and func.id == "getattr" and len(node.args) >= 2:
            name = node.args[1]
            if isinstance(name, ast.Constant) and isinstance(name.value, str):
                accesses[name.value].add(_receiver_name(node.args[0]))
            continue
        # ``attrgetter("field")`` も読み取り。受け手は後で束縛されるので
        # 名前では言えない。
        if _is_attrgetter(func):
            for arg in node.args:
                if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                    for part in arg.value.split("."):
                        accesses[part].add(_UNNAMED_RECEIVER)
    return accesses


def _is_attrgetter(func: ast.expr) -> bool:
    """``attrgetter`` / ``operator.attrgetter`` の呼び出しか。"""
    if isinstance(func, ast.Name):
        return func.id == "attrgetter"
    return isinstance(func, ast.Attribute) and func.attr == "attrgetter"


def _unconsumed_fields(*, exempt: set[tuple[str, str]]) -> list[str]:
    """src/ (loader 以外) から読まれていない設定フィールドを、理由つきで列挙する。

    ``exempt`` に挙げた (クラス名, フィールド名) は判定から外す。呼び出し側が
    「読まなくてよい」と「まだ読んでいないだけ」を出し分けるための引数。
    """
    classes = _loader_config_classes()
    accesses = _field_accesses()

    owners: dict[str, list[str]] = defaultdict(list)
    for cls, fields in classes.items():
        for field in fields:
            owners[field].append(cls)

    unconsumed: list[str] = []
    for cls, fields in sorted(classes.items()):
        for field in fields:
            if (cls, field) in exempt:
                continue
            receivers = accesses.get(field, set())
            if not receivers:
                unconsumed.append(f"{cls}.{field} (src/ に参照なし)")
                continue
            if len(owners[field]) == 1:
                continue
            # 同名フィールドを持つクラスが複数ある。このクラス由来と
            # 思われる受け手が 1 つでもあれば「読まれている」とみなす。
            #
            # ヒント未登録のクラスは、以前ここで **無条件に見逃していた**。
            # つまり同名フィールドを持つ 8 クラスは、この検査の外にいた。
            # 見逃しを既定にすると「検査したつもり」になるので、ヒントを
            # 書けと言って落とす側に倒す。
            hints = _RECEIVER_HINTS.get(cls)
            if hints is None:
                unconsumed.append(
                    f"{cls}.{field} (同名: {', '.join(owners[field])} / "
                    f"{cls} の受け手ヒントが _RECEIVER_HINTS にありません)"
                )
                continue
            if not any(hint in receivers for hint in hints):
                unconsumed.append(
                    f"{cls}.{field} (同名: {', '.join(owners[field])} / "
                    f"受け手: {', '.join(sorted(receivers)) or 'なし'})"
                )
    return unconsumed


class TestLoaderConfigFieldsAreConsumed:
    """loader が作る設定フィールドが、本番コードから読まれている。"""

    def test_no_field_is_silently_unconsumed(self) -> None:
        """どの設定フィールドも src/ (loader 以外) から読まれている。

        読まれないフィールドは「シナリオに書いたのに効かない」宣言になる。
        意図的に読まないものは ``_ALLOWED_UNCONSUMED`` に、続く PR で読む
        予定のものは ``_PENDING_CONSUMERS`` に、どちらも理由つきで登録する。
        """
        unconsumed = _unconsumed_fields(
            exempt=set(_ALLOWED_UNCONSUMED) | set(_PENDING_CONSUMERS),
        )

        assert not unconsumed, (
            "loader が読み取っているのに本番経路が使っていないフィールドがあります。\n"
            "シナリオに書いても効かない宣言になり、失敗文の裏に原因が隠れます "
            "(#830 / #840 と同じ形)。\n\n  "
            + "\n  ".join(unconsumed)
        )

    def test_pending_consumers_are_removed_once_wired(self) -> None:
        """配線待ちリストに、既に本番経路が読んでいるフィールドが残っていない。

        猶予を無期限にしないための歯止め。配線した PR は、この表から自分の
        項目を消さないと緑にならない。消し忘れたまま次のフィールドを足すと、
        そちらの配線漏れが猶予の陰に隠れる。
        """
        still_unconsumed = {
            entry.split(" ", 1)[0]
            for entry in _unconsumed_fields(exempt=set(_ALLOWED_UNCONSUMED))
        }
        already_wired = [
            f"{cls}.{field}"
            for (cls, field) in _PENDING_CONSUMERS
            if f"{cls}.{field}" not in still_unconsumed
        ]
        assert not already_wired, (
            "配線が済んだフィールドが _PENDING_CONSUMERS に残っています。"
            f"表から消してください: {already_wired}"
        )

    def test_pending_entries_state_which_pr_will_consume_them(self) -> None:
        """配線待ちリストの各項目に、実在するフィールドと空でない理由が書かれている。"""
        classes = _loader_config_classes()
        broken = [
            f"{cls}.{field}"
            for (cls, field), reason in _PENDING_CONSUMERS.items()
            if field not in classes.get(cls, ()) or not reason.strip()
        ]
        assert not broken, (
            "配線待ちリストの項目が、存在しないフィールドを指しているか理由が空です: "
            f"{broken}"
        )

    def test_allowlist_has_no_stale_entries(self) -> None:
        """許可リストに、既に存在しないフィールドが残っていない。

        古い項目が残ると、後から同名のフィールドを足したときに黙って
        見逃される。
        """
        classes = _loader_config_classes()
        stale = [
            f"{cls}.{field}"
            for (cls, field) in _ALLOWED_UNCONSUMED
            if field not in classes.get(cls, ())
        ]
        assert not stale, f"許可リストに存在しないフィールドが残っています: {stale}"

    def test_allowlist_entries_state_a_reason(self) -> None:
        """許可リストの理由が空文字列でない。

        「読まれなくても壊れない」理由を書く欄があっても、空や空白で登録
        できるなら「登録すれば無検査で通る」抜け道が残る。中身の妥当さは
        レビューが見るしかないが、空であることは機械で落とせる。
        """
        blank = sorted(
            f"{cls}.{field}"
            for (cls, field), reason in _ALLOWED_UNCONSUMED.items()
            if not reason.strip()
        )

        assert not blank, f"許可の理由が書かれていません: {blank}"

    def test_receiver_hints_point_at_real_classes(self) -> None:
        """受け手ヒントが、実在する設定クラスを指している。

        クラス名を変えたときにヒントだけ取り残されると、同名フィールドの
        判定が黙って無効化される。
        """
        classes = _loader_config_classes()
        unknown = [cls for cls in _RECEIVER_HINTS if cls not in classes]
        assert not unknown, f"存在しないクラスへのヒントが残っています: {unknown}"


class TestAccessCollectionRules:
    """``_accesses_in_source`` の走査規則を、短いソースで直接確かめる。

    この走査は以前 ``受け手.フィールド`` の正規表現だった。``re.findall`` が
    重複しない位置で 2 セグメントずつ食べるため、**チェーンの段数の偶奇で
    最後のフィールドが見えたり見えなかったりした**。

    どれが「正規表現へ差し戻すと落ちる」テストかを明示しておく。全部が
    回帰ガードだと読むと、判別力の無いテストを根拠に安心してしまう。

    - 差し戻すと落ちる: 3 段 / 5 段のチェーン、コメントと文字列の除外、
      名前で言えない受け手、代入の除外
    - 差し戻しても通る (新実装の基準ケース): 2 段のチェーン、``getattr``
      の文字列リテラル。どちらも旧正規表現でも一致していた
    """

    def test_two_segment_chain_is_seen(self) -> None:
        """``metadata.show_world_map`` は受け手 metadata として読まれる。

        基準ケース。旧正規表現でも一致していたので、AST 化の回帰ガードには
        ならない。走査の土台が壊れていないことだけを見る。
        """
        acc = _accesses_in_source("metadata.show_world_map\n")

        assert acc["show_world_map"] == {"metadata"}

    def test_three_segment_chain_is_seen(self) -> None:
        """``scenario.metadata.show_world_map`` も読まれる (旧実装では見えなかった)。

        3 段は旧正規表現では ``scenario.metadata`` までしか拾えず、
        ``show_world_map`` が **読んでいるのに読んでいない** と判定された。
        本番コードにローカル変数を置いて回避していたのはこれが理由。
        """
        acc = _accesses_in_source("scenario.metadata.show_world_map\n")

        assert acc["show_world_map"] == {"metadata"}

    def test_five_segment_chain_is_seen(self) -> None:
        """奇数段がいくら深くなっても最後のフィールドが読まれる。"""
        acc = _accesses_in_source("a.b.c.d.target_field\n")

        assert acc["target_field"] == {"d"}

    def test_comments_and_docstrings_are_not_counted(self) -> None:
        """コメントや文字列の中の ``spawn.initial_items`` は読まれたと数えない。

        旧実装は本文をそのまま正規表現で走ったので、コメントに名前を書く
        だけで検査を満足できた。宣言が効かないままガードが緑になる。
        """
        source = (
            '"""spawn.initial_items を将来使う予定。"""\n'
            "# spawn.initial_items は spawn から読む\n"
            'note = "spawn.initial_items"\n'
        )

        acc = _accesses_in_source(source)

        assert "initial_items" not in acc

    def test_getattr_with_a_literal_name_is_seen(self) -> None:
        """``getattr(source, "equals")`` は受け手 source として読まれる。

        基準ケース (旧正規表現にも getattr 専用の走査があった)。遠景 cue 系は
        この形でしか読まれておらず、落とすと「誰も読んでいない」と誤判定する。
        """
        acc = _accesses_in_source('getattr(source, "equals", None)\n')

        assert acc["equals"] == {"source"}

    def test_getattr_on_an_object_is_not_treated_as_the_builtin(self) -> None:
        """``obj.getattr("field")`` は組み込みではないので数えない。

        無関係なメソッドの名前が偶然 getattr であるだけの場合に「読まれた」と
        数えると、実装が無くても検査を満足できる。
        """
        acc = _accesses_in_source('obj.getattr(cfg, "zzz_unlikely_field")\n')

        assert "zzz_unlikely_field" not in acc

    def test_assignment_to_an_attribute_is_not_a_read(self) -> None:
        """``cfg.spawn_spot_id = 1`` は読み取りと数えない。

        書き込みは「宣言が効いている」根拠にならない。数えてしまうと、代入を
        1 行置くだけで検査を満足できる抜け道になる。
        """
        acc = _accesses_in_source("cfg.spawn_spot_id = 1\n")

        assert "spawn_spot_id" not in acc

    def test_deleting_an_attribute_is_not_a_read(self) -> None:
        """``del cfg.spawn_spot_id`` も読み取りと数えない。"""
        acc = _accesses_in_source("del cfg.spawn_spot_id\n")

        assert "spawn_spot_id" not in acc

    def test_match_pattern_keyword_is_seen(self) -> None:
        """``case Cfg(objective=v):`` の objective は読まれたと数える。

        match のキーワードは文字列で持たれ ast.Attribute にならない。拾わない
        と、実際に読んでいるのに「読んでいない」と落ちる (偽陽性)。
        """
        source = "match cfg:\n    case Cfg(objective=v):\n        use(v)\n"

        acc = _accesses_in_source(source)

        assert acc["objective"] == {_UNNAMED_RECEIVER}

    def test_attrgetter_with_a_literal_name_is_seen(self) -> None:
        """``attrgetter("objective")`` も読み取りとして数える。

        受け手は後から束縛されるので名前では言えない。読まれていることだけを
        示し、クラスの見分けには使わせない。
        """
        acc = _accesses_in_source('attrgetter("objective")\n')

        assert acc["objective"] == {_UNNAMED_RECEIVER}

    def test_receiver_that_has_no_name_is_marked_as_unnamed(self) -> None:
        """呼び出しの戻り値への属性アクセスは、受け手を印で表す。

        読まれていることは示せるが、どのクラス由来かは示せない。
        """
        acc = _accesses_in_source("load().initial_state\n")

        assert acc["initial_state"] == {_UNNAMED_RECEIVER}

    def test_the_unnamed_marker_never_matches_a_receiver_hint(self) -> None:
        """名前で言えない受け手の印は、どのクラスのヒントにも一致しない。

        素の名前と同じ扱いにすると、同名フィールドの片方だけが読まれている
        状態を「読まれている」と誤認する (#840 を見逃した理由)。
        """
        matching = [
            cls for cls, hints in _RECEIVER_HINTS.items() if _UNNAMED_RECEIVER in hints
        ]

        assert not matching, f"印がヒントに混入しています: {matching}"
