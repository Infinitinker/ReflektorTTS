#include "wakeup.h"

#include <atomic>
#include <mutex>
#include <string>

#include "log.h"

namespace reflektortts {
namespace {

// Used by the API client's threads, which run until the process ends, so it is never destroyed.
struct Wakeups {
    std::mutex mutex;  // Held while posting, so disable_wakeups() waits for a post under way.
    bool enabled = false;
    std::atomic<bool> pending = false;
};

Wakeups& g_wakeups = *new Wakeups();

}  // namespace

void enable_wakeups() {
    std::lock_guard lock(g_wakeups.mutex);
    g_wakeups.enabled = true;
}

void disable_wakeups() {
    std::lock_guard lock(g_wakeups.mutex);
    g_wakeups.enabled = false;
}

void wake_window() {
    if (g_wakeups.pending.exchange(true)) {
        return;
    }
    std::lock_guard lock(g_wakeups.mutex);
    if (!g_wakeups.enabled) {
        g_wakeups.pending = false;
        return;
    }
    SDL_Event event{};
    event.type = kWakeupEvent;
    if (!SDL_PushEvent(&event)) {
        g_wakeups.pending = false;
        log_message(std::string("Cannot wake the window: ") + SDL_GetError());
    }
}

void wakeup_received() {
    g_wakeups.pending = false;
}

}  // namespace reflektortts
