// How the API client reaches the core: where the API listens, a request, and the event stream. Each
// OS has its own implementation; Windows has WinHTTP's (transport_winhttp.h).

#pragma once

#include <cstddef>
#include <memory>
#include <optional>
#include <string>

namespace reflektortts {

// Where the core's API listens: on this computer only, on a port of each ReflektorTTS's own
// (reflektortts.identity.API_PORTS). The core gives the overlay its port, and the desktop app gives
// the settings window the same port; a client told none connects to the installed ReflektorTTS's.
constexpr const char* kCoreHost = "127.0.0.1";
constexpr int kDefaultCorePort = 47821;
// The core's events are small; a bigger one is skipped, so a wrong server cannot fill memory.
constexpr std::size_t kMaxEventBytes = std::size_t{1024} * 1024;
// The same for answers to requests, such as the voice list.
constexpr std::size_t kMaxResponseBytes = std::size_t{4} * 1024 * 1024;

struct HttpResponse {
    int status = 0;
    std::string body;
};

// An open stream of the core's events, closed when destroyed.
class EventStream {
public:
    virtual ~EventStream() = default;
    // Waits for the next message and returns it, or nullopt once the stream has closed.
    // Messages bigger than kMaxEventBytes are skipped (after logging that).
    virtual std::optional<std::string> receive() = 0;
};

// How a client reaches the core's API at kCoreHost, on the port it was made for; one implementation
// per OS.
// Both functions may be called from several threads at once.
class Transport {
public:
    virtual ~Transport() = default;
    // Sends a request, with body as its JSON body unless it is empty. Returns nullopt if the
    // core cannot be reached or the answer is bigger than kMaxResponseBytes.
    virtual std::optional<HttpResponse> send(const std::string& method, const std::string& path,
                                             const std::string& body) = 0;
    // Opens the WebSocket at path. Returns nullptr if the core cannot be reached.
    virtual std::unique_ptr<EventStream> open_event_stream(const std::string& path) = 0;
};

}  // namespace reflektortts
