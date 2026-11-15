"""ゲームの世界の application 層に、ドメインの決まりが漏れた形が紛れ込まないよう見張る (#2199)。

application 層は集約と宣言を順に呼ぶだけにする (CLAUDE.md「ドメインモデルは振る舞いで設計する」)。
構文木で次の 4 つの形を見つけたら落とす。

- ドメインの型で見分ける: isinstance の第 2 引数、または match の case のクラスが game_world.domain の型
- None を見て分岐する: None との比較 (is / is not / == / !=) と case None
- 知覚の値をその場で作る: 目立ち方・知覚の品質・刺激の型のコンストラクタを直に呼ぶ。クラスメソッドのファクトリは落とさない
- ドメインの値を取り出して比べる: 順序比較と == / != (None を除く) のうち、片側が属性か呼び出しのもの

見ないもの: in / not in (帳簿やキャッシュの引き当て)、ドメインに問うて分岐する手順 (`if item.has_run_out(now):`)。
後者は複数の集約を順に呼ぶ手順と構文で見分けられないので、レビューの観点で補う。
名前は import 文だけから追うので、別名の代入 (`N = Notable`)、ワイルドカード import、`type(x) is 型` は追わない。
"""

from __future__ import annotations

import ast
import importlib
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_APPLICATION_ROOT = _REPO_ROOT / "src/ai_rpg_world/game_world/application"
_APPLICATION_PACKAGE = "ai_rpg_world.game_world.application"
_DOMAIN_PACKAGE = "ai_rpg_world.game_world.domain"

_PERCEPTION_VALUE_MODULES = frozenset(
    {
        f"{_DOMAIN_PACKAGE}.perception.salience",
        f"{_DOMAIN_PACKAGE}.perception.perceived_quality",
        f"{_DOMAIN_PACKAGE}.perception.surroundings_awareness",
        f"{_DOMAIN_PACKAGE}.perception.announcement_stimulus",
        f"{_DOMAIN_PACKAGE}.perception.bodily_stimulus",
        f"{_DOMAIN_PACKAGE}.perception.sight_stimulus",
        f"{_DOMAIN_PACKAGE}.perception.sound_stimulus",
        f"{_DOMAIN_PACKAGE}.lighting.sight_quality",
        f"{_DOMAIN_PACKAGE}.sound.hearing_quality",
    }
)

_EXTRACTED_VALUE_COMPARISONS = (ast.Lt, ast.LtE, ast.Gt, ast.GtE, ast.Eq, ast.NotEq)


@dataclass(frozen=True)
class _Shape:
    label: str
    hint: str


TYPE_SWITCH = _Shape(
    "ドメインの型を isinstance / match で見分けている",
    "型ごとの違いは、その型のメソッドに置き、application 層はそのメソッドを呼ぶだけにする",
)
NONE_BRANCH = _Shape(
    "None を見て分岐している",
    "無いことをドメインの型で表し (例: DeadPerceiver)、その型に振る舞いを持たせる",
)
PERCEPTION_VALUE = _Shape(
    "知覚の値をその場で作っている",
    "目立ち方・知覚の品質・刺激は、宣言や値オブジェクトのファクトリに作らせる (例: BodilyStimulus.on_waking)",
)
EXTRACTED_COMPARISON = _Shape(
    "ドメインの値を取り出して比べている",
    "比べる決まりは、その値を持つ集約・値オブジェクトのメソッドに置く",
)


@dataclass(frozen=True)
class _Leak:
    path: str
    line: int
    shape: _Shape
    source: str

    def explained(self) -> str:
        return (
            f"{self.path}:{self.line}: {self.shape.label}: {self.source}\n"
            f"    直し方: {self.shape.hint}。ドメインの集約・値オブジェクトに振る舞いを置く"
        )


@dataclass(frozen=True)
class _AllowedLeak:
    path: str
    shape: _Shape
    marker: str
    reason: str

    def __post_init__(self) -> None:
        if not self.reason.strip():
            raise ValueError(f"allowed leak in {self.path} ({self.marker!r}) has no reason")

    def covers(self, leak: _Leak) -> bool:
        return leak.path == self.path and leak.shape == self.shape and self.marker in leak.source


_EXIT_TO_BEING_CONTRACT = "写し先が being.contract の型なので、game_world の型を観測の出口で写す"

_ALLOWED_LEAKS: tuple[_AllowedLeak, ...] = (
    _AllowedLeak("observation_exit.py", TYPE_SWITCH, "case PersonRef():", _EXIT_TO_BEING_CONTRACT),
    _AllowedLeak("observation_exit.py", TYPE_SWITCH, "case Unidentified():", _EXIT_TO_BEING_CONTRACT),
    _AllowedLeak("observation_exit.py", TYPE_SWITCH, "case DisplayName():", _EXIT_TO_BEING_CONTRACT),
    _AllowedLeak("observation_exit.py", TYPE_SWITCH, "case NoVisibleName():", _EXIT_TO_BEING_CONTRACT),
    _AllowedLeak(
        "action/carry_out_action.py",
        NONE_BRANCH,
        "if failure is not None:",
        "全行為の ActionSteps.unmet_precondition が欠けを None で返す。前提の確かめで None を見て分けない形に #2200 で直す",
    ),
)


def _is_within(module: str, package: str) -> bool:
    return module == package or module.startswith(package + ".")


def _resolve_from(node: ast.ImportFrom, package: str) -> str:
    if node.level == 0:
        return node.module or ""
    parts = package.split(".")
    anchor = parts[: len(parts) - (node.level - 1)]
    return ".".join(anchor + ([node.module] if node.module else []))


def _package_of(path: Path, root: Path) -> str:
    return ".".join([_APPLICATION_PACKAGE, *path.relative_to(root).parent.parts])


def _imported_names(tree: ast.Module, package: str) -> dict[str, str]:
    names: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            base = _resolve_from(node, package)
            for alias in node.names:
                names[alias.asname or alias.name] = f"{base}.{alias.name}"
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.asname:
                    names[alias.asname] = alias.name
                else:
                    top = alias.name.split(".")[0]
                    names[top] = top
    return names


def _load(qualified: str) -> Any:
    try:
        return importlib.import_module(qualified)
    except ModuleNotFoundError as missing:
        # 名前がモジュールでなく属性のときだけ親から引く。依存の欠けなど別の原因は隠さない
        if missing.name != qualified:
            raise
        module, _, attribute = qualified.rpartition(".")
        return getattr(importlib.import_module(module), attribute)


def _attribute_of(owner: Any, attribute: str) -> Any:
    if isinstance(owner, ModuleType) and not hasattr(owner, attribute):
        return _load(f"{owner.__name__}.{attribute}")
    return getattr(owner, attribute, None)


class _Resolver:
    def __init__(self, imported: dict[str, str]) -> None:
        self._imported = imported

    def resolve(self, node: ast.expr) -> Any:
        if isinstance(node, ast.Name):
            qualified = self._imported.get(node.id)
            if qualified is None or not _is_within(qualified, "ai_rpg_world"):
                return None
            return _load(qualified)
        if isinstance(node, ast.Attribute):
            owner = self.resolve(node.value)
            return _attribute_of(owner, node.attr) if owner is not None else None
        return None

    def domain_types(self, node: ast.expr) -> list[type]:
        candidates = node.elts if isinstance(node, ast.Tuple) else [node]
        resolved = [self.resolve(candidate) for candidate in candidates]
        return [obj for obj in resolved if isinstance(obj, type) and obj.__module__.startswith(_DOMAIN_PACKAGE + ".")]


def _is_none(node: ast.expr) -> bool:
    return isinstance(node, ast.Constant) and node.value is None


def _shape_of(node: ast.AST, resolver: _Resolver) -> _Shape | None:
    if isinstance(node, ast.Call):
        if isinstance(node.func, ast.Name) and node.func.id == "isinstance" and len(node.args) == 2:
            return TYPE_SWITCH if resolver.domain_types(node.args[1]) else None
        built = resolver.resolve(node.func)
        if isinstance(built, type) and built.__module__ in _PERCEPTION_VALUE_MODULES:
            return PERCEPTION_VALUE
        return None
    if isinstance(node, ast.MatchClass):
        return TYPE_SWITCH if resolver.domain_types(node.cls) else None
    if isinstance(node, ast.MatchSingleton):
        return NONE_BRANCH if node.value is None else None
    if isinstance(node, ast.Compare):
        operands = [node.left, *node.comparators]
        if any(_is_none(operand) for operand in operands):
            return NONE_BRANCH
        if any(isinstance(op, _EXTRACTED_VALUE_COMPARISONS) for op in node.ops) and any(
            isinstance(operand, (ast.Attribute, ast.Call)) for operand in operands
        ):
            return EXTRACTED_COMPARISON
    return None


def _leaks_in(path: Path, root: Path) -> list[_Leak]:
    source = path.read_text(encoding="utf-8")
    lines = source.splitlines()
    tree = ast.parse(source, filename=str(path))
    resolver = _Resolver(_imported_names(tree, _package_of(path, root)))
    relative = path.relative_to(root).as_posix()
    found: list[_Leak] = []
    for node in ast.walk(tree):
        shape = _shape_of(node, resolver)
        if shape is None:
            continue
        line = getattr(node, "lineno")
        found.append(_Leak(relative, line, shape, lines[line - 1].strip()))
    return sorted(found, key=lambda leak: (leak.path, leak.line, leak.shape.label))


def _all_leaks(root: Path) -> list[_Leak]:
    paths = sorted(root.rglob("*.py"))
    assert paths, f"no modules under {root}"
    return [leak for path in paths for leak in _leaks_in(path, root)]


def _unallowed(leaks: list[_Leak], allowed: tuple[_AllowedLeak, ...]) -> list[_Leak]:
    return [leak for leak in leaks if not any(entry.covers(leak) for entry in allowed)]


def _report(leaks: list[_Leak]) -> str:
    return "application 層にドメインの決まりが漏れている:\n" + "\n".join(leak.explained() for leak in leaks)


def test_game_world_application_has_no_leaked_domain_rules() -> None:
    """game_world/application のどのファイルにも、許可の一覧に載っていない 4 つの形が無い。"""
    unallowed = _unallowed(_all_leaks(_APPLICATION_ROOT), _ALLOWED_LEAKS)

    assert unallowed == [], _report(unallowed)


def test_every_allowed_leak_still_matches_the_code() -> None:
    """許可の一覧のどの項目も、いまのコードの漏れにちょうど 1 か所当たる。直したら一覧から外す。"""
    leaks = _all_leaks(_APPLICATION_ROOT)

    matches = {entry.marker: sum(entry.covers(leak) for leak in leaks) for entry in _ALLOWED_LEAKS}

    assert matches == {entry.marker: 1 for entry in _ALLOWED_LEAKS}


def test_allowed_leak_without_reason_is_rejected() -> None:
    """理由が空の例外は、許可の一覧に載せようとした時点で ValueError になる。"""
    with pytest.raises(ValueError):
        _AllowedLeak("observation_exit.py", TYPE_SWITCH, "case PersonRef():", " ")


_NO_WEATHER = "from ai_rpg_world.game_world.domain.declaration.time_and_weather.weather_state import NoWeather\n"
_REACHED = "from ai_rpg_world.game_world.domain.world_progress.group_decision import GroupDecisionReachedEvent\n"


@pytest.mark.parametrize(
    ("source", "shape"),
    [
        (_NO_WEATHER + "def f(w):\n    if isinstance(w, NoWeather):\n        pass\n", TYPE_SWITCH),
        (_REACHED + "def f(e):\n    return isinstance(e, (int, GroupDecisionReachedEvent))\n", TYPE_SWITCH),
        (
            "from ai_rpg_world.game_world.domain.declaration import time_and_weather\n"
            "def f(w):\n    return isinstance(w, time_and_weather.weather_state.NoWeather)\n",
            TYPE_SWITCH,
        ),
        (_NO_WEATHER + "def f(w):\n    match w:\n        case NoWeather():\n            pass\n", TYPE_SWITCH),
        ("def f(p):\n    if p is None:\n        pass\n", NONE_BRANCH),
        ("def f(p):\n    return 1 if p is not None else 2\n", NONE_BRANCH),
        ("def f(p):\n    return [x for x in p if x != None]\n", NONE_BRANCH),
        ("def f(p):\n    match p:\n        case None:\n            pass\n", NONE_BRANCH),
        ("from ai_rpg_world.game_world.domain.perception import Notable\nNotable()\n", PERCEPTION_VALUE),
        ("from ai_rpg_world.game_world.domain.lighting import SeesClearly\nSeesClearly()\n", PERCEPTION_VALUE),
        ("from ai_rpg_world.game_world.domain import perception\nperception.Felt()\n", PERCEPTION_VALUE),
        (
            "import ai_rpg_world.game_world.domain.lighting.sight_quality\n"
            "ai_rpg_world.game_world.domain.lighting.sight_quality.SeesShapes()\n",
            PERCEPTION_VALUE,
        ),
        (
            "from ai_rpg_world.game_world.domain.perception.bodily_stimulus import BodilyStimulus as B\n"
            "def f(p, t, at):\n    return B(person=p, text=t, salience=None, at=at)\n",
            PERCEPTION_VALUE,
        ),
        ("def f(item, now):\n    return item.expires_at <= now\n", EXTRACTED_COMPARISON),
        ("def f(a, b):\n    return a.value == b.value\n", EXTRACTED_COMPARISON),
        ("def f(stock):\n    return stock.count() > 0\n", EXTRACTED_COMPARISON),
    ],
)
def test_leaked_shape_is_reported_with_file_and_shape(tmp_path: Path, source: str, shape: _Shape) -> None:
    """application 層に 4 つの形のどれかを書くと、そのファイルと形が報告される。"""
    (tmp_path / "module.py").write_text(source, encoding="utf-8")

    leaks = _all_leaks(tmp_path)

    assert [(leak.path, leak.shape) for leak in leaks] == [("module.py", shape)]


@pytest.mark.parametrize(
    "source",
    [
        "def f(event, registration):\n    return isinstance(event, registration.event_type)\n",
        "def f(x):\n    return isinstance(x, (int, str))\n",
        "from ai_rpg_world.eventing import DomainEvent\ndef f(e):\n    return isinstance(e, DomainEvent)\n",
        "from ai_rpg_world.game_world.domain.perception import BodilyStimulus\n"
        "def f(p, t, at):\n    return BodilyStimulus.on_waking(p, t, at)\n",
        "from ai_rpg_world.game_world.domain.perception import ItemRanOutNotice\n"
        "def f(t, at):\n    return ItemRanOutNotice(t, at)\n",
        "def f(self, spot):\n    return spot not in self._lighting\n",
        "def f(a, b):\n    return a < b\n",
        "def f(self, occasion):\n    return self is occasion.AFTER\n",
        "def f(item, now):\n    if item.has_run_out(now):\n        item.run_out(now)\n",
        "def f(p):\n    match p:\n        case int():\n            pass\n        case _:\n            pass\n",
    ],
)
def test_shapes_outside_the_watch_are_not_reported(tmp_path: Path, source: str) -> None:
    """ドメイン外の型の isinstance、ファクトリ、in による引き当て、名前どうしの比較、問うて分岐する手順は報告しない。"""
    (tmp_path / "module.py").write_text(source, encoding="utf-8")

    assert _all_leaks(tmp_path) == []


def test_leak_on_the_allowed_list_does_not_fail(tmp_path: Path) -> None:
    """許可の一覧にファイル・形・行の目印が合う項目があれば、その漏れは落ちず、同じファイルのほかの漏れは落ちる。"""
    (tmp_path / "module.py").write_text(
        "def f(p, q):\n    if p is None:\n        pass\n    if q is None:\n        pass\n", encoding="utf-8"
    )
    allowed = (_AllowedLeak("module.py", NONE_BRANCH, "if p is None:", "例外の理由"),)

    unallowed = _unallowed(_all_leaks(tmp_path), allowed)

    assert [leak.source for leak in unallowed] == ["if q is None:"]


def test_failure_message_names_file_shape_and_how_to_fix(tmp_path: Path) -> None:
    """落ちたときの文面に、ファイルと行、形、直し方の手がかりが出る。"""
    (tmp_path / "module.py").write_text(
        _NO_WEATHER + "def f(w):\n    return isinstance(w, NoWeather)\n", encoding="utf-8"
    )

    message = _report(_all_leaks(tmp_path))

    assert "module.py:3: ドメインの型を isinstance / match で見分けている: return isinstance(w, NoWeather)" in message
    assert "ドメインの集約・値オブジェクトに振る舞いを置く" in message
