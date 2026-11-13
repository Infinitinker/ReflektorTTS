// Wakes the overlay when the app loads a DLL, so each graphics API is hooked as soon as its DLL
// arrives.

#pragma once

#include <windows.h>

namespace reflektortts {

// Signals the event each time the app loads a DLL, through the loader's DLL notifications (as
// ReShade does). Returns false where the system offers none; then the caller has to poll.
bool signal_on_dll_load(HANDLE event);

}  // namespace reflektortts
