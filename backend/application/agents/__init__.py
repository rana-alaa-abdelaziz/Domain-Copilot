"""
Agent orchestration: StandardsMapper, CurriculumDesigner, ItemGenerator.

These coordinate calls to LlmProvider/VectorStore via domain.ports —
orchestration logic only. No direct SDK imports (openai, ollama, etc.)
belong here; that's what the architecture boundary test enforces.
"""
