// Hooks keyboard and mouse reads of DirectInput 8 and 1-7 devices, found through throwaway devices:
// while input is blocked, the app reads no keys pressed, a still mouse, and of buffered events only
// key and button releases.

#include "input/dinput_hook.h"

#define DIRECTINPUT_VERSION 0x0800
#include <dinput.h>

#include <array>
#include <cstddef>
#include <cstring>
#include <initializer_list>
#include <mutex>
#include <string>
#include <utility>

#include "hooks/code_hook.h"
#include "hooks/vtable_hook.h"
#include "input/blocking.h"
#include "log.h"
#include "memory/addresses.h"
#include "memory/exported_function.h"
#include "memory/functions.h"

namespace reflektortts {
namespace {

// The device methods used here sit at the same vtable slots in every DirectInput version, A and W.
using ReleaseFn = ULONG(STDMETHODCALLTYPE*)(void* object);
using GetCapabilitiesFn = HRESULT(STDMETHODCALLTYPE*)(void* device, DIDEVCAPS* capabilities);
using GetDeviceStateFn = HRESULT(STDMETHODCALLTYPE*)(void* device, DWORD size, void* data);
using GetDeviceDataFn = HRESULT(STDMETHODCALLTYPE*)(void* device, DWORD object_size, DIDEVICEOBJECTDATA* data,
                                                    DWORD* count, DWORD flags);
using CreateDeviceFn = HRESULT(STDMETHODCALLTYPE*)(void* input, REFGUID kind, void** device, IUnknown* outer);
using CreateDeviceExFn = HRESULT(STDMETHODCALLTYPE*)(void* input, REFGUID kind, REFIID iid, void** device,
                                                     IUnknown* outer);
using CreateInputFn = HRESULT(WINAPI*)(HINSTANCE instance, DWORD version, REFIID iid, void** input, IUnknown* outer);

constexpr int kReleaseIndex = 2;
constexpr int kCreateDeviceIndex = 3;
constexpr int kCreateDeviceExIndex = 9;  // IDirectInput7 only.
constexpr int kGetCapabilitiesIndex = 3;
constexpr int kGetDeviceStateIndex = 9;
constexpr int kGetDeviceDataIndex = 10;

// Device types: DirectInput 8 uses DI8DEVTYPE_*, versions 1-7 the older DIDEVTYPE_* values.
constexpr BYTE kMouse = 0x12;
constexpr BYTE kKeyboard = 0x13;
constexpr BYTE kOldMouse = 2;
constexpr BYTE kOldKeyboard = 3;

// Each device vtable (A and W, DirectInput 8 and 7) keeps its own original methods, reached by
// its own copy of the detours: a code hook sends every device of any vtable through the detour
// of the vtable that installed it, so the detours cannot look their original up by vtable.
struct HookedVtable {
    void** vtable = nullptr;
    GetDeviceStateFn get_device_state = nullptr;
    GetDeviceDataFn get_device_data = nullptr;
};
constexpr std::size_t kMaxVtables = 8;
HookedVtable g_hooked[kMaxVtables];
std::size_t g_hooked_count = 0;
std::mutex g_install_mutex;

enum class DeviceKind { other, keyboard, mouse };

DeviceKind device_kind(void* device) {
    DIDEVCAPS capabilities{};
    capabilities.dwSize = sizeof(capabilities);
    auto get_capabilities = function_at<GetCapabilitiesFn>(vtable_of(device)[kGetCapabilitiesIndex]);
    if (FAILED(get_capabilities(device, &capabilities))) {
        return DeviceKind::other;
    }
    BYTE type = LOBYTE(capabilities.dwDevType);
    if (type == kKeyboard || type == kOldKeyboard) {
        return DeviceKind::keyboard;
    }
    return type == kMouse || type == kOldMouse ? DeviceKind::mouse : DeviceKind::other;
}

HRESULT get_device_state(GetDeviceStateFn original, void* device, DWORD size, void* data) {
    HRESULT result = original(device, size, data);
    if (SUCCEEDED(result) && data != nullptr && app_input_blocked() && device_kind(device) != DeviceKind::other) {
        std::memset(data, 0, size);
    }
    return result;
}

// A release of a key or mouse button: the high bit of the event's data is clear.
bool is_release(DeviceKind kind, const DIDEVICEOBJECTDATA& event) {
    bool button = kind == DeviceKind::keyboard || (event.dwOfs >= DIMOFS_BUTTON0 && event.dwOfs <= DIMOFS_BUTTON7);
    return button && (event.dwData & 0x80) == 0;
}

// Events are still read, so they do not pile up and reach the app after the panel closes.
// Only releases are kept: a key held when the panel opened (such as the hotkey's) must not
// stay down for the app. Events are object_size bytes apart, since their size differs by version.
HRESULT get_device_data(GetDeviceDataFn original, void* device, DWORD object_size, DIDEVICEOBJECTDATA* data,
                        DWORD* count, DWORD flags) {
    HRESULT result = original(device, object_size, data, count, flags);
    // Without a buffer the call only counts waiting events (or flushes them); the count is left
    // as is, because apps such as GTA2 skip what they read when told nothing was waiting.
    if (FAILED(result) || count == nullptr || data == nullptr || !app_input_blocked()) {
        return result;
    }
    DeviceKind kind = device_kind(device);
    if (kind == DeviceKind::other) {
        return result;
    }
    BYTE* events = bytes_of(data);
    DWORD kept = 0;
    for (DWORD i = 0; i < *count; ++i) {
        BYTE* event = events + static_cast<std::size_t>(i) * object_size;
        if (is_release(kind, *object_at<const DIDEVICEOBJECTDATA>(event))) {
            std::memmove(events + static_cast<std::size_t>(kept) * object_size, event, object_size);
            ++kept;
        }
    }
    *count = kept;
    return result;
}

void release(void* object) {
    function_at<ReleaseFn>(vtable_of(object)[kReleaseIndex])(object);
}

template <std::size_t N>
HRESULT STDMETHODCALLTYPE get_device_state_detour(void* device, DWORD size, void* data) {
    return get_device_state(g_hooked[N].get_device_state, device, size, data);
}

template <std::size_t N>
HRESULT STDMETHODCALLTYPE get_device_data_detour(void* device, DWORD object_size, DIDEVICEOBJECTDATA* data,
                                                 DWORD* count, DWORD flags) {
    return get_device_data(g_hooked[N].get_device_data, device, object_size, data, count, flags);
}

template <std::size_t... N>
constexpr auto make_detours(std::index_sequence<N...>) {
    return std::pair{std::array<GetDeviceStateFn, kMaxVtables>{&get_device_state_detour<N>...},
                     std::array<GetDeviceDataFn, kMaxVtables>{&get_device_data_detour<N>...}};
}
constexpr auto kDetours = make_detours(std::make_index_sequence<kMaxVtables>());

void hook_device_vtable(void* device) {
    void** vtable = vtable_of(device);
    std::size_t count = g_hooked_count;
    for (std::size_t i = 0; i < count; ++i) {
        if (g_hooked[i].vtable == vtable) {
            return;
        }
    }
    if (count == kMaxVtables) {
        log_message("Too many DirectInput device types to hook");
        return;
    }
    // hook_method stores each original before anything can call the detour that uses it.
    HookedVtable& entry = g_hooked[count];
    entry.vtable = vtable;
    g_hooked_count = count + 1;
    if (!hook_method(vtable, kGetDeviceStateIndex, kDetours.first[count], &entry.get_device_state) ||
        !hook_method(vtable, kGetDeviceDataIndex, kDetours.second[count], &entry.get_device_data)) {
        log_message("Could not hook DirectInput device methods");
    }
}

// Devices share their class's vtable, so throwaway keyboard and mouse devices give us the
// app's, the same way the Direct3D hooks find theirs.
void hook_devices(void* input, const IID* device_iid) {
    for (const GUID* kind : {&GUID_SysKeyboard, &GUID_SysMouse}) {
        void* device = nullptr;
        auto create_device = function_at<CreateDeviceFn>(vtable_of(input)[kCreateDeviceIndex]);
        if (SUCCEEDED(create_device(input, *kind, &device, nullptr)) && device != nullptr) {
            hook_device_vtable(device);
            release(device);
        }
        if (device_iid == nullptr) {
            continue;
        }
        // DirectInput 7 can also hand out its newest device interface, in case its vtable differs.
        device = nullptr;
        auto create_device_ex = function_at<CreateDeviceExFn>(vtable_of(input)[kCreateDeviceExIndex]);
        if (SUCCEEDED(create_device_ex(input, *kind, *device_iid, &device, nullptr)) && device != nullptr) {
            hook_device_vtable(device);
            release(device);
        }
    }
}

bool hook_version(const wchar_t* module_name, const char* create_name, DWORD version,
                  std::initializer_list<std::pair<const IID*, const IID*>> interfaces) {
    HMODULE module = GetModuleHandleW(module_name);
    auto create = exported_function<CreateInputFn>(module, create_name);
    if (create == nullptr) {
        return false;
    }
    for (const auto& [input_iid, device_iid] : interfaces) {
        void* input = nullptr;
        if (SUCCEEDED(create(overlay_module(), version, *input_iid, &input, nullptr)) && input != nullptr) {
            hook_devices(input, device_iid);
            release(input);
        }
    }
    return true;
}

}  // namespace

void install_dinput_hooks() {
    std::scoped_lock lock(g_install_mutex);
    std::size_t before = g_hooked_count;
    bool dinput8 = hook_version(L"dinput8.dll", "DirectInput8Create", 0x0800,
                                {{&IID_IDirectInput8A, nullptr}, {&IID_IDirectInput8W, nullptr}});
    bool dinput = hook_version(
        L"dinput.dll", "DirectInputCreateEx", 0x0700,
        {{&IID_IDirectInput7A, &IID_IDirectInputDevice7A}, {&IID_IDirectInput7W, &IID_IDirectInputDevice7W}});
    if (g_hooked_count > before) {
        const char* versions = dinput8 && dinput ? "8 and 1-7" : dinput8 ? "8" : "1-7";
        log_message(std::string("Blocking keyboard and mouse input through DirectInput ") + versions +
                    " while the panel is open");
    }
}

}  // namespace reflektortts
