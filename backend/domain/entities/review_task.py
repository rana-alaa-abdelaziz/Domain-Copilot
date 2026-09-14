from dataclasses import dataclass


@dataclass
class ReviewTask:
    item_id: str
    status: str
