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

void apply_status(const json& status) {
    std::lock_guard lock(g_state_mutex);
    const json& game = status.at("game");
    g_state.game = game.is_null() ? "" : game.at("title").get<std::string>();
    g_state.voice = status.at("voice").get<std::string>();
    g_state.paused = status.at("paused").get<bool>();
}

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
        } else if (type == "error") {
            std::lock_guard lock(g_state_mutex);
            g_state.last_error = event.at("message").get<std::string>();
        }
    } catch (const json::exception& error) {
        log_message(std::string("Ignoring a malformed event: ") + error.what());
    }
}

// Returns false if the core cannot be reached, e.g. because it is not running.
bool load_voices() {
    std::optional<Response> response = send({L"GET", L"/v1/voices", ""});
    if (!response) {
        return false;
    }
    if (response->status != 200) {
        log_message("Cannot fetch the voice list (HTTP " + std::to_string(response->status) + "): " + response->body);
        return true;
    }
    try {
        // Kept in a variable: looping over json::parse(...).at(...) would read a destroyed temporary.
        json document = json::parse(response->body);
        std::vector<VoiceOption> voices;
        for (const json& voice : document.at("voices")) {
            voices.push_back({voice.at("id").get<std::string>(), voice.at("name").get<std::string>(),
                              voice.at("language").get<std::string>()});
        }
        std::lock_guard lock(g_state_mutex);
        g_state.voices = std::move(voices);
    } catch (const json::exception& error) {
        log_message(std::string("Cannot read the voice list: ") + error.what());
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

// Runs one session: fetches the voice list, then follows /v1/events until it ends.
void listen_for_events() {
    if (!load_voices()) {
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

void request_voice(const std::string& voice_id) {
    enqueue({L"PATCH", L"/v1/settings", json{{"voice", voice_id}}.dump()});
}

}  // namespace reflektortts
