# Use cases: AnalyzeGaps, DraftModule, GenerateItems, SubmitForReview
# Each orchestrates domain entities + ports. No SDK imports — only domain.ports interfaces.

class SubmitForReview:
    def publish(self, item, review_task):
        raise NotImplementedError(
            "Publish path not yet implemented — this must enforce the "
            "review-queue approval gate before landing real logic."
        )