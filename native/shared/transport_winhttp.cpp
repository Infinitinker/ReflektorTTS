// The transport over WinHTTP, Windows only: the core's events over a WebSocket, requests and
// commands over HTTP.

#include "transport_winhttp.h"

#include <windows.h>
#include <winhttp.h>

#include <string>
#include <utility>

#include "log.h"

namespace reflektortts {
namespace {

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
    [[nodiscard]] HINTERNET get() const { return handle_; }
    explicit operator bool() const { return handle_ != nullptr; }

private:
    HINTERNET handle_;
};

// UTF-8 to UTF-16, for WinHTTP's arguments.
std::wstring widen(const std::string& text) {
    if (text.empty()) {
        return {};
    }
    int length = MultiByteToWideChar(CP_UTF8, 0, text.data(), static_cast<int>(text.size()), nullptr, 0);
    std::wstring wide(length, L'\0');
    MultiByteToWideChar(CP_UTF8, 0, text.data(), static_cast<int>(text.size()), wide.data(), length);
    return wide;
}

// Returns nullopt for a body bigger than kMaxResponseBytes.
std::optional<std::string> read_body(HINTERNET request) {
    std::string body;
    DWORD available = 0;
    while (WinHttpQueryDataAvailable(request, &available) && available > 0) {
        if (body.size() + available > kMaxResponseBytes) {
            log_message("Skipping an answer bigger than " + std::to_string(kMaxResponseBytes) + " bytes");
            return std::nullopt;
        }
        std::string chunk(available, '\0');
        DWORD read = 0;
        if (!WinHttpReadData(request, chunk.data(), available, &read)) {
            break;
        }
        body.append(chunk.data(), read);
    }
    return body;
}

HINTERNET open_web_socket(HINTERNET connection, const std::wstring& path) {
    Handle request(WinHttpOpenRequest(connection, L"GET", path.c_str(), nullptr, WINHTTP_NO_REFERER,
                                      WINHTTP_DEFAULT_ACCEPT_TYPES, 0));
    if (!request || !WinHttpSetOption(request.get(), WINHTTP_OPTION_UPGRADE_TO_WEB_SOCKET, nullptr, 0) ||
        !WinHttpSendRequest(request.get(), WINHTTP_NO_ADDITIONAL_HEADERS, 0, nullptr, 0, 0, 0) ||
        !WinHttpReceiveResponse(request.get(), nullptr)) {
        return nullptr;
    }
    // The socket takes over the connection; the HTTP request handle is closed on return.
    return WinHttpWebSocketCompleteUpgrade(request.get(), 0);
}

class WinHttpEventStream : public EventStream {
public:
    WinHttpEventStream(HINTERNET connection, HINTERNET socket) : connection_(connection), socket_(socket) {}

    std::optional<std::string> receive() override {
        std::string message;
        bool too_big = false;
        char buffer[4096];
        for (;;) {
            DWORD read = 0;
            WINHTTP_WEB_SOCKET_BUFFER_TYPE type{};
            if (WinHttpWebSocketReceive(socket_.get(), buffer, sizeof(buffer), &read, &type) != NO_ERROR ||
                type == WINHTTP_WEB_SOCKET_CLOSE_BUFFER_TYPE) {
                return std::nullopt;
            }
            if (!too_big && message.size() + read > kMaxEventBytes) {
                log_message("Skipping an event bigger than " + std::to_string(kMaxEventBytes) + " bytes");
                too_big = true;
                message.clear();
            }
            if (!too_big) {
                message.append(buffer, read);
            }
            if (type == WINHTTP_WEB_SOCKET_UTF8_MESSAGE_BUFFER_TYPE ||
                type == WINHTTP_WEB_SOCKET_BINARY_MESSAGE_BUFFER_TYPE) {
                if (!too_big) {
                    return message;
                }
                message.clear();
                too_big = false;
            }
        }
    }

private:
    // Declared first, so it is closed after the socket.
    Handle connection_;
    Handle socket_;
};

class WinHttpTransport : public Transport {
public:
    explicit WinHttpTransport(HINTERNET session) : session_(session), host_(widen(kCoreHost)) {}

    std::optional<HttpResponse> send(const std::string& method, const std::string& path,
                                     const std::string& body) override {
        Handle connection(connect());
        if (!connection) {
            return std::nullopt;
        }
        Handle request(WinHttpOpenRequest(connection.get(), widen(method).c_str(), widen(path).c_str(), nullptr,
                                          WINHTTP_NO_REFERER, WINHTTP_DEFAULT_ACCEPT_TYPES, 0));
        if (!request) {
            return std::nullopt;
        }
        bool has_body = !body.empty();
        const wchar_t* headers = has_body ? L"Content-Type: application/json" : WINHTTP_NO_ADDITIONAL_HEADERS;
        // -1 means "headers are zero-terminated"; with no headers the length must be 0.
        DWORD headers_length = has_body ? static_cast<DWORD>(-1) : 0;
        // WinHttpSendRequest only reads the body, though it takes it as void*.
        void* data = has_body ? const_cast<char*>(body.data()) : WINHTTP_NO_REQUEST_DATA;  // NOLINT(*-const-cast)
        auto length = static_cast<DWORD>(body.size());
        if (!WinHttpSendRequest(request.get(), headers, headers_length, data, length, length, 0) ||
            !WinHttpReceiveResponse(request.get(), nullptr)) {
            return std::nullopt;
        }
        DWORD status = 0;
        DWORD size = sizeof(status);
        WinHttpQueryHeaders(request.get(), WINHTTP_QUERY_STATUS_CODE | WINHTTP_QUERY_FLAG_NUMBER,
                            WINHTTP_HEADER_NAME_BY_INDEX, &status, &size, WINHTTP_NO_HEADER_INDEX);
        std::optional<std::string> response_body = read_body(request.get());
        if (!response_body) {
            return std::nullopt;
        }
        return HttpResponse{static_cast<int>(status), std::move(*response_body)};
    }

    std::unique_ptr<EventStream> open_event_stream(const std::string& path) override {
        HINTERNET connection = connect();
        if (connection == nullptr) {
            return nullptr;
        }
        HINTERNET socket = open_web_socket(connection, widen(path));
        if (socket == nullptr) {
            WinHttpCloseHandle(connection);
            return nullptr;
        }
        return std::make_unique<WinHttpEventStream>(connection, socket);
    }

private:
    [[nodiscard]] HINTERNET connect() const {
        return WinHttpConnect(session_.get(), host_.c_str(), static_cast<INTERNET_PORT>(kCorePort), 0);
    }

    Handle session_;
    std::wstring host_;
};

}  // namespace

std::unique_ptr<Transport> make_winhttp_transport(const wchar_t* user_agent) {
    HINTERNET session =
        WinHttpOpen(user_agent, WINHTTP_ACCESS_TYPE_NO_PROXY, WINHTTP_NO_PROXY_NAME, WINHTTP_NO_PROXY_BYPASS, 0);
    if (session == nullptr) {
        log_message("Cannot start WinHTTP, so ReflektorTTS cannot be reached");
        return nullptr;
    }
    return std::make_unique<WinHttpTransport>(session);
}

}  // namespace reflektortts
