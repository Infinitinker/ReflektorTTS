// Sets up ImGui on the app's Direct3D 12 device and draws each frame on the swap chain's back
// buffer, recording its own command list and submitting it to the app's command queue.

#include "renderers/d3d12_renderer.h"

#include <d3d12.h>
#include <dxgi1_4.h>
#include <imgui.h>
#include <imgui_impl_dx12.h>

#include <array>
#include <utility>

#include "hooks/d3d12_queue_hook.h"
#include "log.h"
#include "renderers/overlay_frame.h"

namespace reflektortts {
namespace {

enum class State { NotStarted, Running, Disabled };

// Per back buffer index: the allocator the overlay records with and the fence value
// that tells when the GPU has finished with it.
struct FrameSlot {
    ID3D12CommandAllocator* allocator = nullptr;
    UINT64 fence_value = 0;
};

constexpr UINT kMaxBackBuffers = DXGI_MAX_SWAP_CHAIN_BUFFERS;
// ImGui needs one descriptor per texture; the font atlas is its only texture.
constexpr UINT kSrvDescriptorCount = 16;

State g_state = State::NotStarted;
IDXGISwapChain* g_swap_chain = nullptr;
ID3D12Device* g_device = nullptr;
ID3D12CommandQueue* g_queue = nullptr;
ID3D12DescriptorHeap* g_srv_heap = nullptr;
UINT g_free_srv_slots[kSrvDescriptorCount];
UINT g_free_srv_count = 0;
// How many of ImGui's textures use each descriptor: one, or more for the first once all are taken.
// A descriptor goes back on the free list when its last texture is freed, so the list never holds
// one twice and never outgrows the heap.
std::array<UINT, kSrvDescriptorCount> g_srv_users{};
ID3D12DescriptorHeap* g_rtv_heap = nullptr;
ID3D12GraphicsCommandList* g_command_list = nullptr;
ID3D12Fence* g_fence = nullptr;
HANDLE g_fence_event = nullptr;
UINT64 g_last_fence_value = 0;
FrameSlot g_slots[kMaxBackBuffers];
// The back buffer format ImGui's pipeline draws to.
DXGI_FORMAT g_format = DXGI_FORMAT_UNKNOWN;

UINT srv_descriptor_size() {
    return g_device->GetDescriptorHandleIncrementSize(D3D12_DESCRIPTOR_HEAP_TYPE_CBV_SRV_UAV);
}

void allocate_srv(ImGui_ImplDX12_InitInfo*, D3D12_CPU_DESCRIPTOR_HANDLE* cpu, D3D12_GPU_DESCRIPTOR_HANDLE* gpu) {
    UINT slot = 0;
    if (g_free_srv_count == 0) {
        log_message("Out of D3D12 texture descriptors; sharing the first one");
    } else {
        slot = g_free_srv_slots[--g_free_srv_count];
    }
    ++g_srv_users[slot];
    cpu->ptr = g_srv_heap->GetCPUDescriptorHandleForHeapStart().ptr + static_cast<SIZE_T>(slot) * srv_descriptor_size();
    gpu->ptr = g_srv_heap->GetGPUDescriptorHandleForHeapStart().ptr + static_cast<UINT64>(slot) * srv_descriptor_size();
}

void free_srv(ImGui_ImplDX12_InitInfo*, D3D12_CPU_DESCRIPTOR_HANDLE cpu, D3D12_GPU_DESCRIPTOR_HANDLE) {
    SIZE_T slot = (cpu.ptr - g_srv_heap->GetCPUDescriptorHandleForHeapStart().ptr) / srv_descriptor_size();
    if (slot >= kSrvDescriptorCount || g_srv_users[slot] == 0) {
        log_message("ImGui freed a D3D12 texture descriptor the overlay did not give out; ignoring it");
        return;
    }
    if (--g_srv_users[slot] == 0) {
        g_free_srv_slots[g_free_srv_count++] = static_cast<UINT>(slot);
    }
}

void wait_for_fence(UINT64 value) {
    if (g_fence->GetCompletedValue() < value) {
        g_fence->SetEventOnCompletion(value, g_fence_event);
        WaitForSingleObject(g_fence_event, INFINITE);
    }
}

bool create_heap(D3D12_DESCRIPTOR_HEAP_TYPE type, UINT count, D3D12_DESCRIPTOR_HEAP_FLAGS flags,
                 ID3D12DescriptorHeap** heap) {
    D3D12_DESCRIPTOR_HEAP_DESC desc{};
    desc.Type = type;
    desc.NumDescriptors = count;
    desc.Flags = flags;
    return SUCCEEDED(
        g_device->CreateDescriptorHeap(&desc, __uuidof(ID3D12DescriptorHeap), reinterpret_cast<void**>(heap)));
}

bool init_imgui(DXGI_FORMAT format) {
    ImGui_ImplDX12_InitInfo info;
    info.Device = g_device;
    info.CommandQueue = g_queue;
    info.NumFramesInFlight = static_cast<int>(kMaxBackBuffers);
    info.RTVFormat = format;
    info.DSVFormat = DXGI_FORMAT_UNKNOWN;
    info.SrvDescriptorHeap = g_srv_heap;
    info.SrvDescriptorAllocFn = allocate_srv;
    info.SrvDescriptorFreeFn = free_srv;
    g_format = format;
    return ImGui_ImplDX12_Init(&info);
}

bool create_device_objects(DXGI_FORMAT format) {
    if (!create_heap(D3D12_DESCRIPTOR_HEAP_TYPE_CBV_SRV_UAV, kSrvDescriptorCount,
                     D3D12_DESCRIPTOR_HEAP_FLAG_SHADER_VISIBLE, &g_srv_heap) ||
        !create_heap(D3D12_DESCRIPTOR_HEAP_TYPE_RTV, kMaxBackBuffers, D3D12_DESCRIPTOR_HEAP_FLAG_NONE, &g_rtv_heap)) {
        return false;
    }
    for (UINT slot = kSrvDescriptorCount; slot > 0; --slot) {
        g_free_srv_slots[g_free_srv_count++] = slot - 1;
    }
    for (FrameSlot& slot : g_slots) {
        if (FAILED(g_device->CreateCommandAllocator(D3D12_COMMAND_LIST_TYPE_DIRECT, __uuidof(ID3D12CommandAllocator),
                                                    reinterpret_cast<void**>(&slot.allocator)))) {
            return false;
        }
    }
    if (FAILED(g_device->CreateCommandList(0, D3D12_COMMAND_LIST_TYPE_DIRECT, g_slots[0].allocator, nullptr,
                                           __uuidof(ID3D12GraphicsCommandList),
                                           reinterpret_cast<void**>(&g_command_list))) ||
        FAILED(g_device->CreateFence(0, D3D12_FENCE_FLAG_NONE, __uuidof(ID3D12Fence),
                                     reinterpret_cast<void**>(&g_fence)))) {
        return false;
    }
    g_command_list->Close();
    g_fence_event = CreateEventW(nullptr, FALSE, FALSE, nullptr);
    return g_fence_event != nullptr && init_imgui(format);
}

// Apps change the back buffer format, e.g. when HDR is turned on, and ImGui's pipeline draws
// to one format only, so it is made again for the new one once the GPU is done with the old.
bool follow_format(DXGI_FORMAT format) {
    if (format == g_format) {
        return true;
    }
    log_message("The app changed its Direct3D 12 back buffer format; recreating the overlay's pipeline");
    wait_for_fence(g_last_fence_value);
    ImGui_ImplDX12_Shutdown();
    return init_imgui(format);
}

void start(IDXGISwapChain* swap_chain) {
    ID3D12Device* device = nullptr;
    if (FAILED(swap_chain->GetDevice(__uuidof(ID3D12Device), reinterpret_cast<void**>(&device)))) {
        return;
    }
    // The overlay's drawing goes through the app's queue, which is known only once
    // the app has submitted work to it.
    ID3D12CommandQueue* queue = app_command_queue(device);
    if (queue == nullptr) {
        device->Release();
        return;
    }
    DXGI_SWAP_CHAIN_DESC desc{};
    swap_chain->GetDesc(&desc);
    if (!claim_overlay("Direct3D 12", desc.OutputWindow)) {
        device->Release();
        g_state = State::Disabled;
        return;
    }
    g_swap_chain = swap_chain;
    g_device = device;
    g_queue = queue;
    if (!create_device_objects(desc.BufferDesc.Format)) {
        log_message("Direct3D 12 overlay setup failed; overlay disabled");
        g_state = State::Disabled;
        return;
    }
    g_state = State::Running;
}

// Whether the swap chain belongs to the device the overlay draws with. A swap chain the app
// recreates, with a new device, can get the address of the one it freed, so the address alone
// does not tell.
bool on_our_device(IDXGISwapChain* swap_chain) {
    ID3D12Device* device = nullptr;
    if (FAILED(swap_chain->GetDevice(__uuidof(ID3D12Device), reinterpret_cast<void**>(&device)))) {
        return false;
    }
    device->Release();
    return device == g_device;
}

// Apps replace their swap chain, e.g. when switching from the menu to gameplay, so the
// overlay follows the swap chain that presented last. Moving to another device is not
// supported yet; the old one is abandoned, never released (see forget_renderer_backend).
void switch_swap_chain(IDXGISwapChain* swap_chain) {
    ID3D12Device* device = nullptr;
    if (FAILED(swap_chain->GetDevice(__uuidof(ID3D12Device), reinterpret_cast<void**>(&device)))) {
        return;
    }
    device->Release();
    if (device != g_device) {
        log_message("The app moved to another Direct3D 12 device; overlay disabled");
        g_state = State::Disabled;
        return;
    }
    DXGI_SWAP_CHAIN_DESC desc{};
    swap_chain->GetDesc(&desc);
    set_overlay_window(desc.OutputWindow);
    g_swap_chain = swap_chain;
}

// The back buffer is taken per frame so the overlay never keeps the app's buffers alive.
ID3D12Resource* current_back_buffer(IDXGISwapChain* swap_chain, UINT& index) {
    IDXGISwapChain3* swap_chain3 = nullptr;
    if (FAILED(swap_chain->QueryInterface(__uuidof(IDXGISwapChain3), reinterpret_cast<void**>(&swap_chain3)))) {
        return nullptr;
    }
    index = swap_chain3->GetCurrentBackBufferIndex();
    swap_chain3->Release();
    ID3D12Resource* back_buffer = nullptr;
    if (index >= kMaxBackBuffers ||
        FAILED(swap_chain->GetBuffer(index, __uuidof(ID3D12Resource), reinterpret_cast<void**>(&back_buffer)))) {
        return nullptr;
    }
    return back_buffer;
}

}  // namespace

void render_d3d12_frame(IDXGISwapChain* swap_chain) {
    if (g_state == State::NotStarted) {
        start(swap_chain);
    } else if (g_state == State::Running && (swap_chain != g_swap_chain || !on_our_device(swap_chain))) {
        switch_swap_chain(swap_chain);
    }
    if (g_state != State::Running || swap_chain != g_swap_chain) {
        return;
    }
    UINT index = 0;
    ID3D12Resource* back_buffer = current_back_buffer(swap_chain, index);
    if (back_buffer == nullptr) {
        return;
    }
    D3D12_RESOURCE_DESC desc = back_buffer->GetDesc();
    if (!follow_format(desc.Format)) {
        log_message("Direct3D 12 overlay setup failed; overlay disabled");
        g_state = State::Disabled;
        back_buffer->Release();
        return;
    }
    FrameSlot& slot = g_slots[index];
    wait_for_fence(slot.fence_value);
    slot.allocator->Reset();
    g_command_list->Reset(slot.allocator, nullptr);

    D3D12_CPU_DESCRIPTOR_HANDLE target = g_rtv_heap->GetCPUDescriptorHandleForHeapStart();
    target.ptr +=
        static_cast<SIZE_T>(index) * g_device->GetDescriptorHandleIncrementSize(D3D12_DESCRIPTOR_HEAP_TYPE_RTV);
    g_device->CreateRenderTargetView(back_buffer, nullptr, target);

    ImGui_ImplDX12_NewFrame();
    build_overlay_frame(static_cast<UINT>(desc.Width), desc.Height);

    D3D12_RESOURCE_BARRIER barrier{};
    barrier.Type = D3D12_RESOURCE_BARRIER_TYPE_TRANSITION;
    barrier.Transition.pResource = back_buffer;
    barrier.Transition.Subresource = D3D12_RESOURCE_BARRIER_ALL_SUBRESOURCES;
    barrier.Transition.StateBefore = D3D12_RESOURCE_STATE_PRESENT;
    barrier.Transition.StateAfter = D3D12_RESOURCE_STATE_RENDER_TARGET;
    g_command_list->ResourceBarrier(1, &barrier);
    g_command_list->OMSetRenderTargets(1, &target, FALSE, nullptr);
    g_command_list->SetDescriptorHeaps(1, &g_srv_heap);
    ImGui_ImplDX12_RenderDrawData(ImGui::GetDrawData(), g_command_list);
    std::swap(barrier.Transition.StateBefore, barrier.Transition.StateAfter);
    g_command_list->ResourceBarrier(1, &barrier);
    g_command_list->Close();

    ID3D12CommandList* lists[] = {g_command_list};
    g_queue->ExecuteCommandLists(1, lists);
    g_queue->Signal(g_fence, ++g_last_fence_value);
    slot.fence_value = g_last_fence_value;
    back_buffer->Release();
}

}  // namespace reflektortts
