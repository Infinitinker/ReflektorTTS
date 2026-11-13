// Tells the user why the panel cannot start, when its arguments are wrong or its window cannot
// open: on standard error, in the log and in an SDL message box.

#include "startup_error.h"

#include <SDL3/SDL_messagebox.h>

#include <cstdio>

#include "log.h"

namespace reflektortts {

void report_startup_error(const std::string& message) {
    std::fputs((message + "\n").c_str(), stderr);
    std::fflush(stderr);
    log_message(message);
    if (!SDL_ShowSimpleMessageBox(SDL_MESSAGEBOX_ERROR, "Settings – ReflektorTTS", message.c_str(), nullptr)) {
        log_message(std::string("Cannot show a message box: ") + SDL_GetError());
    }
}

}  // namespace reflektortts
