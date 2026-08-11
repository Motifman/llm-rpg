"""LLM 向け表示・記憶層（プロンプト組み立て・観測・行動結果の統合）

## services の実装をここで再輸出しない理由

以前はここで ``llm.services`` の実装 (``DefaultPromptBuilder`` など 7 個) を
再輸出していた。**そのため ``llm`` 配下のどの submodule を 1 つ import しても、
services 一式が読み込まれた。** Python はパッケージの ``__init__`` を先に実行
するので、``llm.contracts.dtos`` から DTO を 1 つ取るだけで prompt_builder まで
付いてくる。

これが循環 import の火種になった。``observation/contracts/interfaces.py`` が
``llm.contracts.dtos`` から型を 1 つ引いたところ、この ``__init__`` 経由で
``llm.services.prompt_builder_config`` が読み込まれ、そこから
``observation.contracts.interfaces`` へ戻ってきた。

再輸出された 7 個は **``from ai_rpg_world.application.llm import ...`` の形で
一度も使われていなかった** (``src/`` ``tests/`` ``scripts/`` で 0 件を確認)。
利用側はいずれも実体のモジュールを直接指している
(例: ``from ...llm.services.prompt_builder import DefaultPromptBuilder``)。
つまり火種だけを抱えて、利点は無かった。

契約 (contracts) と例外は軽いのでここに残す。**実装は各モジュールから直接
import する。**

同じ形の再輸出は ``application/guild/__init__.py`` と
``application/speech/__init__.py`` にも残っている (#1024)。
"""

from ai_rpg_world.application.llm.contracts import (
    ActionResultEntry,
    SystemPromptPlayerInfoDto,
    IActionResultStore,
    IContextFormatStrategy,
    ICurrentStateFormatter,
    IPromptBuilder,
    IRecentEventsFormatter,
    IShortTermMemory,
    ISystemPromptBuilder,
)
from ai_rpg_world.application.llm.exceptions import (
    LlmApplicationException,
    PlayerProfileNotFoundForPromptException,
)


__all__ = [
    "ActionResultEntry",
    "SystemPromptPlayerInfoDto",
    "IActionResultStore",
    "IContextFormatStrategy",
    "ICurrentStateFormatter",
    "IPromptBuilder",
    "IRecentEventsFormatter",
    "IShortTermMemory",
    "ISystemPromptBuilder",
    "LlmApplicationException",
    "PlayerProfileNotFoundForPromptException",
]
