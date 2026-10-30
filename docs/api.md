# Local API (v1)

Every ReflektorTTS user interface, the in-game overlay included, controls the core through this API. It is served by the core on **`http://127.0.0.1:47821/v1`**, only on the local machine. The port is fixed so the overlay knows where to connect.

Requests and responses are JSON (UTF-8). There is no authentication: the API only listens on 127.0.0.1.

## Status

The status object, returned by several requests and sent as an event:

```json
{
  "type": "status",
  "game": { "title": "Grand Theft Auto 2", "pid": 4824 },
  "voice": "windows:Microsoft Adam",
  "game_language": "auto",
  "output_language": "pl",
  "paused": false,
  "ducking": true,
  "duck_volume": 0.3,
  "subtitles": true,
  "subtitle_size": "medium",
  "subtitle_position": "top",
  "sources": [
    {
      "name": "messages",
      "type": "memory",
      "enabled": true,
      "stages": [
        {
          "key": "messages/0:tracker",
          "type": "tracker",
          "summary": "Waits until a line settles",
          "warning": "Needed: without it, the voice restarts on every reading.",
          "enabled": true
        }
      ]
    }
  ]
}
```

| Field | Meaning |
|---|---|
| `game` | The game being read, or `null` while waiting for one |
| `voice` | The current voice, as `engine:name` |
| `game_language` | The language of the game's text (ISO 639-1 code), or `auto` to let e.g. translation detect it |
| `output_language` | The language lines are prepared, spoken and shown in (ISO 639-1 code) |
| `paused` | Whether reading is paused |
| `ducking` | Whether the game's sound is lowered while lines are spoken |
| `duck_volume` | The game's volume while lines are spoken, as a fraction of its own volume (0 to 1) |
| `subtitles` | Whether lines are shown as subtitles over the game |
| `subtitle_size` | `small`, `medium` or `large` |
| `subtitle_position` | `top` or `bottom` of the screen |
| `sources` | The stages of the game being read, per source in the game's profile, with whether the player has each switched on; empty while waiting for a game |

A source's `name` is its name in the profile, `type` its plugin, and `enabled` whether the player has it switched on; `name` identifies it for `PATCH /v1/sources`. A stage's `type` is its name in the profile and `summary` says in a few words what it does; `warning` (or `null`) is shown while the stage is switched off, if reading breaks without it. `key` identifies the stage for `PATCH /v1/stages`.

## Requests

### `GET /v1/status`

Returns the status.

### `GET /v1/voices`

Returns the voices available now, from every speech engine that works on this system:

```json
{
  "voices": [
    { "id": "piper:en_US-ljspeech-medium", "engine": "piper", "name": "en_US-ljspeech-medium", "language": "en-US" },
    { "id": "windows:Microsoft Adam", "engine": "windows", "name": "Microsoft Adam", "language": "pl-PL" }
  ]
}
```

`id` is what `PATCH /v1/settings` takes; `language` is a BCP 47 tag, so a UI can offer only the voices that speak the output language. Piper lists downloaded voices and the default voice, which is downloaded on first use.

### `GET /v1/languages`

Returns the languages the pipeline supports, with their names in their own language:

```json
{ "languages": [{ "code": "en", "name": "English" }, { "code": "pl", "name": "Polski" }] }
```

`game_language` also accepts `auto`.

### `PATCH /v1/settings`

Changes settings and saves them. Send any of the fields:

```json
{ "game_language": "en", "output_language": "pl", "voice": "windows:Microsoft Adam" }
```

- `game_language`: a `code` from `/v1/languages`, or `auto`.
- `output_language`: a `code` from `/v1/languages`. Lines read from then on are prepared for it. If the current voice does not speak it, the core switches to the voice last chosen for that language, or else the first voice that speaks it; with no such voice, the voice stays.
- `voice`: an `id` from `/v1/voices`. Switching starts a new speech process; the next line is spoken with the new voice. The voice is also remembered for its language.
- `ducking`: `true` or `false`, whether the game's sound is lowered while lines are spoken.
- `duck_volume`: a number from 0 to 1, the game's volume while lines are spoken as a fraction of its own; applies at once, also while lowered.
- `subtitles`: `true` or `false`, whether lines are shown as subtitles over the game. Switching them off hides the one shown.
- `subtitle_size`: `small`, `medium` or `large`.
- `subtitle_position`: `top` or `bottom`. Games usually show their own text at the bottom, so the default is `top`.

The ducking and subtitle fields are applied first, then the others in the order listed, so an explicit `voice` wins over the one a new output language picks. Returns the status.

### `PATCH /v1/sources`

Switches a source of the game being read on or off. A switched-off source is not read until switched on again; its stages keep their own settings. The choice is saved per game:

```json
{ "name": "messages", "enabled": false }
```

Returns the status.

### `PATCH /v1/stages`

Switches a stage of the game being read on or off. The choice is saved per game and applies to the next line read:

```json
{ "key": "messages/2:normalize", "enabled": false }
```

Returns the status.

### `POST /v1/pause`

Stops the line being spoken and ignores new lines until resumed. Returns the status.

### `POST /v1/resume`

Resumes reading. Returns the status.

### `POST /v1/stop`

Stops the line being spoken; the next line is spoken as usual. Returns the status.

## Errors

A request that cannot be carried out returns **HTTP 400** with a message for the user:

```json
{ "error": "There is no voice \"piper:missing\". Available: piper:en_US-ljspeech-medium, windows:Microsoft Adam." }
```

## Events: `GET /v1/events` (WebSocket)

On connecting, the client receives the current status. After that, every event the core produces arrives as one JSON text message. The server sends a ping every 30 seconds.

| `type` | Sent when | Other fields |
|---|---|---|
| `status` | The game, voice, languages, pause state or a stage switch changes | As in the status object |
| `line` | A line has passed all stages and goes to the speech service | `source`: the source's name in the profile; `text`: the line |
| `subtitle` | The subtitle to show over the game changes, while subtitles are on | `text`: the subtitle, or `""` to hide it. The core decides how long each one stays: while it is spoken plus a moment, and at least as long as it takes to read |
| `error` | A source, stage or sink fails (reported once until it works again) | `kind`: `source.error`, `stage.error` or `sink.error`; `origin`: which one; `message`: for the user |

Example:

```json
{ "type": "line", "source": "messages", "text": "Welcome to the Downtown District." }
```

Clients should ignore event types and fields they do not know, so the API can grow without breaking them.

## Versioning

Breaking changes get a new version prefix (`/v2`); `/v1` keeps working alongside it for a while. New fields, requests and event types can be added to `/v1`. Until the first release, `/v1` itself may still change.
