// Reads the panel's command line: --profile <id>, --port <port> and the --dock-* arguments, all
// four or none. A missing, unknown or wrong argument throws ArgumentError, which ends with how to
// start the panel.

#include "arguments.h"

#include <algorithm>
#include <array>
#include <charconv>
#include <cstddef>
#include <format>
#include <functional>
#include <map>
#include <memory>
#include <string_view>
#include <system_error>

namespace reflektortts {
namespace {

constexpr char kUsage[] =
    "Start it as: reflektortts-panel --profile <id> [--port <port>] "
    "[--dock-side right|left --dock-x <x> --dock-y <y> --dock-height <height>]";
constexpr std::array<std::string_view, 4> kDockNames = {"--dock-side", "--dock-x", "--dock-y", "--dock-height"};
constexpr int kMaxPort = 65535;

bool known(std::string_view name) {
    return name == "--profile" || name == "--port" || std::ranges::find(kDockNames, name) != kDockNames.end();
}

ArgumentError usage_error(const std::string& what) {
    return ArgumentError(std::format("{} {}", what, kUsage));
}

int number(const std::string& name, const std::string& value) {
    int result = 0;
    const char* end = std::to_address(value.end());
    auto [last, error] = std::from_chars(value.data(), end, result);
    if (error != std::errc() || last != end) {
        throw usage_error(std::format("\"{}\" after {} is not a whole number.", value, name));
    }
    return result;
}

Dock read_dock(const std::map<std::string, std::string, std::less<>>& values) {
    Dock dock;
    const std::string& side = values.at("--dock-side");
    if (side == "right") {
        dock.side = DockSide::Right;
    } else if (side == "left") {
        dock.side = DockSide::Left;
    } else {
        throw usage_error(std::format("\"{}\" after --dock-side is neither right nor left.", side));
    }
    dock.x = number("--dock-x", values.at("--dock-x"));
    dock.y = number("--dock-y", values.at("--dock-y"));
    dock.height = number("--dock-height", values.at("--dock-height"));
    if (dock.height <= 0) {
        throw usage_error("The height after --dock-height must be more than 0.");
    }
    return dock;
}

}  // namespace

PanelArguments parse_arguments(std::span<char* const> arguments) {
    std::map<std::string, std::string, std::less<>> values;
    for (auto argument = arguments.begin(); argument != arguments.end(); ++argument) {
        std::string name = *argument;
        if (!known(name)) {
            throw usage_error(std::format("Unknown argument \"{}\".", name));
        }
        if (values.contains(name)) {
            throw usage_error(std::format("{} is given twice.", name));
        }
        ++argument;
        if (argument == arguments.end() || std::string_view(*argument).empty()) {
            throw usage_error(std::format("Nothing given after {}.", name));
        }
        values[name] = *argument;
    }
    auto profile = values.find("--profile");
    if (profile == values.end()) {
        throw usage_error("No profile given, so there are no settings to show.");
    }
    PanelArguments result{.profile = profile->second};
    if (auto port = values.find("--port"); port != values.end()) {
        result.port = number("--port", port->second);
        if (result.port < 1 || result.port > kMaxPort) {
            throw usage_error("The port after --port must be from 1 to 65535.");
        }
    }
    auto dock_values =
        std::ranges::count_if(kDockNames, [&values](std::string_view name) { return values.contains(name); });
    if (static_cast<std::size_t>(dock_values) == kDockNames.size()) {
        result.dock = read_dock(values);
    } else if (dock_values != 0) {
        throw usage_error("The dock arguments go together: give all four, or none.");
    }
    return result;
}

}  // namespace reflektortts
