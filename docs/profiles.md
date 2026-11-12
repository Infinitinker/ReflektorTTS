# Profiles

A profile describes one app: how to recognize it, where to read its text, and how to process that text before it is spoken (the `stages` of each source). Voices are chosen by the user in the settings panel, not in the profile.

## Where profiles are

- **Bundled** profiles ship with ReflektorTTS (`src/reflektortts/profiles/bundled/` in this repository) and are replaced with each update, so their fixes reach everyone. They are not edited in place.
- **Your own** profiles go in `%LOCALAPPDATA%\ReflektorTTS\profiles\` (or the folder given with `--profiles`). A file there with a bundled profile's name, e.g. `grand-theft-auto-2-1999.json`, replaces that profile completely, and keeps its settings; it no longer gets the bundled profile's fixes.
- Of two profiles that match the same build of an app (the same executable name and a build in both, or no builds listed), your own is used and the bundled one is set aside. Two of your own clash: neither is used until one is disabled.
- Any profile, bundled or your own, can be disabled; its app is then not read. A broken profile file is not used, and the reason is shown.
- Some sources can read an app only once its own settings are changed, e.g. VLC's web interface switched on. ReflektorTTS makes that change when you enable the source's **integration**, and puts it back when you disable it. Until then a profile whose sources all need one is **not set up**, and its app is not read.

The desktop app's Profiles tab lists them all with their medal (see `rating` below) and state, and does the rest. For a profile that needs an integration, **Integration…** opens a window with a group for it, named after it, which says what it changes and whether it is enabled, with a button that enables or disables it. **Copy to edit** copies a bundled profile to your folder (where it replaces the bundled one) and shows it there for your editor; **Remove** deletes your own file; **Import…** adds a profile file to your own once it is checked (a broken one is refused with the reason); **Reload** reads the files again after you edit them. A changed profile applies the next time its app starts.

[Writing a profile](#writing-a-profile) below walks through writing one, step by step, with no programming. The profile format is not final yet: [what may still change](#what-may-still-change) says which parts. Its JSON Schema is `src/reflektortts/profiles/profile.schema.json`.

An editor that understands JSON Schema (e.g. Visual Studio Code) checks a profile as you type and suggests its fields when the profile names the schema in a `$schema` field:

```json
{
  "$schema": "https://raw.githubusercontent.com/Infinitinker/ReflektorTTS/main/src/reflektortts/profiles/profile.schema.json",
  "version": 1,
  ...
}
```

ReflektorTTS ignores that field. The editor checks only the profile's own fields; the fields of each source and stage are checked by their plugins when ReflektorTTS loads the profile.

## Writing a profile

This guide takes you from an app ReflektorTTS does not know to a profile that reads it aloud. You need no programming, only:

- a text editor: Notepad will do, and Visual Studio Code also checks the profile as you type (see `$schema` above);
- for a game, [Cheat Engine](https://www.cheatengine.org/), a free tool that finds where a game keeps its text in memory. Its installer may offer other software: decline it.

The steps use Grand Theft Auto 2 as the example; its bundled profile, `grand-theft-auto-2-1999.json`, is where they end. For an app that ReflektorTTS reads in another way, such as VLC, copy its profile instead and change only what differs.

### What may still change

The format is not final yet. Profiles keep working across updates: each has a `version`, and ReflektorTTS migrates older ones when it reads them. But this guide may change with the format, in these parts:

- the fields of each source and stage, which come from their plugins and may gain new settings;
- the sources and stages there are: new ones are added as more apps are supported;
- the steps with Cheat Engine, which suit games that keep their text as plain strings; games that do not may need another source.

### 1. Start the file

In the ReflektorTTS window's Profiles tab, select a bundled profile close to your app and choose **Copy to edit**, or create a new file in `%LOCALAPPDATA%\ReflektorTTS\profiles\`, named after the app as [Naming](#naming) says, such as `grand-theft-auto-2-1999.json`. Start with what recognizes the app:

```json
{
  "version": 1,
  "app": { "title": "Grand Theft Auto 2", "year": 1999 },
  "match": {
    "executables": [{ "name": "gta2.exe" }]
  }
}
```

`name` is the file name of the app's program: look in the app's folder, or in Task Manager's **Details** tab while it runs. Save the file as UTF-8, choose **Reload** in the Profiles tab, and start the app. The Status tab then says it is reading it; a profile with a mistake is shown as broken in the Profiles tab instead, with the reason.

### 2. Note the app's version

A game's text sits at different places in different versions of it (retail, patched, Steam), so a profile for a game names each version it was written for by its SHA-256, a fingerprint of its program file. To get it, list a made-up one, 64 zeros, and reload:

```json
"executables": [{ "name": "gta2.exe", "sha256": ["0000000000000000000000000000000000000000000000000000000000000000"] }]
```

Start the app: the Status tab says this version is not supported yet and shows its SHA-256, and the log has it too, to copy (Settings tab, **Open logs folder**, `reflektortts.log`). Put it in place of the zeros. If you have PowerShell at hand, `Get-FileHash gta2.exe` in the app's folder shows it as well; write it in lowercase.

### 3. Find the text in memory

Cheat Engine finds the place in memory where the game keeps the line it shows, and then a pointer chain: the way to that place from a fixed point in the game's program, which stays the same each time the game starts.

1. Start the game and get a line of text on screen, such as a subtitle or a message.
2. Start Cheat Engine, click the computer icon at the top left (**Open Process**) and choose the game's program.
3. Set **Value Type** to **String**, type a few words of the shown line exactly as shown, and click **First Scan**. If nothing is found, tick **UTF-16** and scan again: many games keep text that way.
4. When the game shows another line, type a few of its words and click **Next Scan**. Repeat until only a few addresses are left; the one that always holds the line on screen is the one you want. Double-click it to add it to the list at the bottom.
5. That address changes each time the game starts, so find a pointer chain to it: right-click it in the list, choose **Pointer scan for this address**, keep the settings, click **OK** and save the scan.
6. Close the game, start it again, and find the line's address again (steps 3 and 4). In the pointer scan window, choose **Pointer scanner > Rescan memory** and give it the new address. Do this once or twice more: what is left works every time.
7. Choose a result whose **Base Address** starts with the game's program, such as `"gta2.exe"+272F40`, and with few offsets.

In the profile, that result is the base `address` without the quotes, `"gta2.exe+272F40"`, and its offsets in the order of the columns, **Offset 0** first: `["E4"]`.

The `encoding` follows from how you found the text: `utf-16le` if you ticked UTF-16, otherwise `cp1252` for most games in Western European languages, `cp1250` for games in Central European ones (Polish, Czech, Hungarian), or `utf-8` if letters with accents look wrong with those.

For a game on Avalanche Studios' engine (the `avalanche` source), look for the shown line's ID instead of its text: set **Value Type** to **4 Bytes** and scan for the exact value 0 while no subtitle shows, then **Changed value** when one appears, **Unchanged value** while it stays, and 0 again after it is gone. Then find its pointer chain the same way.

### 4. Add the source

Add a `sources` list with a `memory` source, whose pointer chain names the version you found it in (`exe_sha256`, the SHA-256 from step 2):

```json
"sources": [
  {
    "type": "memory",
    "name": "subtitles",
    "encoding": "utf-16le",
    "pointers": [
      {
        "exe_sha256": "420af867036b1a66ef94c54b8db2e7e654da359031987c6602bcfa74972e089f",
        "address": "gta2.exe+272F40",
        "offsets": ["E4"]
      }
    ],
    "stages": [
      { "type": "tracker" }
    ]
  }
]
```

A game that shows text in several places, such as subtitles and a help box, gets one source for each, with its own `name`. Another version of the game gets its SHA-256 in `match` and its own entry in `pointers`.

### 5. Clean up the text

The `stages` of a source work on each line before it is shown and spoken, in order. Start with `tracker`, which every source like this needs: it passes a line on once it has stayed on screen for a moment, and not again until it changes. Then add what the app's text needs, as [the format](#format-version-1) describes each stage:

- `replace`, if the app's text has formatting marks: GTA2 writes colored words as `#word#`, and `{"pattern": "#([^#]*)#", "replace": "\\1"}` keeps the word without the marks;
- `translate`, so the voice can read the app in another language (lektor mode);
- `normalize`, usually only for speech (`"text": false`), so numbers and amounts are spoken as words.

If names come out wrong, add a `glossary`: names to keep untranslated, slang to translate by its meaning, and how a voice should pronounce a name.

### 6. Test

Choose **Reload** after each change and start the app again: a changed profile applies the next time its app starts. Play through a few scenes and listen. The Status tab says when a source cannot read the app, and what to do; the log has the details. If lines are read twice or cut short, change the `tracker`'s `stable_ms`; if menus or other text are read as garbage, check the pointer chain again with Cheat Engine after restarting the game.

Leave `overlay` off until the rest works. It loads the overlay into the app, so it needs the `sha256` of every version the profile lists, and should be tried in each.

### 7. Rate and share

Give the profile a `rating` medal for how far you tested it yourself, from `bronze` to `platinum`, as [the format](#format-version-1) describes. Then share it, as [CONTRIBUTING.md](../CONTRIBUTING.md#contributing-a-profile) says: in a pull request, or attached to an app support issue.

## Format (version 1)

A profile is a JSON file saved as UTF-8 (with or without a byte order mark), as current editors do by default.

- `version`: the profile format version. Older profiles are migrated automatically.
- `app`: the app's `title` and original release `year`, for display.
- `match`: how the app is recognized. `executables` lists its executables, because one app can ship several. Each has a `name` (the file name, e.g. `"gta2.exe"`) and, optionally, `sha256`: the SHA-256 of each build of that file the profile supports, in lowercase hex. With `sha256`, only those builds are read, and another build is reported as not supported yet, with its SHA-256, in the Status tab of the desktop app. Without it, any build with that name is read, which suits programs that update often.
- `rating` (optional): how far the profile is tested, as a medal, shown in the Profiles tab with what it means. Rate your profile by what you checked yourself, not by what you expect:
  - `bronze`: some of the app's texts are read, tried only briefly, so others may be missed.
  - `silver`: the main texts (dialogue, subtitles) are read, tested in the first part of the app.
  - `gold`: the main texts are read, tested through most of the app.
  - `platinum`: every text the app shows is read, tested through all of it.

  Without it, the profile is shown as not rated. Every bundled profile has one.
- `overlay` (optional, default `false`): whether the overlay is loaded into the app. It needs `sha256` for every executable, so the overlay is only ever loaded into builds it was tested with.
- `glossary` (optional): words and phrases of the app that translation and speech treat specially, by the input language they are written in (two-letter code, e.g. `"en"`; Norwegian is `"nb"`). A line read in another language gets none of them, since terms of one language turn another into gibberish; a glossary for another language can be added next to it. Each language has one entry per `term` (as the app writes it, e.g. `"Big Smoke"`, or a list of the ways it writes it, e.g. `["Big Smoke", "Big smoke"]`; each is matched as written, and in capitals in shouted lines, so a lowercase "big smoke" is still smoke), with one or more of:
  - `keep`: `true` if the term is never translated, e.g. a name that is also a word, like `"Sweet"`, which would otherwise become "Słodki". Matched with the same capitals, so "sweet" is still translated. Add `"female": true` for a woman's name, so it is declined as one.
  - `means`: plain words in the glossary's language the term is translated as, for slang the translation gets wrong, e.g. `{"term": "hood", "means": "neighborhood"}`, so "hood" becomes "okolica", not "kaptur". Matched in any capitals. A term is either kept or given a meaning, not both.
  - `pronounce`: how the term is pronounced, by output language, for the `pronounce` stage, e.g. `{"term": "Carl", "pronounce": {"pl": "Karl"}}`, so a Polish voice does not read it "Tsarl" while subtitles keep "Carl".

  For example:

  ```json
  "glossary": {
    "en": [
      { "term": "Sweet", "keep": true },
      { "term": "hood", "means": "neighborhood" },
      { "term": "Carl", "pronounce": { "pl": "Karl" } }
    ]
  }
  ```
- `sources` (optional): where to read the app's text. Each entry has a `type` (the source plugin), a `name`, optionally `poll_interval_ms` (default 250) and `stages`. Its other fields are defined by the plugin's own schema.
- `stages` (optional, per source): processing applied in order to that source's text, each with a `type`, the plugin's own fields, and optionally where it starts on: `text` (the text shown, e.g. subtitles) and `speech` (what is spoken), both `true` by default. For example, `{"type": "normalize", "text": false}` spells out numbers for the voice while subtitles keep "$50,000". The stages are:
  - `tracker`: passes a line on once it has stayed unchanged for `stable_ms` (default 500; the text is checked on every read of the source, so the wait is rounded up to whole `poll_interval_ms`: with 250 ms polling, 300 waits 500, so set a multiple), has at least `min_letters` letters (default 4), and letters make up at least half of its visible characters; the same line is passed on again only after it disappears or changes. Nearly every source needs it, because sources report the current text on every read.
  - `replace`: `rules`, a list of replacements applied in order, e.g. to remove an app's formatting marks. Each rule is either:
    - `{"find": "#", "replace": ""}`: plain text, matched literally;
    - `{"pattern": "#([^#]*)#", "replace": "\\1"}`: a regular expression (Python syntax), where `\1`, `\2`... in `replace` insert the pattern's groups. In JSON a backslash is written twice. GTA2 marks colored words like `#TEST#`; this rule keeps the word and drops the marks. Invalid patterns are reported when the profile loads, and a replacement that doesn't fit its pattern (such as `\2` for a pattern with one group) when the app starts. A pattern may take at most 0.1 s on a line; a line it takes longer on is skipped, and reported as a stage error.
  - `translate`: translates lines from the input language into the output language the user chose in the settings panel (lektor mode), when the two differ and a translation model for them is installed (otherwise lines pass untranslated). Models for English to and from about 50 languages, and for Spanish to and from Portuguese, can be downloaded in the desktop app's Translations tab. The input language is English unless the user chooses another. Place it after the stages that clean up the text and before `normalize`. It follows the profile's `glossary` for the line's input language, and leaves a line as written if it has fewer than `min_letters` letters (default 1) besides its kept terms and those with `pronounce`, so a line of only names, like "Carl, Zero, Zero, Carl.", is not translated.
  - `pronounce`: respells the terms of the `glossary` for the input language that have a `pronounce` for the output language, so the voice pronounces them right, e.g. "Carl" as "Karl" for a Polish voice. It keeps the ending a term was declined with ("Carlowi" becomes "Karlowi", "Big Smoke'a" becomes "Big Smołka"), and matches terms as written or in capitals, so "Carlos" and "carl" stay. Place it after `translate` and before `normalize`, usually only for speech: `{"type": "pronounce", "text": false}`. It has no settings.
  - `normalize`: spells out numbers, money, percentages, units, times, dates, common abbreviations and the symbols & and + in the output language the user chose in the settings panel, e.g. `$50,000` becomes "fifty thousand dollars" in English and "pięćdziesiąt tysięcy dolarów" in Polish, "2 min" becomes "dwie minuty", and "o 14:30" becomes "o czternastej trzydzieści". Place it after the stages that clean up the text. It has no settings.

### Memory source (`"type": "memory"`)

Reads text from the app's memory through a pointer chain, written as in Cheat Engine. Fields are described in `src/reflektortts/sources/memory/settings.schema.json`:

- `encoding`: how the app stores text: `utf-16le`, `utf-8`, `cp1250` or `cp1252`.
- `pointers`: one entry per supported build of the app. Memory addresses differ between releases (e.g. retail, patched, Steam), so each chain names the SHA-256 of the executable it was found in (`exe_sha256`, one of the builds in `match`: a profile that lists its builds and has a chain for another is refused, since that chain would never be used), its base `address` (`"gta2.exe+272F40"`) and its `offsets` in hex. On a build with no matching entry, the user is told the app version is not supported yet.

A pointer can outlive its text, e.g. in the app's menu, and then points at unrelated memory. Readings where under 90% of the characters could appear in dialogue (Latin letters with accents, Cyrillic, spaces, common punctuation) count as no text, so garbage is never read aloud.

### Avalanche source (`"type": "avalanche"`)

Reads subtitles in games on Avalanche Studios' engine (Mad Max). A subtitle there holds the ID of the line it shows, the same in every language. The source reads that ID from the game's memory and the line's text, in the input language set in the settings panel, from the game's own files: the `stringlookup` text files in its bundles, one per language (`_eng`, `_pol`, ...), or their patched versions. The game has text in English, French, German, Italian, Japanese, Polish, Brazilian Portuguese (`pt`), Russian and Spanish. Reading them takes a few seconds, in the background, as soon as the game is detected (and again when the input language is changed to one not read yet); lines shown meanwhile are skipped. Fields are described in `src/reflektortts/sources/avalanche/settings.schema.json`:

- `pointers`: as in the memory source, one chain per build of the game, ending at the shown line's 32-bit ID (0 when no subtitle is shown).

To find the chain, find the shown line's ID first: the subtitle's UI element holds it, and it changes with every line and is 0 between lines.

### VLC source (`"type": "vlc"`)

Reads the subtitles of what VLC media player 3 plays, from the video's subtitle file, in time with VLC: it follows VLC's playback time, its speed and its subtitle delay through VLC's web interface. It has no fields. The bundled profile, `vlc-media-player-2001.json`, uses it for any VLC build, without the overlay: VLC shows its own subtitles, and ReflektorTTS reads them aloud, translated if you choose; the app's settings are in the window **App settings…** opens. It drops the marks subtitles for the hard of hearing use (`[door slams]`, `(sighs)`), lines of music (`♪ … ♪`) and dialogue dashes before reading.

To set it up:

1. Close VLC.
2. In the desktop window's Profiles tab, select VLC media player, click **Integration…**, then **Enable** in the VLC integration group. This turns on VLC's web interface for this computer only (127.0.0.1, also if it was set to listen on the network before), on VLC's own port (8080 unless you changed it), with a random password. Until then the profile is **Not set up**, and VLC is not read.
3. Start VLC and play a video with its subtitles next to it, named like the video: `movie.en.srt` for English or `movie.pl.srt` for Polish next to `movie.mkv`, in the same folder or in a `subtitles` or `subs` folder in it, where VLC itself looks. SubRip (`.srt`), WebVTT (`.vtt`, `.webvtt`), Advanced SubStation Alpha and SubStation Alpha (`.ass`, `.ssa`) and YouTube SubViewer (`.sbv`) files are read.

Of the files there, ReflektorTTS reads one whose name is the video's followed by words, one of which names the input language set in App settings… by its two- or three-letter code or its name in English or in itself, with or without accents (`en`, `eng`, `english`; `fr`, `fre`, `fra`, `french`, `français`, `francais`), such as `Movie.2019.English.srt`, or by its code with a region, such as `movie.pt-BR.srt`; else the one named exactly like the video (`movie.srt`). The video's name must appear as whole words, so `Show - 10.en.srt` is not read for `Show - 1.mkv`. Of several such files, the one with the fewest extra words is read: `movie.en.srt` before `movie.en.sdh.srt`; of files that differ only in their format, such as `movie.en.srt` and `movie.en.vtt`, the `.srt`. A "forced" file, such as `movie.en.forced.srt`, holds only the lines spoken in a foreign language, so it is read only if there is no other. A file in another language, such as `movie.de.srt`, is never read, nor one whose name also names another language, such as `movie.en.de.srt`; `hi` beside another language marks subtitles for the hearing-impaired (`movie.en.hi.srt` is English), and names Hindi only on its own. A word that several languages' names share, such as "Norwegian" for Bokmål and Nynorsk, names the one it usually means (Bokmål), or none. Files in other formats VLC shows, such as `.sub` or `.stl`, are not read. A video or song without any subtitle file is not read, quietly; one that has subtitle files but none to read is reported in the Status tab, with the file name to use.

Good to know:

- **The password** is kept in VLC's own settings file (`vlcrc`), as VLC needs it, and not by ReflektorTTS. VLC's web interface cannot be reached from other computers, but any program on this one that knows the password can control VLC through it.
- If you set up VLC's web interface yourself, e.g. for a remote on your phone, the integration counts as enabled and changes nothing; ReflektorTTS reads VLC as long as the interface answers on 127.0.0.1 (no host set, or `0.0.0.0`, `127.0.0.1` or `localhost`).
- **Disable** puts back what ReflektorTTS changed, except settings you changed since. VLC must be closed to enable or disable, since VLC writes back its settings when it closes.
- **Disable the VLC integration before uninstalling ReflektorTTS** with the option to delete your settings: that deletes ReflektorTTS's record of what it changed (`integrations\vlc.json` in `%LOCALAPPDATA%\ReflektorTTS`), and VLC's web interface then stays on until you turn it off in VLC: **Tools > Preferences**, **Show settings: All**, then **Interface > Main interfaces**, and clear **Web**.
- Only subtitle files are read, not subtitles inside the video file (as in many `.mkv` files). Only their text is read: styling, positions and drawings in `.ass` and `.ssa` files, and the reading aids over words in `.vtt` files (ruby text), are left out. Where several lines are shown at once (signs and dialogue in `.ass` files, often), the one that appeared last is read; lines that appear together are read together, and a line drawn twice at once (on two layers of an `.ass` file, for its border or glow) is read once.
- VLC chooses the subtitles it shows by itself, and you can switch them while watching; ReflektorTTS cannot see which, so with several files the two may differ (VLC prefers `movie.srt`, even in `subs`, to `movie.en.srt`). One file per language avoids that.
- In dense dialogue, or when VLC plays faster, speech falls behind the picture, because new lines wait their turn by default. Set **New lines** in App settings… to **Speed up to catch up** or **Cut off the current one**.
- Only one VLC at a time can be read: the first one started gets the web interface's port. If another program uses that port, VLC's web interface does not start, and the Status tab says what to do.
- VLC 3 installed from videolan.org (or your Linux distribution) is supported. A portable copy of VLC, and VLC from Snap or Flatpak, keep their settings elsewhere, and VLC 4 has not been tried yet.

## Naming

- One app = one file, named `title-year.json`: the app's title and original release year, lowercase ASCII, words separated by hyphens. Example: `grand-theft-auto-2-1999.json`.
- Always include the year, even if no other app shares the title, so a later remake never forces a rename.
- The executable's name is not part of the file name. It goes in `match.executables`.

## What does not belong in a profile

Profiles are shared, so they hold only what describes the app. Per-user state, such as whether a profile is enabled or which voice someone prefers, is stored in the user's settings, not here.
