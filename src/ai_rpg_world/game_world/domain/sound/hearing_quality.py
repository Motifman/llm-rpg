from __future__ import annotations

from dataclasses import dataclass
from typing import Union, final


@final
@dataclass(frozen=True)
class HearsClearly: ...


@final
@dataclass(frozen=True)
class HearsMuffled: ...


@final
@dataclass(frozen=True)
class HearsFaintly: ...


@final
@dataclass(frozen=True)
class HearsNothing: ...


HearingQuality = Union[HearsClearly, HearsMuffled, HearsFaintly, HearsNothing]
