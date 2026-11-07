#include "arguments.h"

#include <algorithm>
#include <array>
#include <charconv>
#include <cstddef>
#include <functional>
#include <map>
#include <string_view>
#include <system_error>

namespace reflektortts {
namespace {

constexpr char kUsage[] =
    "Start it as: reflektortts-panel --profile <id> "
    "[--dock-side right|left --dock-x <x> --dock-y <y> --dock-height <height>]";
constexpr std::array<std::string_view, 5> kNames = {"--profile", "--dock-side", "--dock-x", "--dock-y",
                                                    "--dock-height"};

ArgumentError usage_error(const std::string& what) {
    return ArgumentError(what + " " + kUsage);
}

int number(const std::string& name, const std::string& value) {
    int result = 0;
    const char* end = value.data() + value.size();
    auto [last, error] = std::from_chars(value.data(), end, result);
    if (error != std::errc() || last != end) {
        throw usage_error("\"" + value + "\" after " + name + " is not a whole number.");
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
        throw usage_error("\"" + side + "\" after --dock-side is neither right nor left.");
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
    for (std::size_t i = 0; i < arguments.size(); ++i) {
        std::string name = arguments[i];
        if (std::ranges::find(kNames, name) == kNames.end()) {
            throw usage_error("Unknown argument \"" + name + "\".");
        }
        if (values.contains(name)) {
            throw usage_error(name + " is given twice.");
        }
        if (i + 1 == arguments.size() || std::string_view(arguments[i + 1]).empty()) {
            throw usage_error("Nothing given after " + name + ".");
        }
        values[name] = arguments[++i];
    }
    auto profile = values.find("--profile");
    if (profile == values.end()) {
        throw usage_error("No profile given, so there are no settings to show.");
    }
    PanelArguments result{profile->second, std::nullopt};
    std::size_t dock_values = values.size() - 1;
    if (dock_values == kNames.size() - 1) {
        result.dock = read_dock(values);
    } else if (dock_values != 0) {
        throw usage_error("The dock arguments go together: give all four, or none.");
    }
    return result;
}

}  // namespace reflektortts
