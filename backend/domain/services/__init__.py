"""Domain services — pure business-logic algorithms with no I/O, no SDK
imports. Distinct from domain/ports, which defines abstract interfaces
implemented by infrastructure. A domain service holds a business rule
(like the chunking strategy in ADR-001) that doesn't belong to a single
entity and has no side effects of its own."""
