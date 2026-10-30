// Loads the overlay DLL into a running game.
// Usage: reflektortts-inject (<process.exe> | --pid <id>) [path\to\reflektortts-overlay.dll]

#include <windows.h>
#include <tlhelp32.h>

#include <cstdio>
#include <cwchar>
#include <filesystem>
#include <string>

namespace {

// Exit codes; the core relies on kWrongBitness to try the other (32/64-bit) build.
constexpr int kFailed = 1;
constexpr int kUsageError = 2;
constexpr int kWrongBitness = 3;

DWORD find_process_id(const std::wstring& process_name) {
    HANDLE snapshot = CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0);
    if (snapshot == INVALID_HANDLE_VALUE) {
        return 0;
    }
    PROCESSENTRY32W entry{};
    entry.dwSize = sizeof(entry);
    DWORD process_id = 0;
    for (BOOL more = Process32FirstW(snapshot, &entry); more; more = Process32NextW(snapshot, &entry)) {
        if (_wcsicmp(entry.szExeFile, process_name.c_str()) == 0) {
            process_id = entry.th32ProcessID;
            break;
        }
    }
    CloseHandle(snapshot);
    return process_id;
}

std::filesystem::path default_dll_path() {
    wchar_t own_path[MAX_PATH];
    GetModuleFileNameW(nullptr, own_path, MAX_PATH);
    return std::filesystem::path(own_path).replace_filename(L"reflektortts-overlay.dll");
}

bool same_bitness(HANDLE process) {
    BOOL own_wow64 = FALSE;
    BOOL target_wow64 = FALSE;
    IsWow64Process(GetCurrentProcess(), &own_wow64);
    IsWow64Process(process, &target_wow64);
    return own_wow64 == target_wow64;
}

bool load_library_in(HANDLE process, const std::wstring& dll_path) {
    SIZE_T size = (dll_path.size() + 1) * sizeof(wchar_t);
    void* remote_path = VirtualAllocEx(process, nullptr, size, MEM_COMMIT | MEM_RESERVE, PAGE_READWRITE);
    if (remote_path == nullptr) {
        return false;
    }
    bool loaded = false;
    if (WriteProcessMemory(process, remote_path, dll_path.c_str(), size, nullptr)) {
        auto load_library = reinterpret_cast<LPTHREAD_START_ROUTINE>(
            GetProcAddress(GetModuleHandleW(L"kernel32.dll"), "LoadLibraryW"));
        HANDLE thread = CreateRemoteThread(process, nullptr, 0, load_library, remote_path, 0, nullptr);
        if (thread != nullptr) {
            WaitForSingleObject(thread, INFINITE);
            DWORD module_handle = 0;
            loaded = GetExitCodeThread(thread, &module_handle) && module_handle != 0;
            CloseHandle(thread);
        }
    }
    VirtualFreeEx(process, remote_path, 0, MEM_RELEASE);
    return loaded;
}

}  // namespace

int wmain(int argc, wchar_t** argv) {
    bool by_pid = argc > 1 && std::wcscmp(argv[1], L"--pid") == 0;
    int first_path = by_pid ? 3 : 2;
    if (argc < first_path || argc > first_path + 1) {
        std::fwprintf(stderr, L"Usage: reflektortts-inject (<process.exe> | --pid <id>) [overlay.dll]\n");
        return kUsageError;
    }
    std::wstring process_name = by_pid ? std::wstring(L"PID ") + argv[2] : argv[1];
    std::filesystem::path dll_path =
        argc > first_path ? std::filesystem::absolute(argv[first_path]) : default_dll_path();

    if (!std::filesystem::exists(dll_path)) {
        std::fwprintf(stderr, L"Overlay DLL not found: %ls\n", dll_path.c_str());
        return kFailed;
    }
    DWORD process_id = by_pid ? static_cast<DWORD>(std::wcstoul(argv[2], nullptr, 10)) : find_process_id(process_name);
    if (process_id == 0) {
        std::fwprintf(stderr, L"%ls is not running: start the game first.\n", process_name.c_str());
        return kFailed;
    }
    HANDLE process = OpenProcess(PROCESS_CREATE_THREAD | PROCESS_QUERY_INFORMATION | PROCESS_VM_OPERATION |
                                     PROCESS_VM_WRITE | PROCESS_VM_READ,
                                 FALSE, process_id);
    if (process == nullptr) {
        std::fwprintf(stderr, L"Cannot open %ls (error %lu): is it running as administrator?\n",
                      process_name.c_str(), GetLastError());
        return kFailed;
    }
    if (!same_bitness(process)) {
        std::fwprintf(stderr, L"%ls and this injector differ in bitness (32-bit vs 64-bit): use the matching build.\n",
                      process_name.c_str());
        CloseHandle(process);
        return kWrongBitness;
    }
    bool loaded = load_library_in(process, dll_path.wstring());
    CloseHandle(process);
    if (!loaded) {
        std::fwprintf(stderr, L"Failed to load the overlay into %ls.\n", process_name.c_str());
        return kFailed;
    }
    std::fwprintf(stdout, L"Overlay loaded into %ls (PID %lu).\n", process_name.c_str(), process_id);
    return 0;
}
