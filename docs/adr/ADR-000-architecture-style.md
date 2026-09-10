# ADR-000: Architecture Style

## Status
Accepted

## Context
This project needs clear separation between core domain logic (gap
analysis, curriculum design, item generation) and volatile external
concerns (LLM provider APIs, vector store, web framework, database).
Provider APIs and models are expected to change during and after the
build; domain logic should not need to change when they do.

## Decision
Adopt a Clean Architecture-style layering:

- `domain/` — entities, ports (interfaces), and domain errors. No
  framework or SDK imports.
- `application/` — use cases and agent orchestration, depending only
  on `domain.ports` abstractions.
- `infrastructure/` — concrete adapters (LLM providers, vector store,
  API framework, database) implementing domain ports.

An automated test (`test_architecture_boundaries.py`) enforces that
`domain/` and `application/` never import restricted SDK/framework
packages directly.

## Consequences
- Slightly more upfront structure than a flat script-style build.
- Swapping LLM providers or the vector store later touches only
  `infrastructure/`, not domain or application logic.
- New contributors have one place (`domain/ports`) to see every
  external capability the system depends on.