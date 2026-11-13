"""How the API writes a profile: the speech rules of the stages it uses."""

from collections.abc import Collection
from dataclasses import replace

from reflektortts.api.encoders import profile_json
from reflektortts.profiles.catalog import Choice, ProfileState, ProfileView, Standing
from tests.api.fake_core import MAD_MAX

RULES: dict[str, dict[str, tuple[str, ...]]] = {
    "normalize": {"Numbers, dates and units": ("en", "pl")},
    "tracker": {"Glossary grammar": ("pl",)},
}


def rules_of(stages: Collection[str]) -> dict[str, tuple[str, ...]]:
    return {rule: languages for stage in sorted(stages) for rule, languages in RULES.get(stage, {}).items()}


def view(glossary: bool) -> ProfileView:
    assert MAD_MAX.profile is not None
    profile = MAD_MAX.profile if glossary else replace(MAD_MAX.profile, glossary={})
    return ProfileView(Choice(replace(MAD_MAX, profile=profile), Standing.USED), ProfileState.NOT_RUNNING)


def test_a_profile_lists_the_speech_rules_of_the_stages_it_uses() -> None:
    assert profile_json(view(glossary=True), rules_of)["speech_rules"] == [
        {"name": "Glossary grammar", "languages": ["pl"]}
    ]


def test_a_profile_without_a_glossary_has_no_use_for_glossary_grammar() -> None:
    assert profile_json(view(glossary=False), rules_of)["speech_rules"] == []
