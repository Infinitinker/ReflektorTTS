// reflektortts-panel --profile <id> [--dock-...]: the settings panel of one profile in a window of
// its own, whether or not its app runs. The desktop app starts it, beside its own window.

#include <SDL3/SDL_main.h>

#include <cstddef>
#include <exception>
#include <memory>
#include <span>
#include <string>
#include <utility>

#include "api_client.h"
#include "arguments.h"
#include "panel_window.h"
#include "startup_error.h"
#include "transport_winhttp.h"
#include "wakeup.h"

namespace {

// What the process exits with when its command line is wrong.
constexpr int kUsageExitCode = 2;

}  // namespace

int main(int argc, char* argv[]) {
    using namespace reflektortts;
    try {
        std::span<char* const> command_line(argv, argc > 0 ? static_cast<std::size_t>(argc) : 0);
        PanelArguments arguments = parse_arguments(command_line.subspan(command_line.empty() ? 0 : 1));
        std::unique_ptr<Transport> transport = make_winhttp_transport(L"ReflektorTTS panel");
        if (!transport) {
            report_startup_error(
                "The settings window cannot connect to ReflektorTTS: WinHTTP, part of Windows, did not start.");
            return 1;
        }
        start_api_client(std::move(transport), {arguments.profile, wake_window});
        return run_panel_window(arguments.dock);
    } catch (const ArgumentError& error) {
        report_startup_error(error.what());
        return kUsageExitCode;
    } catch (const std::exception& error) {
        report_startup_error(std::string("The settings window stopped because of an error: ") + error.what());
        return 1;
    }
}
