// The settings panel's Processing box: each stage of the profile, grouped by source, with a tick
// for the text shown and one for speech, and a few words on what it does, or why it does nothing
// with the chosen languages, or that reading needs it while it is off.

#include "processing_section.h"

#include <imgui.h>

#include <algorithm>
#include <string>

#include "api_client.h"
#include "text_fit.h"
#include "widgets.h"

namespace reflektortts {
namespace {

// The tick columns at the right of the Processing box: one for the text shown, one for speech.
// Each is as wide as its heading, which sits on the box's title line.
constexpr const char* kTextHeading = "Text";
constexpr const char* kSpeechHeading = "Speech";

float tick_column_width(const char* heading) {
    return std::max(ImGui::CalcTextSize(heading).x, ImGui::GetFrameHeight());
}

float tick_columns_width() {
    return tick_column_width(kTextHeading) + ImGui::GetStyle().ItemSpacing.x + tick_column_width(kSpeechHeading);
}

// Where the tick columns start, from the window's left edge.
float tick_columns_x() {
    return ImGui::GetContentRegionMax().x - tick_columns_width();
}

void draw_tick_headings() {
    float x = tick_columns_x();
    for (const char* heading : {kTextHeading, kSpeechHeading}) {
        float width = tick_column_width(heading);
        ImGui::SameLine(x + (width - ImGui::CalcTextSize(heading).x) * 0.5f);
        ImGui::TextDisabled("%s", heading);
        x += width + ImGui::GetStyle().ItemSpacing.x;
    }
}

// The words after a stage's name: why it does nothing, else its warning while it is off for
// either output, else its summary. Always on the stage's own line, so the panel keeps its height;
// text too long to fit before the ticks is cut and shown whole on hover.
void draw_stage_note(const StageOption& stage) {
    const std::string* note = &stage.summary;
    ImVec4 color = ImGui::GetStyleColorVec4(ImGuiCol_TextDisabled);
    if (stage.inactive) {
        note = &*stage.inactive;
    } else if ((!stage.text || !stage.speech) && stage.warning) {
        note = &*stage.warning;
        color = kWarningColor;
    }
    if (note->empty()) {
        return;
    }
    ImGui::SameLine();
    float width = tick_columns_x() - ImGui::GetCursorPosX() - ImGui::GetStyle().ItemSpacing.x;
    std::string shown = fit_width(*note, width);
    ImGui::TextColored(color, "%s", shown.c_str());
    if (shown != *note && ImGui::IsItemHovered(ImGuiHoveredFlags_AllowWhenDisabled)) {
        ImGui::SetTooltip("%s", note->c_str());
    }
}

// A stage's ticks, each centered under its column's heading.
void draw_stage_ticks(const StageOption& stage) {
    struct Tick {
        const char* heading;
        StageOutput output;
        bool on;
    };
    const Tick ticks[] = {{kTextHeading, StageOutput::Text, stage.text},
                          {kSpeechHeading, StageOutput::Speech, stage.speech}};
    float x = tick_columns_x();
    for (const Tick& tick : ticks) {
        float width = tick_column_width(tick.heading);
        ImGui::SameLine(x + (width - ImGui::GetFrameHeight()) * 0.5f);
        bool on = tick.on;
        if (ImGui::Checkbox(("##" + std::string(tick.heading) + ":" + stage.key).c_str(), &on)) {
            request_stage_enabled(stage.key, tick.output, on);
        }
        x += width + ImGui::GetStyle().ItemSpacing.x;
    }
}

void draw_stage(const StageOption& stage) {
    // A stage that does nothing with the user's languages is grayed out but keeps its ticks, so
    // it works again as soon as the languages allow. Its reason is not faded, to stay readable.
    ImGui::BeginDisabled(stage.inactive.has_value());
    ImGui::AlignTextToFramePadding();
    ImGui::TextUnformatted(stage.type.c_str());
    ImGui::EndDisabled();
    draw_stage_note(stage);
    ImGui::BeginDisabled(stage.inactive.has_value());
    draw_stage_ticks(stage);
    ImGui::EndDisabled();
}

}  // namespace

void draw_processing(const ProfileSettings& settings) {
    begin_box("Processing");
    draw_tick_headings();
    // Source names matter only when an app has more than one source.
    bool headings = settings.sources.size() > 1;
    for (const SourceStages& source : settings.sources) {
        // A switched-off source's stages stay visible, grayed out, and keep their own state.
        ImGui::BeginDisabled(!source.enabled);
        if (headings) {
            ImGui::TextUnformatted(source.source.c_str());
            ImGui::Indent();
        }
        for (const StageOption& stage : source.stages) {
            draw_stage(stage);
        }
        if (headings) {
            ImGui::Unindent();
        }
        ImGui::EndDisabled();
    }
    end_box();
}

}  // namespace reflektortts
