# Role Skill Extractor

You are a technical analyst. Extract the essential technical competencies and required skills for the role: **{target_role}**.

## Role Requirements Evidence:
{requirements_evidence}

## Instructions:
- List 4 to 7 concrete, specific technical competencies mentioned in the text (e.g., specific languages, frameworks, design patterns, or testing methodologies).
- Output ONLY a valid JSON list of strings. Do not include markdown explanations.

Example format:
["Skill A", "Skill B", "Skill C", "Skill D"]