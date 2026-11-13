// Loads the overlay DLL into a running game, and starts it there with the port of the core's API.
// Usage: reflektortts-inject (<process.exe> | --pid <id>) [--port <port>] [path\to\reflektortts-overlay.dll]

#include <windows.h>
#include <fcntl.h>
#include <io.h>
#include <tlhelp32.h>

#include <cstdint>
#include <cstdio>
#include <cstring>
#include <cwchar>
#include <filesystem>
#include <optional>
#include <string>
#include <system_error>

namespace {

// Exit codes; the core relies on kWrongBitness to try the other (32/64-bit) build.
constexpr int kFailed = 1;
constexpr int kUsageError = 2;
constexpr int kWrongBitness = 3;

constexpr wchar_t kUsage[] = L"Usage: reflektortts-inject (<process.exe> | --pid <id>) [--port <port>] [overlay.dll]\n";
// The overlay's entry point, which the DLL exports (native/overlay/src/dllmain.cpp).
constexpr char kEntryPoint[] = "reflektortts_start_overlay";
constexpr unsigned long kMaxPort = 65535;

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
    // Grows the buffer until the path fits, so the injector also works from a long path.
    std::wstring own_path(MAX_PATH, L'\0');
    for (;;) {
        DWORD length = GetModuleFileNameW(nullptr, own_path.data(), static_cast<DWORD>(own_path.size()));
        if (length < own_path.size()) {
            own_path.resize(length);
            break;
        }
        own_path.resize(own_path.size() * 2);
    }
    return std::filesystem::path(own_path).replace_filename(L"reflektortts-overlay.dll");
}

bool same_bitness(HANDLE process) {
    BOOL own_wow64 = FALSE;
    BOOL target_wow64 = FALSE;
    IsWow64Process(GetCurrentProcess(), &own_wow64);
    IsWow64Process(process, &target_wow64);
    return own_wow64 == target_wow64;
}

// Where the DLL exports name, relative to the start of the DLL once loaded, or nullopt if it does
// not export it. The DLL is mapped here as an image, without running any of it, and its export table
// read; the injector and the DLL have the same bitness, so the table has the injector's layout.
std::optional<DWORD> export_offset(const std::filesystem::path& dll_path, const char* name) {
    HMODULE image = LoadLibraryExW(dll_path.c_str(), nullptr, LOAD_LIBRARY_AS_IMAGE_RESOURCE);
    if (image == nullptr) {
        return std::nullopt;
    }
    // The handle's low bits mark a DLL mapped as an image resource; the image starts at the rest.
    const auto* base = reinterpret_cast<const BYTE*>(reinterpret_cast<std::uintptr_t>(image) & ~std::uintptr_t{3});
    const auto* dos = reinterpret_cast<const IMAGE_DOS_HEADER*>(base);
    const auto* headers = reinterpret_cast<const IMAGE_NT_HEADERS*>(base + dos->e_lfanew);
    // A DLL of the other bitness has headers of another layout, so it is not read on.
    bool own_bitness = headers->OptionalHeader.Magic == IMAGE_NT_OPTIONAL_HDR_MAGIC;
    const IMAGE_DATA_DIRECTORY& directory = headers->OptionalHeader.DataDirectory[IMAGE_DIRECTORY_ENTRY_EXPORT];
    std::optional<DWORD> offset;
    if (own_bitness && directory.Size != 0) {
        const auto* exports = reinterpret_cast<const IMAGE_EXPORT_DIRECTORY*>(base + directory.VirtualAddress);
        const auto* names = reinterpret_cast<const DWORD*>(base + exports->AddressOfNames);
        const auto* ordinals = reinterpret_cast<const WORD*>(base + exports->AddressOfNameOrdinals);
        const auto* functions = reinterpret_cast<const DWORD*>(base + exports->AddressOfFunctions);
        for (DWORD i = 0; i < exports->NumberOfNames && !offset; ++i) {
            if (std::strcmp(reinterpret_cast<const char*>(base + names[i]), name) == 0) {
                offset = functions[ordinals[i]];
            }
        }
    }
    FreeLibrary(image);
    return offset;
}

// Where the DLL is loaded in the game, or nullptr if it is not. The remote thread's exit code holds
// only 32 bits of LoadLibraryW's module handle, which on 64-bit can be zero for a loaded module; the
// game's module list says for sure.
BYTE* module_base(DWORD process_id, const std::filesystem::path& dll_path) {
    // While the game is still loading modules, the snapshot fails with ERROR_BAD_LENGTH and
    // has to be taken again.
    constexpr int kSnapshotTries = 20;
    HANDLE snapshot = INVALID_HANDLE_VALUE;
    for (int i = 0; i < kSnapshotTries && snapshot == INVALID_HANDLE_VALUE; ++i) {
        snapshot = CreateToolhelp32Snapshot(TH32CS_SNAPMODULE | TH32CS_SNAPMODULE32, process_id);
        if (snapshot == INVALID_HANDLE_VALUE && GetLastError() != ERROR_BAD_LENGTH) {
            break;
        }
    }
    if (snapshot == INVALID_HANDLE_VALUE) {
        return nullptr;
    }
    MODULEENTRY32W entry{};
    entry.dwSize = sizeof(entry);
    BYTE* base = nullptr;
    for (BOOL more = Module32FirstW(snapshot, &entry); more && base == nullptr;
         more = Module32NextW(snapshot, &entry)) {
        std::error_code error;
        if (std::filesystem::equivalent(entry.szExePath, dll_path, error)) {
            base = entry.modBaseAddr;
        }
    }
    CloseHandle(snapshot);
    return base;
}

// Loads the DLL in the game; returns where it is loaded, or nullptr if it could not be loaded.
BYTE* load_library_in(HANDLE process, DWORD process_id, const std::filesystem::path& dll_path) {
    std::wstring path = dll_path.wstring();
    SIZE_T size = (path.size() + 1) * sizeof(wchar_t);
    void* remote_path = VirtualAllocEx(process, nullptr, size, MEM_COMMIT | MEM_RESERVE, PAGE_READWRITE);
    if (remote_path == nullptr) {
        return nullptr;
    }
    bool started = false;
    if (WriteProcessMemory(process, remote_path, path.c_str(), size, nullptr)) {
        // The new thread runs LoadLibraryW as its start routine: both are WINAPI and take one pointer.
        // The HMODULE it returns comes back cut to the thread's DWORD exit code, which nothing reads,
        // since module_base finds the DLL. Casting through void (*)(), which stands for any function,
        // tells the compiler that the cast is meant.
        auto load_library = reinterpret_cast<LPTHREAD_START_ROUTINE>(
            reinterpret_cast<void (*)()>(GetProcAddress(GetModuleHandleW(L"kernel32.dll"), "LoadLibraryW")));
        HANDLE thread = CreateRemoteThread(process, nullptr, 0, load_library, remote_path, 0, nullptr);
        if (thread != nullptr) {
            WaitForSingleObject(thread, INFINITE);
            CloseHandle(thread);
            started = true;
        }
    }
    VirtualFreeEx(process, remote_path, 0, MEM_RELEASE);
    return started ? module_base(process_id, dll_path) : nullptr;
}

// Starts the overlay's entry point on a thread of its own in the game, given port (0 for the
// installed ReflektorTTS's). The thread runs for as long as the game does, so it is not waited for.
bool start_overlay_in(HANDLE process, BYTE* entry_point, unsigned long port) {
    auto start = reinterpret_cast<LPTHREAD_START_ROUTINE>(entry_point);
    // The port travels as the thread's parameter, a pointer-sized number.
    auto* parameter = reinterpret_cast<void*>(static_cast<std::uintptr_t>(port));
    HANDLE thread = CreateRemoteThread(process, nullptr, 0, start, parameter, 0, nullptr);
    if (thread == nullptr) {
        return false;
    }
    CloseHandle(thread);
    return true;
}

// The number after --port, or nullopt if it is not a port.
std::optional<unsigned long> read_port(const wchar_t* text) {
    wchar_t* end = nullptr;
    unsigned long port = std::wcstoul(text, &end, 10);
    if (end == text || *end != L'\0' || port < 1 || port > kMaxPort) {
        return std::nullopt;
    }
    return port;
}

}  // namespace

// The program's entry point, found by its name, so it keeps external linkage.
// NOLINTNEXTLINE(misc-use-internal-linkage)
int wmain(int argc, wchar_t** argv) {
    // Messages are written as UTF-8, the encoding the core reads them in: paths and process
    // names can hold any character, and the default C locale cuts a message off at the first
    // one outside Latin-1.
    _setmode(_fileno(stdout), _O_U8TEXT);
    _setmode(_fileno(stderr), _O_U8TEXT);
    bool by_pid = argc > 1 && std::wcscmp(argv[1], L"--pid") == 0;
    int next = by_pid ? 3 : 2;
    if (argc < next) {
        std::fputws(kUsage, stderr);
        return kUsageError;
    }
    unsigned long port = 0;
    if (next < argc && std::wcscmp(argv[next], L"--port") == 0) {
        std::optional<unsigned long> given = next + 1 < argc ? read_port(argv[next + 1]) : std::nullopt;
        if (!given) {
            std::fwprintf(stderr, L"The port after --port must be from 1 to 65535.\n%ls", kUsage);
            return kUsageError;
        }
        port = *given;
        next += 2;
    }
    if (argc > next + 1) {
        std::fputws(kUsage, stderr);
        return kUsageError;
    }
    std::wstring process_name = by_pid ? std::wstring(L"PID ") + argv[2] : argv[1];
    std::filesystem::path dll_path = argc > next ? std::filesystem::absolute(argv[next]) : default_dll_path();

    if (!std::filesystem::exists(dll_path)) {
        std::fwprintf(stderr, L"Overlay DLL not found: %ls\n", dll_path.c_str());
        return kFailed;
    }
    std::optional<DWORD> entry_offset = export_offset(dll_path, kEntryPoint);
    if (!entry_offset) {
        std::fwprintf(stderr, L"%ls is not an overlay this injector can start: use the injector from its build.\n",
                      dll_path.c_str());
        return kFailed;
    }
    DWORD process_id = by_pid ? static_cast<DWORD>(std::wcstoul(argv[2], nullptr, 10)) : find_process_id(process_name);
    if (process_id == 0) {
        std::fwprintf(stderr, L"%ls is not running: start the game first.\n", process_name.c_str());
        return kFailed;
    }
    HANDLE process = OpenProcess(
        PROCESS_CREATE_THREAD | PROCESS_QUERY_INFORMATION | PROCESS_VM_OPERATION | PROCESS_VM_WRITE | PROCESS_VM_READ,
        FALSE, process_id);
    if (process == nullptr) {
        std::fwprintf(stderr, L"Cannot open %ls (error %lu): is it running as administrator?\n", process_name.c_str(),
                      GetLastError());
        return kFailed;
    }
    if (!same_bitness(process)) {
        std::fwprintf(stderr, L"%ls and this injector differ in bitness (32-bit vs 64-bit): use the matching build.\n",
                      process_name.c_str());
        CloseHandle(process);
        return kWrongBitness;
    }
    BYTE* loaded_at = load_library_in(process, process_id, dll_path);
    bool started = loaded_at != nullptr && start_overlay_in(process, loaded_at + *entry_offset, port);
    DWORD start_error = started ? 0 : GetLastError();
    CloseHandle(process);
    if (loaded_at == nullptr) {
        std::fwprintf(stderr, L"Failed to load the overlay into %ls.\n", process_name.c_str());
        return kFailed;
    }
    if (!started) {
        std::fwprintf(stderr, L"The overlay was loaded into %ls, but could not start (error %lu).\n",
                      process_name.c_str(), start_error);
        return kFailed;
    }
    std::fwprintf(stdout, L"Overlay loaded into %ls (PID %lu).\n", process_name.c_str(), process_id);
    return 0;
}
