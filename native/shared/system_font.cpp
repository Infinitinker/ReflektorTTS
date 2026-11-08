#include "system_font.h"

#include <imgui.h>

#include <filesystem>
#include <system_error>

#include "log.h"

#ifdef _WIN32
#include <windows.h>
#endif

namespace reflektortts {
namespace {

// Where the system's interface font is, or an empty path if it is not known for this system.
std::filesystem::path system_font_path() {
#ifdef _WIN32
    wchar_t windows_dir[MAX_PATH];
    if (GetWindowsDirectoryW(windows_dir, MAX_PATH) == 0) {
        return {};
    }
    return std::filesystem::path(windows_dir) / L"Fonts" / L"segoeui.ttf";
#else
    return {};
#endif
}

}  // namespace

bool load_system_font(float size) {
    std::filesystem::path font = system_font_path();
    std::error_code error;
    if (font.empty() || !std::filesystem::exists(font, error) ||
        ImGui::GetIO().Fonts->AddFontFromFileTTF(font.string().c_str(), size) == nullptr) {
        log_message("The system font was not found; accented letters may not display");
        return false;
    }
    return true;
}

}  // namespace reflektortts
