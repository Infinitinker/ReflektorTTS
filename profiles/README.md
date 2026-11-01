# Profiles

Each file in this folder is a profile for one app: how to recognize it, where to read its text, and how to process that text before it is spoken (the `stages` of each source). Voices are chosen by the user in the overlay, not in the profile.

The profile format is not finalized yet. Its JSON Schema is `src/reflektortts/profiles/profile.schema.json`; a full guide to writing and contributing profiles will be added here once the format settles.

## Format (version 2)

- `version`: the profile format version. Older profiles are migrated automatically.
- `app`: the app's `title` and original release `year`, for display.
- `match`: how the app is recognized. `executables` lists its executables, because one app can ship several. Each has a `name` (the file name, e.g. `"gta2.exe"`) and, optionally, `sha256`: the SHA-256 of each build of that file the profile supports, in lowercase hex. With `sha256`, only those builds are read, and another build is reported as not supported yet, with its SHA-256, in the Status tab of the desktop app. Without it, any build with that name is read, which suits programs that update often.
- `overlay` (optional, default `false`): whether the overlay is loaded into the app. It needs `sha256` for every executable, so the overlay is only ever loaded into builds it was tested with.
- `sources` (optional): where to read the app's text. Each entry has a `type` (the source plugin), a `name`, optionally `poll_interval_ms` (default 250) and `stages`. Its other fields are defined by the plugin's own schema.
- `stages` (optional, per source): processing applied in order to that source's text, each with a `type` and the plugin's own fields:
  - `tracker`: passes a line on once it has stayed unchanged for `stable_ms` (default 500), has at least `min_letters` letters (default 4), and letters make up at least half of its visible characters; the same line is passed on again only after it disappears or changes. Nearly every source needs it, because sources report the current text on every read.
  - `replace`: `rules`, a list of replacements applied in order, e.g. to remove an app's formatting marks. Each rule is either:
    - `{"find": "#", "replace": ""}`: plain text, matched literally;
    - `{"pattern": "#([^#]*)#", "replace": "\\1"}`: a regular expression (Python syntax), where `\1`, `\2`... in `replace` insert the pattern's groups. In JSON a backslash is written twice. GTA2 marks colored words like `#TEST#`; this rule keeps the word and drops the marks. Invalid patterns are reported when the profile loads.
  - `translate`: translates lines from the input language into the output language the user chose in the overlay (lektor mode), when the two differ and a translation model for them is installed (otherwise lines pass untranslated). Only English to Polish is available so far. The input language is English unless the user chooses another. Place it after the stages that clean up the text and before `normalize`. It has no settings.
  - `normalize`: spells out numbers, money, percentages, units, times, dates, common abbreviations and the symbols & and + in the output language the user chose in the overlay, e.g. `$50,000` becomes "fifty thousand dollars" in English and "pięćdziesiąt tysięcy dolarów" in Polish, "2 min" becomes "dwie minuty", and "o 14:30" becomes "o czternastej trzydzieści". Place it after the stages that clean up the text. It has no settings.

### Memory source (`"type": "memory"`)

Reads text from the app's memory through a pointer chain, written as in Cheat Engine. Fields are described in `src/reflektortts/sources/memory/settings.schema.json`:

- `encoding`: how the app stores text: `utf-16le`, `utf-8`, `cp1250` or `cp1252`.
- `pointers`: one entry per supported build of the app. Memory addresses differ between releases (e.g. retail, patched, Steam), so each chain names the SHA-256 of the executable it was found in (`exe_sha256`, one of the builds in `match`), its base `address` (`"gta2.exe+272F40"`) and its `offsets` in hex. On a build with no matching entry, the user is told the app version is not supported yet.

A pointer can outlive its text, e.g. in the app's menu, and then points at unrelated memory. Readings where under 90% of the characters could appear in dialogue (Latin letters with accents, Cyrillic, spaces, common punctuation) count as no text, so garbage is never read aloud.

### Avalanche source (`"type": "avalanche"`)

Reads subtitles in games on Avalanche Studios' engine (Mad Max). A subtitle there holds the ID of the line it shows, the same in every language. The source reads that ID from the game's memory and the line's text, in the input language set in the overlay, from the game's own files: the `stringlookup` text files in its bundles, one per language (`_eng`, `_pol`, ...), or their patched versions. Reading them takes a few seconds, in the background, as soon as the game is detected (and again when the input language is changed to one not read yet); lines shown meanwhile are skipped. Fields are described in `src/reflektortts/sources/avalanche/settings.schema.json`:

- `pointers`: as in the memory source, one chain per build of the game, ending at the shown line's 32-bit ID (0 when no subtitle is shown).

To find the chain, find the shown line's ID first: the subtitle's UI element holds it, and it changes with every line and is 0 between lines.

## Naming

- One app = one file, named `title-year.json`: the app's title and original release year, lowercase ASCII, words separated by hyphens. Example: `grand-theft-auto-2-1999.json`.
- Always include the year, even if no other app shares the title, so a later remake never forces a rename.
- The executable's name is not part of the file name. It goes in `match.executables`.

## What does not belong in a profile

Profiles are shared, so they hold only what describes the app. Per-user state, such as whether a profile is enabled or which voice someone prefers, is stored in the user's settings, not here.
