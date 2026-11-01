#include "ui.h"

#include <imgui.h>

#include <algorithm>
#include <cctype>
#include <cfloat>
#include <cmath>
#include <cstddef>
#include <string>
#include <vector>

#include "api_client.h"
#include "input.h"

namespace reflektortts {
namespace {

constexpr double kHintSeconds = 10.0;
constexpr float kPanelWidth = 420.0f;
constexpr float kHeaderFontSize = 20.0f;
constexpr int kMaxLastLineRows = 9;
constexpr float kSubtitleWidth = 0.7f;   // Of the screen's width.
constexpr float kSubtitleMargin = 0.05f;  // Of the screen's height, from its top or bottom edge.
constexpr float kMinSubtitleFontSize = 16.0f;

// A setting's value as the core knows it, and its name in the panel.
struct Choice {
    const char* value;
    const char* name;
};
constexpr Choice kSubtitleSizes[] = {{"small", "Small"}, {"medium", "Medium"}, {"large", "Large"}};
constexpr Choice kSubtitlePositions[] = {{"top", "Top"}, {"bottom", "Bottom"}};
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

// Splits text into lines no wider than width in the given font and size, breaking between words.
std::vector<std::string> wrap_lines(ImFont* font, float size, const std::string& text, float width) {
    std::vector<std::string> lines;
    const char* start = text.c_str();
    const char* end = start + text.size();
    while (start < end) {
        const char* line_end = font->CalcWordWrapPosition(size, start, end, width);
        if (line_end == start) {
            ++line_end;
        }
        lines.emplace_back(start, line_end);
        start = line_end;
        while (start < end && (*start == ' ' || *start == '\n')) {
            ++start;
        }
    }
    return lines;
}

// Text wrapped to the box, cut after max_lines lines with "..." so the panel never grows past it.
void clamped_wrapped_text(const std::string& text, int max_lines) {
    float width = ImGui::GetContentRegionAvail().x;
    std::vector<std::string> lines = wrap_lines(ImGui::GetFont(), ImGui::GetFontSize(), text, width);
    if (lines.size() > static_cast<std::size_t>(max_lines)) {
        lines.resize(max_lines);
        std::string& last = lines.back();
        while (!last.empty() && ImGui::CalcTextSize((last + "...").c_str()).x > width) {
            // Drop one UTF-8 character: its continuation bytes, then its first byte.
            while (!last.empty() && (static_cast<unsigned char>(last.back()) & 0xC0) == 0x80) {
                last.pop_back();
            }
            if (!last.empty()) {
                last.pop_back();
            }
        }
        last += "...";
    }
    for (const std::string& line : lines) {
        ImGui::TextUnformatted(line.c_str());
    }
}

float subtitle_font_size(const std::string& size, float screen_height) {
    float share = size == "small" ? 0.03f : size == "large" ? 0.05f : 0.04f;
    return std::max(kMinSubtitleFontSize, screen_height * share);
}

// The current subtitle, centred at the top or bottom of the screen on a dark band. It is drawn
// on the background layer: over the game, under the panel, and never taking input.
void draw_subtitle(const CoreState& state) {
    if (state.subtitle.empty()) {
        return;
    }
    const ImGuiViewport* viewport = ImGui::GetMainViewport();
    ImFont* font = ImGui::GetFont();
    float size = subtitle_font_size(state.subtitle_size, viewport->Size.y);
    std::vector<std::string> lines = wrap_lines(font, size, state.subtitle, viewport->Size.x * kSubtitleWidth);
    std::vector<float> widths;
    float widest = 0.0f;
    for (const std::string& line : lines) {
        widths.push_back(font->CalcTextSizeA(size, FLT_MAX, 0.0f, line.c_str()).x);
        widest = std::max(widest, widths.back());
    }
    ImVec2 padding(size * 0.5f, size * 0.25f);
    ImVec2 band(widest + padding.x * 2.0f, size * static_cast<float>(lines.size()) + padding.y * 2.0f);
    float margin = viewport->Size.y * kSubtitleMargin;
    float x = viewport->Pos.x + (viewport->Size.x - band.x) * 0.5f;
    float y = state.subtitle_position == "bottom" ? viewport->Pos.y + viewport->Size.y - margin - band.y
                                                  : viewport->Pos.y + margin;
    ImDrawList* draw = ImGui::GetBackgroundDrawList();
    draw->AddRectFilled(ImVec2(x, y), ImVec2(x + band.x, y + band.y), IM_COL32(0, 0, 0, 160), size * 0.25f);
    for (std::size_t i = 0; i < lines.size(); ++i) {
        ImVec2 position(x + padding.x + (widest - widths[i]) * 0.5f, y + padding.y + size * static_cast<float>(i));
        draw->AddText(font, size, position, IM_COL32(255, 255, 255, 255), lines[i].c_str());
    }
}

// Indents the controls that follow, narrowed by the indent so their labels still line up with the rest.
void begin_indented() {
    ImGui::Indent();
    ImGui::PushItemWidth(ImGui::CalcItemWidth() - ImGui::GetStyle().IndentSpacing);
}

void end_indented() {
    ImGui::PopItemWidth();
    ImGui::Unindent();
}

// A sub-heading with its controls indented under it.
void begin_section(const char* title) {
    ImGui::TextUnformatted(title);
    begin_indented();
}

void end_section() {
    end_indented();
}

template <std::size_t N>
void draw_choice_combo(const char* label, const std::string& current, const Choice (&choices)[N],
                       void (*request)(const std::string&)) {
    const char* shown = current.c_str();
    for (const Choice& choice : choices) {
        if (current == choice.value) {
            shown = choice.name;
        }
    }
    if (!ImGui::BeginCombo(label, shown)) {
        return;
    }
    for (const Choice& choice : choices) {
        bool selected = current == choice.value;
        if (ImGui::Selectable(choice.name, selected) && !selected) {
            request(choice.value);
        }
    }
    ImGui::EndCombo();
}

std::string language_name(const CoreState& state, const std::string& code) {
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

void draw_language_combo(const char* label, const CoreState& state, const std::string& current,
                         void (*request)(const std::string&)) {
    if (!ImGui::BeginCombo(label, language_name(state, current).c_str())) {
        return;
    }
    for (const LanguageOption& language : state.languages) {
        bool selected = language.code == current;
        if (ImGui::Selectable((language.name + "##" + language.code).c_str(), selected) && !selected) {
            request(language.code);
        }
    }
    ImGui::EndCombo();
}

// Voices that speak the output language, grouped by engine.
void draw_voice_combo(const CoreState& state) {
    std::string language = state.output_language;
    bool any = false;
    for (const VoiceOption& voice : state.voices) {
        any = any || primary_language(voice.language) == language;
    }
    if (!any) {
        // The message takes the voice's place, so the panel keeps its height.
        ImGui::BeginDisabled();
        if (ImGui::BeginCombo("Voice", state.voices.empty() ? "No voices installed" : "No voice for this language")) {
            ImGui::EndCombo();
        }
        ImGui::EndDisabled();
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

void draw_speech_pace(const CoreState& state) {
    // While dragging, the slider shows its own value; the core gets it, in steps of 0.1, on release.
    static float dragged_rate = 0.0f;
    float rate = dragged_rate > 0.0f ? dragged_rate : state.speech_rate;
    if (ImGui::SliderFloat("Reading speed", &rate, 0.5f, 2.0f, "%.1fx", ImGuiSliderFlags_AlwaysClamp)) {
        dragged_rate = rate;
    }
    if (ImGui::IsItemDeactivatedAfterEdit()) {
        request_speech_rate(std::round(rate * 10.0f) / 10.0f);
    }
    if (!ImGui::IsItemActive()) {
        dragged_rate = 0.0f;
    }
    bool cut_off = state.cut_off_lines;
    if (ImGui::Checkbox("Cut off the current line for a new one", &cut_off)) {
        request_cut_off_lines(cut_off);
    }
}

void draw_ducking(const CoreState& state) {
    bool ducking = state.ducking;
    if (ImGui::Checkbox("Lower game sound while speaking", &ducking)) {
        request_ducking(ducking);
    }
    // While dragging, the slider shows its own value; the core gets it on release.
    static int dragged_percent = -1;
    int percent = dragged_percent >= 0 ? dragged_percent : static_cast<int>(std::lround(state.duck_volume * 100.0f));
    // Indented under the checkbox it depends on.
    ImGui::BeginDisabled(!state.ducking);
    begin_indented();
    if (ImGui::SliderInt("Game volume", &percent, 0, 100, "%d%%", ImGuiSliderFlags_AlwaysClamp)) {
        dragged_percent = percent;
    }
    if (ImGui::IsItemDeactivatedAfterEdit()) {
        request_duck_volume(static_cast<float>(percent) / 100.0f);
    }
    if (!ImGui::IsItemActive()) {
        dragged_percent = -1;
    }
    end_indented();
    ImGui::EndDisabled();
}

// Where text comes from: the game's language and its sources, each of which can be switched off.
void draw_game(const CoreState& state) {
    begin_box("Game");
    draw_language_combo("Game language", state, state.game_language, request_game_language);
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

void draw_subtitle_settings(const CoreState& state) {
    bool subtitles = state.subtitles;
    if (ImGui::Checkbox("Show subtitles", &subtitles)) {
        request_subtitles(subtitles);
    }
    // Indented under the checkbox they depend on, like the game volume.
    ImGui::BeginDisabled(!state.subtitles);
    begin_indented();
    draw_choice_combo("Size", state.subtitle_size, kSubtitleSizes, request_subtitle_size);
    draw_choice_combo("Position", state.subtitle_position, kSubtitlePositions, request_subtitle_position);
    end_indented();
    ImGui::EndDisabled();
}

// Where text goes: the language it is prepared in, how it is spoken and how it is shown.
void draw_output(const CoreState& state) {
    begin_box("Output");
    draw_language_combo("Language", state, state.output_language, request_output_language);
    begin_section("Speech");
    draw_voice_combo(state);
    draw_speech_pace(state);
    draw_ducking(state);
    if (ImGui::Button(state.paused ? "Resume reading" : "Pause reading")) {
        request_paused(!state.paused);
    }
    ImGui::SameLine();
    if (ImGui::Button("Stop this line")) {
        request_stop_line();
    }
    end_section();
    begin_section("Subtitles");
    draw_subtitle_settings(state);
    end_section();
    end_box();
}

// The text cut to fit width, ending in "..." if it does not fit whole.
std::string fit_width(const std::string& text, float width) {
    if (ImGui::CalcTextSize(text.c_str()).x <= width) {
        return text;
    }
    std::string cut = text;
    while (!cut.empty() && ImGui::CalcTextSize((cut + "...").c_str()).x > width) {
        cut.pop_back();
        while (!cut.empty() && (static_cast<unsigned char>(cut.back()) & 0xC0) == 0x80) {
            cut.pop_back();  // The rest of a UTF-8 character.
        }
    }
    return cut + "...";
}

// The words after a stage's name: why it does nothing, else its warning while it is switched off,
// else its summary. Always on the stage's own line, so the panel keeps its height; text too long
// for the panel is cut and shown whole on hover.
void draw_stage_note(const StageOption& stage) {
    const std::string* note = &stage.summary;
    ImVec4 color = ImGui::GetStyleColorVec4(ImGuiCol_TextDisabled);
    if (stage.inactive) {
        note = &*stage.inactive;
    } else if (!stage.enabled && stage.warning) {
        note = &*stage.warning;
        color = kWarningColor;
    }
    if (note->empty()) {
        return;
    }
    ImGui::SameLine();
    std::string shown = fit_width(*note, ImGui::GetContentRegionAvail().x);
    ImGui::TextColored(color, "%s", shown.c_str());
    if (shown != *note && ImGui::IsItemHovered(ImGuiHoveredFlags_AllowWhenDisabled)) {
        ImGui::SetTooltip("%s", note->c_str());
    }
}

void draw_stage(const StageOption& stage) {
    // A stage that does nothing with the player's languages is greyed out but keeps its tick, so
    // it works again as soon as the languages allow. Its reason is not faded, to stay readable.
    ImGui::BeginDisabled(stage.inactive.has_value());
    bool enabled = stage.enabled;
    if (ImGui::Checkbox((stage.type + "##" + stage.key).c_str(), &enabled)) {
        request_stage_enabled(stage.key, enabled);
    }
    ImGui::EndDisabled();
    draw_stage_note(stage);
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

void draw_last_line(const CoreState& state) {
    begin_box("Last line");
    if (state.last_line.empty()) {
        ImGui::TextDisabled("-");
    } else {
        clamped_wrapped_text(state.last_line, kMaxLastLineRows);
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
        draw_last_line(state);
    }
    draw_footer(state);
    ImGui::End();
}

}  // namespace

void draw_ui() {
    CoreState state = core_state();
    draw_subtitle(state);
    if (panel_open()) {
        draw_panel(state);
    } else if (ImGui::GetTime() < kHintSeconds) {
        draw_hint();
    }
}

}  // namespace reflektortts
