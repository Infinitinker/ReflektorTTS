"""A small game folder in Mad Max's layout, for tests."""

from pathlib import Path

from tests.sources.avalanche.fake_files import CHUNKED, DEFLATE, STORED, bundle, stringlookup, write_archive

KILL = 0xAFA0D59E
CHAMPION = 0x838A371D
MENU = 0x1F79A85C
CUTSCENE = "missions/main_missions/mm1010/mm1010_cs010_p2"


def make_game(game_dir: Path) -> Path:
    """A cutscene bundle with Polish and English text, a patched Polish file, and the menus' text."""
    cutscene = bundle(
        {
            f"{CUTSCENE}_pol.stringlookup": stringlookup({KILL: "Zabić go!", CHAMPION: "To ja zostanę czempinem!"}),
            f"{CUTSCENE}_eng.stringlookup": stringlookup({KILL: "Yeah, kill him!", CHAMPION: "I'll be the champion!"}),
            f"{CUTSCENE}.blo": b"\x01" * 300,
        }
    )
    write_archive(
        game_dir / "archives_win64" / "game0.tab",
        [("mm1010_cs010_p2.bl", cutscene, CHUNKED), ("model.modelc", b"\x02" * 500, DEFLATE)],
    )
    write_archive(
        game_dir / "patch_win64" / "game0.tab",
        [
            (
                "mm1010_cs010_p2_pol.stringlookup",
                stringlookup({KILL: "Tak jest, zabić go!", CHAMPION: "To ja zostanę czempinem!"}),
                DEFLATE,
            ),
            ("master_gui_pol.stringlookup", stringlookup({MENU: "Nowa gra"}), STORED),
            ("master_gui_eng.stringlookup", stringlookup({MENU: "New game"}), STORED),
        ],
    )
    return game_dir
