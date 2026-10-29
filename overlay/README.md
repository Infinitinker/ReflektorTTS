# In-game overlay

A DLL loaded into the game process. It hooks the point where the game shows each frame and draws a Dear ImGui window on top. For now it only shows a "Hello, world!" box; the logic stays in the Python core, so the overlay only draws, captures input and grabs frames.

Supported graphics APIs: **Direct3D 9, 11 and 12**. The overlay hooks only the APIs whose DLLs the game has already loaded, and the first API to show a frame gets the overlay. Older APIs (DirectDraw, Direct3D 1–8) and OpenGL/Vulkan are not supported yet.

The overlay follows whichever swap chain or device the game presented with last, since games often replace them, e.g. between the menu and gameplay. It never holds the game's back buffers between frames, and it never releases a device the game has replaced: some games and wrappers destroy their device regardless of other references, so touching it again would crash the game.

Hooks replace entries in the vtables of the graphics API's objects (found through a throwaway object of the same class) instead of patching function code. Other overlays such as RivaTuner Statistics Server, Steam or Discord patch function code and may rewrite their patches over ours; vtable entries stay out of their way, and our hooks call theirs, so both overlays show.

| Path | Job |
|---|---|
| `src/dllmain.cpp` | Starts the overlay on a separate thread and installs the hooks for the APIs the game uses |
| `src/vtable_hook.h` | Replaces one vtable entry and keeps the previous one to call |
| `src/dxgi_hook.cpp` | Hooks `IDXGISwapChain::Present` and `Present1`, shared by Direct3D 11 and 12 |
| `src/d3d12_queue_hook.cpp` | Finds the game's Direct3D 12 command queue, which the D3D12 renderer submits to |
| `src/d3d9_hook.cpp` | Hooks `IDirect3DDevice9::Present` and `Reset` |
| `src/d3d11_renderer.cpp`, `src/d3d12_renderer.cpp`, `src/d3d9_renderer.cpp` | Set up ImGui on the game's device and draw each frame, one file per API |
| `src/overlay_frame.cpp` | Gives the overlay to one API and builds each ImGui frame |
| `src/probe_window.cpp` | Hidden window for the throwaway devices used to locate API methods |
| `src/ui.cpp` | What the overlay shows |
| `injector/inject.cpp` | Loads the DLL into a running game |

The only dependency, [Dear ImGui](https://github.com/ocornut/imgui) (MIT), is fetched by CMake at configure time.

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

The results are in `overlay/build/bin/`: `reflektortts-overlay.dll` and `reflektortts-inject.exe`. Both link the MinGW runtime statically, so they need no extra DLLs.

## Trying it

1. Start the game and wait until it shows its first screen, so its graphics DLLs are loaded.
2. Run the injector with the game's process name:
   ```bash
   overlay/build/bin/reflektortts-inject.exe gta2.exe
   ```
3. A "ReflektorTTS" window with "Hello, world!" appears in the top-left corner.

To load a new build, restart the game: the DLL stays loaded until the game exits.

If no window appears, the overlay writes what went wrong to the debugger output; read it with [DebugView](https://learn.microsoft.com/sysinternals/downloads/debugview).
