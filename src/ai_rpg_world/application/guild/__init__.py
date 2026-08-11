"""guild 文脈のアプリケーション層。

## services の実装をここで再輸出しない理由

以前はここで ``GuildCommandService`` を再輸出していた。**そのためこのパッケージ配下の
submodule を 1 つ import すると、services 一式が読み込まれた。** Python は
パッケージの ``__init__`` を先に実行するので、小さな DTO を 1 つ取るだけで
実装まで付いてくる。

これが循環 import の火種になる (#1018 で ``llm`` 側が実際に発火した:
観測層の型定義が ``llm.contracts.dtos`` を引いたら ``llm/__init__.py`` 経由で
``prompt_builder_config`` が読み込まれ、観測層へ戻ってきた)。

再輸出は ``from ai_rpg_world.application.guild import ...`` の形で一度も使われて
いなかった (``src/`` ``tests/`` ``scripts/`` で 0 件)。利用側は実体のモジュールを
直接指している。**火種だけを抱えて利点は無かった。**

契約 (contracts) と例外は軽いのでここに残す。**実装は各モジュールから直接
import する。**
"""

from ai_rpg_world.application.guild.contracts.commands import (
    CreateGuildCommand,
    AddGuildMemberCommand,
    LeaveGuildCommand,
    ChangeGuildRoleCommand,
)
from ai_rpg_world.application.guild.contracts.dtos import GuildCommandResultDto

__all__ = [
    "CreateGuildCommand",
    "AddGuildMemberCommand",
    "LeaveGuildCommand",
    "ChangeGuildRoleCommand",
    "GuildCommandResultDto",
]
