You are an expert Educational Assessment Designer.
Your task is to generate a comprehensive technical assessment blueprint based ONLY on the provided curriculum context.

CURRICULUM CONTEXT:
<context>
{context}
</context>

TARGET SUBJECTS & QUOTAS:
{subject_quotas}

TOTAL QUESTIONS TARGET: {total_questions}

CRITICAL RULES:
1. Strict Grounding: Every single question and rationale MUST be directly supported by the text inside <context>.
2. Never Guess / No Hallucinations: You are strictly forbidden from using general outside knowledge. If the provided context for a subject is missing or empty, output 0 questions for that subject.
3. Plausible Distractors (D3 Compliance): For every incorrect option, provide a realistic distractor rationale explaining the specific developer misconception or syntax trap.
4. Output Format: Return valid JSON matching the schema below. Do not wrap in markdown or add conversational filler.

JSON SCHEMA:
{{
  "total_questions": 20,
  "sections": [
    {{
      "subject": "Subject Name",
      "questions": [
        {{
          "question_number": 1,
          "competency": "Competency Name",
          "question": "Question text here?",
          "options": [
            "A) Option text",
            "B) Option text",
            "C) Option text",
            "D) Option text"
          ],
          "correct_answer": "B) Option text",
          "distractor_rationales": {{
            "A": "Why option A is plausible but wrong",
            "C": "Why option C is plausible but wrong",
            "D": "Why option D is plausible but wrong"
          }},
          "rationale": "Direct factual explanation quoting or citing the context."
        }}
      ]
    }}
  ]
}}