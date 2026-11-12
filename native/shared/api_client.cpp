// The API client: follows the core's events and keeps reconnecting, keeps the state a client knows
// about the core, and sends commands and changes to its profile (/v1/profiles/<id>/...) on a
// background thread.

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

// The client's threads run until the process ends, so what they use is never destroyed: a static
// destructor would take it from under them as the process exits.
struct Client {
    std::unique_ptr<Transport> transport;
    ApiClientOptions options;

    std::mutex state_mutex;
    CoreState state;

    std::mutex requests_mutex;
    std::condition_variable requests_ready;
    std::deque<Request> requests;
};

Client& g_client = *new Client();

// Changes the state under its lock, then tells the client's user. Called on the client's threads,
// which no exception may leave.
template <typename Change>
void update_state(Change change) {
    {
        std::scoped_lock lock(g_client.state_mutex);
        change(g_client.state);
    }
    if (!g_client.options.on_change) {
        return;
    }
    try {
        g_client.options.on_change();
    } catch (const std::exception& error) {
        log_message(std::string("Cannot tell the window that the state changed: ") + error.what());
    }
}

// Sets the error the panel shows, or hides it with an empty message; from_source marks a source's
// error, which follow_source_error takes away once the source works again.
void set_error(CoreState& state, std::string message, bool from_source = false) {
    state.last_error = std::move(message);
    state.last_error_from_source = from_source;
}

std::optional<std::string> optional_text(const json& value) {
    return value.is_null() ? std::nullopt : std::optional(value.get<std::string>());
}

std::vector<SourceStages> read_sources(const json& sources) {
    std::vector<SourceStages> result;
    for (const json& source : sources) {
        SourceStages entry{source.at("name").get<std::string>(),
                           source.at("type").get<std::string>(),
                           source.at("enabled").get<bool>(),
                           {}};
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

// The settings that the status and a profile's settings both carry.
ProfileSettings read_settings(const json& view) {
    ProfileSettings settings;
    settings.voice = view.at("voice").get<std::string>();
    settings.input_language = view.at("input_language").get<std::string>();
    settings.output_language = view.at("output_language").get<std::string>();
    settings.ducking = view.at("ducking").get<bool>();
    settings.duck_volume = view.at("duck_volume").get<float>();
    settings.speech_rate = view.at("speech_rate").get<float>();
    settings.new_line = view.at("new_line").get<std::string>();
    settings.subtitles = view.at("subtitles").get<bool>();
    settings.subtitle_size = view.at("subtitle_size").get<std::string>();
    settings.subtitle_position = view.at("subtitle_position").get<std::string>();
    settings.sources = read_sources(view.at("sources"));
    return settings;
}

// Parses everything first, so a malformed status leaves the state untouched.
void apply_status(const json& status) {
    const json& app = status.at("app");
    std::string title = app.is_null() ? "" : app.at("title").get<std::string>();
    std::string profile = app.is_null() ? "" : app.at("profile").get<std::string>();
    bool paused = status.at("paused").get<bool>();
    ProfileSettings settings = read_settings(status);
    update_state([&](CoreState& state) {
        state.app = std::move(title);
        state.profile = std::move(profile);
        state.running = !app.is_null();
        state.paused = paused;
        state.settings = std::move(settings);
    });
}

// The same for a profile's settings (GET /v1/profiles/<id>/settings and profile_settings events).
void apply_profile_settings(const json& view) {
    std::string title = view.at("app").at("title").get<std::string>();
    bool running = view.at("running").get<bool>();
    ProfileSettings settings = read_settings(view);
    update_state([&](CoreState& state) {
        state.app = std::move(title);
        state.running = running;
        state.settings = std::move(settings);
        state.settings_error.clear();
    });
}

// The core's message for a request it refused, else the HTTP status.
std::string error_message(const HttpResponse& response) {
    json body = json::parse(response.body, nullptr, false);
    if (body.is_object() && body.contains("error") && body["error"].is_string()) {
        return body["error"].get<std::string>();
    }
    return "The request failed (HTTP " + std::to_string(response.status) + ").";
}

// Percent-encodes text for one segment of a URL path; a profile ID is a file name, so it can hold
// any character.
std::string encode_path_segment(const std::string& text) {
    std::string encoded;
    for (char c : text) {
        auto byte = static_cast<unsigned char>(c);
        bool unreserved = (byte >= 'a' && byte <= 'z') || (byte >= 'A' && byte <= 'Z') ||
                          (byte >= '0' && byte <= '9') || byte == '-' || byte == '.' || byte == '_' || byte == '~';
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

// /v1/profiles/<profile>/<route>
std::string profile_path(const std::string& profile, const char* route) {
    return "/v1/profiles/" + encode_path_segment(profile) + "/" + route;
}

// Loads the settings of the profile the client keeps to. Returns false if the core cannot be
// reached; a refusal, such as for an unknown profile, is kept to be shown instead of the settings.
bool load_profile_settings(const std::string& profile) {
    std::optional<HttpResponse> response = g_client.transport->send("GET", profile_path(profile, "settings"), "");
    if (!response) {
        return false;
    }
    if (response->status != 200) {
        std::string message = error_message(*response);
        log_message("Cannot load the settings of profile " + profile + ": " + message);
        update_state([&](CoreState& state) { state.settings_error = std::move(message); });
        return true;
    }
    try {
        apply_profile_settings(json::parse(response->body));
    } catch (const json::exception& error) {
        log_message(std::string("Cannot read the profile's settings: ") + error.what());
        update_state([](CoreState& state) { state.settings_error = "The settings ReflektorTTS sent cannot be read."; });
    }
    return true;
}

// Whether the lines and errors of the app being read concern the client: they do unless it keeps
// to a profile whose app is not the one being read.
bool follows_app_being_read() {
    std::scoped_lock lock(g_client.state_mutex);
    return !g_client.options.profile || g_client.state.running;
}

// A status carries the error of the source of the app being read that failed last and has not
// worked since. A source's error the panel shows follows it, so it goes once the source works.
void follow_source_error(const json& status) {
    const auto source_error = status.find("source_error");
    if (source_error == status.end() || !follows_app_being_read()) {
        return;
    }
    {
        std::scoped_lock lock(g_client.state_mutex);
        if (!g_client.state.last_error_from_source) {
            return;
        }
    }
    std::string message = source_error->is_null() ? "" : source_error->at("message").get<std::string>();
    update_state([&](CoreState& state) {
        if (state.last_error_from_source) {
            bool from_source = !message.empty();
            set_error(state, std::move(message), from_source);
        }
    });
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
            follow_source_error(event);
            if (!g_client.options.profile) {
                apply_status(event);
            } else if (!load_profile_settings(*g_client.options.profile)) {
                // An app starting or stopping, or a voice installed or removed, can change the
                // profile's settings as shown, but the core sends them only when they are changed.
                log_message("Cannot reach the core to load the profile's settings again");
            }
        } else if (type == "profile_settings") {
            if (g_client.options.profile && event.at("profile").get<std::string>() == *g_client.options.profile) {
                apply_profile_settings(event);
            }
        } else if (type == "line" && follows_app_being_read()) {
            std::string line = event.at("text").get<std::string>();
            update_state([&](CoreState& state) { state.last_line = std::move(line); });
        } else if (type == "subtitle" && follows_app_being_read()) {
            std::string subtitle = event.at("text").get<std::string>();
            update_state([&](CoreState& state) { state.subtitle = std::move(subtitle); });
        } else if (type == "error" && follows_app_being_read()) {
            std::string message = event.at("message").get<std::string>();
            bool from_source = event.at("kind").get<std::string>() == "source.error";
            update_state([&](CoreState& state) { set_error(state, std::move(message), from_source); });
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
    std::optional<HttpResponse> response = g_client.transport->send("GET", path, "");
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
                language_options.push_back({language.at("code").get<std::string>(),
                                            language.at("name").get<std::string>(),
                                            language.at("english_name").get<std::string>()});
            }
        }
        update_state([&](CoreState& state) {
            state.voices = std::move(voice_options);
            state.languages = std::move(language_options);
        });
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
    std::unique_ptr<EventStream> events = g_client.transport->open_event_stream("/v1/events");
    if (!events) {
        return;
    }
    // Loaded once the events flow, so no change made in between is missed.
    if (g_client.options.profile && !load_profile_settings(*g_client.options.profile)) {
        return;
    }
    update_state([](CoreState& state) {
        state.connected = true;
        set_error(state, "");
    });
    log_message("Connected to the ReflektorTTS core");
    while (std::optional<std::string> message = events->receive()) {
        handle_event(*message);
    }
}

void disconnected() {
    update_state([](CoreState& state) {
        state.connected = false;
        // Without the core, nothing would ever hide the subtitle.
        state.subtitle.clear();
    });
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
            std::unique_lock lock(g_client.requests_mutex);
            g_client.requests_ready.wait(lock, [] { return !g_client.requests.empty(); });
            request = std::move(g_client.requests.front());
            g_client.requests.pop_front();
        }
        std::string error;
        try {
            std::optional<HttpResponse> response = g_client.transport->send(request.method, request.path, request.body);
            if (!response) {
                error = "ReflektorTTS is not reachable.";
            } else if (response->status != 200) {
                error = error_message(*response);
            }
        } catch (const std::exception& failure) {
            log_message(std::string("A request to the core failed: ") + failure.what());
            error = "The request failed.";
        } catch (...) {
            error = "The request failed.";
        }
        if (!error.empty()) {
            update_state([&](CoreState& state) { set_error(state, std::move(error)); });
        }
    }
}

void enqueue(Request request) {
    {
        std::scoped_lock lock(g_client.requests_mutex);
        g_client.requests.push_back(std::move(request));
    }
    g_client.requests_ready.notify_one();
}

// Sends a change to the client's profile, at /v1/profiles/<id>/<route>.
void request_profile_change(const char* route, const json& body) {
    std::string profile;
    {
        std::scoped_lock lock(g_client.state_mutex);
        profile = g_client.state.profile;
    }
    if (profile.empty()) {
        log_message("No app is being read, so the change is not sent");
        update_state(
            [](CoreState& state) { set_error(state, "No app is being read, so the change cannot be saved."); });
        return;
    }
    enqueue({"PATCH", profile_path(profile, route), body.dump()});
}

void request_setting(const json& setting) {
    request_profile_change("settings", setting);
}

}  // namespace

void start_api_client(std::unique_ptr<Transport> transport, ApiClientOptions options) {
    g_client.transport = std::move(transport);
    if (options.profile) {
        g_client.state.profile = *options.profile;
    }
    g_client.options = std::move(options);
    std::thread(event_loop).detach();
    std::thread(request_loop).detach();
}

CoreState core_state() {
    std::scoped_lock lock(g_client.state_mutex);
    return g_client.state;
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
    update_state([](CoreState& state) { set_error(state, ""); });
}

}  // namespace reflektortts
