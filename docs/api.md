# Local API (v1)

Every ReflektorTTS user interface, the in-game overlay included, controls the core through this API. It is served by the core on **`http://127.0.0.1:47821/v1`**, only on the local machine. The port is fixed so the overlay knows where to connect.

Requests and responses are JSON (UTF-8). There is no authentication, but web pages are kept out: a page open in the player's browser can also reach 127.0.0.1, so the API refuses what only browsers send (see [Requests from web pages](#requests-from-web-pages)).

## Status

Settings belong to the game being read: the status shows that game's, and changes are saved for it. A game played for the first time starts with the defaults. While no game is being read, the status shows the defaults, and changes apply until a game starts but are not saved.

The status object, returned by several requests and sent as an event:

```json
{
  "type": "status",
  "game": { "title": "Grand Theft Auto 2", "pid": 4824 },
  "voice": "windows:Microsoft Adam",
  "game_language": "en",
  "output_language": "pl",
  "paused": false,
  "ducking": true,
  "duck_volume": 0.3,
  "speech_rate": 1.0,
  "cut_off_lines": false,
  "subtitles": true,
  "subtitle_size": "medium",
  "subtitle_position": "top",
  "sources": [
    {
      "name": "subtitles",
      "type": "memory",
      "enabled": true,
      "stages": [
        {
          "key": "subtitles/0:tracker",
          "type": "tracker",
          "summary": "Waits until a line settles",
          "warning": "Needed: or the voice restarts on every reading",
          "enabled": true,
          "inactive": null
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
| `game_language` | The language of the game's text (ISO 639-1 code); English unless the player chose another |
| `output_language` | The language lines are prepared, spoken and shown in (ISO 639-1 code) |
| `paused` | Whether reading is paused |
| `ducking` | Whether the game's sound is lowered while lines are spoken |
| `duck_volume` | The game's volume while lines are spoken, as a fraction of its own volume (0 to 1) |
| `speech_rate` | How fast lines are spoken, as a multiple of the voice's own pace (0.5 to 2) |
| `cut_off_lines` | Whether a new line cuts off the one being spoken; if not, lines wait their turn |
| `subtitles` | Whether lines are shown as subtitles over the game |
| `subtitle_size` | `small`, `medium` or `large` |
| `subtitle_position` | `top` or `bottom` of the screen |
| `sources` | The stages of the game being read, per source in the game's profile, with whether the player has each switched on; empty while waiting for a game |

A source's `name` is its name in the profile, `type` its plugin, and `enabled` whether the player has it switched on; `name` identifies it for `PATCH /v1/sources`. A stage's `type` is its name in the profile and `summary` says in a few words what it does; `warning` (or `null`) is shown while the stage is switched off, if reading breaks without it. `inactive` says why the stage does nothing with the current languages (e.g. "Game and output language are the same" for `translate`), or is `null` if it works with them; such a stage is skipped whatever its `enabled`, which keeps the player's choice for when the languages change. `key` identifies the stage for `PATCH /v1/stages`.

## Requests

### `GET /v1/status`

Returns the status.

### `GET /v1/voices`

Returns the voices available now, from every speech engine that works on this system:

```json
{
  "voices": [
    { "id": "piper:en_US-ljspeech-medium", "engine": "piper", "name": "en_US-ljspeech-medium", "language": "en-US", "engine_title": "Piper" },
    { "id": "windows:Microsoft Adam", "engine": "windows", "name": "Microsoft Adam", "language": "pl-PL", "engine_title": "Windows" }
  ]
}
```

`id` is what `PATCH /v1/settings` takes; `language` is a BCP 47 tag, so a UI can offer only the voices that speak the output language; `engine_title` is the engine's name as shown to players. Only installed voices are listed; ReflektorTTS never downloads one by itself.

### `POST /v1/voices/preview`

`{"voice": "piper:pl_PL-gosia-medium"}` speaks a sample sentence in the voice's language, so the player can hear it. It runs apart from the game being read, if any: the game keeps its voice and its sound is not lowered. A new preview cuts off the one playing. Answers 202 at once, and `preview` events say when it starts and ends; 400 if the voice is not installed or speaks no supported language.

### `GET /v1/languages`

Returns the languages the pipeline supports, with their names in their own language:

```json
{ "languages": [{ "code": "en", "name": "English" }, { "code": "pl", "name": "Polski" }] }
```

### `PATCH /v1/settings`

Changes settings and saves them for the game being read (see Status). Send any of the fields:

```json
{ "game_language": "en", "output_language": "pl", "voice": "windows:Microsoft Adam" }
```

- `game_language`: a `code` from `/v1/languages`.
- `output_language`: a `code` from `/v1/languages`. Lines read from then on are prepared for it. If the current voice does not speak it, the core switches to the voice last chosen for that language, or else the first voice that speaks it; with no such voice, the voice stays.
- `voice`: an `id` from `/v1/voices`. While a game is read, switching starts a new speech process and the next line is spoken with the new voice; otherwise the voice is only remembered, and loaded when a game starts. The voice is also remembered for its language.
- `ducking`: `true` or `false`, whether the game's sound is lowered while lines are spoken.
- `duck_volume`: a number from 0 to 1, the game's volume while lines are spoken as a fraction of its own; applies at once, also while lowered.
- `speech_rate`: a number from 0.5 to 2, how fast lines are spoken relative to the voice's own pace; applies from the next line.
- `cut_off_lines`: `true` makes a new line cut off the one being spoken (and drop any waiting); `false`, the default, queues it, with at most 3 lines waiting and the oldest dropped first. `POST /v1/stop` then moves on to the next waiting line, and pausing drops the waiting ones.
- `subtitles`: `true` or `false`, whether lines are shown as subtitles over the game. Switching them off hides the one shown.
- `subtitle_size`: `small`, `medium` or `large`.
- `subtitle_position`: `top` or `bottom`. Games usually show their own text at the bottom, so the default is `top`.

The ducking and subtitle fields are applied first, then the others in the order listed, so an explicit `voice` wins over the one a new output language picks. Returns the status.

### `PATCH /v1/sources`

Switches a source of the game being read on or off. A switched-off source is not read until switched on again; its stages keep their own settings. The choice is saved per game:

```json
{ "name": "subtitles", "enabled": false }
```

Returns the status.

### `PATCH /v1/stages`

Switches a stage of the game being read on or off. The choice is saved per game and applies to the next line read:

```json
{ "key": "subtitles/3:normalize", "enabled": false }
```

Returns the status.

### `POST /v1/pause`

Stops the line being spoken, drops the lines waiting their turn, and ignores new lines until resumed. Returns the status.

### `POST /v1/resume`

Resumes reading. Returns the status.

### `POST /v1/stop`

Stops the line being spoken; the next waiting line, or the next line read, is spoken as usual. Returns the status.

## Downloads

Voices and translation models the player can download, from download source plugins (Piper voices, Argos Translate models). Nothing downloads unless a client asks; what is installed is used right away.

### `GET /v1/downloads`

Lists every source's entries in the languages ReflektorTTS supports. With `?refresh=1` the lists are fetched from the internet first (a client does this when its downloads view opens); without it, or offline, the lists saved earlier are used.

```json
{
  "entries": [
    {
      "id": "piper:pl_PL-gosia-medium",
      "source_title": "Piper",
      "kind": "voice",
      "name": "pl_PL-gosia-medium",
      "languages": ["pl"],
      "size": 63205000,
      "license": "# Model card for gosia (medium) ...",
      "page": "https://huggingface.co/rhasspy/piper-voices/tree/main/pl/pl_PL/gosia/medium",
      "state": "available",
      "done": 0,
      "total": null
    }
  ],
  "errors": []
}
```

- `source_title`: the source's name as shown to players, e.g. `Argos Translate`.
- `kind`: `voice` or `translation`; `languages`: a voice's language, or a translation's from and to.
- `size` in bytes, or `null` if the source does not say.
- `license`: as the source publishes it (for Piper voices, the voice's model card), or `null` if the source does not; `page` is where to read more.
- `state`: `available`, `downloading` (with `done` and `total` bytes) or `installed`.
- `errors`: why a source's list could not be shown, e.g. without an internet connection and no list saved earlier; the other sources are still listed.

### `POST /v1/downloads`

Starts downloading an entry from the list: `{"id": "piper:pl_PL-gosia-medium"}`. Returns **202** at once; progress comes as `download` events. Several downloads can run at once.

### `DELETE /v1/downloads/<id>`

Removes an installed entry.

## Errors

A request that cannot be carried out returns **HTTP 400** with a message for the user:

```json
{ "error": "There is no voice \"piper:missing\". Available: piper:en_US-ljspeech-medium, windows:Microsoft Adam." }
```

Every other failure uses the same format: **404** for a path that does not exist, **405** for a method a path does not take (the message lists the ones it does), and **500** for an unexpected error inside ReflektorTTS, whose details are in its log.

## Requests from web pages

So that a web page cannot control ReflektorTTS or listen to its events, requests are refused when they carry what browsers add and ReflektorTTS's own clients never do. A client must therefore:

- send no `Origin` header (browsers send it with cross-site requests and with every WebSocket): **403**;
- address `127.0.0.1` or `localhost` in the `Host` header (a page that rebinds its own domain name to 127.0.0.1 sends that name): **403**;
- send a body only as JSON, with `Content-Type: application/json` (pages can send text or form data unasked, but not JSON): **415**.

These refusals use the same `{"error": "..."}` format.

## Events: `GET /v1/events` (WebSocket)

On connecting, the client receives the current status. After that, every event the core produces arrives as one JSON text message. The server sends a ping every 30 seconds.

| `type` | Sent when | Other fields |
|---|---|---|
| `status` | The game, voice, languages, pause state or a stage switch changes | As in the status object |
| `line` | A line has passed all stages and goes to the speech service | `source`: the source's name in the profile; `text`: the line |
| `subtitle` | The subtitle to show over the game changes, while subtitles are on | `text`: the subtitle, or `""` to hide it. The core decides how long each one stays: while it is spoken plus a moment, and at least as long as it takes to read |
| `error` | A source, stage or sink fails (reported once until it works again) | `kind`: `source.error`, `stage.error` or `sink.error`; `origin`: which one; `message`: for the user |
| `download` | A download moves on, a few times a second at most | `id`; `state`: `downloading`, `installed`, `failed` or `removed`; `done` and `total` bytes (`total` may be `null`); `message`: why it failed, for the user |
| `preview` | A voice preview starts (also while its voice loads) or ends: spoken, cut off by another preview, or its voice could not be loaded | `voice`; `playing`: `true` when it starts, `false` when it ends. A preview cut off by another one gets no `false`: the other's `true` replaces it |

Example:

```json
{ "type": "line", "source": "subtitles", "text": "Welcome to the Downtown District." }
```

Clients should ignore event types and fields they do not know, so the API can grow without breaking them.

## Versioning

Breaking changes get a new version prefix (`/v2`); `/v1` keeps working alongside it for a while. New fields, requests and event types can be added to `/v1`. Until the first release, `/v1` itself may still change.
