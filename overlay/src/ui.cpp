#include "ui.h"

#include <imgui.h>

#include <cctype>
#include <cfloat>
#include <cmath>
#include <string>

#include "api_client.h"
#include "input.h"

namespace reflektortts {
namespace {

constexpr double kHintSeconds = 10.0;
constexpr float kPanelWidth = 420.0f;
constexpr float kHeaderFontSize = 20.0f;
constexpr int kMaxLastSpokenLines = 9;
constexpr char kAuto[] = "auto";
constexpr ImVec4 kErrorColor(1.0f, 0.45f, 0.4f, 1.0f);
constexpr ImVec4 kWarningColor(1.0f, 0.75f, 0.3f, 1.0f);
const ImU32 kGreen = IM_COL32(90, 200, 110, 255);
const ImU32 kAmber = IM_COL32(240, 180, 60, 255);
const ImU32 kGrey = IM_COL32(140, 140, 140, 255);

void draw_hint() {
    ImGui::SetNextWindowPos(ImVec2(10.0f, 10.0f));
    ImGui::SetNextWindowBgAlpha(0.6f);
    ImGui::Begin("##hint", nullptr,
                 ImGuiWindowFlags_NoDecoration | ImGuiWindowFlags_NoInputs | ImGuiWindowFlags_AlwaysAutoResize |
                     ImGuiWindowFlags_NoSavedSettings | ImGuiWindowFlags_NoFocusOnAppearing | ImGuiWindowFlags_NoNav);
    ImGui::TextUnformatted("ReflektorTTS: Ctrl+Shift+R opens settings");
    ImGui::End();
}

// A coloured dot followed by a label, on the current line.
void dot_label(ImU32 color, const char* label) {
    ImVec2 position = ImGui::GetCursorScreenPos();
    float radius = ImGui::GetFontSize() * 0.3f;
    float line = ImGui::GetTextLineHeight();
    ImGui::GetWindowDrawList()->AddCircleFilled(ImVec2(position.x + radius, position.y + line * 0.5f), radius, color);
    ImGui::Dummy(ImVec2(radius * 2.0f, line));
    ImGui::SameLine();
    ImGui::TextUnformatted(label);
}

float dot_label_width(const char* label) {
    return ImGui::GetFontSize() * 0.6f + ImGui::GetStyle().ItemSpacing.x + ImGui::CalcTextSize(label).x;
}

void align_right(float width) {
    ImGui::SameLine(ImGui::GetContentRegionMax().x - width);
}

// A bordered box whose height follows its contents.
void begin_box(const char* title) {
    ImGui::BeginChild(title, ImVec2(0.0f, 0.0f), ImGuiChildFlags_Borders | ImGuiChildFlags_AutoResizeY);
    ImGui::TextDisabled("%s", title);
}

void end_box() {
    ImGui::EndChild();
}

// Text wrapped to the box, cut after max_lines lines with "..." so the panel never grows past it.
void clamped_wrapped_text(const std::string& text, int max_lines) {
    ImFont* font = ImGui::GetFont();
    float size = ImGui::GetFontSize();
    float width = ImGui::GetContentRegionAvail().x;
    const char* start = text.c_str();
    const char* end = start + text.size();
    for (int line = 0; line < max_lines && start < end; ++line) {
        const char* line_end = font->CalcWordWrapPosition(size, start, end, width);
        if (line_end == start) {
            ++line_end;
        }
        std::string piece(start, line_end);
        if (line == max_lines - 1 && line_end < end) {
            while (!piece.empty() && ImGui::CalcTextSize((piece + "...").c_str()).x > width) {
                // Drop one UTF-8 character: its continuation bytes, then its first byte.
                while (!piece.empty() && (static_cast<unsigned char>(piece.back()) & 0xC0) == 0x80) {
                    piece.pop_back();
                }
                if (!piece.empty()) {
                    piece.pop_back();
                }
            }
            piece += "...";
        }
        ImGui::TextUnformatted(piece.c_str());
        start = line_end;
        while (start < end && (*start == ' ' || *start == '\n')) {
            ++start;
        }
    }
}

std::string language_name(const CoreState& state, const std::string& code) {
    if (code == kAuto) {
        return "Auto";
    }
    for (const LanguageOption& language : state.languages) {
        if (language.code == code) {
            return language.name;
        }
    }
    return code;
}

// The language part of a tag: "pl-PL" is "pl".
std::string primary_language(const std::string& tag) {
    return tag.substr(0, tag.find_first_of("-_"));
}

std::string engine_title(std::string engine) {
    if (!engine.empty()) {
        engine[0] = static_cast<char>(std::toupper(static_cast<unsigned char>(engine[0])));
    }
    return engine;
}

void draw_header(const CoreState& state) {
    ImGui::PushFont(nullptr, kHeaderFontSize);
    ImGui::TextUnformatted("ReflektorTTS");
    ImGui::PopFont();
    const char* connection = state.connected ? "Connected" : "Not connected";
    align_right(dot_label_width(connection));
    dot_label(state.connected ? kGreen : kGrey, connection);
    ImGui::Separator();
}

// The game being read, and whether reading is active or paused.
void draw_status(const CoreState& state) {
    ImGui::TextUnformatted(state.game.c_str());
    const char* reading = state.paused ? "Paused" : "Active";
    align_right(dot_label_width(reading));
    dot_label(state.paused ? kAmber : kGreen, reading);
}

// A small arrow between groups, showing which way text flows through the app.
void draw_flow_arrow() {
    float size = ImGui::GetFontSize() * 0.5f;
    ImVec2 top = ImGui::GetCursorScreenPos();
    float center = top.x + ImGui::GetContentRegionAvail().x * 0.5f;
    ImGui::GetWindowDrawList()->AddTriangleFilled(ImVec2(center - size, top.y), ImVec2(center + size, top.y),
                                                  ImVec2(center, top.y + size), ImGui::GetColorU32(ImGuiCol_TextDisabled));
    ImGui::Dummy(ImVec2(0.0f, size));
}

void draw_language_combo(const char* label, const CoreState& state, const std::string& current, bool with_auto,
                         void (*request)(const std::string&)) {
    if (!ImGui::BeginCombo(label, language_name(state, current).c_str())) {
        return;
    }
    if (with_auto && ImGui::Selectable("Auto##auto", current == kAuto) && current != kAuto) {
        request(kAuto);
    }
    for (const LanguageOption& language : state.languages) {
        bool selected = language.code == current;
        if (ImGui::Selectable((language.name + "##" + language.code).c_str(), selected) && !selected) {
            request(language.code);
        }
    }
    ImGui::EndCombo();
}

// Voices that speak the speech language, grouped by engine.
void draw_voice_combo(const CoreState& state) {
    std::string language = state.speech_language;
    bool any = false;
    for (const VoiceOption& voice : state.voices) {
        any = any || primary_language(voice.language) == language;
    }
    if (!any) {
        ImGui::BeginDisabled();
        if (ImGui::BeginCombo("Voice", "No voice for this language")) {
            ImGui::EndCombo();
        }
        ImGui::EndDisabled();
        ImGui::PushStyleColor(ImGuiCol_Text, kWarningColor);
        ImGui::TextWrapped("Add a %s voice in Windows Settings > Time & language > Speech, or download a Piper voice.",
                           language_name(state, language).c_str());
        ImGui::PopStyleColor();
        return;
    }
    if (!ImGui::BeginCombo("Voice", state.voice.c_str())) {
        return;
    }
    std::string engine;
    for (const VoiceOption& voice : state.voices) {
        if (primary_language(voice.language) != language) {
            continue;
        }
        if (voice.engine != engine) {
            engine = voice.engine;
            ImGui::TextDisabled("%s", engine_title(engine).c_str());
        }
        bool selected = voice.id == state.voice;
        ImGui::Indent();
        if (ImGui::Selectable((voice.id + "##" + voice.id).c_str(), selected) && !selected) {
            request_voice(voice.id);
        }
        ImGui::Unindent();
    }
    ImGui::EndCombo();
}

void draw_ducking(const CoreState& state) {
    bool ducking = state.ducking;
    if (ImGui::Checkbox("Lower game sound while speaking", &ducking)) {
        request_ducking(ducking);
    }
    // While dragging, the slider shows its own value; the core gets it on release.
    static int dragged_percent = -1;
    int percent = dragged_percent >= 0 ? dragged_percent : static_cast<int>(std::lround(state.duck_volume * 100.0f));
    ImGui::BeginDisabled(!state.ducking);
    if (ImGui::SliderInt("Game volume", &percent, 0, 100, "%d%%", ImGuiSliderFlags_AlwaysClamp)) {
        dragged_percent = percent;
    }
    if (ImGui::IsItemDeactivatedAfterEdit()) {
        request_duck_volume(static_cast<float>(percent) / 100.0f);
    }
    if (!ImGui::IsItemActive()) {
        dragged_percent = -1;
    }
    ImGui::EndDisabled();
}

// Where text comes from: the game's language and its sources, each of which can be switched off.
void draw_game(const CoreState& state) {
    begin_box("Game");
    draw_language_combo("Game language", state, state.game_language, true, request_game_language);
    for (const SourceStages& source : state.sources) {
        bool enabled = source.enabled;
        if (ImGui::Checkbox((source.source + "##source:" + source.source).c_str(), &enabled)) {
            request_source_enabled(source.source, enabled);
        }
        ImGui::SameLine();
        ImGui::TextDisabled("%s", source.type.c_str());
    }
    end_box();
}

// Where text goes: the language it is prepared in, and how it is spoken.
void draw_output(const CoreState& state) {
    begin_box("Output");
    draw_language_combo("Language", state, state.speech_language, false, request_speech_language);
    draw_voice_combo(state);
    draw_ducking(state);
    if (ImGui::Button(state.paused ? "Resume reading" : "Pause reading")) {
        request_paused(!state.paused);
    }
    ImGui::SameLine();
    if (ImGui::Button("Stop this line")) {
        request_stop_line();
    }
    end_box();
}

void draw_stage(const StageOption& stage) {
    bool enabled = stage.enabled;
    if (ImGui::Checkbox((stage.type + "##" + stage.key).c_str(), &enabled)) {
        request_stage_enabled(stage.key, enabled);
    }
    if (!stage.summary.empty()) {
        ImGui::SameLine();
        ImGui::TextDisabled("%s", stage.summary.c_str());
    }
    if (!stage.enabled && stage.warning) {
        ImGui::PushStyleColor(ImGuiCol_Text, kWarningColor);
        ImGui::TextWrapped("%s", stage.warning->c_str());
        ImGui::PopStyleColor();
    }
}

void draw_text_processing(const CoreState& state) {
    begin_box("Text processing");
    // Source names matter only when a game has more than one source.
    bool headings = state.sources.size() > 1;
    for (const SourceStages& source : state.sources) {
        // A switched-off source's stages stay visible, greyed out, and keep their own state.
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

void draw_last_spoken(const CoreState& state) {
    begin_box("Last spoken");
    if (state.last_line.empty()) {
        ImGui::TextDisabled("-");
    } else {
        clamped_wrapped_text(state.last_line, kMaxLastSpokenLines);
    }
    end_box();
}

void draw_footer(const CoreState& state) {
    if (!state.last_error.empty()) {
        ImGui::PushStyleColor(ImGuiCol_Text, kErrorColor);
        ImGui::PushTextWrapPos(ImGui::GetContentRegionMax().x - ImGui::GetFrameHeight() * 1.5f);
        ImGui::TextWrapped("%s", state.last_error.c_str());
        ImGui::PopTextWrapPos();
        ImGui::PopStyleColor();
        align_right(ImGui::GetFrameHeight());
        if (ImGui::SmallButton("x")) {
            dismiss_error();
        }
    }
    ImGui::TextDisabled("Ctrl+Shift+R closes this panel");
}

void draw_panel(const CoreState& state) {
    ImGui::SetNextWindowPos(ImVec2(20.0f, 20.0f), ImGuiCond_FirstUseEver);
    ImGui::SetNextWindowSizeConstraints(ImVec2(kPanelWidth, 0.0f), ImVec2(kPanelWidth, FLT_MAX));
    ImGui::Begin("ReflektorTTS", nullptr,
                 ImGuiWindowFlags_NoTitleBar | ImGuiWindowFlags_NoCollapse | ImGuiWindowFlags_NoSavedSettings |
                     ImGuiWindowFlags_AlwaysAutoResize);
    draw_header(state);
    if (!state.connected) {
        ImGui::TextWrapped("Not connected to ReflektorTTS. Is it running?");
    } else {
        // Top to bottom, the way a line goes through the app: game, processing, output.
        draw_status(state);
        draw_game(state);
        draw_flow_arrow();
        draw_text_processing(state);
        draw_flow_arrow();
        draw_output(state);
        draw_last_spoken(state);
    }
    draw_footer(state);
    ImGui::End();
}

}  // namespace

void draw_ui() {
    if (panel_open()) {
        draw_panel(core_state());
    } else if (ImGui::GetTime() < kHintSeconds) {
        draw_hint();
    }
}

}  // namespace reflektortts
