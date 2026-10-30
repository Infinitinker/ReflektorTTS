#pragma once

namespace reflektortts {

// Hooks reading the keyboard and mouse through DirectInput 8 (dinput8.dll) and DirectInput 1-7
// (dinput.dll), whichever the game has loaded: while input is blocked, the game reads no keys
// pressed, a still mouse, and of buffered events only key and button releases. Gamepads are
// read as usual.
void install_dinput_hooks();

}  // namespace reflektortts
