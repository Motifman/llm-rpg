"""想定外例外の trace が、実際に例外を受けたハンドラを指すことを保証する。

## なぜこの試験が要るか

``_unexpected_exception_result(exc, location=..., stage=...)`` は
``tool_exception_location`` / ``tool_exception_stage`` を trace へ残す。
これは **例外が起きた場所を後から特定するための唯一の手がかり**で、
``trace.jsonl`` を読む側はこの 2 つで原因箇所を絞る。

``location`` は以前 ``"_use_item"`` のハードコードだった。#847 で他のハンドラの
広い ``try`` を刻むにあたって引数にしたが、引数にすると新しい失敗の形が生まれる。

    def _give_item(self, ...):
        try:
            ...
        except Exception as e:
            return _unexpected_exception_result(e, location="_use_item", stage="lookup")
                                                          ^^^^^^^^^^^^ 貼り付けたまま

こうなると trace は嘘の場所を指す。**間違っていても動くし、テストも落ちない。**
`_use_item` を調べても該当する経路が見つからない、という形で人間の時間だけが
溶ける。静かな失敗そのものなので、構造で止める。

## なぜ AST で見るか

「呼び出し側が正しい値を渡す」は実行時には検証できない。この関数を呼ぶのは
例外経路だけで、全経路を通す試験は書けない (書けるなら #847 は要らない)。
そこで **ソースの構造**を見る。囲っている関数の名前は AST から確実に取れる。

## この試験が見ないこと

``stage`` の値が段の実態と合っているかは見ない (``"item_lookup"`` と書いて
別の段で使っても検出できない)。同じ ``location`` の中での取り違えなので、
場所の特定は効き続ける。文字列リテラルであることだけを要求する。

``location`` も「囲っている関数のどれかと一致する」までしか見ない。closure から
呼ぶときに外側のハンドラ名を書くのを許すためで、詳しい理由は
``test_location_names_one_of_the_enclosing_functions`` の docstring にある。

## レビューで塞いだ穴

初版はこの 3 つを取りこぼしていた。いずれも「一見守っているが実は検出しない」形
だったので、経緯を残す。

1. **走査が ``executors/`` の中だけだった。** ヘルパを 1 階層上の
   ``services/tool_executor_helpers.py`` (``exception_result`` の隣) へ昇格させる
   のは #847 で自然な次の一手で、そうすると静かに範囲外になった。``src/`` 全体へ
   広げた
2. **``import ... as`` で別名にすると、その 1 件だけ収集から消えた。** 走査が
   0 件なら空振り検出が止めるが、一部だけ消えるのは何も止めない。import 文を先に
   読んで別名も照合する
3. **closure から正しいハンドラ名を渡すと落ちた。** 緑にする唯一の道が「trace に
   private な closure 名を書くこと」で、検出器が trace を劣化させる方へ人を誘導し
   ていた。囲っている関数のどれかと一致すればよい形に変えた
"""

from __future__ import annotations

import ast
import pathlib

import pytest

#: 見張る関数名。
_HELPER_NAME = "_unexpected_exception_result"

#: 走査対象。**``src/`` 全体**を見る。
#:
#: 最初は ``executors/`` だけを見ていた。レビューで穴が出た。``exception_result``
#: の定義場所 ``services/tool_executor_helpers.py`` は 1 階層上にあり、走査範囲の
#: **外**だった。#847 でハンドラを刻んでいくとこのヘルパを共有の場所へ昇格させる
#: のが自然な次の一手で、そのとき見張りは静かに範囲外になる。実際に 1 階層上へ
#: 「location が関数名と不一致」な呼び出しを置く変異を入れたら、13 passed で
#: 素通りした。
#:
#: ``src/`` 全体 (1,397 モジュール) の parse は実測 0.92 秒。collection 時の一度
#: だけなので、範囲を絞る理由が無い。
_SRC_DIR = pathlib.Path(__file__).resolve().parents[5] / "src"


class _CallSite:
    """``_unexpected_exception_result`` の 1 呼び出し箇所。"""

    def __init__(
        self,
        *,
        path: pathlib.Path,
        lineno: int,
        enclosing_functions: tuple[str, ...],
        location: object,
        stage: object,
    ) -> None:
        self.path = path
        self.lineno = lineno
        #: 外側から内側の順。``("_use_item",)`` や
        #: ``("_use_item", "_nested_recover")``。関数の外なら空。
        self.enclosing_functions = enclosing_functions
        self.location = location
        self.stage = stage

    def __repr__(self) -> str:  # pragma: no cover - 失敗表示用
        where = ".".join(self.enclosing_functions) or "<関数の外>"
        return f"{self.path.name}:{self.lineno} ({where})"


def _literal_keyword(call: ast.Call, name: str) -> object:
    """キーワード引数が文字列リテラルならその値、無ければ ``None``、
    リテラルでなければ ``_NOT_A_LITERAL`` を返す。"""
    for keyword in call.keywords:
        if keyword.arg != name:
            continue
        if isinstance(keyword.value, ast.Constant) and isinstance(
            keyword.value.value, str
        ):
            return keyword.value.value
        return _NOT_A_LITERAL
    return None


_NOT_A_LITERAL = object()


def _called_name(func: ast.expr) -> str | None:
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return None


def _local_names_bound_to_the_helper(tree: ast.Module) -> set[str]:
    """このモジュール内で ``_HELPER_NAME`` に束縛されているローカル名を集める。

    ``from ... import _unexpected_exception_result as helper`` と書かれると、
    呼び出しは ``helper(...)`` になる。名前だけを文字列比較していると **その 1 件
    だけが収集から静かに消える**。走査 0 件なら空振り検出が止めるが、一部だけ
    消えるのは何も止めない。レビューで実証された穴。

    そこで import 文を先に読み、別名も照合対象に加える。
    """
    names = {_HELPER_NAME}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            for alias in node.names:
                if alias.name == _HELPER_NAME and alias.asname:
                    names.add(alias.asname)
    return names


def _collect_value_position_references() -> list[str]:
    """ヘルパ名が「直接呼ぶ」以外の位置に現れる箇所を集める。

    ## なぜ要るか

    ここまでの見張りは **``location=`` に書かれたリテラル**を読む。だから名前を
    一段でも束ね直されると、何も見えなくなる。

        def _interact(self, ...):
            _fail = partial(_unexpected_exception_result, location="_totally_wrong")
            return _fail(e, stage="target_lookup")

    これを実際に置いて走らせたら **13 passed**。嘘の location が緑で通った。

    そしてこれは理論上の穴ではなく、**#847 の C が必ず生む圧力**である。B の時点で
    ``location="_use_item"`` のリテラルは 5 個。C1〜C7 で 9 ハンドラへ広げれば同じ
    リテラルが 30〜40 個並ぶ。そこで誰かが必ず「ハンドラ冒頭で 1 回束ねれば済む」と
    考える。**その瞬間に見張りが無効化され、しかも緑のままになる。** 静かな失敗を
    止めるために入れた仕組みが静かに無効化されるのが、一番悪い形。

    なので「束ねること自体」を禁じる。ヘルパ名が出てよいのは 3 か所だけ。

    - ``def _unexpected_exception_result`` の定義
    - ``_unexpected_exception_result(...)`` の直接呼び出し (呼ばれる位置)
    - ``import`` 文

    変数への代入、``partial`` の引数、デコレータ、辞書の値などに現れたら落とす。
    冗長にリテラルを書き写す形を強制することになるが、**それがこの見張りの前提**で
    あり、明文化されていなかったのが問題だった (レビュー指摘)。

    束ねたくなったら、この試験を消すのではなく **見張り方をまず設計し直す**こと。
    """
    violations: list[str] = []
    for path in sorted(_SRC_DIR.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        helper_names = _local_names_bound_to_the_helper(tree)
        # 直接呼び出しの func に当たるノードは許す。ノードの同一性で持つ。
        called_funcs = {
            id(node.func)
            for node in ast.walk(tree)
            if isinstance(node, ast.Call) and _called_name(node.func) in helper_names
        }
        for node in ast.walk(tree):
            if not isinstance(node, (ast.Name, ast.Attribute)):
                continue
            if _called_name(node) not in helper_names:
                continue
            if id(node) in called_funcs:
                continue
            violations.append(
                f"{path.relative_to(_SRC_DIR)}:{node.lineno}"
            )
    return violations


def _collect_call_sites() -> list[_CallSite]:
    """``src/`` 全体から ``_unexpected_exception_result`` の呼び出しを全部集める。

    ``ast.walk`` は親を教えてくれないので、関数定義を降りながら「いま何の中か」を
    スタックで持って回る。**一番内側の名前だけでなく、外側の名前も全部残す。**
    closure から呼ぶとき、trace に書くべきなのは普通は外側のハンドラ名なので、
    内側の名前との一致を強制すると trace の質が落ちる方へ人を誘導してしまう
    (レビュー指摘)。
    """
    sites: list[_CallSite] = []

    def visit(node: ast.AST, enclosing: tuple[str, ...], helper_names: set[str]) -> None:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            enclosing = enclosing + (node.name,)
        if isinstance(node, ast.Call) and _called_name(node.func) in helper_names:
            sites.append(
                _CallSite(
                    path=path,
                    lineno=node.lineno,
                    enclosing_functions=enclosing,
                    location=_literal_keyword(node, "location"),
                    stage=_literal_keyword(node, "stage"),
                )
            )
        for child in ast.iter_child_nodes(node):
            visit(child, enclosing, helper_names)

    for path in sorted(_SRC_DIR.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        helper_names = _local_names_bound_to_the_helper(tree)
        for child in ast.iter_child_nodes(tree):
            visit(child, (), helper_names)
    # 定義自体 (`def _unexpected_exception_result`) は Call ではないので入らない。
    return sites


_CALL_SITES = _collect_call_sites()


class TestTheGuardActuallyLooksAtSomething:
    """走査が空振りしていない。"""

    def test_call_sites_are_found(self) -> None:
        """executor 群に呼び出しが 1 件以上ある。

        パス構成や関数名が変わってヘルパを 1 件も拾えなくなると、以下の試験は
        全部「対象 0 件で成功」になる。空振りをここで止める。
        """
        assert _CALL_SITES, (
            f"{_HELPER_NAME} の呼び出しが 1 件も見つかりません。"
            f" 走査先: {_SRC_DIR}"
        )

    def test_the_helper_is_defined_in_the_scanned_tree(self) -> None:
        """ヘルパの定義が走査対象のどこかにある (関数名の綴り違いを止める)。"""
        defined = any(
            isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name == _HELPER_NAME
            for path in _SRC_DIR.rglob("*.py")
            for node in ast.walk(ast.parse(path.read_text(encoding="utf-8")))
        )

        assert defined, f"{_HELPER_NAME} の定義が {_SRC_DIR} に見つかりません。"


class TestEveryCallSitePassesItsOwnHandlerName:
    """呼び出し箇所の location が、囲っている関数名と一致する。"""

    @pytest.mark.parametrize("site", _CALL_SITES, ids=repr)
    def test_location_names_one_of_the_enclosing_functions(
        self, site: _CallSite
    ) -> None:
        """``location`` が、その呼び出しを囲む関数のどれかの名前と一致する。

        コピー元の名前を貼り替え忘れる (``_give_item`` の中で ``location=
        "_use_item"`` と書く) と trace が嘘の場所を指すので、それを止める。

        「どれか」で足りるとしたのは、closure の中から呼ぶとき外側のハンドラ名を
        書くのが正しいから。一番内側との一致を強制すると、**テストを緑にする唯一の
        道が「trace に private な closure 名を書くこと」**になり、trace を読む人が
        探すハンドラ名が消える。どちらの名前も grep で辿れるので、嘘でないことだけ
        を要求する (レビュー指摘)。
        """
        assert site.enclosing_functions, (
            f"{site} は関数の外で呼ばれています。location の正しさを確認できません。"
        )
        assert site.location in site.enclosing_functions, (
            f"{site} の location={site.location!r} が、囲っている関数"
            f" {site.enclosing_functions} のどれとも一致しません。"
        )

    @pytest.mark.parametrize("site", _CALL_SITES, ids=repr)
    def test_stage_is_a_string_literal(self, site: _CallSite) -> None:
        """``stage`` が文字列リテラルで渡されている。

        変数や式で渡されると、どの段かがソースを読んだだけでは分からず、
        trace の値から呼び出し箇所へ逆に辿れなくなる。
        """
        assert site.stage is not None, f"{site} に stage が渡されていません。"
        assert site.stage is not _NOT_A_LITERAL, (
            f"{site} の stage が文字列リテラルではありません。"
        )


class TestTheHelperIsOnlyEverCalledDirectly:
    """ヘルパ名を束ね直して見張りをすり抜ける形を禁じる。"""

    def test_the_helper_name_appears_only_in_call_position(self) -> None:
        """ヘルパ名が定義・直接呼び出し・import 以外の位置に現れない。

        ``partial(_unexpected_exception_result, location=...)`` のように一度変数へ
        束ねられると、``location`` のリテラルが呼び出し箇所から消え、AST の見張りが
        何も見なくなる。実際に置いたら 13 passed で素通りした。

        C で同じリテラルが 30〜40 個並ぶと束ねたくなるので、構造で禁じておく。
        """
        violations = _collect_value_position_references()

        assert not violations, (
            f"{_HELPER_NAME} が直接呼び出し以外の位置に現れています: {violations}。"
            " 変数や partial に束ねると location のリテラルが消え、見張りが無効に"
            " なります。束ねたい場合はまず見張り方を設計し直してください。"
        )


class TestTheGuardsDocumentationStaysTrue:
    """ヘルパ側の docstring が指すこの試験の場所が、嘘になっていない。"""

    def test_the_helper_docstring_points_at_an_existing_path(self) -> None:
        """ヘルパの docstring が名指しするテストのパスが実在する。

        ``_unexpected_exception_result`` の docstring は「この試験が見張っている」と
        書いてパスを名指ししている。この試験をリネームすると、その案内が静かに嘘に
        なる (レビュー指摘)。実在確認をここで固定する。
        """
        helper_source = next(
            path
            for path in _SRC_DIR.rglob("*.py")
            if any(
                isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                and node.name == _HELPER_NAME
                for node in ast.walk(ast.parse(path.read_text(encoding="utf-8")))
            )
        )
        text = helper_source.read_text(encoding="utf-8")
        repo_root = _SRC_DIR.parent
        mentioned = [
            token
            for token in text.replace("``", " ").split()
            if token.startswith("tests/") and token.endswith(".py")
        ]

        assert mentioned, (
            f"{helper_source} の docstring が見張りテストのパスを指していません。"
        )
        missing = [t for t in mentioned if not (repo_root / t).exists()]
        assert not missing, f"docstring が実在しないパスを指しています: {missing}"


class TestStagesAreDistinguishableWithinAHandler:
    """同じハンドラの中で stage が重複していない。"""

    def test_no_duplicate_stage_within_the_same_location(self) -> None:
        """同一 ``location`` の中に同じ ``stage`` が 2 つ以上ない。

        重複すると trace の 2 つの値がそろっても呼び出し箇所が一意に決まらず、
        場所を特定するという目的が達せられない。
        """
        seen: dict[tuple[object, object], _CallSite] = {}
        duplicates: list[tuple[_CallSite, _CallSite]] = []
        for site in _CALL_SITES:
            # 非リテラルは値が分からないので重複を判定できない。除外しないと
            # 別々の箇所が「同じ _NOT_A_LITERAL」として重複扱いされ、失敗表示が
            # 人を誤誘導する (レビュー指摘)。非リテラル自体は別の試験が落とす。
            if _NOT_A_LITERAL in (site.location, site.stage):
                continue
            key = (site.location, site.stage)
            if key in seen:
                duplicates.append((seen[key], site))
                continue
            seen[key] = site

        assert not duplicates, f"location と stage の組が重複しています: {duplicates}"
