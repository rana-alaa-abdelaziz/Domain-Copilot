"""
Bulk-ingestion script: uploads every PDF/DOCX in corpus/standards/ to the
running API via POST /api/ingest/file.

Usage (from repo root, with containers running):
    python scripts/run_full_ingestion.py
"""
import sys
from pathlib import Path

import requests

# ── Configuration ────────────────────────────────────────────────────────────
API_BASE   = "http://localhost:8000"
LOGIN_URL  = f"{API_BASE}/api/auth/login"
INGEST_URL = f"{API_BASE}/api/ingest/file"

# Default admin credentials — change if yours differ
EMAIL    = "instructor@example.com"
PASSWORD = "password123"

CORPUS_DIR = Path(__file__).resolve().parents[1] / "corpus" / "standards"

# Map filename substrings → doc_category passed to the API
CATEGORY_MAP = {
    "JD_": "requirement",
    "rubric_": "requirement",
    "syllabus_": "reference_curriculum",
    "standard_": "methodology",
    "competency": "requirement",
    "Competency": "requirement",
    "SSC": "requirement",
    "QF_": "requirement",
    "CIISEC": "requirement",
    "Containerization": "requirement",
    "Software Engineer": "requirement",
    "Database Administrator": "requirement",
    "Systems Developer": "requirement",
    "poisoned": None,   # skip
}

SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".doc", ".txt"}


def get_category(filename: str) -> str | None:
    for key, cat in CATEGORY_MAP.items():
        if key in filename:
            return cat
    return "requirement"  # safe default


def login(session: requests.Session) -> bool:
    resp = session.post(LOGIN_URL, data={"username": EMAIL, "password": PASSWORD})
    if resp.status_code == 200:
        token = resp.json().get("access_token")
        session.headers.update({"Authorization": f"Bearer {token}"})
        print(f"Logged in as {EMAIL}")
        return True
    print(f"Login failed ({resp.status_code}): {resp.text}")
    return False


def ingest_file(session: requests.Session, path: Path) -> None:
    category = get_category(path.name)
    if category is None:
        print(f"   Skipping {path.name} (excluded)")
        return

    with path.open("rb") as fh:
        resp = session.post(
            INGEST_URL,
            files={"file": (path.name, fh, "application/octet-stream")},
            data={"doc_category": category},
        )

    if resp.status_code == 200:
        data = resp.json()
        msg    = data.get("message", "")
        chunks = data.get("chunks_embedded", 0)
        print(f"   OK  {path.name} — {msg} ({chunks} chunks embedded)")
    else:
        print(f"   ERR {path.name} — HTTP {resp.status_code}: {resp.text[:200]}")


def main() -> None:
    if not CORPUS_DIR.exists():
        print(f"Corpus directory not found: {CORPUS_DIR}")
        sys.exit(1)

    files = sorted(
        p for p in CORPUS_DIR.iterdir()
        if p.is_file() and p.suffix.lower() in SUPPORTED_EXTENSIONS
    )

    if not files:
        print(f"No supported files found in {CORPUS_DIR}")
        sys.exit(0)

    print(f"Found {len(files)} file(s) in corpus/standards/\n")

    session = requests.Session()
    if not login(session):
        sys.exit(1)

    print()
    for i, path in enumerate(files, 1):
        print(f"[{i}/{len(files)}] Ingesting: {path.name}")
        ingest_file(session, path)

    print("\nBulk ingestion complete!")


if __name__ == "__main__":
    main()
