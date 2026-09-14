"""
FR-3 evaluation harness. Runs eval/golden_set.yaml against the real
HybridRetrieveUseCase (real Postgres + pgvector + full-text search + the
configured LLM provider for query embedding), and reports:

  - hit_rate:        for "standard" (expected_answerable) questions, the
                      fraction where at least one of the expected_keywords
                      appears in ANY of the top-k retrieved chunks.
  - top1_precision:  the stricter version — expected_keywords must appear
                      in the TOP-1 (highest fused-score) chunk specifically.
                      This is the retrieval-level proxy for "groundedness"
                      described in golden_set.yaml's header — it is not a
                      check on a generated answer, since no answer
                      generation use case exists yet.
  - refusal_correctness: for adversarial questions (expected_answerable
                      is false), the fraction correctly showing low
                      evidence — either RetrievalResult.has_evidence is
                      False, or the top fused_score falls below
                      REFUSAL_SCORE_THRESHOLD.

REFUSAL_SCORE_THRESHOLD is a starting heuristic, not a calibrated value —
per FR-3's own instruction to "record actual baseline numbers, including
the bad ones, with interpretation", run this once, look at the printed
per-question fused scores for adversarial cases, and adjust the threshold
based on real numbers rather than guessing twice.

Usage:
    python scripts/eval.py
"""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import yaml
from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

project_root = Path(__file__).resolve().parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from backend.application.use_cases.hybrid_retrieve import HybridRetrieveUseCase
from backend.infrastructure.config import get_llm_provider, get_settings
from backend.infrastructure.vectorstore.pg_keyword_search import PgKeywordSearch
from backend.infrastructure.vectorstore.pgvector_store import PgVectorStore

GOLDEN_SET_PATH = project_root / "eval" / "golden_set.yaml"
RESULTS_PATH = project_root / "eval" / "latest_results.json"
TOP_K = 5

# Starting heuristic — see module docstring. With the MIN_SIMILARITY
# floor now enforced in PgVectorStore.query() (0.3), dense search no
# longer force-returns irrelevant nearest-neighbors for out-of-corpus
# queries, so a "found nothing real" case should now show has_evidence
# == False outright, not just a low score. This threshold is kept as a
# second layer of defense for genuinely weak (but present) matches, not
# the primary refusal mechanism anymore — recalibrate after re-running
# against real adversarial-case scores.
REFUSAL_SCORE_THRESHOLD = 0.02


def load_golden_set() -> list[dict]:
    with open(GOLDEN_SET_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f)


def keyword_hit(content: str, keywords: list[str]) -> bool:
    content_lower = content.lower()
    return any(kw.lower() in content_lower for kw in keywords)


def main():
    load_dotenv()
    settings = get_settings()

    db_url = settings.database_url
    if not db_url:
        print("ERROR: DATABASE_URL not set in environment or .env file.")
        sys.exit(1)
    if db_url.startswith("postgresql://"):
        db_url = db_url.replace("postgresql://", "postgresql+psycopg2://", 1)

    engine = create_engine(db_url)
    Session = sessionmaker(bind=engine)
    session = Session()

    llm_provider = get_llm_provider(settings)
    vector_store = PgVectorStore(session)
    keyword_search = PgKeywordSearch(session)
    retrieve_uc = HybridRetrieveUseCase(
        llm_provider=llm_provider,
        vector_store=vector_store,
        keyword_search=keyword_search,
    )

    print(f"LLM provider for query embedding: {type(llm_provider).__name__}")
    print(f"Golden set: {GOLDEN_SET_PATH}")

    golden_set = load_golden_set()
    print(
        f"Loaded {len(golden_set)} entries "
        f"({sum(1 for e in golden_set if e['category'] == 'adversarial')} adversarial)\n"
    )

    standard_entries = [e for e in golden_set if e["category"] == "standard"]
    adversarial_entries = [e for e in golden_set if e["category"] == "adversarial"]

    per_question_results = []

    # --- Standard (answerable) questions: hit_rate + top1_precision ---
    hit_count = 0
    top1_count = 0
    for entry in standard_entries:
        result = retrieve_uc.execute(entry["question"], top_k=TOP_K)
        keywords = entry["expected_keywords"]

        any_hit = any(keyword_hit(c.content, keywords) for c in result.citations)
        top1_hit = bool(result.citations) and keyword_hit(
            result.citations[0].content, keywords
        )

        hit_count += int(any_hit)
        top1_count += int(top1_hit)

        per_question_results.append(
            {
                "id": entry["id"],
                "category": "standard",
                "question": entry["question"],
                "any_hit": any_hit,
                "top1_hit": top1_hit,
                "top1_score": result.citations[0].fused_score
                if result.citations
                else None,
                "num_citations": len(result.citations),
            }
        )

    hit_rate = hit_count / len(standard_entries) if standard_entries else 0.0
    top1_precision = top1_count / len(standard_entries) if standard_entries else 0.0

    # --- Adversarial questions: refusal_correctness ---
    correct_refusals = 0
    for entry in adversarial_entries:
        result = retrieve_uc.execute(entry["question"], top_k=TOP_K)
        top_score = result.citations[0].fused_score if result.citations else 0.0

        correctly_refused = (not result.has_evidence) or (
            top_score < REFUSAL_SCORE_THRESHOLD
        )
        correct_refusals += int(correctly_refused)

        per_question_results.append(
            {
                "id": entry["id"],
                "category": "adversarial",
                "adversarial_type": entry["adversarial_type"],
                "question": entry["question"],
                "correctly_refused": correctly_refused,
                "top1_score": top_score,
                "num_citations": len(result.citations),
            }
        )

    refusal_correctness = (
        correct_refusals / len(adversarial_entries) if adversarial_entries else 0.0
    )

    # --- Report ---
    print("=" * 60)
    print("EVALUATION RESULTS")
    print("=" * 60)
    print(f"Standard questions:     {len(standard_entries)}")
    print(
        f"  Hit rate (top-{TOP_K}):     {hit_rate:.1%}  ({hit_count}/{len(standard_entries)})"
    )
    print(
        f"  Top-1 precision:      {top1_precision:.1%}  ({top1_count}/{len(standard_entries)})"
    )
    print(f"Adversarial questions:  {len(adversarial_entries)}")
    print(
        f"  Refusal correctness:  {refusal_correctness:.1%}  ({correct_refusals}/{len(adversarial_entries)})"
    )
    print("=" * 60)

    print("\nFailures (standard questions with no hit in top-k):")
    for r in per_question_results:
        if r["category"] == "standard" and not r["any_hit"]:
            print(f"  [{r['id']}] {r['question']}")
            print(f"      top1_score={r['top1_score']}, citations={r['num_citations']}")

    print("\nFailures (adversarial questions NOT correctly refused):")
    for r in per_question_results:
        if r["category"] == "adversarial" and not r["correctly_refused"]:
            print(f"  [{r['id']}] ({r['adversarial_type']}) {r['question']}")
            print(f"      top1_score={r['top1_score']}, citations={r['num_citations']}")

    # --- Persist for diffing across runs / pasting into EVALUATION.md ---
    report = {
        "run_at": datetime.now(timezone.utc).isoformat(),
        "llm_provider": type(llm_provider).__name__,
        "refusal_score_threshold": REFUSAL_SCORE_THRESHOLD,
        "summary": {
            "hit_rate": hit_rate,
            "top1_precision": top1_precision,
            "refusal_correctness": refusal_correctness,
            "standard_count": len(standard_entries),
            "adversarial_count": len(adversarial_entries),
        },
        "per_question": per_question_results,
    }
    RESULTS_PATH.parent.mkdir(exist_ok=True)
    with open(RESULTS_PATH, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)
    print(f"\nFull results written to {RESULTS_PATH}")

    session.close()


if __name__ == "__main__":
    main()
