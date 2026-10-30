# Writing plugins

ReflektorTTS reads text through **sources**, processes it with **stages**, and speaks it with **TTS engines**. Each is a plugin that registers itself through a Python entry point, so adding one never needs changes in the core or the UI. The built-in plugins register the same way; read them as examples.

| Kind | Entry-point group | Contract | Built-in examples |
|---|---|---|---|
| Source | `reflektortts.sources` | `Source` in `pipeline/protocols.py` | `memory` (`sources/memory/`) |
| Stage | `reflektortts.stages` | `Stage` in `pipeline/protocols.py` | `tracker`, `replace`, `translate`, `normalize` (`stages/`) |
| TTS engine | `reflektortts.tts_engines` | `TtsEngine` in `tts/engine.py` | `piper`, `windows` (`tts/engines/`) |

Sinks (where finished lines go) follow the `Sink` contract but have no plugin group yet: the core uses its built-in `tts`, `subtitles` and `events` sinks, which the player sets up in the overlay rather than per game. A group will be added with the first sink a profile needs to choose.

## Registering a plugin

A plugin package declares an entry point whose value is a plugin object, for example in its `pyproject.toml`:

```toml
[project.entry-points."reflektortts.sources"]
ocr = "my_package.ocr_plugin:PLUGIN"
```

The entry point's object must be a `SourcePlugin`, `StagePlugin` or `EnginePlugin`; anything else is rejected when plugins are loaded.

## Settings and profiles

Profiles choose plugins by `type`. A source entry in a profile looks like this:

```json
{
  "type": "memory",
  "name": "messages",
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

```python
class Source(Protocol):
    name: str
    poll_interval: float  # seconds between reads

    def read(self) -> str | None: ...  # the text shown right now, or None
    def close(self) -> None: ...
```

```python
SourcePlugin(type="memory", settings_schema=..., create=create)


def create(source: SourceSettings, game: RunningGame) -> Source: ...
```

- `create` gets the profile's entry (`source.settings` holds the plugin's own, already validated fields; `source.name` and `source.poll_interval` come from the core) and the running game (its profile and process ID). Turn the settings into your own dataclasses here rather than passing dicts around.
- `read` returns the **current** text on every call, even if it has not changed; the tracker stage turns that into one line per change. Return `None` (or an empty string) when there is no text.
- Raise an exception with a message the player understands when reading fails ("Cannot read the game's memory at 672F40."). The runner reports it once as a `source.error` event and keeps polling; it logs when the source works again. A source that cannot start at all should raise from `create`, e.g. "This version of the game is not supported by its profile yet".
- `close` releases what the source holds (handles, files). It is called when the game exits.
- Platform-specific code stays inside the plugin, behind a small interface with one implementation per OS (see `sources/memory/process_memory.py`).

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
    warning_when_disabled="Needed: without it, the voice restarts on every reading.",
)


def create(settings: Mapping[str, Any]) -> Stage: ...
```

- Return the event to pass on (use `dataclasses.replace` to change its text), or `None` to drop it.
- An event with **empty text** means the source has no text right now. Stages that keep state, like the tracker, use it to notice a line disappearing; empty text is never delivered to sinks.
- `event.game_language` and `event.output_language` are the languages the player chose (ISO 639-1, e.g. `pl`; the game language may be `auto`), current when the line was read. Stages that depend on language, like `normalize` (output language) and `translate` (from the game to the output language), use them instead of settings of their own, so the player's choice applies to every game. A stage without rules for a language should pass the line unchanged.
- Players can switch each stage on and off in the overlay; a switched-off stage is skipped. Next to its tick they see its `type` and its `summary`, a few words on what it does. Set `warning_when_disabled` if reading breaks without the stage.
- Each source gets its own stage objects, so a stage may keep state per source.
- Heavy dependencies and models belong in an optional extra and the user data folder, imported and downloaded only when the stage first needs them, as `translate` does (`stages/translate/`).
- Exceptions are reported once as `stage.error`; the event is dropped.

## TTS engines

```python
class TtsEngine(Protocol):
    def synthesize(self, text: str) -> Iterator[AudioChunk]: ...  # mono int16 samples + sample rate
```

```python
EnginePlugin(name="piper", create=create, list_voices=list_voices)


def create(voice_name: str) -> TtsEngine: ...
def list_voices() -> list[VoiceInfo]: ...
```

- Voices are written `engine:name`, e.g. `windows:Microsoft Adam`; `create` gets the part after the colon.
- Yield audio as soon as a part is ready (Piper yields per sentence), so speech starts early. The player plays it in short blocks so a new line can cut it off.
- Raise `VoiceError` with a helpful message when a voice cannot be used, e.g. listing the installed voices and where to get more.
- Engines run in the TTS process, but the core imports the plugin module to list voices. **Keep that import cheap**: import heavy libraries (models, runtimes) inside `create` or the engine class, as `tts/engines/piper.py` does.

## Testing

Tests live in `tests/`, mirroring the package: the tests for `src/reflektortts/stages/tracker.py` are in `tests/stages/test_tracker.py`. They run without a game, GPU, audio device or network. Put hardware- and game-dependent parts behind an interface and test against a fake kept in `tests/`, as `tests/sources/memory/fake_memory.py` and the fake streams in `tests/tts/test_playback.py` do.
