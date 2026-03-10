# CONVENTIONS

## General Style

- The codebase largely follows a DDD-inspired layered structure
- Public APIs are commonly type-annotated
- Domain concepts are grouped by bounded context and then split into aggregates, value objects, repositories, events, and services
- Tests mirror the production package structure

## Naming

- Modules, functions, and tests use `snake_case`
- Classes use `PascalCase`
- Test files follow `test_*.py`
- Several abstractions use Java/C#-style `I*` prefixes or `interfaces.py`, for example:
  - `src/ai_rpg_world/application/observation/contracts/interfaces.py`
  - `src/ai_rpg_world/domain/world/repository/connected_spots_provider.py`

## Typing

- Type hints are used broadly across domain value objects, aggregates, services, and application services
- The codebase still favors `typing.List`, `typing.Tuple`, and `typing.Optional` instead of Python 3.10 built-in generics
- This means the effective style is modern-enough typing with some older syntax conventions retained

## Docstrings

- Many core classes and methods include docstrings
- Structured docstrings with `Args`, `Returns`, and `Raises` appear in several modules
- Docstring style is not fully uniform; some methods use short descriptions while others are more structured
- Language is mixed: English exception messages appear beside Japanese docstrings and comments

## Validation And Exceptions

- Domain-specific exception hierarchies exist and are used in many value objects and services
- Application services often translate or wrap lower-level failures into application exceptions
- There is some inconsistency where raw `ValueError` is still used in places that otherwise follow domain-specific exception patterns

## Layering Conventions

- Repository interfaces are defined in domain packages
- Application services depend on abstractions rather than persistence implementations
- Infrastructure owns concrete repositories, event publishing, DI, and external-service adapters
- Event handlers are often registered from infrastructure-side registries

## Repository And Event Patterns

- Aggregates emit domain events
- Repositories and the unit-of-work coordinate pending event publication
- Read models exist for query-heavy flows such as shop and trade
- In-memory adapters are the default implementation style for many repositories
