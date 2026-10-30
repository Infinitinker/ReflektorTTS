#pragma once

#include <optional>
#include <string>
#include <vector>

namespace reflektortts {

struct VoiceOption {
    std::string id;
    std::string engine;
    std::string name;
    std::string language;  // BCP 47 tag, e.g. "pl-PL".
};

struct LanguageOption {
    std::string code;
    std::string name;
};

struct StageOption {
    std::string key;
    std::string type;  // The stage's name in the profile, e.g. "tracker".
    std::string summary;
    std::optional<std::string> warning;  // Shown while the stage is switched off.
    bool enabled = true;
};

struct SourceStages {
    std::string source;
    std::string type;  // The source plugin, e.g. "memory".
    bool enabled = true;
    std::vector<StageOption> stages;
};

// What the overlay knows about the core, from its /v1 API.
struct CoreState {
    bool connected = false;
    std::string game;  // Empty while no game is being read.
    std::string voice;
    std::string game_language;    // A code, or "auto".
    std::string output_language;  // A code, e.g. "pl".
    bool paused = false;
    bool ducking = true;       // Whether the game's sound is lowered while speaking.
    float duck_volume = 0.3f;  // The game's volume while speaking, as a fraction of its own.
    bool subtitles = false;    // Whether lines are shown as subtitles over the game.
    std::string subtitle_size = "medium";   // "small", "medium" or "large".
    std::string subtitle_position = "top";  // "top" or "bottom".
    std::vector<SourceStages> sources;
    std::string subtitle;  // The subtitle to show now; empty when none.
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
void request_stop_line();
void request_voice(const std::string& voice_id);
void request_game_language(const std::string& code);
void request_output_language(const std::string& code);
void request_source_enabled(const std::string& name, bool enabled);
void request_stage_enabled(const std::string& key, bool enabled);
void request_ducking(bool enabled);
void request_duck_volume(float volume);
void request_subtitles(bool enabled);
void request_subtitle_size(const std::string& size);
void request_subtitle_position(const std::string& position);

// Hides the last error until a new one arrives.
void dismiss_error();

}  // namespace reflektortts
