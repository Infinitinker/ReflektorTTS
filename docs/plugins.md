# Writing plugins

ReflektorTTS reads text through **sources**, processes it with **stages**, and speaks it with **TTS engines**; **download sources** offer the voices and translation models the user can download. Each is a plugin that registers itself through a Python entry point, so adding one never needs changes in the core or the UI. The built-in plugins register the same way; read them as examples.

| Kind | Entry-point group | Contract | Built-in examples |
|---|---|---|---|
| Source | `reflektortts.sources` | `Source` in `pipeline/protocols.py` | `memory`, `avalanche`, `vlc` (`sources/`) |
| Stage | `reflektortts.stages` | `Stage` in `pipeline/protocols.py` | `tracker`, `replace`, `translate`, `pronounce`, `normalize` (`stages/`) |
| TTS engine | `reflektortts.tts_engines` | `TtsEngine` in `tts/engine.py` | `piper`, `windows` (`tts/engines/`) |
| Download source | `reflektortts.downloads` | `DownloadSource` in `downloads/source.py` | `piper`, `argos` (`downloads/`) |

Sinks (where finished lines go) follow the `Sink` contract but have no plugin group yet: the core uses its built-in `tts`, `subtitles` and `events` sinks, which the user sets up in the overlay rather than per app. A group will be added with the first sink a profile needs to choose.

## Registering a plugin

A plugin package declares an entry point whose value is a plugin object, for example in its `pyproject.toml`:

```toml
[project.entry-points."reflektortts.sources"]
ocr = "my_package.ocr_plugin:PLUGIN"
```

The entry point's object must be a `SourcePlugin`, `StagePlugin`, `EnginePlugin` or `DownloadPlugin`. A plugin that cannot be imported, or is something else, is logged and skipped, so it never stops ReflektorTTS or the other plugins; so is a source or stage plugin whose settings schema is not a valid JSON Schema, and of two plugins of one kind with the same type (or download sources with the same name), the second. Likewise, a source or stage that fails while an app is read is reported (`source.error`, `stage.error`) and skipped, and a stage whose `inactive_reason` fails counts as inactive.

## Settings and profiles

Profiles choose plugins by `type`. A source entry in a profile looks like this:

```json
{
  "type": "memory",
  "name": "subtitles",
  "poll_interval_ms": 250,
  "encoding": "utf-16le",
  "pointers": [ ... ],
  "stages": [
    { "type": "tracker", "stable_ms": 500 },
    { "type": "replace", "rules": [{ "find": "#", "replace": "" }] }
  ]
}
```

The core reads `type`, `name`, `poll_interval_ms` and `stages` (for a stage entry: `type`). **Every other field belongs to the plugin** and is checked against the plugin's own JSON Schema, which it ships as a file next to its code and returns as `settings_schema`. Profiles that do not match are rejected with the file, the path of the problem and what is wrong, e.g. `game.json: $.sources[0].stages[1].limit: '3' is not of type 'integer'`.

Write schemas with `"additionalProperties": false` so typos are caught, give every field a `description` (UIs will show it), and document defaults in the description.

## Sources

A source is named after how it reads (`memory`, reading text through a pointer chain), when it needs one engine's know-how, after that engine (`avalanche`, for Avalanche Studios' engine), or, when it reads one app through what that app offers, after the app (`vlc`, through VLC's web interface), with no category prefix. Every profile for a game on that engine uses the same source with its own addresses.

```python
class Source(Protocol):
    name: str
    poll_interval: float  # seconds between reads

    def read(self, languages: Languages) -> str | None: ...  # the text shown right now, or None
    def close(self) -> None: ...
```

```python
SourcePlugin(type="memory", settings_schema=..., create=create, builds=builds)


def create(source: SourceSettings, app: RunningApp) -> Source: ...
def builds(settings: Mapping[str, Any]) -> Iterable[str]: ...  # optional
```

- `create` gets the profile's entry (`source.settings` holds the plugin's own, already validated fields; `source.name` and `source.poll_interval` come from the core) and the running app (its profile and process ID). Turn the settings into your own dataclasses here rather than passing dicts around.
- `builds` is optional: the builds of the app (the SHA-256 of its executable) that the source's fields are for, such as one per pointer chain. In a profile that lists its builds, each must be listed, or the profile is refused when it loads, which catches a mistyped hash.
- `read` returns the **current** text on every call, even if it has not changed; the tracker stage turns that into one line per change. Return `None` (or an empty string) when there is no text.
- `languages` are the user's input and output languages. Most sources read whatever the app shows and ignore them; a source that can read a line in several languages, like `avalanche`, reads it in the input language.
- `read` runs on the thread that polls every source, so keep it quick: do slow work (reading an app's files, say) in a thread of your own and return `None` until it is done, as `avalanche` does.
- Raise an exception with a message the user understands when reading fails ("Cannot read the app's memory at 672F40."), saying what to do where you can. Keep it short: the Status tab gives it two lines and cuts a longer one, showing it whole only while the mouse is over it. The runner reports it once as a `source.error` event and keeps polling; the status shows the error (the desktop window's Status tab, the overlay's panel) until the source works again, which is logged. If it fails with another message meanwhile (the next video has no subtitles either, say), the status shows the new message instead, without another event and only in the debug log; so a message may name what it is about, such as a file. A source that cannot start at all should raise from `create`, e.g. "This version of the app is not supported by its profile yet"; it is not tried again until the app starts again, so a problem the user can fix while the app runs (a setting of the app, say) belongs in `read`.
- `close` releases what the source holds (handles, files). It is called when the app exits.
- Platform-specific code stays inside the plugin, behind a small interface with one implementation per OS. Code that several sources need goes into a shared module instead: sources that read the app's memory use `process_memory/` for the process and pointer chains (`parse_pointer_chains`, `chain_for`, `resolve`), and `apps/executable.py` for the app's executable (`executable_path`, `executable_sha256`).

### Integrations

Some apps can be read only once their own settings are changed, e.g. a web interface switched on. A source plugin then offers an **integration**, which the user enables from the desktop window's Profiles tab, with the profile's Integration… button, instead of editing the app's settings by hand:

```python
SourcePlugin(type="vlc", settings_schema=..., create=create, integration=create_integration)


def create_integration(state_file: Path) -> Integration: ...  # Touches no files.


class Integration(Protocol):  # In reflektortts/integrations.py.
    name: str  # Read after "the": "VLC integration".
    description: str  # What enabling changes and disabling puts back, for the user.

    def state(self) -> IntegrationState: ...  # ENABLED, DISABLED, or UNAVAILABLE with a reason.
    def enable(self) -> None: ...  # Raises IntegrationError with what to do.
    def disable(self) -> None: ...  # The same.
```

- `integration` is a factory: given the path of a JSON file the integration may keep its state in (`integrations/<type>.json` in the state folder; neither may exist yet, so create the folder when you first write), it returns the integration. The core calls it once, at start, and only `state`, `enable` and `disable` may then touch files or the app, so creating it never fails and tests can create the core without the app. A factory that raises anyway is logged and skipped. The integration's ID is the plugin's type.
- A profile whose sources **all** need an integration that is not enabled is not read at all: its app is not even watched for, and the Profiles tab shows it as "Not set up"; its Integration… button opens a window with a group for the integration (its `name` as the title, its `description`, its state and an Enable or Disable button). A profile with another source still reads that one.
- `state` checks the app's settings on every call (the user can change them outside ReflektorTTS); the core calls it whenever profiles are listed or chosen, every few seconds, so keep it to reading a file. Count a setup the user made by hand as `ENABLED`, if the source can read with it. Say why it is `UNAVAILABLE` in the user's terms, in a way that also fits users who do not have the app ("VLC's settings file was not found: if VLC is installed, start it once, close it, and try again"). A `state` that raises counts as unavailable with the error as its reason, and is logged once.
- `enable` changes only what the source needs; `disable` puts back what `enable` changed, line for line, and leaves alone what the user changed since (record the original and the value written, in the state file, not in the app's own settings). Never store a secret the app keeps itself: the source reads it from the app's settings. Write atomically, and refuse with an `IntegrationError` what cannot be done safely, e.g. while the app runs and would overwrite its settings: its message is shown to the user as it is ("Close VLC first, then try again."). The core refuses to enable an unavailable integration with its reason, so `enable` need not check that again.
- Calls are made under the core's lock, one at a time; keep them quick.
- The `vlc` source is the example (`sources/vlc/`). Its integration (`integration.py`) adds VLC's web interface to `extraintf` in VLC's settings file (`vlcrc`, edited as bytes so every other byte stays as VLC wrote it, `vlcrc.py`), sets a random password if there is none, and limits the interface to 127.0.0.1 if no host is set; a web interface the user set up counts as enabled and is left alone. It refuses while VLC runs (`apps.detector.running_processes`), records each line it replaced and the value it wrote (only the password's SHA-256), and on disable takes out only the module it added and puts back each other line whose value is still its own. The source (`source.py`) reads the password and port from `vlcrc` each time the file changes, asks VLC's web interface for its status, and reads the cue of the media's subtitle file (found by `subtitles.py`) at VLC's playback time (`timing.py`): `formats/` holds one parser per format (`srt.py`, `vtt.py`, `ass.py`, `sbv.py`), each turning the file's text into the same cues (`cues.py`) with the shared text cleanup in `markup.py`, and its `__init__.py` picks the parser by the file's extension; the HTTP client is behind a function the tests fake (`web.py`, `tests/sources/vlc/fake_vlc.py`).

## Stages

```python
class Stage(Protocol):
    def process(self, event: TextEvent) -> TextEvent | None: ...
```

```python
StagePlugin(
    type="tracker",
    settings_schema=...,
    create=create,
    summary="Waits until a line settles",
    warning_when_disabled="Needed: or the voice restarts on every reading",
    inactive_reason=inactive_reason,  # Optional.
)


def create(settings: Mapping[str, Any], glossaries: Glossaries) -> Stage: ...


def inactive_reason(languages: Languages) -> str | None: ...
```

- `create` gets the stage's own, already validated fields from the profile, and the profile's glossaries (`reflektortts.glossary`), by input language: terms of the app to keep untranslated, translate with a given meaning, or speak another way. Use the one for each line's `input_language`, which the user can change while the app runs, if your stage translates or speaks; otherwise ignore them.
- Return the event to pass on (use `dataclasses.replace` to change its text), or `None` to drop it.
- An event with **empty text** means the source has no text right now. Stages that keep state, like the tracker, use it to notice a line disappearing; empty text is never delivered to sinks.
- `event.input_language` and `event.output_language` are the languages the user chose (ISO 639-1, e.g. `pl`), current when the line was read. Stages that depend on language, like `normalize` (output language) and `translate` (from the input to the output language), use them instead of settings of their own, so the user's choice applies to every app.
- A stage that does nothing with some languages says so with `inactive_reason`: given the user's languages, it returns why, in a few words for the user ("Input and output language are the same"), or `None` if the stage works with them. Meanwhile the runner skips the stage, so `process` only sees languages it works with, and the overlay grays the stage out with the reason, keeping the user's tick. `translate` uses it for matching languages and pairs without a model, and `normalize` for output languages without rules.
- Users can switch each stage on and off in the overlay, for the text shown and for speech; a switched-off stage is skipped there. Next to its tick they see its `type` and its `summary`, a few words on what it does. Set `warning_when_disabled` if reading breaks without the stage; it replaces the summary while the stage is off for either. The overlay keeps each stage to one line and cuts longer text, so keep these short.
- Each source gets its own stage objects for the text shown and for speech, so a stage may keep state; it is the same for both while both have it on, since they read the same lines. A stage with costly work shares its results between them, as `translate` does with its recent translations, so a line is translated once.
- Import heavy dependencies only when the stage first needs them, so the core starts fast. Models live in the user data folder and are never downloaded by the stage: it uses an installed one, or doesn't apply (`inactive_reason`), as `translate` does (`stages/translate/`).
- Exceptions are reported once as `stage.error`; the event is dropped.

## TTS engines

```python
class TtsEngine(Protocol):
    def synthesize(self, text: str, rate: float) -> Iterator[AudioChunk]: ...  # mono int16 samples + sample rate
```

```python
EnginePlugin(name="piper", create=create, list_voices=list_voices)


def create(voice_name: str) -> TtsEngine: ...
def list_voices() -> list[VoiceInfo]: ...
```

- Voices are written `engine:name`, e.g. `windows:Microsoft Adam`; `create` gets the part after the colon. A `VoiceInfo` also carries the engine's name as shown to users (`engine_title`, e.g. `Windows`).
- `rate` is the user's reading speed, a multiple of the voice's own pace from 0.5 to 2.
- Yield audio as soon as a part is ready (Piper yields per sentence), so speech starts early. The player plays it in short blocks so a new line can cut it off.
- Raise `VoiceError` with a helpful message when a voice cannot be used, e.g. listing the installed voices and where to get more.
- Engines run in the TTS process, but the core imports the plugin module to list voices. **Keep that import cheap**: import heavy libraries (models, runtimes) inside `create` or the engine class, as `tts/engines/piper.py` does.
- An engine that works on some systems only is registered on every one: it imports its system's libraries inside `list_voices` and `create`, and its `list_voices` returns no voices on the others, as `tts/engines/windows.py` does. Any other failure to list voices is logged as a warning, and the engine is skipped.
- List only installed voices, and never download one in `create`: downloads are a download source's job.

## Download sources

```python
class DownloadSource(Protocol):
    def entries(self, refresh: bool) -> list[Entry]: ...
    def download(self, entry: Entry, progress: Progress) -> None: ...
    def remove(self, entry: Entry) -> None: ...
```

```python
DownloadPlugin(name="piper", create=PiperVoices)  # create gets a cache folder of the source's own
```

- Every source behaves the same, so the desktop app shows them all alike. An `Entry` has an ID starting with the source's name (`piper:pl_PL-gosia-medium`; for a voice, the ID its speech engine gives the voice once installed, so it can be previewed and voices installed by other means are told apart), the source's name as shown to users (`source_title`, e.g. `Argos Translate`), a kind (`voice` or `translation`), its languages, size (or `None`), license as the source publishes it (or `None` if it does not), a page to read more, and whether it is installed.
- `entries` lists only languages in `reflektortts.languages.LANGUAGES` (every ISO 639-1 language), by the codes there: `primary_language` turns a catalog's tags into them (`no_NO` is `nb`). Leave out what ReflektorTTS cannot run, such as voices that need parts it does not ship. With `refresh`, fetch the list from the internet and save it in the cache folder; without a connection, use the saved list; raise `DownloadError` with a message for the user only if there is neither.
- `download` checks the download (against the source's checksums, if it gives any), installs it where its engine or stage finds it, and reports progress as it goes; it runs on a thread of its own. Use a staging folder (`reflektortts.staging`, in the folder you install into, so one cut off by quitting is removed at the next start), so a failed download never leaves a broken install, and treat names from the list or an archive as untrusted: check that every file lands inside its folder (a name like `../x` or, on Windows, `D:x` leads out) and cap what an archive may unpack to.
- Fetch with `downloads/http.py` and keep lists with `downloads/cache.py`, so every source talks to the internet the same way.

## Testing

Tests live in `tests/`, mirroring the package: the tests for `src/reflektortts/stages/tracker.py` are in `tests/stages/test_tracker.py`. They run without a running app, GPU, audio device or network. Put hardware- and app-dependent parts behind an interface and test against a fake kept in `tests/`, as `tests/process_memory/fake_memory.py` and the fake streams in `tests/tts/test_playback.py` do. Test an integration against settings files in pytest's `tmp_path`, never the user's own; `tests/fake_integration.py` stands in for one where the core or the API is tested.
