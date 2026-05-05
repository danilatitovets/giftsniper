from app.services.gift_intake import scrub_import_line


def test_scrub_list_prefix_and_url():
    assert "Ice Cream" in scrub_import_line("1) Ice Cream #217467")
    u = scrub_import_line("noise https://getgems.io/nft/x end")
    assert u.startswith("https://")


def test_scrub_buy_prefix():
    s = scrub_import_line("buy: Ice Cream 217467 at 180")
    assert "217467" in s
