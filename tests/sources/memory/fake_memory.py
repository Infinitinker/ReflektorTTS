"""An in-memory ProcessMemory for tests."""


class FakeMemory:
    def __init__(self, regions: dict[int, bytes], modules: dict[str, int], pointer_size: int = 4) -> None:
        self.pointer_size = pointer_size
        self.closed = False
        self._regions = regions
        self._modules = modules

    def read(self, address: int, size: int) -> bytes:
        for start, data in self._regions.items():
            if start <= address < start + len(data):
                return data[address - start : address - start + size]
        return b""

    def module_base(self, name: str) -> int | None:
        return self._modules.get(name.lower())

    def close(self) -> None:
        self.closed = True
