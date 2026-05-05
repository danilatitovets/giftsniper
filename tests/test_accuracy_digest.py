from pathlib import Path


def test_accuracy_digest_module_documents_limitations():
    p = Path(__file__).resolve().parents[1] / "app" / "services" / "accuracy_digest.py"
    src = p.read_text(encoding="utf-8")
    assert "Owner accuracy digest" in src
    assert ".env" in src or "не гарантируют" in src
