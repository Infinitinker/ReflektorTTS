// Windows' structs with every field zero, to be filled in before they are read.

#pragma once

namespace reflektortts {

// A struct with every field zero: for one the caller fills in, or one a Windows call fills in. Zero
// is not a value of some of the enums in such structs (Direct3D 9's swap effect and device type), so
// each of those must be set before the struct is read.
template <typename T>
T zeroed() {
    // NOLINTNEXTLINE(bugprone-invalid-enum-default-initialization)
    return T{};
}

}  // namespace reflektortts
