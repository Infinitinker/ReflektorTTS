#pragma once

#include <functional>
#include <memory>
#include <optional>
#include <string>

#include "core_state.h"
#include "transport.h"

namespace reflektortts {

struct ApiClientOptions {
    // The profile whose settings the client shows and changes, whether or not its app runs (the
    // panel's window). Without one, it follows the app being read, as the status says (the overlay).
    std::optional<std::string> profile;
    // Called on one of the client's threads after its state changes, e.g. to wake a window waiting
    // for input. It must not throw.
    std::function<void()> on_change;
};

// Connects to the core's API through transport on background threads, and keeps reconnecting.
// Call once; the threads run for as long as the process.
void start_api_client(std::unique_ptr<Transport> transport, ApiClientOptions options = {});

CoreState core_state();

// Commands are sent on a background thread; the result arrives as a status event.
void request_paused(bool paused);
void request_stop_line();

// Changes to the settings of the client's profile; while it follows the app being read and no app
// is, they are not sent.
void request_voice(const std::string& voice_id);
void request_input_language(const std::string& code);
void request_output_language(const std::string& code);
void request_source_enabled(const std::string& name, bool enabled);
void request_stage_enabled(const std::string& key, StageOutput output, bool enabled);
void request_ducking(bool enabled);
void request_duck_volume(float volume);
void request_speech_rate(float rate);
void request_new_line(const std::string& new_line);
void request_subtitles(bool enabled);
void request_subtitle_size(const std::string& size);
void request_subtitle_position(const std::string& position);

// Hides the last error until a new one arrives.
void dismiss_error();

}  // namespace reflektortts
