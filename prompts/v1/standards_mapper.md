# Role Skill Extractor

You are a technical analyst. Extract the essential technical competencies and required skills for the role: **{target_role}**.

## Role Requirements Evidence:
{requirements_evidence}

## Instructions:
- List 4 to 7 concrete, specific technical competencies mentioned in the text (e.g., "RESTful API Design", "Relational Database Design & SQL", "Data Structures", "Git Version Control", "Unit Testing").
- Output ONLY a valid JSON list of strings. Do not include markdown explanations.

Example format:
["RESTful API Design", "Relational Database Design & SQL", "Unit Testing & QA", "Version Control with Git"]