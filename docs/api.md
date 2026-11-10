# Local API (v1)

Every ReflektorTTS user interface, the desktop app's window and the overlay alike, controls the core through this API. It is served by the core on **`http://127.0.0.1:47821/v1`**, only on the local machine. The port is fixed so the overlay knows where to connect.

Requests and responses are JSON (UTF-8). There is no authentication, but web pages are kept out: a page open in the user's browser can also reach 127.0.0.1, so the API refuses what only browsers send (see [Requests from web pages](#requests-from-web-pages)).

## Status

Settings belong to each app's profile (see [Profile settings](#profile-settings)): the status shows those of the app being read. An app read for the first time starts with the defaults. While no app is being read, the status shows the defaults.

The status object, returned by several requests and sent as an event:

```json
{
  "type": "status",
  "app": { "title": "Grand Theft Auto 2", "pid": 4824, "profile": "grand-theft-auto-2-1999" },
  "unsupported": null,
  "source_error": null,
  "voice": "windows:Microsoft Adam",
  "input_language": "en",
  "output_language": "pl",
  "paused": false,
  "ducking": true,
  "duck_volume": 0.3,
  "speech_rate": 1.0,
  "new_line": "wait",
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
          "enabled": { "text": true, "speech": true },
          "inactive": null
        }
      ]
    }
  ]
}
```

| Field | Meaning |
|---|---|
| `app` | The app being read: its `title`, process ID (`pid`) and `profile`, the ID of its profile, to change its settings with; or `null` while waiting for one |
| `unsupported` | An app running in a build its profile does not list, which is neither read nor given the overlay: its `title` and its executable's `sha256` (or `null` if it could not be read); otherwise `null` |
| `source_error` | Why a source of the app being read fails, as the last `error` event of kind `source.error` said, or the message the source fails with now, if it changed since: the source's name in the profile (`source`) and the `message` for the user. It stays until that source works again, when the status changes to the error of another failing source, if any, or `null`; the next app starts with `null` |
| `voice` | The current voice, as `engine:name`; with no app, the installed voice a new app would start with |
| `input_language` | The language of the app's text (ISO 639-1 code); English unless the user chose another |
| `output_language` | The language lines are prepared, spoken and shown in (ISO 639-1 code) |
| `paused` | Whether reading is paused |
| `ducking` | Whether the app's sound is lowered while lines are spoken |
| `duck_volume` | The app's volume while lines are spoken, as a fraction of its own volume (0 to 1) |
| `speech_rate` | How fast lines are spoken, as a multiple of the voice's own pace (0.5 to 2) |
| `new_line` | What a new line does while another is spoken: `wait`, `cut_off` or `speed_up` |
| `subtitles` | Whether lines are shown as subtitles over the app |
| `subtitle_size` | `small`, `medium` or `large` |
| `subtitle_position` | `top` or `bottom` of the screen |
| `sources` | The stages of the app being read, per source in the app's profile, with whether each is on; empty while waiting for an app |

A source's `name` is its name in the profile, `type` its plugin, and `enabled` whether the user has it switched on; `name` identifies it for `PATCH /v1/profiles/<id>/sources`. A stage's `type` is its name in the profile and `summary` says in a few words what it does; `enabled` says whether the stage is on for the `text` shown (subtitles, `line` events) and for `speech`: as the user switched it, else as the app's profile starts it. `warning` (or `null`) is shown while the stage is off for either, if reading breaks without it. `inactive` says why the stage does nothing with the current languages (e.g. "Input and output language are the same" for `translate`), or is `null` if it works with them; such a stage is skipped whatever its `enabled`, which keeps the user's choice for when the languages change. `key` identifies the stage for `PATCH /v1/profiles/<id>/stages`.

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

`id` is what `PATCH /v1/profiles/<id>/settings` takes as `voice`; `language` is a BCP 47 tag, so a UI can offer only the voices that speak the output language; `engine_title` is the engine's name as shown to users. Only installed voices are listed; ReflektorTTS never downloads one by itself.

### `POST /v1/voices/preview`

`{"voice": "piper:pl_PL-gosia-medium"}` speaks a sample sentence in the voice's language, so the user can hear it. It runs apart from the app being read, if any: the app keeps its voice and its sound is not lowered. A new preview cuts off the one playing. Answers 202 at once, and `preview` events say when it starts and ends; 400 if the voice is not installed or speaks no supported language.

### `GET /v1/languages`

Returns the languages the pipeline supports, with their names in their own language:

```json
{ "languages": [{ "code": "en", "name": "English" }, { "code": "pl", "name": "Polski" }] }
```

### `GET /v1/profiles`

Lists every profile, bundled and the user's own, in ID order:

```json
{
  "profiles": [
    {
      "id": "grand-theft-auto-2-1999",
      "title": "Grand Theft Auto 2",
      "year": 1999,
      "origin": "bundled",
      "state": "reading",
      "reason": null,
      "file": "...\\profiles\\bundled\\grand-theft-auto-2-1999.json",
      "overlay": false,
      "rating": "bronze",
      "executables": [{ "name": "gta2.exe", "sha256": ["420af867..."] }],
      "sources": [{ "name": "subtitles", "type": "memory", "stages": ["tracker", "replace", "translate", "normalize"] }]
    }
  ]
}
```

- `rating`: how far the profile is tested, as its medal (`bronze`, `silver`, `gold` or `platinum`; see the profile format), or `null` if it is not rated or the file is broken.
- `origin`: `bundled`, `custom` (the user's own) or `override` (the user's own, replacing the bundled profile with its ID).
- `state`: `reading`, `not_running`, `unsupported` (its app runs in a build the profile does not list), `not_set_up` (every source of it needs an [integration](#integrations) that is not enabled, so its app is not read), `disabled`, `not_used` (another profile, the user's own, matches the same app), `clash` (another of the user's own does) or `broken` (the file cannot be read as a profile; `title`, `year` and `overlay` are then `null`). `reason` says why for `not_set_up`, `not_used`, `clash` and `broken`.

### `PATCH /v1/profiles`

Enables or disables a profile, saved for the user: `{"id": "mad-max-2015", "enabled": false}`. A disabled profile's app is not watched, and stops being read at once; which profiles clash is decided again. Returns the status; an unknown ID answers 400.

### `POST /v1/profiles`

Adds a profile to the user's own, once it is checked: `{"id": "my-game-2000", "profile": {...}, "replace": false}`. `id` becomes the file name (lowercase letters, digits and hyphens); `profile` is the profile's JSON. A broken profile, or an `id` that cannot be a file name, answers 400 and nothing is written; an `id` the user already has answers 409 unless `replace` is `true`. Returns the status.

### `POST /v1/profiles/<id>/copy`

Copies a bundled profile to the user's folder, where it replaces the bundled one, and returns `{"file": "<the copy's path>"}`. An unknown ID answers 404; a profile that is not bundled, or one the user already has a copy of, 409.

### `DELETE /v1/profiles/<id>`

Deletes the user's own profile file; a bundled profile with the same ID is used again. Returns the status. An unknown ID answers 404; a bundled profile, which cannot be removed, 409.

### `POST /v1/profiles/reload`

Reads the profile files again, e.g. after the user edited one, and returns the status. A changed profile applies the next time its app starts; one no longer used stops being read at once.

### `POST /v1/pause`

Stops the line being spoken, drops the lines waiting their turn, and ignores new lines until resumed. Returns the status.

### `POST /v1/resume`

Resumes reading. Returns the status.

### `POST /v1/stop`

Stops the line being spoken; the next waiting line, or the next line read, is spoken as usual. Returns the status.

## Profile settings

Each profile has its own settings, saved in the settings folder (`settings/profiles/<id>.json`); a profile the user changed nothing for has the defaults. They can be read and changed whether or not the profile's app runs: changes to the app being read apply at once, as the status shows; those to any other profile apply when its app starts. The app being read is `app.profile` in the status. Every request below answers 404 for an unknown profile ID and 409 for a profile whose file cannot be read (state `broken` in `GET /v1/profiles`).

The profile settings object, returned by these requests and sent as an event:

```json
{
  "type": "profile_settings",
  "profile": "grand-theft-auto-2-1999",
  "app": { "title": "Grand Theft Auto 2" },
  "running": true,
  "voice": "windows:Microsoft Adam",
  "input_language": "en",
  "output_language": "pl",
  "ducking": true,
  "duck_volume": 0.3,
  "speech_rate": 1.0,
  "new_line": "wait",
  "subtitles": true,
  "subtitle_size": "medium",
  "subtitle_position": "top",
  "sources": [ ... ]
}
```

`profile` is the profile's ID, `app.title` its app's title, and `running` whether that app is being read now. The other fields mean what they mean in the status, for this profile: `voice` is the voice its app is read with (the one chosen for it if that is installed and speaks the output language, else an installed voice that does, if any), and `sources` are its sources and stages, shaped as in the status, with `inactive` as the profile's own languages decide.

### `GET /v1/profiles/<id>/settings`

Returns the profile's settings.

### `PATCH /v1/profiles/<id>/settings`

Changes the profile's settings and saves them. Send any of the fields below. A request is applied in full or not at all: an unknown field or a wrong value answers 400, naming the field, and changes nothing.

```json
{ "input_language": "en", "output_language": "pl", "voice": "windows:Microsoft Adam" }
```

- `input_language`: a `code` from `/v1/languages`.
- `output_language`: a `code` from `/v1/languages`. Lines read from then on are prepared for it. If the profile's voice does not speak it, the voice becomes the one last chosen for that language, or else the first voice that speaks it; with no such voice, the voice stays.
- `voice`: an `id` from `/v1/voices`. While the profile's app is read, switching starts a new speech process and the next line is spoken with the new voice; otherwise the voice is loaded when the app starts. The voice is also remembered for its language, in every profile.
- `ducking`: `true` or `false`, whether the app's sound is lowered while lines are spoken.
- `duck_volume`: a number from 0 to 1, the app's volume while lines are spoken as a fraction of its own; while the app is read, applies at once, also while lowered.
- `speech_rate`: a number from 0.5 to 2, how fast lines are spoken relative to the voice's own pace; applies from the next line.
- `new_line`: what a new line does while another is spoken. `wait`, the default, queues it, with at most 3 lines waiting and the oldest dropped first; `cut_off` makes it cut off the one being spoken (and drop any waiting); `speed_up` queues it too, and a line that waited starts 25% faster, and 25% more for every line still waiting after it, up to 2×, so the voice catches up. `POST /v1/stop` then moves on to the next waiting line, and pausing drops the waiting ones.
- `subtitles`: `true` or `false`, whether lines are shown as subtitles over the app. Switching them off hides the one shown.
- `subtitle_size`: `small`, `medium` or `large`.
- `subtitle_position`: `top` or `bottom`. Games usually show their own text at the bottom, so the default is `top`.

An explicit `voice` wins over the one a new output language picks. Returns the profile's settings.

### `PATCH /v1/profiles/<id>/sources`

Switches a source of the profile on or off. A switched-off source is not read until switched on again; its stages keep their own settings:

```json
{ "name": "subtitles", "enabled": false }
```

Returns the profile's settings; a source the profile does not have answers 400.

### `PATCH /v1/profiles/<id>/stages`

Switches a stage of the profile on or off, for the text shown (`"output": "text"`) or for speech (`"output": "speech"`). The choice applies to the next line read, and from then on replaces where the profile starts the stage:

```json
{ "key": "subtitles/3:normalize", "output": "text", "enabled": false }
```

Returns the profile's settings; a stage the profile does not have answers 400.

## Integrations

Changes a source needs made in an app's own settings before it can read the app, e.g. VLC's web interface switched on; see [plugins.md](plugins.md#integrations). A profile whose sources all need one that is not enabled has the state `not_set_up`, and is not read.

### `GET /v1/integrations`

Lists every integration, by ID, with its state now:

```json
{
  "integrations": [
    {
      "id": "vlc",
      "name": "VLC integration",
      "description": "Turns on VLC's web interface for this computer only, ...",
      "state": "disabled",
      "reason": null
    }
  ]
}
```

- `id`: the type of the source plugin that offers it; a profile needs the integrations of its sources' `type`s (see `GET /v1/profiles`).
- `name`: what the user calls it, read after "the"; `description`: what enabling it changes and disabling it puts back.
- `state`: `enabled`, `disabled` or `unavailable` (it cannot be enabled now; `reason` says why, for the user; otherwise `null`).

### `PATCH /v1/integrations/<id>`

Enables or disables an integration: `{"enabled": true}`. Returns the integration as `GET /v1/integrations` lists it, and a `status` event follows, after which clients fetch the profiles again: a profile it sets up is read from the next check on, within a few seconds, and an app read through it stops being read once it is disabled. An unknown ID answers 404; one that cannot be changed now (unavailable, or e.g. while the app runs) 409, with what to do, e.g. `{"error": "Close VLC first, then try again."}`.

## Downloads

Voices and translation models the user can download, from download source plugins (Piper voices, Argos Translate models). Nothing downloads unless a client asks; what is installed is used right away.

### `GET /v1/downloads`

Lists every source's entries in the languages ReflektorTTS supports, from the lists saved earlier; see `POST /v1/downloads/refresh` for fetching them again.

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

- `source_title`: the source's name as shown to users, e.g. `Argos Translate`.
- `kind`: `voice` or `translation`; `languages`: a voice's language, or a translation's from and to.
- `size` in bytes, or `null` if the source does not say.
- `license`: as the source publishes it (for Piper voices, the voice's model card), or `null` if the source does not; `page` is where to read more.
- `state`: `available`, `downloading` (with `done` and `total` bytes) or `installed`.
- `errors`: why a source's list could not be shown, e.g. without an internet connection and no list saved earlier; the other sources are still listed.

### `POST /v1/downloads/refresh`

Fetches every source's list from the internet, saves it, and returns the entries as `GET /v1/downloads` does; a client does this when its downloads view opens. It can take a while. Offline, the lists saved earlier are used. It is a POST because it reaches the internet: a web page can send GETs, but not this (see [Requests from web pages](#requests-from-web-pages)).

### `POST /v1/downloads`

Starts downloading an entry from the list: `{"id": "piper:pl_PL-gosia-medium"}`. Returns **202** at once; progress comes as `download` events. Several downloads can run at once; starting one that is already running answers 409. An ID can be used without listing the downloads first: the saved lists are read when needed.

### `DELETE /v1/downloads/<id>`

Removes an installed entry and returns `{"id": "..."}`; a `download` event with the state `removed` follows. An unknown ID answers 404; an entry still downloading, or not installed, 409; files that cannot be deleted (e.g. in use) 400. Each with a message.

## Errors

A request that is wrong as sent returns **HTTP 400** with a message for the user, e.g. an unknown voice in a request body:

```json
{ "error": "There is no voice \"piper:missing\". Available: piper:en_US-ljspeech-medium, windows:Microsoft Adam." }
```

Every other failure uses the same format: **404** for a path, or a profile, integration or download in the path, that does not exist; **405** for a method a path does not take (the message lists the ones it does); **409** for something that cannot be done as things are now: showing or changing the settings of a profile whose file cannot be read, importing a profile with an ID the user already has, copying a profile that is not bundled or already copied, removing a bundled profile, enabling or disabling an integration that cannot be changed now, starting a download that is already running, removing one that is downloading or not installed; and **500** for an unexpected error inside ReflektorTTS, whose details are in its log.

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
| `status` | Anything in the status object changes: the app (also an unsupported one), voice, languages, pause, ducking, speech or subtitle settings, a source or stage switch, a source failing or working again, or a voice or model installed or removed; also after an integration is enabled or disabled, or the profiles change | As in the status object |
| `profile_settings` | A profile's settings are changed through one of the [profile settings](#profile-settings) requests; if its app is being read, a `status` event comes too. Only these requests send it: a client keeping a profile's settings open fetches them again after a `status` event, since an app starting or stopping, or a voice installed or removed, can change `running` or `voice` | As in the profile settings object |
| `line` | A line has passed the stages for the text shown | `source`: the source's name in the profile; `text`: the line |
| `subtitle` | The subtitle to show over the app changes, while subtitles are on | `text`: the subtitle, or `""` to hide it. The core decides how long each one stays: while it is spoken plus a moment, and at least as long as it takes to read |
| `error` | A source, stage or sink fails (reported once until it works again, even if its message changes meanwhile; for a source, the status's `source_error` follows the message and says when it works again) | `kind`: `source.error`, `stage.error` or `sink.error`; `origin`: which one; `message`: for the user |
| `download` | A download moves on, a few times a second at most | `id`; `state`: `downloading`, `installed`, `failed` or `removed`; `done` and `total` bytes (`total` may be `null`); `message`: why it failed, for the user |
| `preview` | A voice preview starts (also while its voice loads) or ends: spoken, cut off by another preview, or its voice could not be loaded | `voice`; `playing`: `true` when it starts, `false` when it ends. A preview cut off by another one gets no `false`: the other's `true` replaces it |

Example:

```json
{ "type": "line", "source": "subtitles", "text": "Welcome to the Downtown District." }
```

Clients should ignore event types and fields they do not know, so the API can grow without breaking them.

## Versioning

Breaking changes get a new version prefix (`/v2`); `/v1` keeps working alongside it for a while. New fields, requests and event types can be added to `/v1`. Until the first release, `/v1` itself may still change.
