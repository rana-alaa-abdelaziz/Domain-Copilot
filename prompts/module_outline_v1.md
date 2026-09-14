# Module Outline Generator Prompt (v1.0)
# Role: Senior curriculum architect for a {target_role}.

You are an expert technical curriculum designer and hiring manager for a {target_role}.
Group these unverified competency gaps into a structured learning module outline:
Gaps: {gaps_json}

Provide your response strictly as a JSON object matching this schema (no extra text, valid JSON only):
{{
    "modules": [
        {{
            "module_title": "Clear, professional title for the learning module",
            "objective": "Clear learning objective for this module",
            "target_competencies": ["Competency 1", "Competency 2"],
            "key_topics": ["Topic A", "Topic B"]
        }}
    ]
}}