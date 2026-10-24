"""共通の配送器に、ゲームのコマンドの文脈の型を指定する。"""

from typing import Any

from ai_rpg_world.application.common.command_scope import CommandContext
from ai_rpg_world.eventing.dispatcher import EventDispatcher


class CommandEventDispatcher(EventDispatcher[CommandContext[Any]]):
    """既存の組み立てと登録で使う、ゲーム向けの配送器。"""
