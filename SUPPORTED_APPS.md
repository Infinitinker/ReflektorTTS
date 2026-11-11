# Supported apps

ReflektorTTS reads these apps as soon as they start, with the profile it comes with for each; VLC media player once its integration is enabled. Each profile is rated with a medal for how far it is tested, so you know what to expect.

| App | Edition | Rating | What is read | Overlay |
| --- | --- | --- | --- | --- |
| [Grand Theft Auto 2](#grand-theft-auto-2) | 1999, the 9.6 freeware release | 🥉 Bronze | Subtitles | No |
| [Grand Theft Auto III](#grand-theft-auto-iii) | 2001, Steam | 🥉 Bronze | Subtitles, mission objectives, pager messages and the help box | No |
| [Grand Theft Auto: Vice City](#grand-theft-auto-vice-city) | 2002, Steam | 🥉 Bronze | Subtitles, mission objectives and the help box | No |
| [Grand Theft Auto: San Andreas](#grand-theft-auto-san-andreas) | 2004, Steam | 🥉 Bronze | Subtitles and the help box | Yes |
| [Mad Max](#mad-max) | 2015, Steam | 🥉 Bronze | Subtitles, in the game language you choose | Yes |
| [VLC media player](#vlc-media-player) | 3, installed from videolan.org | 🥇 Gold | The subtitles of the video playing, from its subtitle file, once the VLC integration is enabled | No |

## Ratings

The medal says how far a profile is tested, by its author, from what they checked themselves:

- 🥉 **Bronze**: some of the app's texts are read, tried only briefly, so others may be missed.
- 🥈 **Silver**: the main texts (dialogue, subtitles) are read, tested in the first part of the app.
- 🥇 **Gold**: the main texts are read, tested through most of the app.
- 💎 **Platinum**: every text the app shows is read, tested through all of it.

A profile rises as it is tested further. If you played on and everything was read, or something was missed, say so in an [app support issue](https://github.com/Infinitinker/ReflektorTTS/issues/new/choose).

## Settings for each app

Every app keeps its own settings: the voice, the languages, the reading speed and the rest. In an app with the overlay, press **Ctrl+Shift+R** to change them in the in-game panel without leaving it, and ReflektorTTS can show each line as a subtitle over the app, for example the translation. Apps without the overlay are read aloud the same way, with no panel and no subtitles of ReflektorTTS's own. For any app, the same settings open with **App settings…**: in the Status tab while the app is read, or in the Profiles tab, whether the app runs or not.

## Grand Theft Auto 2

- **Edition**: the 9.6 freeware release (`gta2.exe`). Other releases are not read yet; the Status tab says so when it meets one.
- **Rating**: 🥉 Bronze.
- **What is read**: subtitles.
- **Overlay**: none, since the game draws with DirectDraw, which the overlay does not support: no in-game panel, and no subtitles of ReflektorTTS's own. Change its settings with **App settings…**: in the Status tab while the game is read, or in the Profiles tab.

## Grand Theft Auto III

- **Edition**: the Steam release (`gta3.exe`). Other releases are not read yet; the Status tab says so when it meets one.
- **Rating**: 🥉 Bronze.
- **What is read**: subtitles with mission objectives, the help box and pager messages.
- **Overlay**: none, since the game draws with Direct3D 8, which the overlay does not support: no in-game panel, and no subtitles of ReflektorTTS's own. Change its settings with **App settings…**: in the Status tab while the game is read, or in the Profiles tab.
- **Glossary**: Misty, 8-Ball, Love and SPANK stay untranslated, and the Polish voice says Claude, Luigi, Joey, Leone and Liberty City the English way.
- **Good to know**: if the game starts only in Windows XP (Service Pack 3) compatibility mode, that mode runs it as administrator, so run ReflektorTTS as administrator too, or it cannot read the game.

## Grand Theft Auto: Vice City

- **Edition**: the Steam release (`gta-vc.exe`). Other releases are not read yet; the Status tab says so when it meets one.
- **Rating**: 🥉 Bronze.
- **What is read**: subtitles with mission objectives, and the help box.
- **Overlay**: none, since the game draws with Direct3D 8, which the overlay does not support: no in-game panel, and no subtitles of ReflektorTTS's own. Change its settings with **App settings…**: in the Status tab while the game is read, or in the Profiles tab.
- **Glossary**: Lance, Vance and Mercedes stay untranslated, the Polish voice says Tommy Vercetti, Sonny, Rosenberg and Vice City the English way, and "the greens" is translated as money.
- **Good to know**: if the game starts only in Windows XP (Service Pack 3) compatibility mode, that mode runs it as administrator, so run ReflektorTTS as administrator too, or it cannot read the game.

## Grand Theft Auto: San Andreas

- **Edition**: the Steam release (`gta-sa.exe`). Other releases are not read yet; the Status tab says so when it meets one.
- **Rating**: 🥉 Bronze.
- **What is read**: subtitles and the help box.
- **Overlay**: yes: change its settings in the in-game panel (**Ctrl+Shift+R**) or with **App settings…**, and switch on subtitles over the game there.
- **Glossary**: Sweet, Big Smoke, Big Bear, Truth and Kendl stay untranslated, the Polish voice says Carl, CJ, Ryder, Woozie, Cesar and Grove Street the English way, and slang is translated by its meaning: "hood" as turf, "paper" as money, "whip" as car, and more.

## Mad Max

- **Edition**: the Steam release (`MadMax.exe`). Other releases are not read yet; the Status tab says so when it meets one.
- **Rating**: 🥉 Bronze.
- **What is read**: subtitles, in the game language you choose as the input language (English, French, German, Italian, Japanese, Polish, Brazilian Portuguese, Russian or Spanish), whatever language the game itself runs in: with English speech and Polish subtitles, for example, the English or the Polish line can be read. The game's text is read from its own files when it starts, which takes a few seconds.
- **Overlay**: yes: change its settings in the in-game panel (**Ctrl+Shift+R**) or with **App settings…**, and switch on subtitles over the game there.

## VLC media player

- **Edition**: VLC 3, installed from videolan.org. A portable copy of VLC keeps its settings elsewhere, and VLC 4 has not been tried yet.
- **Rating**: 🥇 Gold.
- **What is read**: the subtitles of the video playing, in time with VLC, also when you pause, change the speed or the subtitle delay. They are read from the video's subtitle file next to it, in SubRip (`.srt`), WebVTT (`.vtt`), Advanced SubStation Alpha or SubStation Alpha (`.ass`, `.ssa`) or YouTube SubViewer (`.sbv`) format; subtitles inside the video file are not read.
- **Overlay**: none: VLC shows the video's own subtitles, and ReflektorTTS reads them aloud, translated if you choose, without an in-game panel or subtitles of its own. Change its settings with **App settings…**: in the Status tab while a video is read, or in the Profiles tab.
- **Setting it up**: ReflektorTTS follows VLC through VLC's web interface, which is off by default. With VLC closed, select VLC media player in the Profiles tab, choose **Integration…**, then **Enable**: it turns the web interface on for this computer only. **Disable** puts back what it changed. [docs/profiles.md](docs/profiles.md#vlc-source-type-vlc) says how subtitle files are found and more.

## Your app is not listed?

Ask for it with the [app support form](https://github.com/Infinitinker/ReflektorTTS/issues/new/choose), or write its profile yourself: one JSON file, no programming needed. [docs/profiles.md](docs/profiles.md) explains the format, and [CONTRIBUTING.md](CONTRIBUTING.md) how to share it so it ships with ReflektorTTS.
