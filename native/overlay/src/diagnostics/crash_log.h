// Installs the crash log, which logs where the app crashed, so a crash the overlay may cause can
// be traced from the log.

#pragma once

namespace reflektortts {

// Logs the first few crashes in the app's process (access violations and the like) with the
// module and offset they happened at, so a crash the overlay may cause can be traced from the log.
// The app's own error handling still runs afterwards.
void install_crash_log();

}  // namespace reflektortts
