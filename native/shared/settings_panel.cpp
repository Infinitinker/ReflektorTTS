// The settings panel's contents: the header, the Input, Output and Last line boxes, and the last
// error; in the panel's window, without what only makes sense over the app (pausing, stopping the
// line, the last line).

#include "settings_panel.h"

#include <imgui.h>

#include <cctype>
#include <cmath>
#include <string>

#include "api_client.h"
#include "processing_section.h"
#include "text_fit.h"
#include "widgets.h"

namespace reflektortts {
namespace {

constexpr float kHeaderFontSize = 20.0f;
constexpr int kMaxLastLineRows = 9;

constexpr Choice kSubtitleSizes[] = {{"small", "Small"}, {"medium", "Medium"}, {"large", "Large"}};
constexpr Choice kSubtitlePositions[] = {{"top", "Top"}, {"bottom", "Bottom"}};
// What a new line does while another is spoken.
constexpr Choice kNewLines[] = {
    {"wait", "Wait their turn"}, {"cut_off", "Cut off the current one"}, {"speed_up", "Speed up to catch up"}};

// A language as the combo shows it: its English name, then its own, e.g. "Polish (Polski)".
std::string language_label(const LanguageOption& language) {
    if (language.name == language.english_name) {
        return language.name;
    }
    return language.english_name + " (" + language.name + ")";
}

std::string language_name(const CoreState& state, const std::string& code) {
    for (const LanguageOption& language : state.languages) {
        if (language.code == code) {
            return language_label(language);
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
    dot_label(state.connected ? kGreen : kGray, connection);
    ImGui::Separator();
}

// The app, and in the overlay whether reading is active or paused; in a window, whether the app is
// being read, since its settings can be changed either way.
void draw_status(const CoreState& state, PanelPlace place) {
    ImGui::TextUnformatted(state.app.c_str());
    if (place == PanelPlace::Overlay) {
        const char* reading = state.paused ? "Paused" : "Active";
        align_right(dot_label_width(reading));
        dot_label(state.paused ? kAmber : kGreen, reading);
        return;
    }
    const char* reading = state.running ? "Being read" : "Not running";
    align_right(dot_label_width(reading));
    dot_label(state.running ? kGreen : kGray, reading);
    if (!state.running) {
        ImGui::TextDisabled("Changes apply when the app starts.");
    }
}

void draw_language_combo(const char* label, const CoreState& state, const std::string& current,
                         void (*request)(const std::string&)) {
    if (!ImGui::BeginCombo(label, language_name(state, current).c_str())) {
        return;
    }
    for (const LanguageOption& language : state.languages) {
        bool selected = language.code == current;
        if (ImGui::Selectable((language_label(language) + "##" + language.code).c_str(), selected) && !selected) {
            request(language.code);
        }
    }
    ImGui::EndCombo();
}

// Voices that speak the output language, grouped by engine.
void draw_voice_combo(const CoreState& state) {
    const ProfileSettings& settings = state.settings;
    const std::string& language = settings.output_language;
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
    if (!ImGui::BeginCombo("Voice", settings.voice.c_str())) {
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
        bool selected = voice.id == settings.voice;
        ImGui::Indent();
        if (ImGui::Selectable((voice.id + "##" + voice.id).c_str(), selected) && !selected) {
            request_voice(voice.id);
        }
        ImGui::Unindent();
    }
    ImGui::EndCombo();
}

void draw_speech_pace(const ProfileSettings& settings) {
    // While dragging, the slider shows its own value; the core gets it, in steps of 0.1, on release.
    static float dragged_rate = 0.0f;
    float rate = dragged_rate > 0.0f ? dragged_rate : settings.speech_rate;
    if (ImGui::SliderFloat("Reading speed", &rate, 0.5f, 2.0f, "%.1fx", ImGuiSliderFlags_AlwaysClamp)) {
        dragged_rate = rate;
    }
    if (ImGui::IsItemDeactivatedAfterEdit()) {
        request_speech_rate(std::round(rate * 10.0f) / 10.0f);
    }
    if (!ImGui::IsItemActive()) {
        dragged_rate = 0.0f;
    }
    draw_choice_combo("New lines", settings.new_line, kNewLines, request_new_line);
}

void draw_ducking(const ProfileSettings& settings) {
    bool ducking = settings.ducking;
    if (ImGui::Checkbox("Lower app sound while speaking", &ducking)) {
        request_ducking(ducking);
    }
    // While dragging, the slider shows its own value; the core gets it on release.
    static int dragged_percent = -1;
    int percent = dragged_percent >= 0 ? dragged_percent : static_cast<int>(std::lround(settings.duck_volume * 100.0f));
    // Indented under the checkbox it depends on.
    ImGui::BeginDisabled(!settings.ducking);
    begin_indented();
    if (ImGui::SliderInt("App volume", &percent, 0, 100, "%d%%", ImGuiSliderFlags_AlwaysClamp)) {
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

// Where text comes from: the app's language and its sources, each of which can be switched off.
void draw_input(const CoreState& state) {
    begin_box("Input");
    draw_language_combo("Language", state, state.settings.input_language, request_input_language);
    for (const SourceStages& source : state.settings.sources) {
        bool enabled = source.enabled;
        if (ImGui::Checkbox((source.source + "##source:" + source.source).c_str(), &enabled)) {
            request_source_enabled(source.source, enabled);
        }
        ImGui::SameLine();
        ImGui::TextDisabled("%s", source.type.c_str());
    }
    end_box();
}

void draw_subtitle_settings(const ProfileSettings& settings) {
    bool subtitles = settings.subtitles;
    if (ImGui::Checkbox("Show subtitles", &subtitles)) {
        request_subtitles(subtitles);
    }
    // Indented under the checkbox they depend on, like the app volume.
    ImGui::BeginDisabled(!settings.subtitles);
    begin_indented();
    draw_choice_combo("Size", settings.subtitle_size, kSubtitleSizes, request_subtitle_size);
    draw_choice_combo("Position", settings.subtitle_position, kSubtitlePositions, request_subtitle_position);
    end_indented();
    ImGui::EndDisabled();
}

// Pausing and stopping act on the app being read, so they are shown only over it.
void draw_reading_buttons(const CoreState& state) {
    if (ImGui::Button(state.paused ? "Resume reading" : "Pause reading")) {
        request_paused(!state.paused);
    }
    ImGui::SameLine();
    if (ImGui::Button("Stop this line")) {
        request_stop_line();
    }
}

// Where text goes: the language it is prepared in, how it is spoken and how it is shown.
void draw_output(const CoreState& state, PanelPlace place) {
    begin_box("Output");
    draw_language_combo("Language", state, state.settings.output_language, request_output_language);
    begin_section("Speech");
    draw_voice_combo(state);
    draw_speech_pace(state.settings);
    draw_ducking(state.settings);
    if (place == PanelPlace::Overlay) {
        draw_reading_buttons(state);
    }
    end_section();
    begin_section("Subtitles");
    draw_subtitle_settings(state.settings);
    end_section();
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

void draw_error(const CoreState& state) {
    if (state.last_error.empty()) {
        return;
    }
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

}  // namespace

void draw_settings_panel(const CoreState& state, PanelPlace place) {
    draw_header(state);
    if (!state.connected) {
        ImGui::TextWrapped("Not connected to ReflektorTTS. Is it running?");
    } else if (!state.settings_error.empty()) {
        ImGui::PushStyleColor(ImGuiCol_Text, kErrorColor);
        ImGui::TextWrapped("%s", state.settings_error.c_str());
        ImGui::PopStyleColor();
    } else {
        // Top to bottom, the way a line goes through ReflektorTTS: input, processing, output.
        draw_status(state, place);
        draw_input(state);
        draw_flow_arrow();
        draw_processing(state.settings);
        draw_flow_arrow();
        draw_output(state, place);
        if (place == PanelPlace::Overlay) {
            draw_last_line(state);
        }
    }
    draw_error(state);
}

}  // namespace reflektortts
