# Contributing to ReflektorTTS

Thank you for helping! Profiles for more games are the most welcome contribution, and you don't need to be a programmer to write one. Fixes, ideas and bug reports are welcome too.

- **Found a bug?** Open an issue with the bug report form. The logs help most: the Settings tab's **Open logs folder** button opens them.
- **Want a game supported?** Open an issue with the app support form, or write its profile yourself (below).
- **Found a security problem?** Report it privately, as [SECURITY.md](SECURITY.md) describes, not in an issue.

Everything in the project is written in English, with American spelling (license, color, canceled). Contributions are accepted under the project's license: the GPL-3.0-or-later with the additional permission in [COPYRIGHT](COPYRIGHT).

## Contributing a profile

A profile is one JSON file that tells ReflektorTTS how to recognize a game and where its text is. [docs/profiles.md](docs/profiles.md) explains the format.

1. In the ReflektorTTS window's Profiles tab, select a bundled profile close to what you need and choose **Copy to edit**, or start a new file in `%LOCALAPPDATA%\ReflektorTTS\profiles\`.
2. Edit it in any text editor, saved as UTF-8, and choose **Reload**. A profile with a mistake is shown as broken, with the reason.
3. Play the game and check that its text is read. List the `sha256` of each build you tested, which a profile with the overlay must do: once a profile lists builds, the Status tab shows the SHA-256 of any other build it meets.
4. Give it a `rating` medal for how far you tested it, from `bronze` (tried briefly) to `platinum` (every text read, tested to the end); [docs/profiles.md](docs/profiles.md) says what each one takes.
5. Share it: open a pull request that adds it to `src/reflektortts/profiles/bundled/`, with its row and section in [SUPPORTED_APPS.md](SUPPORTED_APPS.md), or attach it to an app support issue.

Name the file after the game and its release year, in lowercase with dashes, like `grand-theft-auto-2-1999.json`.

## Code

[docs/development.md](docs/development.md) has the setup on Windows, how to run ReflektorTTS from source, every check with its command, and the end-to-end test; [docs/architecture.md](docs/architecture.md) explains how the code is organized, and [docs/plugins.md](docs/plugins.md) how to add sources, processing stages, speech engines and download sources as plugins.

1. Work on a branch from `dev`, and open the pull request to `dev`. `main` gets the changes from `dev` through a pull request.
2. Run the checks before pushing: `pytest`, `mypy`, `ruff check`, `ruff format --check` and `lint-imports`; after C++ changes also `tools/check_includes.py`, clang-format and clang-tidy. The `Checks` workflow runs them, with the license check, for every pull request, and the `E2E tests` workflow the end-to-end test.
3. A new dependency needs a license compatible with the GPL-3.0 (MIT, BSD, Apache-2.0, LGPL, GPL), checked before it is added, and every runtime dependency is required, never optional. After adding or upgrading one, `tools/licenses.py` must pass, `tools/release-constraints.txt` and `THIRD-PARTY-NOTICES.md` are written again and committed, and a package under the GPL, LGPL or MPL gets its source listed in `tools/sources.py` ([docs/releasing.md](docs/releasing.md#dependencies-and-notices)).
4. Tests live in `tests/`, mirroring `src/reflektortts/` (the tests for `src/reflektortts/stages/tracker.py` are in `tests/stages/test_tracker.py`), together with their fakes; nothing test-only goes in `src/`. They run without a game, a GPU or the network. The tools' tests are in `tests/tools/`, and the end-to-end test in `tests/e2e/`.
5. Update the docs in the same pull request as the code they describe. Commits follow [Conventional Commits](https://www.conventionalcommits.org/), with a scope from CLAUDE.md, such as `fix(overlay): keep the panel on top`.
