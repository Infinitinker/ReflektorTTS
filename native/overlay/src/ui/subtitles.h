// The subtitles drawn over the app, under the panel, from the current line and the subtitle
// settings.

#pragma once

#include "core_state.h"

namespace reflektortts {

// The current subtitle, centered at the top or bottom of the screen on a dark band. It is drawn
// on the background layer: over the app, under the panel, and never taking input.
void draw_subtitle(const CoreState& state);

}  // namespace reflektortts
