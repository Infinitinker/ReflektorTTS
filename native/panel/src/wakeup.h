// Wakes the frame loop, which waits for SDL's events, when the API client's state changes: an SDL
// event posted from the client's threads.

#pragma once

#include <SDL3/SDL_events.h>

namespace reflektortts {

// The event that wakes the window's event loop when the API client's state changes.
inline constexpr SDL_EventType kWakeupEvent = SDL_EVENT_USER;

// Lets wake_window() post kWakeupEvent: call once SDL's events run, and disable before SDL quits.
void enable_wakeups();
void disable_wakeups();

// Posts kWakeupEvent, unless one is already waiting; does nothing while wakeups are disabled.
// Safe to call from any thread.
void wake_window();

// Call on receiving kWakeupEvent, so the next change posts another.
void wakeup_received();

}  // namespace reflektortts
