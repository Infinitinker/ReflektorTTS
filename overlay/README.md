# In-game overlay

A DLL loaded into the game process. It hooks Direct3D 11's `IDXGISwapChain::Present` and draws a Dear ImGui window on top of each frame. For now it only shows a "Hello, world!" box; the logic stays in the Python core, so the overlay only draws, captures input and grabs frames.

| Path | Job |
|---|---|
| `src/dllmain.cpp` | Starts the overlay on a separate thread when the DLL is loaded |
| `src/d3d11_hook.cpp` | Finds and hooks `Present` and `ResizeBuffers` |
| `src/imgui_renderer.cpp` | Sets up ImGui on the game's D3D11 device and renders each frame |
| `src/ui.cpp` | What the overlay shows |
| `injector/inject.cpp` | Loads the DLL into a running game |

Dependencies are fetched by CMake at configure time: [Dear ImGui](https://github.com/ocornut/imgui) (MIT) and [MinHook](https://github.com/TsudaKageyu/minhook) (BSD-2-Clause).

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

1. Start the game.
2. Run the injector with the game's process name:
   ```bash
   overlay/build/bin/reflektortts-inject.exe gta2.exe
   ```
3. A "ReflektorTTS" window with "Hello, world!" appears in the top-left corner.

To load a new build, restart the game: the DLL stays loaded until the game exits.

If no window appears, the overlay writes what went wrong to the debugger output; read it with [DebugView](https://learn.microsoft.com/sysinternals/downloads/debugview). The overlay supports only Direct3D 11 for now, so for games running through dgVoodoo2, set its output API to Direct3D 11.
