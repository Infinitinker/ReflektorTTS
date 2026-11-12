# Interface texts

How the texts of the interface are written: labels, buttons, menus, hints, messages and errors. Every new or changed text follows these rules.

<!-- shared-start: the rules up to shared-end are the same in every project; change them only where all projects change together. -->

## Rules

| Rule | Write | Not |
| --- | --- | --- |
| English only, with American spelling. | Color, Center, Analyzing colors | Colour, Centre, Analysing colours |
| Sentence case for labels, buttons, menu items, tab names and headings. | Save current settings, Restore defaults | Save Current Settings |
| The ellipsis character `…`, never three dots, and only on a command that asks for more before it acts, and on a progress text. A command that acts at once has none. | Open file…, Export…, Loading…, Downloading… | Loading..., Restore defaults… |
| Hints and descriptions are full sentences ending with a period. Labels have no period. | This item has no settings. (hint); Lock aspect ratio (label) | Small = quiet, large = loud (hint) |
| Clauses are joined with a colon. The en dash `–` is only for ranges and as a separator in names and labels. | The file could not be read: it is damaged. 22–119 mm, Inside – left | Drop a file – it is added to the list |
| Curly quotes “ ” and the apostrophe ’. | Save changes to “Draft”?, Don’t save | Save changes to "Draft"?, Don't save |
| No "Please". | Choose PNG or JPEG. | Please choose PNG or JPEG. |
| A count is written as "Label: n". | Files chosen: 3, Errors: 2 | 3 files chosen, Errors (2) |
| A control with a shortcut shows it as "Action (shortcut)" in its tooltip, with the keys of the system it runs on. | Undo (Ctrl+Z), New tab (⌘T) | Ctrl+Z: Undo |
| An error says what happened, then what to do, in the user's terms, never as a stack trace. | The app’s window was not found: is the app running? | Window handle is null. |
| One name per concept: the terms in `docs/architecture.md`. | the project’s own terms | synonyms for them |
| Units after a space, degrees with no space, × between dimensions. | 10.4 mm, 120 × 120 mm, 360°, 80 MB | 10.4mm, 120x120 mm, 360 deg |

Texts take values through the language's string formatting (template literals, f-strings, `std::format`), never through concatenated strings.

<!-- shared-end -->

## This project's own rules

The interface's texts are plain English strings, written in the code where they are used. There is no translation layer. They are:

- the desktop app's window and tray icon (Tkinter and pystray, in `src/reflektortts/desktop/`);
- the overlay's hint and panel, and the settings window (ImGui, in `native/overlay/src/ui/`, `native/panel/src/` and `native/shared/`);
- what plugins give users to read: a stage's `type`, `summary` and `warning_when_disabled`, the names of download sources and speech engines (`source_title`, `engine_title`), a voice's `installed_note`, an integration's `name` and `description`, and the titles and descriptions in their settings' JSON Schema;
- the messages of errors raised for the user, which the desktop app and the settings panel show as they are: a source's reading error, `IntegrationError`, `VoiceError`, `DownloadError`, and the local API's `{"error": "..."}` (see `docs/plugins.md` and `docs/api.md`);
- the installer's own messages (`[CustomMessages]` in `tools/installer.iss`).

| Rule | Write | Not |
| --- | --- | --- |
| A message the Status tab shows, such as a source's error, fits in two lines: the tab cuts a longer one and shows it whole only while the mouse is over it. A message may name what it is about, such as a file, since a new one replaces the last without another event. | No subtitles found in movie.en.srt: is it in the SubRip (.srt) format? | A paragraph on how VLC looks for subtitle files |
| A stage's `summary` is a few words beside its tick in the settings panel, with no period, like a label. `warning_when_disabled` replaces it while the stage is off. The panel keeps each stage to one line and cuts longer text. | Spells out numbers and money; Needed: or the voice restarts on every reading | This stage spells out the numbers and amounts of money in the line. |
| A language is shown by its English name, then its own name in parentheses. A translation is shown as its two languages' English names joined by an arrow. | Polish (Polski); English → Polish | Polski; en-pl |
| Names of apps, voices, models and other products are written as their makers write them, also where that is not sentence case. | Mad Max, VLC media player, Argos Translate, Microsoft Adam | Mad max, VLC Media Player |
| Where a system cannot show a character, the code that hands the text over replaces it, never the text itself: the tray icon's title on Linux takes only Latin-1, so `latin1` in `desktop/tray.py` writes `…` there as three dots. | `title[: MAX_TITLE - 1] + "…"`, then `latin1(title)` | `"..."` written in the text |

The terms are in [architecture.md](architecture.md). Examples from this app for the shared rules: an error with what to do in "Close VLC first, then try again: VLC writes back its own settings when it closes."; a command that asks for more in "App settings…", "Integration…" and "Import…"; a progress text in "Downloading…" and "Playing…".
