#include "api_client.h"

#include <windows.h>
#include <winhttp.h>

#include <condition_variable>
#include <deque>
#include <mutex>
#include <nlohmann/json.hpp>
#include <optional>
#include <thread>

#include "log.h"

namespace reflektortts {
namespace {

using nlohmann::json;

constexpr wchar_t kHost[] = L"127.0.0.1";
constexpr INTERNET_PORT kPort = 47821;  // Must match reflektortts.api.server.PORT.
constexpr DWORD kReconnectMs = 2000;

struct Request {
    const wchar_t* method;
    std::wstring path;
    std::string body;
};

std::mutex g_state_mutex;
CoreState g_state;

std::mutex g_requests_mutex;
std::condition_variable g_requests_ready;
std::deque<Request> g_requests;

HINTERNET g_session = nullptr;

class Handle {
public:
    explicit Handle(HINTERNET handle) : handle_(handle) {}
    ~Handle() {
        if (handle_ != nullptr) {
            WinHttpCloseHandle(handle_);
        }
    }
    Handle(const Handle&) = delete;
    Handle& operator=(const Handle&) = delete;
    HINTERNET get() const { return handle_; }
    explicit operator bool() const { return handle_ != nullptr; }

private:
    HINTERNET handle_;
};

std::string read_body(HINTERNET request) {
    std::string body;
    DWORD available = 0;
    while (WinHttpQueryDataAvailable(request, &available) && available > 0) {
        std::string chunk(available, '\0');
        DWORD read = 0;
        if (!WinHttpReadData(request, chunk.data(), available, &read)) {
            break;
        }
        body.append(chunk.data(), read);
    }
    return body;
}

struct Response {
    DWORD status;
    std::string body;
};

std::optional<Response> send(const Request& request) {
    Handle connection(WinHttpConnect(g_session, kHost, kPort, 0));
    if (!connection) {
        return std::nullopt;
    }
    Handle handle(WinHttpOpenRequest(connection.get(), request.method, request.path.c_str(), nullptr,
                                     WINHTTP_NO_REFERER, WINHTTP_DEFAULT_ACCEPT_TYPES, 0));
    if (!handle) {
        return std::nullopt;
    }
    bool has_body = !request.body.empty();
    const wchar_t* headers = has_body ? L"Content-Type: application/json" : WINHTTP_NO_ADDITIONAL_HEADERS;
    // -1 means "headers are zero-terminated"; with no headers the length must be 0.
    DWORD headers_length = has_body ? static_cast<DWORD>(-1) : 0;
    void* body = has_body ? const_cast<char*>(request.body.data()) : WINHTTP_NO_REQUEST_DATA;
    auto length = static_cast<DWORD>(request.body.size());
    if (!WinHttpSendRequest(handle.get(), headers, headers_length, body, length, length, 0) ||
        !WinHttpReceiveResponse(handle.get(), nullptr)) {
        return std::nullopt;
    }
    DWORD status = 0;
    DWORD size = sizeof(status);
    WinHttpQueryHeaders(handle.get(), WINHTTP_QUERY_STATUS_CODE | WINHTTP_QUERY_FLAG_NUMBER, WINHTTP_HEADER_NAME_BY_INDEX,
                        &status, &size, WINHTTP_NO_HEADER_INDEX);
    return Response{status, read_body(handle.get())};
}

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
                                    stage.at("enabled").get<bool>(), optional_text(stage.at("inactive"))});
        }
        result.push_back(std::move(entry));
    }
    return result;
}

// Parses everything first, so a malformed status leaves the state untouched.
void apply_status(const json& status) {
    const json& game = status.at("game");
    std::string title = game.is_null() ? "" : game.at("title").get<std::string>();
    std::string voice = status.at("voice").get<std::string>();
    std::string input_language = status.at("input_language").get<std::string>();
    std::string output_language = status.at("output_language").get<std::string>();
    bool paused = status.at("paused").get<bool>();
    bool ducking = status.at("ducking").get<bool>();
    float duck_volume = status.at("duck_volume").get<float>();
    float speech_rate = status.at("speech_rate").get<float>();
    bool cut_off_lines = status.at("cut_off_lines").get<bool>();
    bool subtitles = status.at("subtitles").get<bool>();
    std::string subtitle_size = status.at("subtitle_size").get<std::string>();
    std::string subtitle_position = status.at("subtitle_position").get<std::string>();
    std::vector<SourceStages> sources = read_sources(status.at("sources"));

    std::lock_guard lock(g_state_mutex);
    g_state.game = std::move(title);
    g_state.voice = std::move(voice);
    g_state.input_language = std::move(input_language);
    g_state.output_language = std::move(output_language);
    g_state.paused = paused;
    g_state.ducking = ducking;
    g_state.duck_volume = duck_volume;
    g_state.speech_rate = speech_rate;
    g_state.cut_off_lines = cut_off_lines;
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
            // A voice installed or removed while the game runs changes what the panel can offer.
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
std::optional<json> fetch(const wchar_t* path) {
    std::optional<Response> response = send({L"GET", path, ""});
    if (!response) {
        return std::nullopt;
    }
    json document = json::parse(response->body, nullptr, false);
    if (response->status != 200 || document.is_discarded()) {
        log_message("Unexpected answer from the core (HTTP " + std::to_string(response->status) + "): " + response->body);
        return json();
    }
    return document;
}

// Loads the voices and languages the panel offers. Returns false if the core cannot be reached.
bool load_options() {
    std::optional<json> voices = fetch(L"/v1/voices");
    std::optional<json> languages = fetch(L"/v1/languages");
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

HINTERNET open_event_socket(HINTERNET connection) {
    Handle request(WinHttpOpenRequest(connection, L"GET", L"/v1/events", nullptr, WINHTTP_NO_REFERER,
                                      WINHTTP_DEFAULT_ACCEPT_TYPES, 0));
    if (!request || !WinHttpSetOption(request.get(), WINHTTP_OPTION_UPGRADE_TO_WEB_SOCKET, nullptr, 0) ||
        !WinHttpSendRequest(request.get(), WINHTTP_NO_ADDITIONAL_HEADERS, 0, nullptr, 0, 0, 0) ||
        !WinHttpReceiveResponse(request.get(), nullptr)) {
        return nullptr;
    }
    // The socket takes over the connection; the HTTP request handle is closed on return.
    return WinHttpWebSocketCompleteUpgrade(request.get(), 0);
}

// Runs one session: fetches the voice and language lists, then follows /v1/events until it ends.
void listen_for_events() {
    if (!load_options()) {
        return;
    }
    Handle connection(WinHttpConnect(g_session, kHost, kPort, 0));
    Handle socket(connection ? open_event_socket(connection.get()) : nullptr);
    if (!socket) {
        return;
    }
    {
        std::lock_guard lock(g_state_mutex);
        g_state.connected = true;
        g_state.last_error.clear();
    }
    log_message("Connected to the ReflektorTTS core");

    std::string message;
    char buffer[4096];
    for (;;) {
        DWORD read = 0;
        WINHTTP_WEB_SOCKET_BUFFER_TYPE type{};
        if (WinHttpWebSocketReceive(socket.get(), buffer, sizeof(buffer), &read, &type) != NO_ERROR ||
            type == WINHTTP_WEB_SOCKET_CLOSE_BUFFER_TYPE) {
            break;
        }
        message.append(buffer, read);
        if (type == WINHTTP_WEB_SOCKET_UTF8_MESSAGE_BUFFER_TYPE) {
            handle_event(message);
            message.clear();
        }
    }
    std::lock_guard lock(g_state_mutex);
    g_state.connected = false;
    // Without the core, nothing would ever hide the subtitle.
    g_state.subtitle.clear();
}

void event_loop() {
    for (;;) {
        listen_for_events();
        Sleep(kReconnectMs);
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
        std::optional<Response> response = send(request);
        std::string error;
        if (!response) {
            error = "ReflektorTTS is not reachable.";
        } else if (response->status != 200) {
            json body = json::parse(response->body, nullptr, false);
            error = body.is_object() && body.contains("error") && body["error"].is_string()
                        ? body["error"].get<std::string>()
                        : "The request failed (HTTP " + std::to_string(response->status) + ").";
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

}  // namespace

void start_api_client() {
    g_session = WinHttpOpen(L"ReflektorTTS overlay", WINHTTP_ACCESS_TYPE_NO_PROXY, WINHTTP_NO_PROXY_NAME,
                            WINHTTP_NO_PROXY_BYPASS, 0);
    if (g_session == nullptr) {
        log_message("Cannot start WinHTTP; the overlay cannot reach ReflektorTTS");
        return;
    }
    // The DLL stays loaded until the game exits, so these threads live as long as the game.
    std::thread(event_loop).detach();
    std::thread(request_loop).detach();
}

CoreState core_state() {
    std::lock_guard lock(g_state_mutex);
    return g_state;
}

void request_paused(bool paused) {
    enqueue({L"POST", paused ? L"/v1/pause" : L"/v1/resume", ""});
}

void request_stop_line() {
    enqueue({L"POST", L"/v1/stop", ""});
}

void request_voice(const std::string& voice_id) {
    enqueue({L"PATCH", L"/v1/settings", json{{"voice", voice_id}}.dump()});
}

void request_input_language(const std::string& code) {
    enqueue({L"PATCH", L"/v1/settings", json{{"input_language", code}}.dump()});
}

void request_output_language(const std::string& code) {
    enqueue({L"PATCH", L"/v1/settings", json{{"output_language", code}}.dump()});
}

void request_source_enabled(const std::string& name, bool enabled) {
    enqueue({L"PATCH", L"/v1/sources", json{{"name", name}, {"enabled", enabled}}.dump()});
}

void request_stage_enabled(const std::string& key, bool enabled) {
    enqueue({L"PATCH", L"/v1/stages", json{{"key", key}, {"enabled", enabled}}.dump()});
}

void request_ducking(bool enabled) {
    enqueue({L"PATCH", L"/v1/settings", json{{"ducking", enabled}}.dump()});
}

void request_duck_volume(float volume) {
    enqueue({L"PATCH", L"/v1/settings", json{{"duck_volume", volume}}.dump()});
}

void request_speech_rate(float rate) {
    enqueue({L"PATCH", L"/v1/settings", json{{"speech_rate", rate}}.dump()});
}

void request_cut_off_lines(bool cut_off) {
    enqueue({L"PATCH", L"/v1/settings", json{{"cut_off_lines", cut_off}}.dump()});
}

void request_subtitles(bool enabled) {
    enqueue({L"PATCH", L"/v1/settings", json{{"subtitles", enabled}}.dump()});
}

void request_subtitle_size(const std::string& size) {
    enqueue({L"PATCH", L"/v1/settings", json{{"subtitle_size", size}}.dump()});
}

void request_subtitle_position(const std::string& position) {
    enqueue({L"PATCH", L"/v1/settings", json{{"subtitle_position", position}}.dump()});
}

void dismiss_error() {
    std::lock_guard lock(g_state_mutex);
    g_state.last_error.clear();
}

}  // namespace reflektortts
