"""モジュールが単独で import できること (循環 import が無いこと) を保証する。

## なぜこの試験が要るか

フルスイートでは import 順が揃うので循環が隠れる。実際 2026-08-11 まで
``uv run pytest tests/application/observation`` 単体が collection error で
1 件も走らない状態が続いていた。原因は次の循環。

    application/observation/contracts/interfaces.py
      → application/llm/contracts/dtos (ToolRuntimeContextDto)
        → application/llm/__init__.py が services 一式を読み込む
          → services/prompt_builder.py
            → services/prompt_builder_config.py
              → application/observation/contracts/interfaces.py  ← 戻る

**観測周りを触っている人が、該当ファイルだけを走らせようとすると最初に
つまずく形**なので、フルスイートが緑でも直す価値がある。

火種は llm/__init__.py が services 一式を再輸出していたことで、llm 配下の
submodule を 1 つ import するだけで prompt_builder まで付いてきた。そこを外すと
循環は消える。観測層側も型定義が実装を実行時に引かない形へ直したので、**両方が
戻ったときにここが落ちる**。

ここは **新しいインタプリタを起こして** import する。同じプロセスで試すと、
先に読み込まれた別モジュールが循環を埋めてしまい、試験が空振りする。
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

_SRC = Path(__file__).resolve().parents[2] / "src"

#: 単独 import を保証する観測層のモジュール。
#:
#: contracts (入口の型定義) と、そこから最短で辿れる代表的な services を選ぶ。
#: 観測層の全モジュールを列挙しないのは、循環は「層をまたぐ辺」で起きるので
#: 入口を押さえれば足りるため。
_OBSERVATION_MODULES = [
    "ai_rpg_world.application.observation.contracts.interfaces",
    "ai_rpg_world.application.observation.contracts.dtos",
    "ai_rpg_world.application.observation.services.observation_pipeline",
    "ai_rpg_world.application.observation.services.observation_recipient_resolver",
    "ai_rpg_world.application.observation.services.observed_event_registry",
    (
        "ai_rpg_world.application.observation.services.recipient_strategies"
        ".spot_graph_recipient_strategy"
    ),
    "ai_rpg_world.application.observation.services.formatters.combat_formatter",
]

#: 単独 import で落ちるが、**この試験の対象外**にするモジュールと理由。
#:
#: 空にしておくのが正しい状態。ここへ足すのは「循環 import とは別の壊れ方を
#: しているが、今は直さない」と決めたときだけで、必ず理由を書く。
#:
#: 2026-08-11 の時点では 5 件あった (存在しない ``domain.battle`` /
#: ``inventory.exceptions.base_exception`` を参照する孤児)。参照 0 件の削除漏れ
#: だったので #1024 で消し、この一覧は空に戻った。
_KNOWN_BROKEN: dict[str, str] = {}


def _contract_modules() -> list[str]:
    """``contracts/`` 配下と ``interfaces.py`` のモジュール名を集める。

    層の **内側** にある型定義が外側の実装を実行時に引くと循環になる。今回の
    欠陥がまさにその形だったので、同じ位置にあるモジュールを一括で見張る。
    """
    found: list[str] = []
    for path in sorted(_SRC.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        if "contracts" not in path.parts and path.name != "interfaces.py":
            continue
        parts = list(path.relative_to(_SRC).with_suffix("").parts)
        if parts[-1] == "__init__":
            parts = parts[:-1]
        if not parts:
            continue
        name = ".".join(parts)
        if name not in _KNOWN_BROKEN:
            found.append(name)
    return found


def _module_id(module_name: str) -> str:
    """pytest の ID にモジュールパスを使う。

    末尾だけを使うと ``contracts`` / ``dtos`` / ``interfaces`` が複数箇所に
    あるため ``contracts6`` のように自動採番され、``-k`` で狙えない。
    """
    return module_name.replace("ai_rpg_world.", "").replace(".", "/")


def _assert_imports_alone(module_name: str) -> None:
    """新しいインタプリタで import できることを確かめる。

    ``sys.executable`` を使うので、パッケージが editable install されている
    前提 (``make dev-install`` / ``uv run``) に依存する。CI 環境を変えて
    ``ModuleNotFoundError: ai_rpg_world`` が出たら、まずそこを疑う。
    """
    completed = subprocess.run(
        [sys.executable, "-c", f"import {module_name}"],
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, (
        f"{module_name} を単独で import できません。\n"
        "循環 import の疑いがあります (層をまたぐ辺を TYPE_CHECKING 下へ "
        "移すか、依存の向きを直してください)。\n\n"
        + completed.stderr[-2000:]
    )


class TestObservationModulesImportOnTheirOwn:
    """観測層の入口モジュールが、他を先に読み込まなくても import できる。"""

    @pytest.mark.parametrize(
        "module_name", _OBSERVATION_MODULES, ids=_module_id
    )
    def test_module_imports_in_a_fresh_interpreter(self, module_name: str) -> None:
        """新しいインタプリタで import しても ImportError にならない。

        循環 import があると、その層だけを走らせる pytest が collection error に
        なり、テストが 1 件も実行されない。
        """
        _assert_imports_alone(module_name)


class TestContractModulesImportOnTheirOwn:
    """層の内側にある型定義が、外側の実装を実行時に引いていない。

    今回の欠陥は ``observation/contracts/interfaces.py`` が
    ``application.llm`` の実装一式を実行時に引いたことだった。同じ位置にある
    モジュールを一括で見張り、同じ形が別の文脈で生まれたら落とす。
    """

    @pytest.mark.parametrize(
        "module_name", _contract_modules(), ids=_module_id
    )
    def test_contract_module_imports_in_a_fresh_interpreter(
        self, module_name: str
    ) -> None:
        """contracts / interfaces のモジュールが単独で import できる。"""
        _assert_imports_alone(module_name)


class TestKnownBrokenModulesAreStillBroken:
    """対象外にした孤児が、直ったのに一覧へ残っていないことを確かめる。

    **``_KNOWN_BROKEN`` は空が正しい状態**なので、parametrize ではなく内部で
    回す。parametrize にすると空の一覧が
    ``empty_parameter_set_mark = fail_at_collect`` で collection error になり、
    「対象外が無い」という正常な状態を落としてしまう。
    """

    def test_the_allowlist_is_empty(self) -> None:
        """一覧が空である。

        **空が正しい状態**なので、それを仕様として固定する。下の 2 つは一覧が
        空の間はループ 0 回で自明に成立するため、「空であること」自体は
        ここでしか守られない。

        ここが落ちたときは、単独 import できないモジュールを誰かが対象外へ
        逃がしたということ。理由を読んで、直すか追跡先を作るか決める。
        """
        assert not _KNOWN_BROKEN, (
            "単独 import できないモジュールが対象外へ登録されています。"
            f"直すか issue を立ててください: {sorted(_KNOWN_BROKEN)}"
        )

    def test_no_entry_is_stale(self) -> None:
        """一覧の項目が今も import できないままである。

        直った項目が残っていると、その後に壊れても見逃す。逆に、直したのに
        一覧から消し忘れた状態もここで気づける。

        **一覧が空の間はループが 0 回で自明に成立する。** 空であることは上の
        ``test_the_allowlist_is_empty`` が守る。
        """
        fixed = []
        for module_name, reason in sorted(_KNOWN_BROKEN.items()):
            completed = subprocess.run(
                [sys.executable, "-c", f"import {module_name}"],
                capture_output=True,
                text=True,
            )
            if completed.returncode == 0:
                fixed.append(f"{module_name} (登録理由: {reason})")

        assert not fixed, (
            "import できるようになった項目が _KNOWN_BROKEN に残っています。"
            "消してください: " + " / ".join(fixed)
        )

    def test_every_entry_states_a_reason(self) -> None:
        """一覧の理由が空文字列でない。

        理由欄があっても空で登録できるなら「登録すれば無検査で通る」抜け道が
        残る。**一覧が空の間は自明に成立する。**
        """
        blank = sorted(
            name for name, reason in _KNOWN_BROKEN.items() if not reason.strip()
        )

        assert not blank, f"対象外にした理由が書かれていません: {blank}"


class TestTheGuardedPopulationIsNotEmpty:
    """走査が壊れて「保証 0 件」に縮退していないことを確かめる。"""

    def test_contract_modules_are_actually_found(self) -> None:
        """``_contract_modules()`` が十分な数のモジュールを見つけている。

        パス計算のずれ (``parents`` の数)、``contracts/`` の改名、判定の書き
        間違いで走査が空になると、**parametrize は 1 件 skip になるだけで
        終了コードは 0** になる。pytest.ini の
        ``empty_parameter_set_mark = fail_at_collect`` でも落ちるが、こちらは
        「何件あるべきか」を数で明示して、静かに半減する形も捕まえる。
        """
        found = _contract_modules()

        assert len(found) >= 40, (
            f"contracts / interfaces のモジュールが {len(found)} 件しか"
            f"見つかりません (2026-08-11 時点で 48 件)。走査条件か _SRC "
            f"({_SRC}) を確認してください"
        )

    def test_the_known_target_is_in_the_guarded_set(self) -> None:
        """今回の欠陥があったモジュールが、走査範囲に入っている。

        件数だけ見ていると、別の 40 件を拾って本命が漏れていても気づけない。
        """
        assert (
            "ai_rpg_world.application.observation.contracts.interfaces"
            in _contract_modules()
        )


#: パッケージごとに「軽い submodule を 1 つ import したときに読み込まれる
#: ``ai_rpg_world`` モジュール数の上限」。
#:
#: Python はパッケージの ``__init__`` を先に実行するので、``__init__`` が実装を
#: 再輸出していると **小さな DTO を 1 つ取るだけで実装が全部読み込まれる**。
#: これが循環 import の火種で、#1018 で実際に発火した (観測層の型定義が
#: ``llm.contracts.dtos`` を引いたら ``llm/__init__.py`` 経由で
#: ``prompt_builder_config`` が読み込まれ、観測層へ戻ってきた)。
#:
#: **上限を置かないと、再輸出を戻す変更が誰にも止められない。** 実測で、
#: ``guild/__init__.py`` に再輸出を戻しても全 13,437 件が緑のままだった。
#:
#: 括弧内は #1024 で外した時点の実測値。上限は実測値 + 少しの余裕で置く。
#: 増やすときは「なぜ増えて良いか」を書くこと。**素直に増やすと火種が戻る。**
_MAX_MODULES_ON_IMPORT: dict[str, int] = {
    # world_graph: 238 → 4
    "ai_rpg_world.application.world_graph.distant_view_service": 20,
    # harvest: 160 → 6
    "ai_rpg_world.application.harvest.contracts.commands": 20,
    # guild: 144 → 6
    "ai_rpg_world.application.guild.contracts.commands": 20,
    # speech: 121 → 13
    "ai_rpg_world.application.speech.contracts.commands": 30,
    # inventory: 58 → 11
    "ai_rpg_world.application.inventory.exceptions": 30,
    # llm: #1018 で services の再輸出を外した先。実測 82 で他より大きいが、
    # 内訳は domain.memory 27 / domain.player 9 など **この DTO 自身のドメイン
    # 依存**で、パッケージ再輸出の問題ではない。再輸出が戻れば 82 を大きく
    # 超えるので、上限としては機能する。
    "ai_rpg_world.application.llm.contracts.dtos": 110,
}

_COUNT_MODULES = (
    "import sys, {module};"
    " print(len([m for m in sys.modules if m.startswith('ai_rpg_world')]))"
)


class TestPackageInitDoesNotDragInImplementations:
    """パッケージの ``__init__`` が実装一式を引き込んでいない。

    ``__init__`` に実装の再輸出を足すと、この上限を超えて落ちる。#1024 で外した
    再輸出が「便利だから」と戻されるのを、ここで機械的に止める。

    件数そのものに意味はない。**桁が変わったら設計が変わった**、という粗い網。
    """

    @pytest.mark.parametrize(
        ("module_name", "limit"),
        sorted(_MAX_MODULES_ON_IMPORT.items()),
        ids=lambda v: _module_id(v) if isinstance(v, str) else str(v),
    )
    def test_importing_a_light_submodule_stays_light(
        self, module_name: str, limit: int
    ) -> None:
        """軽い submodule を 1 つ import しても、読み込みが上限を超えない。

        新しいインタプリタで数える。同じプロセスだと先に読み込まれた分が
        混ざって数えられない。
        """
        completed = subprocess.run(
            [sys.executable, "-c", _COUNT_MODULES.format(module=module_name)],
            capture_output=True,
            text=True,
        )

        assert completed.returncode == 0, (
            f"{module_name} を import できません:\n{completed.stderr[-1000:]}"
        )
        loaded = int(completed.stdout.strip())
        assert loaded <= limit, (
            f"{module_name} を 1 つ import しただけで ai_rpg_world モジュールが "
            f"{loaded} 個読み込まれました (上限 {limit})。\n"
            "パッケージの __init__.py が実装を再輸出していないか確認してください。"
            "循環 import の火種になります (#1018 / #1024)。"
        )
