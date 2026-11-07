<p align="center">
  <img src="docs/images/icon.png" alt="ReflektorTTS icon: a studio microphone in an orange spotlight" width="128">
</p>

<h1 align="center">ReflektorTTS</h1>

<p align="center">
  <b>Your apps, read aloud.</b><br>
  Game dialogue, subtitles and messages, spoken and translated into your language.
</p>

<p align="center">
  <a href="https://github.com/Infinitinker/ReflektorTTS/releases/latest"><img src="https://img.shields.io/github/v/release/Infinitinker/ReflektorTTS?label=download" alt="Latest release"></a>
  <a href="https://github.com/Infinitinker/ReflektorTTS/actions/workflows/checks.yml"><img src="https://github.com/Infinitinker/ReflektorTTS/actions/workflows/checks.yml/badge.svg" alt="Checks"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-GPL--3.0--or--later-blue" alt="License: GPL-3.0-or-later"></a>
  <img src="https://img.shields.io/badge/platform-Windows-0078D6?logo=windows" alt="Platform: Windows">
  <img src="https://img.shields.io/badge/works-offline-2ea44f" alt="Works offline">
</p>

ReflektorTTS reads an app's text aloud as it appears on screen, and can translate it on the way, in the style of a Polish *lektor*: in Poland, foreign films are traditionally shown with one calm voice reading the translation over the original soundtrack, which stays audible underneath. ReflektorTTS does the same for games: the original sound keeps playing, a little quieter, while a voice reads the line in your language.

<p align="center">
  <a href="https://github.com/Infinitinker/ReflektorTTS/releases/latest"><b>⬇️ Download ReflektorTTS for Windows</b></a>
</p>

## What it does

- 🗣️ **Reads the text aloud** as it appears: dialogue, cutscene subtitles, help messages.
- 🌍 **Translates it on the way**, offline, with Argos Translate models.
- 🔉 **Lowers the game's sound** while the voice speaks, and brings it back afterwards.
- 💬 **Shows subtitles** over the game, for example the translation while the original plays.
- 🎮 **Is set up from inside the game**: press **Ctrl+Shift+R** for the ReflektorTTS panel, with no Alt+Tab, which older games often don't survive.
- 🔒 **Stays on your computer**: it runs offline, the text it reads never leaves your computer, and nothing is downloaded unless you ask.
- 🧩 **Learns new apps from profiles**: one small file per app, which anyone can write and share.

## Supported apps

| App | Edition | What is read |
| --- | --- | --- |
| **Grand Theft Auto 2** | 1999, the 9.6 freeware release | Subtitles |
| **Grand Theft Auto: San Andreas** | 2004, Steam | Subtitles and the help box, with a glossary that keeps names like Sweet and Big Smoke untranslated and pronounces them right in Polish |
| **Mad Max** | 2015, Steam | Subtitles, in the game language you choose |

Each app is described by a profile, so more apps can be added without changing ReflektorTTS itself; see [Profiles](#profiles).

## Getting started

1. **Download** `ReflektorTTS-<version>-windows-x64-setup.exe` from the [latest release](https://github.com/Infinitinker/ReflektorTTS/releases/latest) and run it. It installs ReflektorTTS for you alone, without asking for administrator rights, or, if you choose, for all users of the computer.
2. **Start ReflektorTTS** from the installer's last page or the Start menu. Its icon appears next to the clock; click it to open the window.
3. **Start a supported game.** ReflektorTTS notices it and reads its text aloud, with a voice Windows already has.
4. **Press Ctrl+Shift+R** in the game to choose the voice, the languages, the reading speed and more.

For better voices, or to translate, download them in the window's **Voices** and **Translations** tabs.

Rather not install anything? Download `ReflektorTTS-<version>-windows-x64.zip` instead, unpack it anywhere and run `ReflektorTTS.exe`.

<table>
  <tr>
    <td><img src="docs/images/status.png" alt="The Status tab: what ReflektorTTS is doing, its voice, languages and the app's sound, with links to the project and its support pages"></td>
    <td><img src="docs/images/voices.png" alt="The Voices tab, listing Piper voices to download"></td>
  </tr>
  <tr>
    <td align="center">What ReflektorTTS is doing</td>
    <td align="center">Voices to download</td>
  </tr>
</table>

## The desktop window

ReflektorTTS runs next to the clock: its icon there opens the window, pauses reading, switches **Start with Windows** on or off, or quits. Closing the window leaves ReflektorTTS running.

- **Status** shows what ReflektorTTS is doing: the app it reads, or that it waits for one, and an app version its profile does not support yet, with the voice, the languages and what happens to the app's sound: the app's own settings, or with no app running, the ones a new app starts with. It also pauses reading, quits ReflektorTTS, and links to the project page, bug reports and the support pages.
- **Profiles** lists the profiles, bundled and your own, says which are used and why others are not, enables or disables them, and copies, removes or imports profile files. **App settings…** opens the selected app's settings in a window of their own beside the ReflektorTTS window, the same as in the game, whether or not the app is running: set up an app before you start it, or one without the overlay. Clicking it again brings that window to the front.
- **Voices** and **Translations** download voices and translation models; see [Voices](#voices) and [Translation](#translation).
- **Settings** has the **Start with Windows** switch: ReflektorTTS then starts, hidden next to the clock, when you sign in. A first install for you alone turns it on unless you untick it; Task Manager's Startup apps can turn it off too. It also opens the settings, logs and profiles folders.

An app's voice is loaded when the app starts and unloaded when it closes. A translation model, once used, stays loaded until ReflektorTTS quits, so the next app translates right away.

## In the game

In an app with the overlay, press **Ctrl+Shift+R** to open the ReflektorTTS panel. From top to bottom it follows a line through ReflektorTTS:

- **Input**: the app's language, and which of its texts are read.
- **Processing**: the steps each line goes through, such as translation, each switched on or off for the text shown and for speech.
- **Output**: your language, the voice, the reading speed, what a new line does while another is spoken, the app's sound, pause, and subtitles.

It also shows the last line read. Everything chosen there is saved for each app, in `%LOCALAPPDATA%\ReflektorTTS\settings\profiles\`, one file per app; deleting an app's file resets it.

The same settings, without pause and the last line read, open in a window of their own from **App settings…** in the Profiles tab, for any app, running or not.

## Voices

- **Windows voices** are the ones installed in Windows Settings > Time & language > Speech, e.g. Microsoft Adam (Polish). Windows comes with some, so ReflektorTTS speaks without downloading anything.
- **Piper voices** sound more natural and are downloaded in the Voices tab. The preferred default, `en_US-ljspeech-medium`, is trained on the public-domain LJ Speech dataset.

Select a voice to read its license and open its page, then **Download** it: it can be used right away, even in a game that is running. **Preview** lets you hear an installed voice first.

Any language can be chosen as yours. Without a voice for it, lines are only translated and shown as subtitles.

## Translation

Set the game's language in the panel's Input section and yours in Output; when they differ, each line is translated before it is spoken and shown. To hear the original instead, untick `translate` in the panel's Processing section.

Translation uses the models of [Argos Translate](https://github.com/argosopentech/argos-translate), one per pair of languages, downloaded in the Translations tab. They run offline on the CPU, at about 0.1 s per line. The English–Polish model (about 80 MB), for example, is derived from an [OPUS-MT](https://github.com/Helsinki-NLP/Opus-MT) model by Jörg Tiedemann and Santhosh Thottingal and licensed CC-BY 4.0.

A profile's glossary helps the translation along: it keeps names that are also words untranslated ("Sweet" stays a name), gives slang its meaning ("hood" is not a car's hood), and says how names are pronounced ("Carl" is read "Karl" in Polish, while subtitles keep "Carl").

## The game's sound

While a line is spoken, ReflektorTTS lowers the game's sound to 30% of its own volume, like a *lektor* speaking over the original, and brings it back half a second after the voice stops. The panel's Output section switches this off or sets the level. Only the game's slider in the Windows volume mixer changes, not other apps.

## Subtitles

ReflektorTTS can also show each line as a subtitle over the game, for example the translation while the original plays. Switch them on under Subtitles in the panel's Output section, where you also set their size and position. They sit at the top by default, so the game's own text, usually at the bottom, stays visible.

## Profiles

Each app is described by one JSON file, a profile: how to recognize the app, where to read its text, how to process it, and its glossary. Your own go in `%LOCALAPPDATA%\ReflektorTTS\profiles\`, and the Profiles tab imports them. [docs/profiles.md](docs/profiles.md) explains the format, and [CONTRIBUTING.md](CONTRIBUTING.md) how to share a profile so it ships with ReflektorTTS.

## Questions

**My antivirus blocks `reflektortts-inject.exe`.**
The overlay works by loading into the game, as in-game overlays do, which antivirus programs may distrust. Allow `reflektortts-inject.exe` in the `overlay` folder to use the overlay; games are read without it too.

**Windows says "Windows protected your PC".**
ReflektorTTS is not code-signed yet, so Windows SmartScreen doesn't know it. Choose **More info**, then **Run anyway**.

**Can I use it in online games?**
No. The overlay and reading a game's memory are meant for single-player and offline modes. Anti-cheat software may treat them as cheating, which can get your account banned.

**A game runs, but nothing is read.**
Look at the Status tab. It says when a game's version is not supported by its profile yet. The logs, opened from the Settings tab, say more.

**How do I stop ReflektorTTS from starting with Windows?**
Untick **Start with Windows** in the window's Settings tab or in its icon's menu next to the clock.

**Where are my settings?**
Settings, downloaded voices and models, your own profiles and the logs are all in `%LOCALAPPDATA%\ReflektorTTS`. They stay when you update ReflektorTTS.

**How do I update or remove it?**
Run the newer installer. If ReflektorTTS is running, it asks you to quit it first (right-click its icon next to the clock > Quit); quit games that use the overlay too. It then updates ReflektorTTS and keeps your settings. To remove it, use Windows Settings > Apps; it asks whether to delete your settings and downloads too (removing an install for all users leaves each user's own). With the zip, replace its folder to update, and delete it and `%LOCALAPPDATA%\ReflektorTTS` to remove it.

## Contributing

Profiles for more games, fixes and ideas are welcome: see [CONTRIBUTING.md](CONTRIBUTING.md). Found a security problem? Please report it privately, as [SECURITY.md](SECURITY.md) describes.

Further documentation:

- [docs/profiles.md](docs/profiles.md): profiles and their format
- [native/README.md](native/README.md): the native code: the overlay, and the code it shares
- [docs/architecture.md](docs/architecture.md): how ReflektorTTS is built, and what is planned
- [docs/plugins.md](docs/plugins.md): writing sources, stages, speech engines and download sources
- [docs/api.md](docs/api.md): the local API, through which the desktop app and the overlay control ReflektorTTS

## Support

ReflektorTTS is free, with no ads and no tracking. If it makes your games better, you can buy me a coffee:

<p>
  <a href="https://ko-fi.com/infinitinker"><img src="https://img.shields.io/badge/Ko--fi-support-FF5E5B?logo=kofi&logoColor=white" alt="Support on Ko-fi"></a>
  <a href="https://buycoffee.to/infinitinker"><img src="https://img.shields.io/badge/buycoffee.to-support-FFB400" alt="Support on buycoffee.to"></a>
</p>

Ko-fi takes cards and PayPal; buycoffee.to suits Polish supporters, with BLIK and Polish bank transfers.

## License

Copyright (C) 2026 Infinitinker. ReflektorTTS is free software under the GPL-3.0-or-later; see [LICENSE](LICENSE). [COPYRIGHT](COPYRIGHT) adds a permission to combine it with the Intel and NVIDIA libraries that CTranslate2, the translation engine, is built with. The overlay includes Dear ImGui, nlohmann/json, MinHook and the MinGW-w64 runtime, whose licenses are in [THIRD_PARTY_NOTICES](THIRD_PARTY_NOTICES).

Reading Avalanche games' files follows the formats as documented by [Gibbed.MadMax](https://github.com/gigaHours/Gibbed.MadMax) (Rick Gibbed, zlib license); file names are hashed with Bob Jenkins' public-domain lookup3. A game's text is read from your own copy while it runs and is not stored.

ReflektorTTS is not affiliated with the makers of the games it reads; their names and trademarks belong to their owners.
