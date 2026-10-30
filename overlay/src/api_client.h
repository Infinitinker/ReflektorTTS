#pragma once

#include <string>
#include <vector>

namespace reflektortts {

struct VoiceOption {
    std::string id;
    std::string name;
    std::string language;
};

struct LanguageOption {
    std::string code;
    std::string name;
};

// What the overlay knows about the core, from its /v1 API.
struct CoreState {
    bool connected = false;
    std::string game;  // Empty while no game is being read.
    std::string voice;
    std::string language;  // Output language code, e.g. "pl".
    bool paused = false;
    std::string last_line;
    std::string last_error;
    std::vector<VoiceOption> voices;
    std::vector<LanguageOption> languages;
};

// Connects to the core's API on background threads and keeps reconnecting.
void start_api_client();

CoreState core_state();

// Commands are sent on a background thread; the result arrives as a status event.
void request_paused(bool paused);
void request_voice(const std::string& voice_id);
void request_language(const std::string& language_code);

}  // namespace reflektortts
