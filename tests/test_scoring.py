from app.classifier.apartment_rules import extract_apartment, passes_keyword_gate
from app.classifier.scoring import score_extraction

CRITERIA = {
    "price": {"max": 6500},
    "rooms": {"min": 2},
    "locations": {
        "preferred": ["תל אביב", "גבעתיים"],
        "neighborhoods": {"preferred": ["פלורנטין", "בורוכוב"]},
    },
}


def test_keyword_gate_rejects_seeker():
    assert not passes_keyword_gate("מחפש דירה להשכרה בתל אביב")
    assert not passes_keyword_gate("מחפשת דירה 3 חדרים")


def test_keyword_gate_accepts_listing():
    assert passes_keyword_gate("דירה להשכרה בתל אביב ללא תיווך")
    assert passes_keyword_gate("2.5 חדרים, כניסה מיידית")


def test_extract_price():
    text = "שכירות: 5,500₪ לחודש"
    result = extract_apartment(text)
    assert result.price_ils == 5500


def test_extract_rooms():
    text = "דירת 3 חדרים להשכרה"
    result = extract_apartment(text)
    assert result.rooms == 3.0


def test_extract_no_brokerage():
    text = "דירה להשכרה ללא תיווך"
    result = extract_apartment(text)
    assert result.brokerage is False


def test_score_high_quality_listing():
    text = "דירת 3 חדרים להשכרה בתל אביב, ₪5,800, ללא תיווך, מרפסת, חניה"
    extraction = extract_apartment(text)
    score, _ = score_extraction(extraction, CRITERIA)
    assert score >= 75


def test_score_seeker_post_penalized():
    text = "מחפש דירה 3 חדרים בתל אביב עד 5500"
    extraction = extract_apartment(text)
    score, _ = score_extraction(extraction, CRITERIA)
    assert score == 0


def test_no_brokerage_keyword_with_lo():
    text = "דירה ללא שותפים, להשכרה"
    assert passes_keyword_gate(text)


def test_alef_thousand():
    text = "שכירות 6.5 אלף"
    result = extract_apartment(text)
    assert result.price_ils == 6500
