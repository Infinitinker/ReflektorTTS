// Finds the app's Direct3D 12 command queue on the swap chain's device, by hooking
// ID3D12CommandQueue::ExecuteCommandLists; the D3D12 renderer submits to that queue.

#include "hooks/d3d12_queue_hook.h"

#include <atomic>
#include <string>

#include "hooks/vtable_hook.h"
#include "log.h"

namespace reflektortts {
namespace {

using ExecuteCommandListsFn = void(STDMETHODCALLTYPE*)(ID3D12CommandQueue*, UINT, ID3D12CommandList* const*);

constexpr int kExecuteCommandListsIndex = 10;

ExecuteCommandListsFn g_original_execute_command_lists = nullptr;
// The device of the swap chain the overlay draws on, once the renderer has asked for a queue;
// only compared, never called.
std::atomic<ID3D12Device*> g_device = nullptr;
std::atomic<ID3D12CommandQueue*> g_queue = nullptr;

bool on_device(ID3D12CommandQueue* queue, ID3D12Device* device) {
    ID3D12Device* queue_device = nullptr;
    if (FAILED(queue->GetDevice(__uuidof(ID3D12Device), reinterpret_cast<void**>(&queue_device)))) {
        return false;
    }
    queue_device->Release();
    return queue_device == device;
}

// The hook sees the queues of every device in the process, e.g. a launcher's or a library's.
void STDMETHODCALLTYPE execute_command_lists_detour(ID3D12CommandQueue* queue, UINT count,
                                                    ID3D12CommandList* const* lists) {
    if (g_queue.load() == nullptr && queue->GetDesc().Type == D3D12_COMMAND_LIST_TYPE_DIRECT) {
        ID3D12Device* device = g_device.load();
        if (device == nullptr || on_device(queue, device)) {
            queue->AddRef();
            ID3D12CommandQueue* none = nullptr;
            if (!g_queue.compare_exchange_strong(none, queue)) {
                queue->Release();
            }
        }
    }
    g_original_execute_command_lists(queue, count, lists);
}

// Direct command queues share their class's vtable, so a throwaway queue gives us the app's.
void** find_command_queue_vtable() {
    HMODULE d3d12 = GetModuleHandleW(L"d3d12.dll");
    auto create = d3d12 == nullptr
                      ? nullptr
                      : reinterpret_cast<decltype(&D3D12CreateDevice)>(GetProcAddress(d3d12, "D3D12CreateDevice"));
    if (create == nullptr) {
        log_message("d3d12.dll is not loaded");
        return nullptr;
    }

    ID3D12Device* device = nullptr;
    HRESULT result = create(nullptr, D3D_FEATURE_LEVEL_11_0, __uuidof(ID3D12Device), reinterpret_cast<void**>(&device));
    if (FAILED(result)) {
        log_message("Could not create a probe D3D12 device (HRESULT " + std::to_string(result) + ")");
        return nullptr;
    }
    D3D12_COMMAND_QUEUE_DESC desc{};
    desc.Type = D3D12_COMMAND_LIST_TYPE_DIRECT;
    ID3D12CommandQueue* queue = nullptr;
    void** vtable = nullptr;
    if (SUCCEEDED(device->CreateCommandQueue(&desc, __uuidof(ID3D12CommandQueue), reinterpret_cast<void**>(&queue)))) {
        vtable = *reinterpret_cast<void***>(queue);
        queue->Release();
    } else {
        log_message("Could not create a probe D3D12 command queue");
    }
    device->Release();
    return vtable;
}

}  // namespace

bool install_d3d12_queue_hook() {
    void** vtable = find_command_queue_vtable();
    if (vtable == nullptr) {
        return false;
    }
    if (!hook_method(vtable, kExecuteCommandListsIndex, &execute_command_lists_detour,
                     &g_original_execute_command_lists)) {
        log_message("Could not hook ID3D12CommandQueue::ExecuteCommandLists");
        return false;
    }
    return true;
}

ID3D12CommandQueue* app_command_queue(ID3D12Device* device) {
    g_device.store(device);
    ID3D12CommandQueue* queue = g_queue.load();
    if (queue != nullptr && !on_device(queue, device)) {
        // Found before the device was known: let the hook look for one on the right device.
        log_message("The first Direct3D 12 command queue found belongs to another device; looking further");
        if (g_queue.compare_exchange_strong(queue, nullptr)) {
            queue->Release();
        }
        return nullptr;
    }
    return queue;
}

}  // namespace reflektortts
