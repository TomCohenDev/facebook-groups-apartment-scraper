import hashlib


def content_hash(group_id: str, normalized_text: str) -> str:
    payload = (group_id + normalized_text[:1000]).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def url_hash(url: str) -> str:
    return hashlib.sha256(url.encode("utf-8")).hexdigest()
