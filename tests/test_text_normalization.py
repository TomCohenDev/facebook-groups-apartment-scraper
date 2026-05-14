from app.utils.text import normalize_text, extract_phone_numbers, canonicalize_facebook_url


def test_removes_ui_noise():
    text = "דירה להשכרה\nLike\nComment\nShare\nעוד"
    result = normalize_text(text)
    assert "Like" not in result
    assert "Comment" not in result
    assert "דירה להשכרה" in result


def test_collapses_whitespace():
    text = "שלום   עולם\n\n\n\nשורה"
    result = normalize_text(text)
    assert "   " not in result
    assert result.count("\n") <= 2


def test_extract_phone_il():
    text = "צלצלו: 052-1234567 או 03-9876543"
    phones = extract_phone_numbers(text)
    assert len(phones) >= 1


def test_canonicalize_facebook_url():
    url = "https://m.facebook.com/groups/123/posts/456?ref=share"
    result = canonicalize_facebook_url(url)
    assert "m.facebook.com" not in result
    assert "ref=share" not in result
    assert "www.facebook.com" in result
