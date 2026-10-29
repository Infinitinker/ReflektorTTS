# Game profiles

Each file in this folder is a profile for one game. For now a profile only identifies the game and the process to watch; text sources, processing and voices will be added as the core supports them.

The profile format and its JSON Schema are not finalized yet. A full guide to writing and contributing profiles will be added here once they are.

## Format

- `version`: the profile format version, used to migrate older profiles.
- `game`: the game's `title` and original release `year`, for display.
- `match`: how the game is recognized. `process` is a list of executable names, because one game can ship several.

## Naming

- One game = one file, named `title-year.json`: the game's title and original release year, lowercase ASCII, words separated by hyphens. Example: `grand-theft-auto-2-1999.json`.
- Always include the year, even if no other game shares the title, so a later remake never forces a rename.
- The process name is not part of the file name. It goes in `match.process`.

## What does not belong in a profile

Profiles are shared, so they hold only what describes the game. Per-user state, such as whether a profile is enabled or which voice someone prefers, is stored in the user's settings, not here.
