# In-game overlay

A DLL loaded into the game process. It hooks the point where the game shows each frame and draws a Dear ImGui control panel on top. All logic stays in the Python core: the overlay is a client of the core's [local API](../docs/api.md) (`http://127.0.0.1:47821/v1`), so it only draws, captures input and grabs frames. See also [docs/architecture.md](../docs/architecture.md).

## Using it

The core loads the overlay into a game when it detects it (see the main README, `--overlay`). For the first 10 seconds a hint shows in the top-left corner. Then:

- **Ctrl+Shift+R** opens and closes the panel (only while the game window is in front).
- The panel has a header with the connection state and a line with the game being read and whether reading is active or paused. Below it, three groups follow the way a line goes through the app, joined by arrows:
  - **Game**: **Game language** (or Auto), and a tick for each source of the game's profile, with its type, to switch it off and on.
  - **Text processing**: a tick for each stage of the game's profile, to switch it off and on. With several sources, stages are grouped under their source's name; a switched-off source's stages are greyed out and keep their own ticks.
  - **Output**: **Language**, the language lines are prepared, spoken and shown in. Under **Speech**: **Voice**, listing only the voices that speak the language, grouped by engine (changing the language switches to the voice last used for it; if no voice speaks it, the panel says where to get one); **Lower game sound while speaking** and its **Game volume** slider; **Pause/Resume reading** and **Stop this line**, which affect only the voice. Under **Subtitles**: **Show subtitles**, with their **Size** and **Position** (top or bottom of the screen).
  - **Last line**: the last line read, up to 9 lines, at the bottom so the controls above never move.
- Subtitles are drawn over the game, under the panel, whether the panel is open or not. Each stays while its line is spoken and a moment after, and at least as long as it takes to read.
- Source and stage ticks are saved per game.
- Changes take effect for the next line and are saved.
- The overlay draws its own mouse cursor while the panel is open, since games often hide the system one.
- While the panel is open, the game gets no keyboard or mouse input, and the cursor is free to leave the game window. Key and mouse-button releases still reach it, as window messages and as buffered DirectInput events, so keys held when the panel opened (such as Ctrl+Shift+R itself) are not stuck down for the game. Gamepads keep working.

## How it works

Supported graphics APIs: **Direct3D 9, 11 and 12**. The overlay waits (up to 2 minutes) until the game has loaded one of them, hooks only the APIs whose DLLs the game uses, and the first API to show a frame gets the overlay. Older APIs (DirectDraw, Direct3D 1–8) and OpenGL/Vulkan are not supported yet.

The overlay follows whichever swap chain or device the game presented with last, since games often replace them, e.g. between the menu and gameplay. It never holds the game's back buffers between frames, and it never releases a device the game has replaced: some games and wrappers destroy their device regardless of other references, so touching it again would crash the game.

Hooks replace entries in the vtables of the graphics API's objects (found through a throwaway object of the same class) instead of patching function code. Other overlays such as RivaTuner Statistics Server, Steam or Discord patch function code and may rewrite their patches over ours; vtable entries stay out of their way, and our hooks call theirs, so both overlays show.

Mouse buttons are read directly while the panel is open, because games using DirectInput or replacing their window procedure keep click messages from arriving.

Blocking the game's input works like ReShade's default "block all input while the overlay is visible". The first time the panel opens, the overlay hooks every keyboard and mouse API the game has loaded (and on later openings, any loaded since): DirectInput 8 and 1–7 devices through their vtables, and through code hooks (MinHook) the message queue (`GetMessage`, `PeekMessage`: input messages for the game's window go to the panel and the game gets `WM_NULL`; other windows are left alone, since DirectInput reads the keyboard through raw input sent to a hidden window of its own), key state (`GetAsyncKeyState`, `GetKeyState`, `GetKeyboardState`), buffered raw input (`GetRawInputBuffer`) and the cursor (`GetCursorPos`, `SetCursorPos`, `ClipCursor`). The overlay's own calls are let through, recognised by their return address, so the panel keeps seeing real input. XInput gamepads are not blocked. Input functions are hooked in code because they are not COM methods; RTSS and similar overlays rewrite code hooks on `Present`, not on these. The panel is laid out in window coordinates and scaled to the game's back buffer, so it lines up with the mouse when the image is scaled (the Direct3D 9 backend ignores that scale).

| Path | Job |
|---|---|
| `src/dllmain.cpp` | Waits for the game's graphics, installs the hooks for the APIs it uses, starts the API client |
| `src/vtable_hook.h` | Replaces one vtable entry and keeps the previous one to call |
| `src/dxgi_hook.cpp` | Hooks `IDXGISwapChain::Present` and `Present1`, shared by Direct3D 11 and 12 |
| `src/d3d12_queue_hook.cpp` | Finds the game's Direct3D 12 command queue, which the D3D12 renderer submits to |
| `src/d3d9_hook.cpp` | Hooks `IDirect3DDevice9::Present` and `Reset` |
| `src/d3d11_renderer.cpp`, `src/d3d12_renderer.cpp`, `src/d3d9_renderer.cpp` | Set up ImGui on the game's device and draw each frame, one file per API |
| `src/overlay_frame.cpp` | Gives the overlay to one API, loads the font and builds each ImGui frame |
| `src/input.cpp` | The panel hotkey, and mouse/keyboard input for ImGui |
| `src/input_blocking.cpp` | Turns blocking the game's input on and off with the panel |
| `src/win32_input_hook.cpp` | Hooks the message queue, key state, raw input and cursor functions |
| `src/dinput_hook.cpp` | Hooks keyboard and mouse reads of DirectInput 8 and 1–7 devices |
| `src/code_hook.cpp` | Code hooks for exported functions (MinHook), and telling the overlay's own calls apart |
| `src/api_client.cpp` | Talks to the core over WinHTTP: events over a WebSocket, commands over HTTP |
| `src/ui.cpp` | The hint and the control panel |
| `src/probe_window.cpp` | Hidden window for the throwaway devices used to locate API methods |
| `injector/inject.cpp` | Loads the DLL into a running game |

Dependencies, fetched by CMake at configure time: [Dear ImGui](https://github.com/ocornut/imgui) (MIT), [nlohmann/json](https://github.com/nlohmann/json) (MIT) and [MinHook](https://github.com/TsudaKageyu/minhook) (BSD-2-Clause). WinHTTP is part of Windows.

## Building on Windows with MSYS2

The overlay must match the game's bitness. Most older games, including GTA2, are 32-bit, so build with the `mingw32` (i686) toolchain. Install it once from an MSYS2 shell:

```bash
pacman -S --needed mingw-w64-i686-toolchain mingw-w64-i686-cmake mingw-w64-i686-ninja
```

Then, from the **MSYS2 MINGW32** shell in the repository root:

```bash
cmake -S overlay -B overlay/build -G Ninja -DCMAKE_BUILD_TYPE=Release
cmake --build overlay/build
```

The results are in `overlay/build/bin/`: `reflektortts-overlay.dll` and `reflektortts-inject.exe`. Both link the MinGW runtime statically, so they need no extra DLLs. To load a new build, restart the game: the DLL stays loaded until the game exits.

## Loading it by hand

The core normally does this. For testing without the core, start the game and run:

```bash
overlay/build/bin/reflektortts-inject.exe gta2.exe
```

or `--pid <id>` instead of the process name. The injector exits with 3 if the game and the build differ in bitness (32-bit vs 64-bit), which the core uses to try another build.

If the overlay does not appear, it writes what went wrong to the debugger output; read it with [DebugView](https://learn.microsoft.com/sysinternals/downloads/debugview).
