# Agentic Workflow & AI Governance

This document describes how AI assistance is governed, configured, and integrated into the project's engineering lifecycle in compliance with Section 6 of the project rubric.

---

## 1. Project Instruction File Encoding Architecture Rules

### What Was Configured
A dedicated workspace instruction file (`CLAUDE.md` / `.cursorrules`) defining clean/hexagonal architecture rules, layer-boundary restrictions, and testing expectations.

### Why
LLM coding assistants default to flat layouts or convenient layer bleeding (e.g., importing web frameworks or database clients directly into domain entities/use cases). Explicit architectural rules instruct the AI on strict boundary limits before generating scaffolding or application code.

### What It Changed
The assistant respects dependency directions:
- `backend/domain/` has zero external runtime dependencies.
- `backend/application/` interacts with persistence, vector stores, and LLM APIs exclusively through interfaces/ports.
- The AI prioritizes strict TDD execution (such as landing failing domain tests before use-case implementations).

### Where It Failed
The assistant occasionally attempted to import convenience utility functions or external typing wrappers into the domain core. These violations were caught by mechanical boundary enforcement tests (`test_architecture_boundaries.py`) and pre-commit checks.

---

## 2. Reusable Versioned Prompt Assets & Skills

### What Was Configured
A structured directory of versioned system instructions and execution templates under `.agent/skills/` (e.g., `tdd-cycle.md`, `approval-gate-validator.md`, and `layer-boundary-auditor.md`).

### Why
Repeated interactions with AI models suffer from prompt drift, inconsistent assumptions, and varying adherence to safety guidelines across feature branches.

### What It Changed
Prompts became versioned, deterministic engineering assets. Any code generation task begins by referencing a standardized skill file, ensuring repeatable domain modeling and strict adherence to the project's naming conventions.

### Where It Failed
If skills are not strictly scoped, the model over-applies guidelines—such as attempting to generate unnecessary architectural scaffolding or boilerplate for simple, single-purpose unit tests.

---

## 3. Sub-Agents Scoped to Distinct Roles

### What Was Configured
Three specialized AI sub-agent operational profiles:
1. **Security & Boundary Reviewer:** Specializes in identifying OWASP Top 10 vulnerabilities, unauthorized model calls, and layer-leakage regressions.
2. **Test Writer:** Adheres to TDD; writes strict unit, contract, and adversarial failure tests before implementations exist.
3. **Documentation Sync:** Audits implementation PRs to keep architecture diagrams, ADRs, and the gap table up to date.

### Why
A single general-purpose model prompt often compromises between speed, architecture purity, and edge-case testing. Role-specialized profiles produce more focused, rigorous feedback.

### What It Changed
The Test Writer agent produced the initial failing test harness for the human-approval gate (`test_item_generator_approval_gate.py`), ensuring that blocking statuses (`pending`, `rejected`, `needs_revision`) halt publication without premature logic mocking.

### Where It Failed
Role agents occasionally duplicate effort or make conflicting assumptions across PR branches if shared state (such as domain error types) is not checked and synchronized first.

---

## 4. Hooks Enforcing Quality Gates Automatically

### What Was Configured
Local Git pre-commit hooks and CI pipelines running:
- Architecture boundary verification (`pytest tests/test_architecture_boundaries.py`)
- Static typing and linting checks (`ruff`, `mypy`)
- Secret scanning (`gitleaks` / `detect-secrets`)

### Why
AI-generated code must never bypass project safety gates. Automated hooks ensure that hallucinations, boundary breaches, or uncommitted dependencies are blocked prior to branch push.

### What It Changed
Removed human cognitive overhead during code reviews for baseline hygiene. Any AI output that breached architectural separation failed instantly at the git hook level before reaching a PR.

### Where It Failed
Overly aggressive pre-commit hooks slowed down rapid prototyping branches when working on incomplete test drafts, requiring clear use of `@pytest.mark.xfail(strict=True)` for intentional TDD red-to-green tracking.

---

## 5. Custom Commands for Repeated Operations

### What Was Configured
A suite of project automation CLI commands (configured via `Makefile` / `invoke`):
- `make test:domain` — runs isolated, dependency-free domain rules.
- `make test:boundaries` — asserts zero illegal cross-layer imports.
- `make verify:gate` — executes the item generator and human-review approval gate verification suites.

### Why
Standardizing recurring workflow operations ensures that both human developers and autonomous AI terminal sessions execute identical commands with fixed environmental contexts.

### What It Changed
Reduced prompt verbosity and context token consumption. The AI executes deterministic, single-line targets to validate changes rather than generating ad-hoc multi-line shell scripts.

### Where It Failed
Model sessions occasionally invoked system commands with incompatible bash/PowerShell syntax across local OS environments before paths were normalized in standardized script runners.