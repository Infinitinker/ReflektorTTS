from importlib.metadata import version

from reflektortts.desktop.about import about


def test_the_version_and_links_come_from_the_package() -> None:
    info = about()

    assert info.version == version("reflektortts")
    assert info.project == "https://github.com/Infinitinker/ReflektorTTS"
    assert info.issues == "https://github.com/Infinitinker/ReflektorTTS/issues"
