from app.utils.hashing import content_hash, url_hash


def test_content_hash_deterministic():
    h1 = content_hash("group_a", "דירה להשכרה בתל אביב")
    h2 = content_hash("group_a", "דירה להשכרה בתל אביב")
    assert h1 == h2


def test_content_hash_different_groups():
    h1 = content_hash("group_a", "same text")
    h2 = content_hash("group_b", "same text")
    assert h1 != h2


def test_content_hash_truncates_at_1000():
    long_text = "א" * 2000
    h1 = content_hash("g", long_text)
    h2 = content_hash("g", "א" * 1000)
    assert h1 == h2


def test_url_hash_is_hex():
    h = url_hash("https://www.facebook.com/groups/test/posts/123")
    assert len(h) == 64
    assert all(c in "0123456789abcdef" for c in h)
