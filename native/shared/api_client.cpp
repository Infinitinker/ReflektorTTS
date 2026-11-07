#include "api_client.h"

#include <chrono>
#include <condition_variable>
#include <cstddef>
#include <cstdio>
#include <deque>
#include <exception>
#include <memory>
#include <mutex>
#include <nlohmann/json.hpp>
#include <optional>
#include <string>
#include <thread>
#include <utility>
#include <vector>

#include "log.h"

namespace reflektortts {
namespace {

using nlohmann::json;

constexpr std::chrono::milliseconds kReconnectDelay(2000);
// How much of an unexpected answer is logged.
constexpr std::size_t kLoggedBytes = 300;

struct Request {
    std::string method;
    std::string path;
    std::string body;
};

std::unique_ptr<Transport> g_transport;

std::mutex g_state_mutex;
CoreState g_state;

std::mutex g_requests_mutex;
std::condition_variable g_requests_ready;
std::deque<Request> g_requests;

std::optional<std::string> optional_text(const json& value) {
    return value.is_null() ? std::nullopt : std::optional(value.get<std::string>());
}

std::vector<SourceStages> read_sources(const json& sources) {
    std::vector<SourceStages> result;
    for (const json& source : sources) {
        SourceStages entry{source.at("name").get<std::string>(), source.at("type").get<std::string>(),
                           source.at("enabled").get<bool>(), {}};
        for (const json& stage : source.at("stages")) {
            entry.stages.push_back({stage.at("key").get<std::string>(), stage.at("type").get<std::string>(),
                                    stage.at("summary").get<std::string>(), optional_text(stage.at("warning")),
                                    stage.at("enabled").at("text").get<bool>(),
                                    stage.at("enabled").at("speech").get<bool>(), optional_text(stage.at("inactive"))});
        }
        result.push_back(std::move(entry));
    }
    return result;
}

// Parses everything first, so a malformed status leaves the state untouched.
void apply_status(const json& status) {
    const json& app = status.at("app");
    std::string title = app.is_null() ? "" : app.at("title").get<std::string>();
    std::string profile = app.is_null() ? "" : app.at("profile").get<std::string>();
    std::string voice = status.at("voice").get<std::string>();
    std::string input_language = status.at("input_language").get<std::string>();
    std::string output_language = status.at("output_language").get<std::string>();
    bool paused = status.at("paused").get<bool>();
    bool ducking = status.at("ducking").get<bool>();
    float duck_volume = status.at("duck_volume").get<float>();
    float speech_rate = status.at("speech_rate").get<float>();
    std::string new_line = status.at("new_line").get<std::string>();
    bool subtitles = status.at("subtitles").get<bool>();
    std::string subtitle_size = status.at("subtitle_size").get<std::string>();
    std::string subtitle_position = status.at("subtitle_position").get<std::string>();
    std::vector<SourceStages> sources = read_sources(status.at("sources"));

    std::lock_guard lock(g_state_mutex);
    g_state.app = std::move(title);
    g_state.profile = std::move(profile);
    g_state.voice = std::move(voice);
    g_state.input_language = std::move(input_language);
    g_state.output_language = std::move(output_language);
    g_state.paused = paused;
    g_state.ducking = ducking;
    g_state.duck_volume = duck_volume;
    g_state.speech_rate = speech_rate;
    g_state.new_line = std::move(new_line);
    g_state.subtitles = subtitles;
    g_state.subtitle_size = std::move(subtitle_size);
    g_state.subtitle_position = std::move(subtitle_position);
    g_state.sources = std::move(sources);
}

bool load_options();

void handle_event(const std::string& text) {
    json event = json::parse(text, nullptr, false);
    if (event.is_discarded()) {
        log_message("Ignoring an event that is not JSON");
        return;
    }
    try {
        std::string type = event.at("type").get<std::string>();
        if (type == "status") {
            apply_status(event);
        } else if (type == "line") {
            std::lock_guard lock(g_state_mutex);
            g_state.last_line = event.at("text").get<std::string>();
        } else if (type == "subtitle") {
            std::lock_guard lock(g_state_mutex);
            g_state.subtitle = event.at("text").get<std::string>();
        } else if (type == "error") {
            std::lock_guard lock(g_state_mutex);
            g_state.last_error = event.at("message").get<std::string>();
        } else if (type == "download") {
            // A voice installed or removed while the app runs changes what the panel can offer.
            std::string state = event.at("state").get<std::string>();
            if (state == "installed" || state == "removed") {
                load_options();
            }
        }
    } catch (const json::exception& error) {
        log_message(std::string("Ignoring a malformed event: ") + error.what());
    }
}

// Fetches a JSON document. Returns nullopt if the core cannot be reached, and null JSON
// (after logging why) if it answered with an error.
std::optional<json> fetch(const std::string& path) {
    std::optional<HttpResponse> response = g_transport->send("GET", path, "");
    if (!response) {
        return std::nullopt;
    }
    json document = json::parse(response->body, nullptr, false);
    if (response->status != 200 || document.is_discarded()) {
        log_message("Unexpected answer from the core (HTTP " + std::to_string(response->status) +
                    "): " + response->body.substr(0, kLoggedBytes));
        return json();
    }
    return document;
}

// Loads the voices and languages the panel offers. Returns false if the core cannot be reached.
bool load_options() {
    std::optional<json> voices = fetch("/v1/voices");
    std::optional<json> languages = fetch("/v1/languages");
    if (!voices || !languages) {
        return false;
    }
    try {
        std::vector<VoiceOption> voice_options;
        if (!voices->is_null()) {
            for (const json& voice : voices->at("voices")) {
                voice_options.push_back({voice.at("id").get<std::string>(), voice.at("engine").get<std::string>(),
                                         voice.at("name").get<std::string>(), voice.at("language").get<std::string>()});
            }
        }
        std::vector<LanguageOption> language_options;
        if (!languages->is_null()) {
            for (const json& language : languages->at("languages")) {
                language_options.push_back({language.at("code").get<std::string>(), language.at("name").get<std::string>()});
            }
        }
        std::lock_guard lock(g_state_mutex);
        g_state.voices = std::move(voice_options);
        g_state.languages = std::move(language_options);
    } catch (const json::exception& error) {
        log_message(std::string("Cannot read the voice or language list: ") + error.what());
    }
    return true;
}

// Runs one session: fetches the voice and language lists, then follows /v1/events until it ends.
void listen_for_events() {
    if (!load_options()) {
        return;
    }
    std::unique_ptr<EventStream> events = g_transport->open_event_stream("/v1/events");
    if (!events) {
        return;
    }
    {
        std::lock_guard lock(g_state_mutex);
        g_state.connected = true;
        g_state.last_error.clear();
    }
    log_message("Connected to the ReflektorTTS core");
    while (std::optional<std::string> message = events->receive()) {
        handle_event(*message);
    }
}

void disconnected() {
    std::lock_guard lock(g_state_mutex);
    g_state.connected = false;
    // Without the core, nothing would ever hide the subtitle.
    g_state.subtitle.clear();
}

// An exception leaving a thread would end the process, so each loop catches every one.
void event_loop() {
    for (;;) {
        try {
            listen_for_events();
        } catch (const std::exception& error) {
            log_message(std::string("Lost the connection to the core: ") + error.what());
        } catch (...) {
            log_message("Lost the connection to the core");
        }
        disconnected();
        std::this_thread::sleep_for(kReconnectDelay);
    }
}

void request_loop() {
    for (;;) {
        Request request;
        {
            std::unique_lock lock(g_requests_mutex);
            g_requests_ready.wait(lock, [] { return !g_requests.empty(); });
            request = std::move(g_requests.front());
            g_requests.pop_front();
        }
        std::string error;
        try {
            std::optional<HttpResponse> response = g_transport->send(request.method, request.path, request.body);
            if (!response) {
                error = "ReflektorTTS is not reachable.";
            } else if (response->status != 200) {
                json body = json::parse(response->body, nullptr, false);
                error = body.is_object() && body.contains("error") && body["error"].is_string()
                            ? body["error"].get<std::string>()
                            : "The request failed (HTTP " + std::to_string(response->status) + ").";
            }
        } catch (const std::exception& failure) {
            log_message(std::string("A request to the core failed: ") + failure.what());
            error = "The request failed.";
        } catch (...) {
            error = "The request failed.";
        }
        if (!error.empty()) {
            std::lock_guard lock(g_state_mutex);
            g_state.last_error = error;
        }
    }
}

void enqueue(Request request) {
    {
        std::lock_guard lock(g_requests_mutex);
        g_requests.push_back(std::move(request));
    }
    g_requests_ready.notify_one();
}

// Percent-encodes text for one segment of a URL path; a profile ID is a file name, so it can hold
// any character.
std::string encode_path_segment(const std::string& text) {
    std::string encoded;
    for (char c : text) {
        auto byte = static_cast<unsigned char>(c);
        bool unreserved = (byte >= 'a' && byte <= 'z') || (byte >= 'A' && byte <= 'Z') || (byte >= '0' && byte <= '9') ||
                          byte == '-' || byte == '.' || byte == '_' || byte == '~';
        if (unreserved) {
            encoded += c;
        } else {
            char escape[4];
            std::snprintf(escape, sizeof(escape), "%%%02X", byte);
            encoded += escape;
        }
    }
    return encoded;
}

// Sends a change to the profile of the app being read, at /v1/profiles/<id>/<route>.
void request_profile_change(const char* route, const json& body) {
    std::string profile;
    {
        std::lock_guard lock(g_state_mutex);
        profile = g_state.profile;
    }
    if (profile.empty()) {
        log_message("No app is being read, so the change is not sent");
        std::lock_guard lock(g_state_mutex);
        g_state.last_error = "No app is being read, so the change cannot be saved.";
        return;
    }
    enqueue({"PATCH", "/v1/profiles/" + encode_path_segment(profile) + "/" + route, body.dump()});
}

void request_setting(const json& setting) {
    request_profile_change("settings", setting);
}

}  // namespace

void start_api_client(std::unique_ptr<Transport> transport) {
    g_transport = std::move(transport);
    std::thread(event_loop).detach();
    std::thread(request_loop).detach();
}

CoreState core_state() {
    std::lock_guard lock(g_state_mutex);
    return g_state;
}

void request_paused(bool paused) {
    enqueue({"POST", paused ? "/v1/pause" : "/v1/resume", ""});
}

void request_stop_line() {
    enqueue({"POST", "/v1/stop", ""});
}

void request_voice(const std::string& voice_id) {
    request_setting(json{{"voice", voice_id}});
}

void request_input_language(const std::string& code) {
    request_setting(json{{"input_language", code}});
}

void request_output_language(const std::string& code) {
    request_setting(json{{"output_language", code}});
}

void request_source_enabled(const std::string& name, bool enabled) {
    request_profile_change("sources", json{{"name", name}, {"enabled", enabled}});
}

void request_stage_enabled(const std::string& key, StageOutput output, bool enabled) {
    const char* name = output == StageOutput::Text ? "text" : "speech";
    request_profile_change("stages", json{{"key", key}, {"output", name}, {"enabled", enabled}});
}

void request_ducking(bool enabled) {
    request_setting(json{{"ducking", enabled}});
}

void request_duck_volume(float volume) {
    request_setting(json{{"duck_volume", volume}});
}

void request_speech_rate(float rate) {
    request_setting(json{{"speech_rate", rate}});
}

void request_new_line(const std::string& new_line) {
    request_setting(json{{"new_line", new_line}});
}

void request_subtitles(bool enabled) {
    request_setting(json{{"subtitles", enabled}});
}

void request_subtitle_size(const std::string& size) {
    request_setting(json{{"subtitle_size", size}});
}

void request_subtitle_position(const std::string& position) {
    request_setting(json{{"subtitle_position", position}});
}

void dismiss_error() {
    std::lock_guard lock(g_state_mutex);
    g_state.last_error.clear();
}

}  // namespace reflektortts
