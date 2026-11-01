"""An Argos Translate package, as its archive is downloaded, for tests."""

import io
import zipfile


def package_bytes(tokenizer: str = "bpe.model") -> bytes:
    """A package with a BPE tokenizer (bpe.model), or a SentencePiece one (sentencepiece.model)."""
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w") as package:
        package.writestr("translate-en_pl-1_9/model/model.bin", b"weights")
        package.writestr("translate-en_pl-1_9/model/config.json", "{}")
        package.writestr(f"translate-en_pl-1_9/{tokenizer}", "tokens")
        package.writestr("translate-en_pl-1_9/README.md", "CC-BY 4.0")
        package.writestr("translate-en_pl-1_9/metadata.json", "{}")
        package.writestr("translate-en_pl-1_9/stanza/en/tokenize/default.pt", b"sentences")
    return archive.getvalue()


PACKAGE_BYTES = package_bytes()
