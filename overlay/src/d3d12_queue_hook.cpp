#include "d3d12_queue_hook.h"

#include <atomic>
#include <string>

#include "log.h"
#include "vtable_hook.h"

namespace reflektortts {
namespace {

using ExecuteCommandListsFn = void(STDMETHODCALLTYPE*)(ID3D12CommandQueue*, UINT, ID3D12CommandList* const*);

constexpr int kExecuteCommandListsIndex = 10;

ExecuteCommandListsFn g_original_execute_command_lists = nullptr;
std::atomic<ID3D12CommandQueue*> g_queue = nullptr;

void STDMETHODCALLTYPE execute_command_lists_detour(ID3D12CommandQueue* queue, UINT count,
                                                    ID3D12CommandList* const* lists) {
    if (g_queue.load() == nullptr && queue->GetDesc().Type == D3D12_COMMAND_LIST_TYPE_DIRECT) {
        queue->AddRef();
        g_queue.store(queue);
    }
    g_original_execute_command_lists(queue, count, lists);
}

// Direct command queues share their class's vtable, so a throwaway queue gives us the app's.
void** find_command_queue_vtable() {
    HMODULE d3d12 = GetModuleHandleW(L"d3d12.dll");
    auto create = d3d12 == nullptr ? nullptr
                                   : reinterpret_cast<decltype(&D3D12CreateDevice)>(
                                         GetProcAddress(d3d12, "D3D12CreateDevice"));
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

ID3D12CommandQueue* app_command_queue() {
    return g_queue.load();
}

}  // namespace reflektortts
