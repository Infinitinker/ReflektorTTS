// The transport over WinHTTP, which comes with Windows: the API client's way to reach the core
// there. Built on Windows only.

#pragma once

#include <memory>

#include "transport.h"

namespace reflektortts {

// A transport over WinHTTP, which comes with Windows. user_agent names the client to the core.
// Returns nullptr (after logging why) if WinHTTP cannot start.
std::unique_ptr<Transport> make_winhttp_transport(const wchar_t* user_agent);

}  // namespace reflektortts
