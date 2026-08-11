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
#: いずれも存在しないモジュールを参照する孤児で、``src/`` と ``tests/`` から
#: 参照が 0 件。循環 import とは別の壊れ方なので、直すのは別の作業にする。
_KNOWN_BROKEN: dict[str, str] = {
    "ai_rpg_world.application.inventory.exceptions.query": (
        "存在しない base_exception を参照する孤児。参照 0 件"
    ),
    "ai_rpg_world.application.inventory.exceptions.query.item_info_query_exception": (
        "同上"
    ),
    "ai_rpg_world.application.inventory.exceptions.query.recipe_info_query_exception": (
        "同上"
    ),
    "ai_rpg_world.infrastructure.mocks.mock_monster": (
        "存在しない domain.battle を参照する孤児。参照 0 件"
    ),
    "ai_rpg_world.infrastructure.mocks.mock_player": "同上",
}


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


def _assert_imports_alone(module_name: str) -> None:
    """新しいインタプリタで import できることを確かめる。"""
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
        "module_name", _OBSERVATION_MODULES, ids=lambda n: n.rsplit(".", 1)[-1]
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
        "module_name", _contract_modules(), ids=lambda n: n.rsplit(".", 1)[-1]
    )
    def test_contract_module_imports_in_a_fresh_interpreter(
        self, module_name: str
    ) -> None:
        """contracts / interfaces のモジュールが単独で import できる。"""
        _assert_imports_alone(module_name)


class TestKnownBrokenModulesAreStillBroken:
    """対象外にした孤児が、直ったのに一覧へ残っていないことを確かめる。"""

    @pytest.mark.parametrize(
        "module_name", sorted(_KNOWN_BROKEN), ids=lambda n: n.rsplit(".", 1)[-1]
    )
    def test_entry_is_not_stale(self, module_name: str) -> None:
        """一覧の項目が今も import できないままである。

        直った項目が残っていると、その後に壊れても見逃す。逆に、直したのに
        一覧から消し忘れた状態もここで気づける。
        """
        completed = subprocess.run(
            [sys.executable, "-c", f"import {module_name}"],
            capture_output=True,
            text=True,
        )

        assert completed.returncode != 0, (
            f"{module_name} は import できるようになっています。"
            f"_KNOWN_BROKEN から消してください (登録理由: {_KNOWN_BROKEN[module_name]})"
        )
