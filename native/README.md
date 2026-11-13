# Native code

ReflektorTTS's C++ code. All logic stays in the Python core: each part is a client of the core's [local API](../docs/api.md) (`http://127.0.0.1:47821/v1` for an installed ReflektorTTS; a run from source has another, so the core gives the overlay its port, and the desktop app gives the settings window the same port), so it only draws and captures input (grabbing frames for OCR is planned). See also [docs/architecture.md](../docs/architecture.md).

It comes in three parts:

- **`shared/`**: a static library (`reflektortts-shared`) with what does not depend on where it is drawn or on the OS: the API client and the settings panel's drawing in Dear ImGui. The API client reaches the core through a small transport interface (`transport.h`), whose only implementation for now is WinHTTP's (`transport_winhttp.cpp`), built on Windows only.
- **`overlay/`**: the overlay, a DLL loaded into the app's process (Windows only), and the injector that loads it. It hooks the point where the app shows each frame and draws the settings panel and the subtitles on top.
- **`panel/`**: the settings panel in a window of its own (`reflektortts-panel.exe`), for one profile whether or not its app runs, so apps without the overlay, and games before they start, can be set up too.

The overlay and the settings window build on the shared library, so `shared/` includes nothing from `overlay/` or `panel/`, and `panel/` nothing from `overlay/`. These directions, and the overlay's own below, are checked by `tools/check_includes.py` (see [Import directions](../docs/architecture.md#import-directions)).

## The overlay

### Using it

The core loads the overlay into an app when it detects it (see the main README, `--overlay`). For the first 10 seconds a hint shows in the top-left corner. Then:

- **Ctrl+Shift+R** opens and closes the panel (only while the app's window is in front).
- The panel has a header with the connection state and a line with the app being read and whether reading is active or paused. Below it, three groups follow the way a line goes through ReflektorTTS, joined by arrows:
  - **Input**: **Language** (English by default), and a tick for each source of the app's profile, with its type, to switch it off and on.
  - **Processing**: each stage of the app's profile, with a few words on what it does, and two ticks to switch it off and on: under **Text** for the text shown (subtitles) and under **Speech** for what is spoken, so `normalize`, for example, can spell out numbers for the voice while subtitles keep them as digits. A stage that does nothing with the chosen languages, such as `translate` when the input and output language are the same, is grayed out with the reason instead and keeps its ticks; a stage that reading needs shows a warning instead while it is off for either. Each stage keeps to one line, so the panel never changes height; hovering shows text that does not fit. With several sources, stages are grouped under their source's name; a switched-off source's stages are grayed out and keep their own ticks.
  - **Output**: **Language**, the language lines are prepared, spoken and shown in. Under **Speech**: **Voice**, listing only the voices that speak the language, grouped by engine (changing the language switches to the voice last used for it; if no installed voice speaks it, the grayed-out box says "No voice for this language", or "No voices installed", and nothing is spoken; a voice downloaded or removed in the desktop app while the app runs is listed, or no longer, right away); **Reading speed** (0.5× to 2×, from the next line); **New lines**, what a line does while another is spoken: **Wait their turn** (the default; at most 3 wait, the oldest dropped first), **Cut off the current one**, or **Speed up to catch up**, where lines wait their turn and a line that waited starts 25% faster, and 25% more for every line still waiting after it, up to 2×; **Lower app sound while speaking** and its **App volume** slider; **Pause/Resume reading** and **Stop this line** (which moves on to the next waiting line), which affect only the voice. Under **Subtitles**: **Show subtitles**, with their **Size** and **Position** (top or bottom of the screen).
  - **Last line**: the last line read, up to 9 lines, at the bottom so the controls above never move.
- Subtitles are drawn over the app, under the panel, whether the panel is open or not. Each stays while its line is spoken and a moment after, and at least as long as it takes to read.
- Changes take effect for the next line and are saved for the app being read. An app read for the first time starts with the defaults. The panel's own place on the screen is not saved.
- The panel is used with the mouse only, so keys pressed for other overlays (such as RivaTuner's hotkeys) while it is open do not press its controls.
- The overlay draws its own mouse cursor while the panel is open, since games often hide the system one.
- While the panel is open, the app gets no keyboard or mouse input, and the cursor is free to leave the app's window. Key and mouse-button releases still reach it, as window messages and as buffered DirectInput events, so keys held when the panel opened (such as Ctrl+Shift+R itself) are not stuck down for the app. Gamepads keep working.

### How it works

Supported graphics APIs: **Direct3D 9, 11 and 12**. The overlay hooks only the APIs whose DLLs the app uses, each as soon as its DLL is loaded, however late (after a launcher, say): Windows tells it about every DLL the app loads, as ReShade has it told. It never loads a Direct3D or DirectInput DLL the app does not use, except `dxgi.dll` and `d3dcompiler_47.dll`, which ImGui's Direct3D 11 and 12 backends link, so they come with the overlay into every app. The first API to show a frame gets the overlay. Older APIs (DirectDraw, Direct3D 1–8) and OpenGL/Vulkan are not supported yet.

The overlay follows whichever swap chain or device the app presented with last, since games often replace them, e.g. between the menu and gameplay. It never holds the app's back buffers between frames, and it never releases a device the app has replaced: some games and wrappers destroy their device regardless of other references, so touching it again would crash the app.

The graphics API's methods are found through the vtable of a throwaway object of the same class, and hooked in their code through MinHook, the way other overlays such as the Steam overlay, RivaTuner Statistics Server, Discord and OBS hook them. Code hooks chain whichever overlay came first: each carries the jump of the one before it, and the chain ends at the method, so every overlay shows. Replacing the vtable entry instead, as the overlay once did, does not chain: in Mad Max the Steam overlay took our vtable entry for the hook after its own and called it, while our hook called the method, which began with Steam's jump, and the two called each other until the game crashed. Code hooks also catch games that keep a method's address instead of reading the vtable each frame, as Mad Max does. RivaTuner Statistics Server, though, removes its hook on each call (putting the function's original code back while it calls it, then its own jump), which wipes out any hook on top of it: the overlay stopped after its first frame in GTA2, and GTA San Andreas crashed once our `Reset` hook was gone. So every half second the overlay checks its hooks: where the jump it overwrote, or the original code, is back in place of its own, it hooks the code that overwritten jump led to, the other overlay's hook, so the chain runs us, then the other overlay, then the function. An overlay that hooks after us writes a jump of its own, whose chain still runs through ours, and is left alone. Where a method cannot be hooked in its code, its vtable entry is replaced instead, and the log says so. (ReShade avoids the question by being loaded as `d3d9.dll` or `dxgi.dll` before the app creates its device and wrapping it; an overlay injected into a running app finds the device already made.)

Mouse buttons are read directly while the panel is open, because games using DirectInput or replacing their window procedure keep click messages from arriving.

Blocking the app's input works like ReShade's default "block all input while the overlay is visible". The first time the panel opens, the overlay hooks every keyboard and mouse API the app has loaded (and on later openings, any loaded since), all through code hooks: the reads of DirectInput 8 and 1–7 devices, the message queue (`GetMessage`, `PeekMessage`: input messages for the app's window go to the panel and the app gets `WM_NULL`; other windows are left alone, since DirectInput reads the keyboard through raw input sent to a hidden window of its own), key state (`GetAsyncKeyState`, `GetKeyState`, `GetKeyboardState`), buffered raw input (`GetRawInputBuffer`) and the cursor (`GetCursorPos`, `SetCursorPos`, `ClipCursor`). The overlay's own calls are let through, recognized by their return address, so the panel keeps seeing real input. XInput gamepads are not blocked. Window messages reach the panel on the thread that draws, at the start of its next frame, since many games handle their window on another thread. The panel is laid out in window coordinates and scaled to the app's back buffer, so it lines up with the mouse when the image is scaled (the Direct3D 9 backend ignores that scale).

The overlay's files, in `overlay/`. Its own headers are included by their path from `src/` (`"hooks/code_hook.h"`), and each folder includes only from itself and the folders listed above it, in the table's order: `memory/`, `diagnostics/`, `hooks/`, `input/`, `ui/`, `renderers/` (`hooks/` from `memory/` and `diagnostics/`, `ui/` from `input/`), while `dllmain.cpp` ties them together. The injector includes only from `memory/`. A new folder goes into this order here and into `OVERLAY_FOLDERS` in `tools/check_includes.py`.

| Path | Job |
|---|---|
| `src/dllmain.cpp` | The DLL's one export, `reflektortts_start_overlay`, which the injector starts with the core's port: installs the hooks for each graphics API the app loads, starts the API client |
| `src/memory/addresses.h` | Addresses as integers and the objects at them, for code that reads memory by its layout |
| `src/memory/functions.h` | Functions as code addresses and back, as MinHook and vtables hold them |
| `src/memory/exported_function.h` | Finds a function a module exports, as the type it has |
| `src/memory/zeroed.h` | Windows' structs with every field zero, to be filled in |
| `src/memory/pe_image.h` | Reads a mapped EXE's or DLL's headers, and what lies at an offset from its start |
| `src/diagnostics/crash_log.cpp` | Logs where the app crashed, with the call stack in 64-bit apps |
| `src/diagnostics/describe_address.h` | Names a code address as module and offset, for the log |
| `src/hooks/code_hook.cpp` | Code hooks (MinHook), kept in place when another overlay cuts them out, and telling the overlay's own calls apart |
| `src/hooks/vtable_hook.h` | Hooks a COM method found through a vtable: in its code, or by replacing the vtable entry |
| `src/hooks/dll_load_watch.cpp` | Wakes the overlay when the app loads a DLL |
| `src/hooks/probe_window.cpp` | Hidden window for the throwaway devices used to locate API methods |
| `src/hooks/dxgi_hook.cpp` | Hooks `IDXGISwapChain::Present` and `Present1`, shared by Direct3D 11 and 12 |
| `src/hooks/d3d12_queue_hook.cpp` | Finds the app's Direct3D 12 command queue on the swap chain's device, which the D3D12 renderer submits to |
| `src/hooks/d3d9_hook.cpp` | Hooks `IDirect3DDevice9::Present` and `Reset` |
| `src/input/panel_input.cpp` | The panel hotkey, and mouse input for ImGui |
| `src/input/blocking.cpp` | Turns blocking the app's input on and off with the panel |
| `src/input/win32_hook.cpp` | Hooks the message queue, key state, raw input and cursor functions |
| `src/input/dinput_hook.cpp` | Hooks keyboard and mouse reads of DirectInput 8 and 1–7 devices |
| `src/ui/overlay_ui.cpp` | The hint, and the panel's window |
| `src/ui/subtitles.cpp` | The subtitles over the app |
| `src/renderers/overlay_frame.cpp` | Gives the overlay to one API, loads the font and builds each ImGui frame |
| `src/renderers/d3d11_renderer.cpp`, `src/renderers/d3d12_renderer.cpp`, `src/renderers/d3d9_renderer.cpp` | Set up ImGui on the app's device and draw each frame, one file per API |
| `injector/inject.cpp` | Loads the DLL into a running app |

### Loading the overlay by hand

The core normally does this. For testing without the core, start the app and run:

```bash
native/build/bin/reflektortts-inject.exe gta2.exe
```

or `--pid <id>` instead of the process name, with the injector from the build matching the app. `--port <port>`, after them, connects the overlay to a core on another port than the installed ReflektorTTS's 47821, such as a run from source's 47822; the core passes its own. The injector loads the DLL, then starts it through its one export, `reflektortts_start_overlay`, on a thread in the app, with the port as the thread's parameter. It exits with 3 if the app and the build differ in bitness (32-bit vs 64-bit), which the core uses to try another build.

If the overlay does not appear, it writes what went wrong to the debugger output, each line starting with `[ReflektorTTS]`. Read it with [DebugView++](https://github.com/CobaltFusion/DebugViewPP) (open source), which shows the debugger output of 32- and 64-bit apps alike, or attach MSYS2's gdb to the app (`gdb -p <process ID>`, from MINGW32 for a 32-bit app), which prints each line as a warning.

## The panel

### Using it

The desktop app starts it for a profile, beside its own window:

```bash
reflektortts-panel --profile grand-theft-auto-2-1999 --port 47821 --dock-side right --dock-x 1108 --dock-y 200 --dock-height 640
```

`--port <port>` is the port of the core's API; without it, the panel connects to the installed ReflektorTTS's, 47821. The desktop app passes its own.

The `--dock-*` arguments go together, all four or none, and are in physical pixels of the screen, measured on the windows' visible frames (title bar included, Windows' invisible resize borders not):

- `--dock-side right|left`: which side of the ReflektorTTS window it opens on;
- `--dock-x <x>`: the edge the two windows share: the panel's left edge (its first pixel) when it opens on the right, its right edge (the first pixel past it, as in Windows' rectangles) when on the left. The panel opens on the display of its pixel next to that edge;
- `--dock-y <y>` and `--dock-height <height>`: the top and height of both windows.

The desktop app opens it on the right of its window if it fits on that display, else on the left; if it fits on neither side, over the ReflektorTTS window at the display's right edge (`src/reflektortts/desktop/panel/dock.py`). Without them, which the desktop app leaves out where Windows cannot tell where its window is, the panel opens centered on the main display, 600 high. Either way it opens as wide as the settings panel and a scrollbar, and cannot be made smaller than it opened, only bigger. Without `--profile <id>`, or with an argument it does not know or a wrong value, it says how to start it (on standard error and in a message box) and exits with 2.

Asking the desktop app for a profile's window while it is open brings that window to the front, restored if it was minimized.

The window, titled "*app* settings – ReflektorTTS", shows the same settings panel as the overlay, for that profile: the header with the connection state, the app and whether it is being read now (if it is not, a note says that changes apply when it starts), and the Input, Processing and Output boxes. It leaves out what only makes sense over a running game: pausing, stopping the line and the last line read. Changes are saved to the profile at once, and apply at once if its app is being read. A profile the core does not know shows the core's message instead (for example "There is no profile ..."); without the core, the window says "Not connected" and keeps trying, like the overlay.

The window can be resized, and its contents follow the window's edge while it is dragged. It follows the display's scale (125%, 150%, ...), also when moved to another display, and so does its smallest size.

### How it works

[SDL3](https://www.libsdl.org) opens the window, reads input and draws, with ImGui's SDL3 and SDL_Renderer backends. SDL picks the renderer itself: Direct3D 11 where it works, else Direct3D 12, Direct3D 9, OpenGL or software; the debugger output says which (`Drawing with SDL's direct3d11 renderer`). It draws only while something happens: for a second after each input (for ImGui's hover delays), and a couple of frames when the client's state changes; otherwise it waits for the next event and uses no CPU. While the user drags the window's edge, Windows runs a loop of its own until the mouse button is released, so the frame loop is stuck in `SDL_WaitEventTimeout`; SDL then sends `SDL_EVENT_WINDOW_EXPOSED` with `data1` = 1 from a timer in that loop, on the main thread, and the panel draws a frame right in an event watch (`SDL_AddEventWatch`), never while one is being drawn already.

Units: Python and `reflektortts.exe` are not DPI aware, so Tk's measures are scaled down above 100% and the desktop app asks Windows for physical pixels instead (`win32_windows.py`: the window's DWM frame bounds, and its display's work area with the thread made per-monitor aware for the call). SDL makes the panel per-monitor DPI aware, so on Windows its window coordinates are physical pixels too, and the display's scale comes separately (`SDL_GetWindowDisplayScale`); the panel still divides by `SDL_GetWindowPixelDensity`, which is 1 there. SDL places a window's client area, so the panel measures its own visible frame (`DwmGetWindowAttribute`) and places the client area inside it.

The API client keeps to the profile given: it loads `GET /v1/profiles/<id>/settings` once the event stream is open, applies the `profile_settings` events of that profile, and loads the settings again after each `status` event, since an app starting or stopping, or a voice installed or removed, can change whether the app is being read and its voice. Changes go to `PATCH /v1/profiles/<id>/settings`, `/sources` and `/stages`.

It is built for Windows only, by the 64-bit build: other systems need a transport for the API client first (see `shared/transport.h`).

| Path | Job |
|---|---|
| `src/main.cpp` | Reads the command line, starts the API client for the profile, runs the window |
| `src/arguments.cpp` | Reads `--profile <id>`, `--port <port>` and the `--dock-*` arguments |
| `src/panel_window.cpp` | Opens the SDL window and ImGui, and runs the frame loop, also while the window is resized |
| `src/placement.cpp` | Sizes the window and places it where it opens |
| `src/window_frame.cpp` | Measures the window's visible frame: through DWM on Windows, SDL's borders elsewhere |
| `src/panel_ui.cpp` | The ImGui window filling the SDL window, and the window's title |
| `src/ui_scale.cpp` | Scales ImGui to the display |
| `src/wakeup.cpp` | Wakes the frame loop when the API client's state changes |
| `src/startup_error.cpp` | Tells the user why the panel cannot start |
| `src/panel.rc` | The program's icon, the desktop app's |

## The shared library

| Path | Job |
|---|---|
| `core_state.h` | What a client knows about the core: the app (the one being read, or the panel's profile's), its profile's settings, sources and stages, the voices and languages |
| `api_client.cpp` | Follows the core's events and keeps reconnecting; sends commands, and changes to its profile (`/v1/profiles/<id>/...`). It follows the app being read, as the overlay needs, or keeps to one profile, as the panel does |
| `transport.h` | How the API client reaches the core: a request, and the event stream |
| `transport_winhttp.cpp` | The transport over WinHTTP, Windows only: events over a WebSocket, commands over HTTP |
| `settings_panel.cpp` | The settings panel's contents: the header, the Input, Output and Last line boxes, and the last error (a source's goes away once the status says the source works again); in the panel's window, without what only makes sense over the app (pausing, stopping the line, the last line) |
| `processing_section.cpp` | The panel's Processing box |
| `widgets.cpp`, `text_fit.cpp` | Small ImGui helpers, and fitting text to a width |
| `system_font.cpp` | Loads the system's font, which has accented letters (Segoe UI on Windows) |
| `log.cpp` | Writes to the debugger output on Windows, to standard error elsewhere |

## Building

`CMakeLists.txt` here is the root project: it fetches the dependencies and builds `shared/`, on Windows `overlay/`, and in the 64-bit Windows build `panel/`. Dependencies, fetched by CMake at configure time, each pinned to the commit of a release: [Dear ImGui](https://github.com/ocornut/imgui) (MIT), [nlohmann/json](https://github.com/nlohmann/json) (MIT), for the overlay [MinHook](https://github.com/TsudaKageyu/minhook) (BSD-2-Clause), and for the panel [SDL3](https://github.com/libsdl-org/SDL) (zlib), built as a static library with only its video and events parts. WinHTTP is part of Windows. Their license texts are kept in `tools/licenses/` and listed in `NATIVE_NOTICES` in `tools/notices.py`, which writes them into `THIRD-PARTY-NOTICES.md` in the repository root, and whose licenses `tools/licenses.py` checks against its allow list; update both when a library moves to another version.

### On Windows with MSYS2

The overlay must match the app's bitness: older games, including GTA2 and GTA San Andreas, are 32-bit, and most modern ones are 64-bit. Build both, each with its own MSYS2 toolchain, and give the core both folders: it uses the one that fits each app.

Install the toolchains once from an MSYS2 shell:

```bash
pacman -S --needed git mingw-w64-i686-toolchain mingw-w64-i686-cmake mingw-w64-i686-ninja
pacman -S --needed git mingw-w64-x86_64-toolchain mingw-w64-x86_64-cmake mingw-w64-x86_64-ninja
```

The builds are named in `CMakePresets.json`, each a Ninja build with the toolchain of the shell it is run from:

| Preset | Build | Folder | Shell |
|---|---|---|---|
| `release-x86` | 32-bit, Release: the overlay for 32-bit apps | `native/build` | MSYS2 MINGW32 |
| `release` | 64-bit, Release: the overlay for 64-bit apps, and the settings window | `native/build64` | MSYS2 MINGW64 |
| `debug` | 64-bit, Debug: debug information and no optimization | `build/native-debug` | MSYS2 MINGW64 |
| `ci` | 64-bit, Release, with the compiler's warnings as errors: the compile commands clang-tidy reads for the 64-bit code, and the build that checks GCC's warnings | `build/native-ci` | MSYS2 MINGW64 |

The folders are relative to the repository root. Each preset also writes `compile_commands.json` into its folder, for clang-tidy and editors. Every build shows the compiler's warnings for ReflektorTTS's own code, those `CMakeLists.txt` turns on; the `ci` preset makes them errors.

The 32-bit build, from the **MSYS2 MINGW32** shell in the repository root:

```bash
cmake -S native --preset release-x86
cmake --build native/build
```

The 64-bit build, from the **MSYS2 MINGW64** shell:

```bash
cmake -S native --preset release
cmake --build native/build64
```

`cmake --build --preset <name>`, run from `native/`, builds a preset too.

The results are in `native/build/bin/` and `native/build64/bin/`: `reflektortts-overlay.dll` and `reflektortts-inject.exe`, and in the 64-bit build `reflektortts-panel.exe` too (the 32-bit build, which is only for the overlay in 32-bit apps, skips the panel and does not fetch SDL). All link the MinGW runtime statically, so they need no extra DLLs. To load a new build, restart the app: the DLL stays loaded until the app exits.

### Checks

The `C++ checks` job of the `Checks` workflow checks this code: the include directions with `tools/check_includes.py`, the formatting with clang-format (`.clang-format` in the repository root) the code with clang-tidy (`.clang-tidy`), which reports the compiler's warnings as Clang sees them, for each build: the 64-bit code through the `ci` preset's compile commands and the 32-bit code through the `release-x86` preset's; and GCC's warnings, by building the `ci` preset, which makes them errors. Every finding fails it. [C++ checks](../docs/development.md#c-checks) in docs/development.md says how to install clang-format and clang-tidy in MSYS2 and run them; run them, and both builds, before committing a change here.
