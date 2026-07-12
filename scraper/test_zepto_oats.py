from zepto_oats import parse_zepto_card


def test_parse_zepto_card_extracts_name_price_pack_rating():
    card_text = "Yoga Bar Oats|₹399|₹499|400g|4.2|(120)"
    result = parse_zepto_card(card_text)
    assert result["sp"] == "Rs.399"
    assert result["mrp"] == "Rs.499"
    assert result["pack_size"] == "400g"
    assert result["rating"] == "4.2"
    assert result["reviews"] == "(120)"


def test_parse_zepto_card_detects_sponsored():
    card_text = "Ad|Quaker Oats|₹199"
    result = parse_zepto_card(card_text)
    assert result["sponsored"] == "True"


def test_parse_zepto_card_not_sponsored_by_default():
    card_text = "Saffola Oats|₹149"
    result = parse_zepto_card(card_text)
    assert result["sponsored"] == "False"


def test_parse_zepto_card_handles_missing_fields():
    result = parse_zepto_card("Some Product Name")
    assert result["sp"] == "N/A"
    assert result["mrp"] == "N/A"
    assert result["pack_size"] == "N/A"
