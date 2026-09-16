# ruff: noqa: B008
import os
import shutil
import tempfile
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile

from backend.domain.entities.user import User
from backend.infrastructure.auth.dependencies import get_current_user

router = APIRouter(prefix="/api/ingest", tags=["Ingestion"])

@router.post("/file")
def ingest_file(
    request: Request,
    file: UploadFile = File(...),
    doc_category: str | None = Form(None),
    current_user: User = Depends(get_current_user),
):
    """
    Upload a document (PDF, etc.) for ingestion.
    """
    pipeline = request.app.state.ingest_pipeline
    
    # Save the uploaded file to a temporary file
    temp_dir = tempfile.mkdtemp()
    temp_path = Path(temp_dir) / file.filename
    
    try:
        with open(temp_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
            
        # Execute ingestion pipeline
        result = pipeline.execute(
            file_path=temp_path,
            source="UI Upload",
            version="1.0",
            doc_category=doc_category
        )
        
        doc = result.ingestion.document if result.ingestion and hasattr(result.ingestion, "document") else None
        doc_id = doc.doc_id if doc else None
        
        return {
            "message": "Ingestion successful" if not result.ingestion.was_skipped else "Ingestion skipped (already exists)",
            "document_id": doc_id,
            "status": doc.status.value if doc and hasattr(doc, "status") else "unknown",
            "chunks_extracted": len(result.chunking.chunks) if result.chunking else 0,
            "chunks_embedded": result.embedding.embedded_count if result.embedding else 0
        }
    finally:
        # Cleanup
        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir)
