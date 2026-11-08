#include "startup_error.h"

#include <SDL3/SDL_messagebox.h>

#include <cstdio>

#include "log.h"

namespace reflektortts {

void report_startup_error(const std::string& message) {
    std::fprintf(stderr, "%s\n", message.c_str());
    std::fflush(stderr);
    log_message(message);
    if (!SDL_ShowSimpleMessageBox(SDL_MESSAGEBOX_ERROR, "ReflektorTTS settings", message.c_str(), nullptr)) {
        log_message(std::string("Cannot show a message box: ") + SDL_GetError());
    }
}

}  // namespace reflektortts
