# In-game overlay

A DLL loaded into the game process. It hooks the point where the game shows each frame and draws a Dear ImGui control panel on top. All logic stays in the Python core: the overlay is a client of the core's [local API](../docs/api.md) (`http://127.0.0.1:47821/v1`), so it only draws, captures input and grabs frames. See also [docs/architecture.md](../docs/architecture.md).

## Using it

The core loads the overlay into a game when it detects it (see the main README, `--overlay`). For the first 10 seconds a hint shows in the top-left corner. Then:

- **Ctrl+Shift+R** opens and closes the panel (only while the game window is in front).
- The panel shows the game being read and the last line, with **Pause/Resume reading** and a **Voice** list. Changing the voice takes effect for the next line and is saved.
- The overlay draws its own mouse cursor while the panel is open, since games often hide the system one.

Known limitation: while the panel is open, games that read the keyboard through DirectInput (like GTA2) still receive key presses.

## How it works

Supported graphics APIs: **Direct3D 9, 11 and 12**. The overlay waits (up to 2 minutes) until the game has loaded one of them, hooks only the APIs whose DLLs the game uses, and the first API to show a frame gets the overlay. Older APIs (DirectDraw, Direct3D 1–8) and OpenGL/Vulkan are not supported yet.

The overlay follows whichever swap chain or device the game presented with last, since games often replace them, e.g. between the menu and gameplay. It never holds the game's back buffers between frames, and it never releases a device the game has replaced: some games and wrappers destroy their device regardless of other references, so touching it again would crash the game.

Hooks replace entries in the vtables of the graphics API's objects (found through a throwaway object of the same class) instead of patching function code. Other overlays such as RivaTuner Statistics Server, Steam or Discord patch function code and may rewrite their patches over ours; vtable entries stay out of their way, and our hooks call theirs, so both overlays show.

Mouse buttons are read directly while the panel is open, because games using DirectInput or replacing their window procedure keep click messages from arriving. The panel is laid out in window coordinates and scaled to the game's back buffer, so it lines up with the mouse when the image is scaled (the Direct3D 9 backend ignores that scale).

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
| `src/api_client.cpp` | Talks to the core over WinHTTP: events over a WebSocket, commands over HTTP |
| `src/ui.cpp` | The hint and the control panel |
| `src/probe_window.cpp` | Hidden window for the throwaway devices used to locate API methods |
| `injector/inject.cpp` | Loads the DLL into a running game |

Dependencies, fetched by CMake at configure time: [Dear ImGui](https://github.com/ocornut/imgui) (MIT) and [nlohmann/json](https://github.com/nlohmann/json) (MIT). WinHTTP is part of Windows.

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
