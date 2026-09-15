from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass
class PublishedCurriculum:
    published_id: str
    thread_id: str
    target_role: str
    module_outline: dict[str, Any]
    assessment_items: dict[str, Any]
    approved_by: str
    published_at: datetime
