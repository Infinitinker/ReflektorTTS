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
#include <format>
#include <optional>
#include <span>
#include <string>
#include <system_error>
#include <utility>
#include <vector>

#include "memory/addresses.h"
#include "memory/exported_function.h"
#include "memory/functions.h"
#include "memory/pe_image.h"

namespace {

using reflektortts::address_of;
using reflektortts::at_rva;
using reflektortts::exported_function;
using reflektortts::function_at;
using reflektortts::pe_headers;
using reflektortts::pointer_at;

// Exit codes; the core relies on kWrongBitness to try the other (32/64-bit) build.
constexpr int kFailed = 1;
constexpr int kUsageError = 2;
constexpr int kWrongBitness = 3;

constexpr const wchar_t* kUsage =
    L"Usage: reflektortts-inject (<process.exe> | --pid <id>) [--port <port>] [overlay.dll]\n";
// The overlay's entry point, which the DLL exports (native/overlay/src/dllmain.cpp).
constexpr const char* kEntryPoint = "reflektortts_start_overlay";
constexpr unsigned long kMaxPort = 65535;

DWORD find_process_id(const std::wstring& process_name) {
    HANDLE snapshot = CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0);
    if (snapshot == INVALID_HANDLE_VALUE) {
        return 0;
    }
    PROCESSENTRY32W entry{};
    entry.dwSize = sizeof(entry);
    DWORD process_id = 0;
    for (BOOL more = Process32FirstW(snapshot, &entry); more != FALSE; more = Process32NextW(snapshot, &entry)) {
        if (_wcsicmp(std::data(entry.szExeFile), process_name.c_str()) == 0) {
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

// The count values of a table at rva in the image mapped at base.
template <typename T>
std::vector<T> table(const BYTE* base, DWORD rva, DWORD count) {
    std::span<const T> values(at_rva<T>(base, rva), count);
    return {values.begin(), values.end()};
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
    const auto* base = pointer_at<const BYTE>(address_of(image) & ~std::uintptr_t{3});
    const IMAGE_NT_HEADERS& headers = pe_headers(base);
    // A DLL of the other bitness has headers of another layout, so it is not read on.
    bool own_bitness = headers.OptionalHeader.Magic == IMAGE_NT_OPTIONAL_HDR_MAGIC;
    const IMAGE_DATA_DIRECTORY& directory = headers.OptionalHeader.DataDirectory[IMAGE_DIRECTORY_ENTRY_EXPORT];
    std::optional<DWORD> offset;
    if (own_bitness && directory.Size != 0) {
        const auto* exports = at_rva<IMAGE_EXPORT_DIRECTORY>(base, directory.VirtualAddress);
        // The tables are copied out, so each lookup in them is checked against their size.
        std::vector<DWORD> names = table<DWORD>(base, exports->AddressOfNames, exports->NumberOfNames);
        std::vector<WORD> ordinals = table<WORD>(base, exports->AddressOfNameOrdinals, exports->NumberOfNames);
        std::vector<DWORD> functions = table<DWORD>(base, exports->AddressOfFunctions, exports->NumberOfFunctions);
        for (std::size_t i = 0; i < names.size() && !offset; ++i) {
            if (std::strcmp(at_rva<char>(base, names.at(i)), name) == 0) {
                offset = functions.at(ordinals.at(i));
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
    for (BOOL more = Module32FirstW(snapshot, &entry); more != FALSE && base == nullptr;
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
    if (WriteProcessMemory(process, remote_path, path.c_str(), size, nullptr) != FALSE) {
        // The new thread runs LoadLibraryW as its start routine: both are WINAPI and take one pointer.
        // The HMODULE it returns comes back cut to the thread's DWORD exit code, which nothing reads,
        // since module_base finds the DLL.
        auto load_library =
            exported_function<LPTHREAD_START_ROUTINE>(GetModuleHandleW(L"kernel32.dll"), "LoadLibraryW");
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
    auto start = function_at<LPTHREAD_START_ROUTINE>(entry_point);
    // The port travels as the thread's parameter, a pointer-sized number.
    auto* parameter = pointer_at<void>(port);
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

// Writes a message, formatted as std::format does, to stream.
template <typename... Args>
void print(std::FILE* stream, std::wformat_string<Args...> format, Args&&... args) {
    std::fputws(std::format(format, std::forward<Args>(args)...).c_str(), stream);
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
    std::span<wchar_t*> given_args(argv, static_cast<std::size_t>(argc));
    std::vector<std::wstring> args(given_args.begin(), given_args.end());
    bool by_pid = args.size() > 1 && args.at(1) == L"--pid";
    std::size_t next = by_pid ? 3 : 2;
    if (args.size() < next) {
        std::fputws(kUsage, stderr);
        return kUsageError;
    }
    unsigned long port = 0;
    if (next < args.size() && args.at(next) == L"--port") {
        std::optional<unsigned long> given =
            next + 1 < args.size() ? read_port(args.at(next + 1).c_str()) : std::nullopt;
        if (!given) {
            print(stderr, L"The port after --port must be from 1 to 65535.\n{}", kUsage);
            return kUsageError;
        }
        port = *given;
        next += 2;
    }
    if (args.size() > next + 1) {
        std::fputws(kUsage, stderr);
        return kUsageError;
    }
    std::wstring process_name = by_pid ? L"PID " + args.at(2) : args.at(1);
    std::filesystem::path dll_path = args.size() > next ? std::filesystem::absolute(args.at(next)) : default_dll_path();

    if (!std::filesystem::exists(dll_path)) {
        print(stderr, L"Overlay DLL not found: {}\n", dll_path.native());
        return kFailed;
    }
    std::optional<DWORD> entry_offset = export_offset(dll_path, kEntryPoint);
    if (!entry_offset) {
        print(stderr, L"{} is not an overlay this injector can start: use the injector from its build.\n",
              dll_path.native());
        return kFailed;
    }
    DWORD process_id =
        by_pid ? static_cast<DWORD>(std::wcstoul(args.at(2).c_str(), nullptr, 10)) : find_process_id(process_name);
    if (process_id == 0) {
        print(stderr, L"{} is not running: start the game first.\n", process_name);
        return kFailed;
    }
    HANDLE process = OpenProcess(
        PROCESS_CREATE_THREAD | PROCESS_QUERY_INFORMATION | PROCESS_VM_OPERATION | PROCESS_VM_WRITE | PROCESS_VM_READ,
        FALSE, process_id);
    if (process == nullptr) {
        print(stderr, L"Cannot open {} (error {}): is it running as administrator?\n", process_name, GetLastError());
        return kFailed;
    }
    if (!same_bitness(process)) {
        print(stderr, L"{} and this injector differ in bitness (32-bit vs 64-bit): use the matching build.\n",
              process_name);
        CloseHandle(process);
        return kWrongBitness;
    }
    BYTE* loaded_at = load_library_in(process, process_id, dll_path);
    bool started = loaded_at != nullptr &&
                   start_overlay_in(process, pointer_at<BYTE>(address_of(loaded_at) + *entry_offset), port);
    DWORD start_error = started ? 0 : GetLastError();
    CloseHandle(process);
    if (loaded_at == nullptr) {
        print(stderr, L"Failed to load the overlay into {}.\n", process_name);
        return kFailed;
    }
    if (!started) {
        print(stderr, L"The overlay was loaded into {}, but could not start (error {}).\n", process_name, start_error);
        return kFailed;
    }
    print(stdout, L"Overlay loaded into {} (PID {}).\n", process_name, process_id);
    return 0;
}
