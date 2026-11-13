// Hooking keyboard and mouse reads of DirectInput 8 and 1-7 devices, to block them while the panel
// is open.

#pragma once

namespace reflektortts {

// Hooks reading the keyboard and mouse through DirectInput 8 (dinput8.dll) and DirectInput 1-7
// (dinput.dll), whichever the app has loaded: while input is blocked, the app reads no keys
// pressed, a still mouse, and of buffered events only key and button releases. Gamepads are
// read as usual.
void install_dinput_hooks();

}  // namespace reflektortts
