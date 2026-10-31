# In-game overlay

A DLL loaded into the game process. It hooks the point where the game shows each frame and draws a Dear ImGui control panel on top. All logic stays in the Python core: the overlay is a client of the core's [local API](../docs/api.md) (`http://127.0.0.1:47821/v1`), so it only draws, captures input and grabs frames. See also [docs/architecture.md](../docs/architecture.md).

## Using it

The core loads the overlay into a game when it detects it (see the main README, `--overlay`). For the first 10 seconds a hint shows in the top-left corner. Then:

- **Ctrl+Shift+R** opens and closes the panel (only while the game window is in front).
- The panel has a header with the connection state and a line with the game being read and whether reading is active or paused. Below it, three groups follow the way a line goes through the app, joined by arrows:
  - **Game**: **Game language** (English by default), and a tick for each source of the game's profile, with its type, to switch it off and on.
  - **Text processing**: a tick for each stage of the game's profile, to switch it off and on. With several sources, stages are grouped under their source's name; a switched-off source's stages are greyed out and keep their own ticks.
  - **Output**: **Language**, the language lines are prepared, spoken and shown in. Under **Speech**: **Voice**, listing only the voices that speak the language, grouped by engine (changing the language switches to the voice last used for it; if no voice speaks it, the panel says where to get one); **Reading speed** (0.5× to 2×, from the next line); **Cut off the current line for a new one**, off by default, so lines wait their turn (at most 3 wait, the oldest dropped first); **Lower game sound while speaking** and its **Game volume** slider; **Pause/Resume reading** and **Stop this line** (which moves on to the next waiting line), which affect only the voice. Under **Subtitles**: **Show subtitles**, with their **Size** and **Position** (top or bottom of the screen).
  - **Last line**: the last line read, up to 9 lines, at the bottom so the controls above never move.
- Subtitles are drawn over the game, under the panel, whether the panel is open or not. Each stays while its line is spoken and a moment after, and at least as long as it takes to read.
- Changes take effect for the next line and are saved for the game being played. A game played for the first time starts with the defaults. The panel's own place on the screen is not saved.
- The panel is used with the mouse only, so keys pressed for other overlays (such as RivaTuner's hotkeys) while it is open do not press its controls.
- The overlay draws its own mouse cursor while the panel is open, since games often hide the system one.
- While the panel is open, the game gets no keyboard or mouse input, and the cursor is free to leave the game window. Key and mouse-button releases still reach it, as window messages and as buffered DirectInput events, so keys held when the panel opened (such as Ctrl+Shift+R itself) are not stuck down for the game. Gamepads keep working.

## How it works

Supported graphics APIs: **Direct3D 9, 11 and 12**. The overlay hooks only the APIs whose DLLs the game uses, each as soon as its DLL is loaded, however late (after a launcher, say): Windows tells it about every DLL the game loads, as ReShade has it told. The first API to show a frame gets the overlay. Older APIs (DirectDraw, Direct3D 1–8) and OpenGL/Vulkan are not supported yet.

The overlay follows whichever swap chain or device the game presented with last, since games often replace them, e.g. between the menu and gameplay. It never holds the game's back buffers between frames, and it never releases a device the game has replaced: some games and wrappers destroy their device regardless of other references, so touching it again would crash the game.

The graphics API's methods are found through the vtable of a throwaway object of the same class, and hooked in their code through MinHook, the way other overlays such as the Steam overlay, RivaTuner Statistics Server, Discord and OBS hook them. Code hooks chain whichever overlay came first: each carries the jump of the one before it, and the chain ends at the method, so every overlay shows. Replacing the vtable entry instead, as the overlay once did, does not chain: in Mad Max the Steam overlay took our vtable entry for the hook after its own and called it, while our hook called the method, which began with Steam's jump, and the two called each other until the game crashed. Code hooks also catch games that keep a method's address instead of reading the vtable each frame, as Mad Max does. RivaTuner Statistics Server, though, removes its hook on each call (putting the function's original code back while it calls it, then its own jump), which wipes out any hook on top of it: the overlay stopped after its first frame in GTA2, and GTA San Andreas crashed once our `Reset` hook was gone. So every half second the overlay checks its hooks: where the jump it overwrote, or the original code, is back in place of its own, it hooks the code that overwritten jump led to, the other overlay's hook, so the chain runs us, then the other overlay, then the function. An overlay that hooks after us writes a jump of its own, whose chain still runs through ours, and is left alone. Where a method cannot be hooked in its code, its vtable entry is replaced instead, and the log says so. (ReShade avoids the question by being loaded as `d3d9.dll` or `dxgi.dll` before the game creates its device and wrapping it; an overlay injected into a running game finds the device already made.)

Mouse buttons are read directly while the panel is open, because games using DirectInput or replacing their window procedure keep click messages from arriving.

Blocking the game's input works like ReShade's default "block all input while the overlay is visible". The first time the panel opens, the overlay hooks every keyboard and mouse API the game has loaded (and on later openings, any loaded since), all through code hooks: the reads of DirectInput 8 and 1–7 devices, the message queue (`GetMessage`, `PeekMessage`: input messages for the game's window go to the panel and the game gets `WM_NULL`; other windows are left alone, since DirectInput reads the keyboard through raw input sent to a hidden window of its own), key state (`GetAsyncKeyState`, `GetKeyState`, `GetKeyboardState`), buffered raw input (`GetRawInputBuffer`) and the cursor (`GetCursorPos`, `SetCursorPos`, `ClipCursor`). The overlay's own calls are let through, recognised by their return address, so the panel keeps seeing real input. XInput gamepads are not blocked. Window messages reach the panel on the thread that draws, at the start of its next frame, since many games handle their window on another thread. The panel is laid out in window coordinates and scaled to the game's back buffer, so it lines up with the mouse when the image is scaled (the Direct3D 9 backend ignores that scale).

| Path | Job |
|---|---|
| `src/dllmain.cpp` | Installs the hooks for each graphics API the game loads, starts the API client |
| `src/dll_load_watch.cpp` | Wakes the overlay when the game loads a DLL |
| `src/vtable_hook.h` | Hooks a COM method found through a vtable: in its code, or by replacing the vtable entry |
| `src/dxgi_hook.cpp` | Hooks `IDXGISwapChain::Present` and `Present1`, shared by Direct3D 11 and 12 |
| `src/d3d12_queue_hook.cpp` | Finds the game's Direct3D 12 command queue, which the D3D12 renderer submits to |
| `src/d3d9_hook.cpp` | Hooks `IDirect3DDevice9::Present` and `Reset` |
| `src/d3d11_renderer.cpp`, `src/d3d12_renderer.cpp`, `src/d3d9_renderer.cpp` | Set up ImGui on the game's device and draw each frame, one file per API |
| `src/overlay_frame.cpp` | Gives the overlay to one API, loads the font and builds each ImGui frame |
| `src/input.cpp` | The panel hotkey, and mouse input for ImGui |
| `src/input_blocking.cpp` | Turns blocking the game's input on and off with the panel |
| `src/win32_input_hook.cpp` | Hooks the message queue, key state, raw input and cursor functions |
| `src/dinput_hook.cpp` | Hooks keyboard and mouse reads of DirectInput 8 and 1–7 devices |
| `src/code_hook.cpp` | Code hooks (MinHook), kept in place when another overlay cuts them out, and telling the overlay's own calls apart |
| `src/api_client.cpp` | Talks to the core over WinHTTP: events over a WebSocket, commands over HTTP |
| `src/ui.cpp` | The hint and the control panel |
| `src/probe_window.cpp` | Hidden window for the throwaway devices used to locate API methods |
| `injector/inject.cpp` | Loads the DLL into a running game |

Dependencies, fetched by CMake at configure time: [Dear ImGui](https://github.com/ocornut/imgui) (MIT), [nlohmann/json](https://github.com/nlohmann/json) (MIT) and [MinHook](https://github.com/TsudaKageyu/minhook) (BSD-2-Clause). WinHTTP is part of Windows.

## Building on Windows with MSYS2

The overlay must match the game's bitness: older games, including GTA2 and GTA San Andreas, are 32-bit, and most modern ones are 64-bit. Build both, each with its own MSYS2 toolchain, and give the core both folders: it uses the one that fits each game.

Install the toolchains once from an MSYS2 shell:

```bash
pacman -S --needed mingw-w64-i686-toolchain mingw-w64-i686-cmake mingw-w64-i686-ninja
pacman -S --needed mingw-w64-x86_64-toolchain mingw-w64-x86_64-cmake mingw-w64-x86_64-ninja
```

The 32-bit build, from the **MSYS2 MINGW32** shell in the repository root:

```bash
cmake -S overlay -B overlay/build -G Ninja -DCMAKE_BUILD_TYPE=Release
cmake --build overlay/build
```

The 64-bit build, from the **MSYS2 MINGW64** shell:

```bash
cmake -S overlay -B overlay/build64 -G Ninja -DCMAKE_BUILD_TYPE=Release
cmake --build overlay/build64
```

The results are in `overlay/build/bin/` and `overlay/build64/bin/`: `reflektortts-overlay.dll` and `reflektortts-inject.exe`. Both link the MinGW runtime statically, so they need no extra DLLs. To load a new build, restart the game: the DLL stays loaded until the game exits.

## Loading it by hand

The core normally does this. For testing without the core, start the game and run:

```bash
overlay/build/bin/reflektortts-inject.exe gta2.exe
```

or `--pid <id>` instead of the process name, with the injector from the build matching the game. It exits with 3 if the game and the build differ in bitness (32-bit vs 64-bit), which the core uses to try another build.

If the overlay does not appear, it writes what went wrong to the debugger output; read it with [DebugView](https://learn.microsoft.com/sysinternals/downloads/debugview).
