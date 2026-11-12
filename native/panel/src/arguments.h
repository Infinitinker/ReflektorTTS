// The panel's command line: the profile to show, the core's port and where to open (Dock), read by
// parse_arguments(), and ArgumentError for one that is wrong.

#pragma once

#include <optional>
#include <span>
#include <stdexcept>
#include <string>

#include "transport.h"

namespace reflektortts {

// The command line is wrong; what() says how, for the user.
class ArgumentError : public std::runtime_error {
public:
    using std::runtime_error::runtime_error;
};

// Which side of the ReflektorTTS window the panel opens on.
enum class DockSide { Right, Left };

// Where the panel opens: beside the ReflektorTTS window, as tall as it. In physical pixels of the
// screen, measured on the window's visible frame (without Windows' invisible resize borders).
struct Dock {
    DockSide side = DockSide::Right;
    // The edge the two windows share: the panel's left edge, its first pixel, on the right; its right
    // edge, the first pixel past it, on the left.
    int x = 0;
    int y = 0;  // The top of both windows.
    int height = 0;  // Both windows' height, frame and title bar included.
};

struct PanelArguments {
    std::string profile;  // The ID of the profile whose settings are shown.
    int port = kDefaultCorePort;  // The port of the core's API.
    std::optional<Dock> dock;  // None: the panel opens centered, at its default size.
};

// Reads the arguments after the program's name: "--profile <id>", optionally "--port <port>", and
// optionally all four of "--dock-side right|left --dock-x <x> --dock-y <y> --dock-height <height>",
// in any order. Throws ArgumentError if the profile is missing, the port or a dock argument is
// missing or wrong, or anything else is given.
PanelArguments parse_arguments(std::span<char* const> arguments);

}  // namespace reflektortts
