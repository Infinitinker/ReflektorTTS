"""ProcessMemory for Windows, through ReadProcessMemory. Works on 32-bit apps from 64-bit Python."""

import ctypes
import sys
from ctypes import wintypes

from reflektortts.process_memory.memory import ProcessMemoryError

assert sys.platform == "win32"

PROCESS_VM_READ = 0x0010
PROCESS_QUERY_INFORMATION = 0x0400
LIST_MODULES_ALL = 0x03
PAGE_SIZE = 0x1000
MAX_MODULE_NAME = 260

_kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
_psapi = ctypes.WinDLL("psapi", use_last_error=True)

_kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
_kernel32.OpenProcess.restype = wintypes.HANDLE
_kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
_kernel32.CloseHandle.restype = wintypes.BOOL
_kernel32.IsWow64Process.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.BOOL)]
_kernel32.IsWow64Process.restype = wintypes.BOOL
_kernel32.ReadProcessMemory.argtypes = [
    wintypes.HANDLE,
    wintypes.LPCVOID,
    wintypes.LPVOID,
    ctypes.c_size_t,
    ctypes.POINTER(ctypes.c_size_t),
]
_kernel32.ReadProcessMemory.restype = wintypes.BOOL
_psapi.EnumProcessModulesEx.argtypes = [
    wintypes.HANDLE,
    ctypes.POINTER(ctypes.c_void_p),
    wintypes.DWORD,
    ctypes.POINTER(wintypes.DWORD),
    wintypes.DWORD,
]
_psapi.EnumProcessModulesEx.restype = wintypes.BOOL
_psapi.GetModuleBaseNameW.argtypes = [wintypes.HANDLE, ctypes.c_void_p, wintypes.LPWSTR, wintypes.DWORD]
_psapi.GetModuleBaseNameW.restype = wintypes.DWORD


class WindowsProcessMemory:
    def __init__(self, pid: int) -> None:
        handle = _kernel32.OpenProcess(PROCESS_QUERY_INFORMATION | PROCESS_VM_READ, False, pid)
        if not handle:
            raise ProcessMemoryError(
                f"Cannot open the app’s process (Windows error {ctypes.get_last_error()}). "
                "If the app runs as administrator, run ReflektorTTS as administrator too."
            )
        self._handle = handle
        wow64 = wintypes.BOOL()
        _kernel32.IsWow64Process(handle, ctypes.byref(wow64))
        self.pointer_size = 4 if wow64.value else ctypes.sizeof(ctypes.c_void_p)
        self._modules: dict[str, int] = {}

    def read(self, address: int, size: int) -> bytes:
        data = self._read_exactly(address, size)
        # A read can fail as a whole if any page in it is unreadable; text near the end of
        # a region still fits in the pages up to that end.
        until_page_end = PAGE_SIZE - address % PAGE_SIZE
        if not data and until_page_end < size:
            data = self._read_exactly(address, until_page_end)
        return data

    def module_base(self, name: str) -> int | None:
        key = name.lower()
        if key not in self._modules:
            self._modules = self._list_modules()
        return self._modules.get(key)

    def close(self) -> None:
        if self._handle:
            _kernel32.CloseHandle(self._handle)
            self._handle = None

    def _read_exactly(self, address: int, size: int) -> bytes:
        buffer = ctypes.create_string_buffer(size)
        count = ctypes.c_size_t()
        # On a partial copy the call fails but count still says how much was copied.
        _kernel32.ReadProcessMemory(self._handle, address, buffer, size, ctypes.byref(count))
        return buffer.raw[: count.value]

    def _list_modules(self) -> dict[str, int]:
        slots = 256
        while True:
            handles = (ctypes.c_void_p * slots)()
            needed = wintypes.DWORD()
            if not _psapi.EnumProcessModulesEx(
                self._handle, handles, ctypes.sizeof(handles), ctypes.byref(needed), LIST_MODULES_ALL
            ):
                raise ProcessMemoryError(
                    f"Cannot list the app’s modules (Windows error {ctypes.get_last_error()}). "
                    "The app may still be starting; try again in a moment."
                )
            if needed.value <= ctypes.sizeof(handles):
                break
            slots = needed.value // ctypes.sizeof(ctypes.c_void_p)

        modules: dict[str, int] = {}
        name = ctypes.create_unicode_buffer(MAX_MODULE_NAME)
        for base in handles[: needed.value // ctypes.sizeof(ctypes.c_void_p)]:
            if base and _psapi.GetModuleBaseNameW(self._handle, base, name, MAX_MODULE_NAME):
                modules.setdefault(name.value.lower(), base)
        return modules
