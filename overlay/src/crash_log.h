#pragma once

namespace reflektortts {

// Logs the first few crashes in the game's process (access violations and the like) with the
// module and offset they happened at, so a crash the overlay may cause can be traced from the log.
// The game's own error handling still runs afterwards.
void install_crash_log();

}  // namespace reflektortts
