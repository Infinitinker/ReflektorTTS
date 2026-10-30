# Game profiles

Each file in this folder is a profile for one game: how to recognize it and where to read its text. Text processing and voices will be added as the core supports them.

The profile format is not finalized yet. Its JSON Schema is `src/reflektortts/profiles/profile.schema.json`; a full guide to writing and contributing profiles will be added here once the format settles.

## Format (version 2)

- `version`: the profile format version. Older profiles are migrated automatically.
- `game`: the game's `title` and original release `year`, for display.
- `match`: how the game is recognized. `process` is a list of executable names, because one game can ship several.
- `sources` (optional): where to read the game's text. Each entry has a `type` (the source plugin), a `name`, and optionally `poll_interval_ms` (default 250). Its other fields are defined by the plugin's own schema.

### Memory source (`"type": "memory"`)

Reads text from the game's memory through a pointer chain, written as in Cheat Engine. Fields are described in `src/reflektortts/sources/memory/settings.schema.json`:

- `encoding`: how the game stores text: `utf-16le`, `utf-8`, `cp1250` or `cp1252`.
- `pointers`: one entry per supported build of the game. Memory addresses differ between releases (e.g. retail, patched, Steam), so each chain names the SHA-256 of the executable it was found in (`exe_sha256`), its base `address` (`"gta2.exe+272F40"`) and its `offsets` in hex. On a build with no matching entry, the user is told the game version is not supported yet.

## Naming

- One game = one file, named `title-year.json`: the game's title and original release year, lowercase ASCII, words separated by hyphens. Example: `grand-theft-auto-2-1999.json`.
- Always include the year, even if no other game shares the title, so a later remake never forces a rename.
- The process name is not part of the file name. It goes in `match.process`.

## What does not belong in a profile

Profiles are shared, so they hold only what describes the game. Per-user state, such as whether a profile is enabled or which voice someone prefers, is stored in the user's settings, not here.
