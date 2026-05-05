from app.services.beta_dataset_workflow import format_beta_dataset_report


def test_format_beta_dataset_report():
    s = {"signal_snapshots_total": 10, "snapshots_with_review_rating": 3, "snapshots_good_rated": 2, "snapshots_bad_rated": 1}
    txt = format_beta_dataset_report(s)
    assert "10" in txt
    assert "signals" in txt and "generated" in txt
