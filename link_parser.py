import re

# приватные инвайты: t.me/joinchat/<hash> или t.me/+<hash>
_PRIVATE_RE = re.compile(r"(?:t\.me|telegram\.me)/(?:joinchat/|\+)([\w-]+)")
# паблики: t.me/<username> или @username
_PUBLIC_RE = re.compile(r"(?:t\.me|telegram\.me)/(@?[A-Za-z0-9_]{4,32})/?$")


def classify_link(raw: str):
    """Возвращает (kind, value): kind в {"private", "public", None}."""
    link = raw.strip()
    if not link:
        return None, None

    if link.startswith("@"):
        return "public", link[1:]

    m = _PRIVATE_RE.search(link)
    if m:
        return "private", m.group(1)

    m = _PUBLIC_RE.search(link)
    if m:
        username = m.group(1).lstrip("@")
        if username.lower() in ("joinchat",):
            return None, None
        return "public", username

    return None, None
