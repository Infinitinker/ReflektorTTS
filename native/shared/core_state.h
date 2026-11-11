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
    std::string name;  // The language's own name, e.g. "Polski".
    std::string english_name;
};

// What a line is prepared for; each stage is switched on and off for each.
enum class StageOutput { Text, Speech };

struct StageOption {
    std::string key;
    std::string type;  // The stage's name in the profile, e.g. "tracker".
    std::string summary;
    std::optional<std::string> warning;  // Shown while the stage is off for either output.
    bool text = true;                     // On for the text shown (subtitles).
    bool speech = true;                   // On for what is spoken.
    std::optional<std::string> inactive;  // Why it does nothing with the user's languages.
};

struct SourceStages {
    std::string source;
    std::string type;  // The source plugin, e.g. "memory".
    bool enabled = true;
    std::vector<StageOption> stages;
};

// A profile's settings, as the status (for the app being read) and the profile settings carry them.
struct ProfileSettings {
    std::string voice;
    std::string input_language;    // A code, e.g. "en".
    std::string output_language;  // A code, e.g. "pl".
    bool ducking = true;       // Whether the app's sound is lowered while speaking.
    float duck_volume = 0.3f;  // The app's volume while speaking, as a fraction of its own.
    float speech_rate = 1.0f;  // How fast lines are spoken, as a multiple of the voice's own pace.
    std::string new_line = "wait";  // What a new line does while another is spoken: "wait", "cut_off", "speed_up".
    bool subtitles = false;    // Whether lines are shown as subtitles over the app.
    std::string subtitle_size = "medium";   // "small", "medium" or "large".
    std::string subtitle_position = "top";  // "top" or "bottom".
    std::vector<SourceStages> sources;
};

// What a client knows about the core, from its /v1 API.
struct CoreState {
    bool connected = false;
    std::string app;      // The title of the profile's app; for the app being read, empty while none is.
    std::string profile;  // The ID of the profile whose settings these are; empty while no app is being read.
    bool running = false;  // Whether the profile's app is being read now.
    bool paused = false;
    ProfileSettings settings;
    // Why the profile's settings cannot be shown, as the core says (e.g. that there is no such
    // profile); empty when they can.
    std::string settings_error;
    std::string subtitle;  // The subtitle to show now; empty when none.
    std::string last_line;
    std::string last_error;
    bool last_error_from_source = false;  // A source's error goes once the status says it works again.
    std::vector<VoiceOption> voices;
    std::vector<LanguageOption> languages;
};

}  // namespace reflektortts
