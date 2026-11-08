"""The file a VLC media URI names, as VLC itself finds it."""

from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import url2pathname

LOCAL_HOSTS = ("", "localhost")


def uri_to_path(uri: str) -> Path | None:
    """The path of a file:// URI, or None for another kind (a stream, a disc).

    VLC writes UTF-8, percent-encoded, and drops a query or fragment ("#" in a name is "%23").
    url2pathname decodes it once: a name with a literal "%20" stays as it is. A host other than
    localhost is a Windows network share, \\\\host\\share\\....
    """
    parts = urlsplit(uri)
    if parts.scheme.lower() != "file":
        return None
    if parts.netloc.lower() in LOCAL_HOSTS:
        return Path(url2pathname(parts.path))
    return Path(url2pathname("//" + parts.netloc + parts.path))
