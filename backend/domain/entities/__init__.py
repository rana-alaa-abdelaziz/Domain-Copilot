class AssessmentItem:
    def __init__(self, id: str, content: str):
        self.id = id
        self.content = content


class ReviewTask:
    def __init__(self, item_id: str, status: str):
        self.item_id = item_id
        self.status = status