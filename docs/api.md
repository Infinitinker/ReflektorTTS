# Local API (v1)

Every ReflektorTTS user interface, the in-game overlay included, controls the core through this API. It is served by the core on **`http://127.0.0.1:47821/v1`**, only on the local machine. The port is fixed so the overlay knows where to connect.

Requests and responses are JSON (UTF-8). There is no authentication: the API only listens on 127.0.0.1.

## Status

The status object, returned by several requests and sent as an event:

```json
{
  "type": "status",
  "game": { "title": "Grand Theft Auto 2", "pid": 4824 },
  "voice": "piper:en_US-ljspeech-medium",
  "paused": false
}
```

| Field | Meaning |
|---|---|
| `game` | The game being read, or `null` while waiting for one |
| `voice` | The current voice, as `engine:name` |
| `paused` | Whether reading is paused |

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

`id` is what `PATCH /v1/settings` takes. Piper lists downloaded voices and the default voice, which is downloaded on first use.

### `PATCH /v1/settings`

Changes settings and saves them. Body:

```json
{ "voice": "windows:Microsoft Adam" }
```

Switching the voice starts a new speech process; the next line is spoken with the new voice. Returns the status.

### `POST /v1/pause`

Stops the line being spoken and ignores new lines until resumed. Returns the status.

### `POST /v1/resume`

Resumes reading. Returns the status.

## Errors

A request that cannot be carried out returns **HTTP 400** with a message for the user:

```json
{ "error": "There is no voice \"piper:missing\". Available: piper:en_US-ljspeech-medium, windows:Microsoft Adam." }
```

## Events: `GET /v1/events` (WebSocket)

On connecting, the client receives the current status. After that, every event the core produces arrives as one JSON text message. The server sends a ping every 30 seconds.

| `type` | Sent when | Other fields |
|---|---|---|
| `status` | The game, voice or pause state changes | As in the status object |
| `line` | A line has passed all stages and goes to the speech service | `source`: the source's name in the profile; `text`: the line |
| `error` | A source, stage or sink fails (reported once until it works again) | `kind`: `source.error`, `stage.error` or `sink.error`; `origin`: which one; `message`: for the user |

Example:

```json
{ "type": "line", "source": "messages", "text": "Welcome to the Downtown District." }
```

Clients should ignore event types and fields they do not know, so the API can grow without breaking them.

## Versioning

Breaking changes get a new version prefix (`/v2`); `/v1` keeps working alongside it for a while. New fields, requests and event types can be added to `/v1`.
