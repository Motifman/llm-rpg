"""環境が毎ターン渡す、行動の選択肢 (design_decisions D2226)。"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Union

from ai_rpg_world.being.contract.errors import ContractViolation, require_bool, require_optional_text, require_text
from ai_rpg_world.being.contract.text_with_people import PersonInText, TextWithPeople

_NAME_LIMIT = 64


def _require_name(value: object, field_name: str) -> None:
    # 名前は LLM のツールと引数の名前になる。provider の多くは ASCII の識別子で 64 文字までに限る。
    if not isinstance(value, str) or not value.isascii() or not value.isidentifier() or len(value) > _NAME_LIMIT:
        raise ContractViolation(f"{field_name} must be an ASCII identifier, got {value!r}")


def _require_label(value: object, field_name: str) -> None:
    if not isinstance(value, PersonInText):
        require_text(value, field_name)


def _label_key(label: str | PersonInText) -> object:
    return label.handle if isinstance(label, PersonInText) else label


@dataclass(frozen=True, kw_only=True)
class FreeText:
    name: str
    label: str
    writes: str | None = None

    def __post_init__(self) -> None:
        _require_name(self.name, "name")
        require_text(self.label, "label")
        require_optional_text(self.writes, "writes")


@dataclass(frozen=True, kw_only=True)
class Candidate:
    """``shown_under`` は、道筋の最初の段の候補を並べて見せるときに頭に置く名前 (例: 籠に乗り込むの、昇降機の籠)。"""

    label: str | PersonInText
    values: Sequence[ChoiceValue] = field(default_factory=tuple)
    count: int = 1
    shown_under: str | None = None

    def __post_init__(self) -> None:
        _require_label(self.label, "label")
        require_optional_text(self.shown_under, "shown_under")
        object.__setattr__(self, "values", _values(self.values))
        if isinstance(self.count, bool) or not isinstance(self.count, int) or self.count < 1:
            raise ContractViolation(f"count must be a positive int, got {self.count!r}")

    def people(self) -> tuple[PersonInText, ...]:
        own = (self.label,) if isinstance(self.label, PersonInText) else ()
        return own + _people_in(self.values)


@dataclass(frozen=True, kw_only=True)
class PickOne:
    """``writes`` は、候補を並べないときに、何を書くかを伝える言葉 (例: 奪う品の名前)。"""

    name: str
    label: str
    candidates: Sequence[Candidate]
    writes: str | None = None

    def __post_init__(self) -> None:
        _require_name(self.name, "name")
        require_text(self.label, "label")
        require_optional_text(self.writes, "writes")
        candidates = tuple(self.candidates)
        if not all(isinstance(c, Candidate) for c in candidates):
            raise ContractViolation("candidates must be Candidate items")
        keys = [_label_key(c.label) for c in candidates]
        if len(set(keys)) != len(keys):
            raise ContractViolation(f"candidates must not repeat a label in {self.name!r}")
        object.__setattr__(self, "candidates", candidates)

    def people(self) -> tuple[PersonInText, ...]:
        return tuple(person for candidate in self.candidates for person in candidate.people())


ChoiceValue = Union[FreeText, PickOne]


def _values(items: Sequence[ChoiceValue]) -> tuple[ChoiceValue, ...]:
    values = tuple(items)
    if not all(isinstance(v, (FreeText, PickOne)) for v in values):
        raise ContractViolation("values must be FreeText or PickOne items")
    names = [v.name for v in values]
    if len(set(names)) != len(names):
        raise ContractViolation(f"values must not repeat a name: {names}")
    return values


def _people_in(values: Sequence[ChoiceValue]) -> tuple[PersonInText, ...]:
    return tuple(person for value in values if isinstance(value, PickOne) for person in value.people())


@dataclass(frozen=True, kw_only=True)
class ArgumentOutline:
    """``required`` は、いちばん上の値として毎ターン必ず渡る引数。

    ``hidden_as`` は、自由に書いた値を【直近の出来事】の呼び出しの行で伏せるときの言葉 (例: 発言)。自由に書いた文を
    そのまま引用すると、手本として写されるため。

    ``listed`` は、候補をこのターンの場面のほかの所で見せていないので、Being が並べて見せる引数 (例: 対象ごとの操作)。
    ``fixed_values`` は、どのターンでも同じ値から選ぶ引数の値 (例: 話し方)。ツールの定義に書いてよい。
    """

    name: str
    label: str
    required: bool = False
    hidden_as: str | None = None
    max_length: int | None = None
    listed: bool = False
    fixed_values: Sequence[str] = ()

    def __post_init__(self) -> None:
        _require_name(self.name, "name")
        require_text(self.label, "label")
        require_bool(self.required, "required")
        require_bool(self.listed, "listed")
        require_optional_text(self.hidden_as, "hidden_as")
        fixed_values = tuple(self.fixed_values)
        for value in fixed_values:
            require_text(value, "fixed_values")
        if len(set(fixed_values)) != len(fixed_values):
            raise ContractViolation(f"fixed_values must not repeat a value: {fixed_values}")
        if fixed_values and self.listed:
            raise ContractViolation(f"{self.name!r} has fixed values and need not be listed")
        object.__setattr__(self, "fixed_values", fixed_values)
        if self.max_length is not None and (
            isinstance(self.max_length, bool) or not isinstance(self.max_length, int) or self.max_length < 1
        ):
            raise ContractViolation("max_length must be a positive int or None")


@dataclass(frozen=True, kw_only=True)
class UnavailableAction:
    """``picked`` は、選べたなら選んだはずの候補の道筋。空なら行動ごと選べない。

    ``argument`` は、``picked`` の最後の名前がどの引数の候補か。道筋の途中の候補がいまは並ばないこともあるので、
    候補の並びからは決められない。

    ``asks`` は、選べたなら道筋の最後の候補が求めたはずの、自分で書く値。``shown_under`` は ``Candidate`` と同じ。
    """

    picked: Sequence[str | PersonInText]
    reason: str | TextWithPeople
    argument: str | None = None
    asks: Sequence[FreeText] = ()
    shown_under: str | None = None

    def __post_init__(self) -> None:
        picked = tuple(self.picked)
        for label in picked:
            _require_label(label, "picked")
        if picked and self.argument is None:
            raise ContractViolation(f"unavailable path {picked!r} must name the argument of its last step")
        if not picked and self.argument is not None:
            raise ContractViolation("unavailable whole action must not name an argument")
        if self.argument is not None:
            _require_name(self.argument, "argument")
        if not isinstance(self.reason, TextWithPeople):
            require_text(self.reason, "reason")
        asks = tuple(self.asks)
        if not all(isinstance(a, FreeText) and a.writes is not None for a in asks):
            raise ContractViolation("asks must be FreeText items that say what to write")
        if asks and not picked:
            raise ContractViolation("unavailable whole action must not ask for values")
        require_optional_text(self.shown_under, "shown_under")
        if self.shown_under is not None and len(picked) != 1:
            raise ContractViolation(f"only a one-step unavailable path is shown under a name, got {picked!r}")
        object.__setattr__(self, "picked", picked)
        object.__setattr__(self, "asks", asks)

    def covers_whole_action(self) -> bool:
        return not self.picked

    def people(self) -> tuple[PersonInText, ...]:
        in_reason = self.reason.people.values() if isinstance(self.reason, TextWithPeople) else ()
        return tuple(p for p in (*self.picked, *in_reason) if isinstance(p, PersonInText))


@dataclass(frozen=True, kw_only=True)
class ActionChoice:
    """``outline`` と ``takes_details`` を、候補によらず行動の種類ごとに変えないのは、ターンごとの値から
    引数を組むと、候補の無いターンに引数が消えてツールの定義が変わるため。
    """

    name: str
    label: str
    description: str
    outline: Sequence[ArgumentOutline] = field(default_factory=tuple)
    takes_details: bool = False
    values: Sequence[ChoiceValue] = field(default_factory=tuple)
    unavailable: Sequence[UnavailableAction] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        _require_name(self.name, "name")
        require_text(self.label, "label")
        require_text(self.description, "description")
        outline = tuple(self.outline)
        if not all(isinstance(o, ArgumentOutline) for o in outline):
            raise ContractViolation("outline must be ArgumentOutline items")
        outline_names = [o.name for o in outline]
        if len(set(outline_names)) != len(outline_names):
            raise ContractViolation(f"outline must not repeat a name: {outline_names}")
        require_bool(self.takes_details, "takes_details")
        values = _values(self.values)
        _require_outlined(values, frozenset(outline_names), self.takes_details, top=True)
        required = [o.name for o in outline if o.required]
        if [v.name for v in values] != required:
            raise ContractViolation(f"values must give the required outline {required} in order")
        unavailable = tuple(self.unavailable)
        if not all(isinstance(u, UnavailableAction) for u in unavailable):
            raise ContractViolation("unavailable must be UnavailableAction items")
        if any(u.covers_whole_action() for u in unavailable) and _offers_candidates(values):
            raise ContractViolation(f"{self.name!r} is unavailable as a whole but still offers candidates")
        if len(set(unavailable)) != len(unavailable):
            raise ContractViolation(f"{self.name!r} repeats an unavailable action")
        for u in unavailable:
            if u.argument is not None and u.argument not in outline_names and not self.takes_details:
                raise ContractViolation(f"{self.name!r} has no argument {u.argument!r} for an unavailable action")
            if u.picked and _leads_to_a_candidate(values, tuple(_label_key(label) for label in u.picked)):
                raise ContractViolation(f"{self.name!r} offers {u.picked!r} as a candidate and as unavailable")
        _require_paths(values, frozenset(), nested=False)
        object.__setattr__(self, "outline", outline)
        object.__setattr__(self, "values", values)
        object.__setattr__(self, "unavailable", unavailable)

    def can_be_chosen(self) -> bool:
        if any(u.covers_whole_action() for u in self.unavailable):
            return False
        return all(v.candidates for v in self.values if isinstance(v, PickOne))

    def people(self) -> tuple[PersonInText, ...]:
        return _people_in(self.values) + tuple(p for u in self.unavailable for p in u.people())


def _require_outlined(
    values: Sequence[ChoiceValue], outline_names: frozenset[str], takes_details: bool, *, top: bool
) -> None:
    for value in values:
        if value.name not in outline_names and (top or not takes_details):
            raise ContractViolation(f"value {value.name!r} is not in the outline")
        if isinstance(value, PickOne):
            for candidate in value.candidates:
                _require_outlined(candidate.values, outline_names, takes_details, top=False)


def _offers_candidates(values: tuple[ChoiceValue, ...]) -> bool:
    return any(v.candidates for v in values if isinstance(v, PickOne))


def _require_paths(values: Sequence[ChoiceValue], outer_names: frozenset[str], *, nested: bool) -> None:
    # 兄弟の候補が同じ名前 (how) を持つのはよいが、道筋に沿って重なると、引数を平らに並べたときに衝突する。
    names = outer_names | {v.name for v in values}
    for value in values:
        if value.name in outer_names:
            raise ContractViolation(f"values must not repeat {value.name!r} along a path")
        if not isinstance(value, PickOne):
            continue
        if nested and not value.candidates:
            raise ContractViolation(f"nested values must offer candidates: {value.name!r}")
        if nested and any(c.shown_under is not None for c in value.candidates):
            raise ContractViolation(f"only a first step is shown under a name: {value.name!r}")
        for candidate in value.candidates:
            _require_paths(candidate.values, names, nested=True)


def _leads_to_a_candidate(values: Sequence[ChoiceValue], picked: tuple[object, ...]) -> bool:
    if not picked:
        return True
    return any(
        _leads_to_a_candidate(c.values, picked[1:])
        for v in values
        if isinstance(v, PickOne)
        for c in v.candidates
        if _label_key(c.label) == picked[0]
    )


@dataclass(frozen=True)
class ActionChoices:
    """``note`` は、並べて見せない引数をどこから書き写すかを伝える一言。"""

    choices: Sequence[ActionChoice]
    note: str | None = None

    def __post_init__(self) -> None:
        require_optional_text(self.note, "note")
        choices = tuple(self.choices)
        if not all(isinstance(c, ActionChoice) for c in choices):
            raise ContractViolation("choices must be ActionChoice items")
        names = [c.name for c in choices]
        if len(set(names)) != len(names):
            raise ContractViolation(f"choices must not repeat a name: {names}")
        object.__setattr__(self, "choices", choices)

    def people(self) -> tuple[PersonInText, ...]:
        """候補・いまはできない道筋・理由の文に出る人。同じ人が何度も出ることがある。"""
        return tuple(person for choice in self.choices for person in choice.people())
