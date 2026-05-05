from app.i18n import t


def test_start_text_promotes_link_or_address_not_name_search():
    txt = t("start.main", "ru").lower()
    assert "ссылк" in txt and "конкретн" in txt
    assert "1️⃣" in t("start.main", "ru")
    h = t("help.main", "ru").lower()
    assert "ссыл" in h and ("адрес" in h or "address" in h)


def test_help_text_promotes_link_or_address():
    txt = t("help.main", "ru").lower()
    assert "ссылку на конкретный nft" in txt
    assert "nft address" in txt
