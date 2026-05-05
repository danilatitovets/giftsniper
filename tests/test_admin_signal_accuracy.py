from app.services.signal_accuracy_dashboard import taxonomy_classes
from app.services.signal_review import ISSUE_TAXONOMY


def test_taxonomy_export_matches_review_module():
    assert "no_sales_trait_issue" in ISSUE_TAXONOMY
    assert ISSUE_TAXONOMY == taxonomy_classes()
