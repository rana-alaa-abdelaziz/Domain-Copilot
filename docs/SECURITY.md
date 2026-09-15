# Security

## Prompt Injection (OWASP LLM Top 10 §5)
We mitigate and test against prompt injection via our evaluation golden set and end-to-end integration tests.

Our test suite covers all critical injection vectors:
- **Direct Injection (q23, q24):** Malicious instructions embedded directly into the user query. This ensures our retrieval and immediate processing pipelines do not erroneously execute raw user input as system commands.
- **Indirect Injection (q26):** Malicious instructions embedded inside a retrieved document (e.g., `poisoned_requirement_doc.docx`). Per OWASP LLM Top 10, this is the most critical vector, as the LLM could blindly trust instructions fetched from a seemingly legitimate internal source. This is verified end-to-end in `backend/tests/test_indirect_prompt_injection.py` by observing an agent's (`StandardsMapper`) behavior when exposed to a poisoned chunk.
