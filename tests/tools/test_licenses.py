"""The license check: reading license expressions and names, judging each component against the allow
list and its exceptions, and finding exceptions no component needs."""

import os
from importlib.metadata import Distribution
from pathlib import Path

from licenses import (
    ALLOWED,
    EXCEPTIONS,
    Allowance,
    Component,
    alternatives,
    judge,
    notice_component,
    package_component,
    report,
    unused,
)
from notices import Notice


class FakeDistribution(Distribution):
    """An installed package that exists only as its METADATA."""

    def __init__(self, metadata: str) -> None:
        self._metadata = metadata

    def read_text(self, filename: str) -> str | None:
        return self._metadata if filename == "METADATA" else None

    def locate_file(self, path: str | os.PathLike[str]) -> Path:
        return Path(path)


def test_an_spdx_expression_is_read_as_its_choices() -> None:
    assert alternatives("Apache-2.0 OR BSD-2-Clause") == [frozenset({"Apache-2.0"}), frozenset({"BSD-2-Clause"})]
    assert alternatives("(MIT OR Zlib) AND Apache-2.0") == [
        frozenset({"MIT", "Apache-2.0"}),
        frozenset({"Zlib", "Apache-2.0"}),
    ]
    assert alternatives("GPL-2.0-or-later WITH Bootloader-exception and MIT") == [
        frozenset({"GPL-2.0-or-later WITH Bootloader-exception", "MIT"})
    ]


def test_names_packages_give_are_read_as_spdx_identifiers_where_they_say_which() -> None:
    assert alternatives("MIT License") == [frozenset({"MIT"})]
    assert alternatives("Apache Software License, GNU General Public License v2 (GPLv2)") == [
        frozenset({"Apache Software License", "GPL-2.0-only"})
    ]


def test_text_that_is_no_expression_is_taken_whole() -> None:
    assert alternatives("see the license text") == [frozenset({"see the license text"})]
    assert alternatives("(MIT") == [frozenset({"(MIT"})]
    assert alternatives("several, below", known=["several, below"]) == [frozenset({"several, below"})]


def test_a_component_under_allowed_licenses_passes() -> None:
    verdict = judge(Component("aiohttp", "aiohttp 3.14", "Apache-2.0 AND MIT"), exceptions=())

    assert verdict.refused == ()
    assert verdict.excepted == ()


def test_a_license_not_on_the_list_is_refused() -> None:
    verdict = judge(Component("tool", "tool 1.0", "MIT AND SSPL-1.0"), exceptions=())

    assert verdict.refused == ("SSPL-1.0",)


def test_of_the_choices_an_expression_offers_an_allowed_one_counts() -> None:
    assert judge(Component("tool", "tool 1.0", "SSPL-1.0 OR MIT"), exceptions=()).refused == ()


def test_an_exception_allows_a_license_only_for_its_component() -> None:
    exceptions = [Allowance("tqdm", "MPL-2.0", "Combined under section 3.3.")]

    allowed = judge(Component("tqdm", "tqdm 4.70", "MPL-2.0 AND MIT"), exceptions)
    other = judge(Component("other", "other 1.0", "MPL-2.0"), exceptions)

    assert (allowed.refused, allowed.excepted) == ((), ("MPL-2.0",))
    assert other.refused == ("MPL-2.0",)


def test_licenses_of_the_parts_a_package_contains_are_judged_too() -> None:
    component = Component("engine", "engine 1.0", "MIT", contains=("LicenseRef-Proprietary",))

    assert judge(component, exceptions=()).refused == ("LicenseRef-Proprietary",)
    allowed = judge(component, [Allowance("engine", "LicenseRef-Proprietary", "Permitted in COPYRIGHT.")])
    assert allowed.excepted == ("LicenseRef-Proprietary",)


def test_exceptions_no_component_needs_are_found() -> None:
    needed = Allowance("tqdm", "MPL-2.0", "Combined under section 3.3.")
    gone = Allowance("removed", "MPL-2.0", "No longer shipped.")
    changed = Allowance("tqdm", "Zlib", "No longer under it.")
    verdicts = [judge(Component("tqdm", "tqdm 4.70", "MPL-2.0 AND MIT"), [needed, gone, changed])]

    assert unused(verdicts, [needed, gone, changed]) == [gone, changed]


def test_a_package_is_keyed_by_its_canonical_name_with_its_metadata_license() -> None:
    package = FakeDistribution("Name: Typing_Extensions\nVersion: 4.16.0\nLicense-Expression: PSF-2.0\n")

    assert package_component(package) == Component("typing-extensions", "Typing_Extensions 4.16.0", "PSF-2.0")


def test_a_package_with_parts_its_metadata_leaves_out_carries_their_licenses() -> None:
    package = FakeDistribution("Name: ctranslate2\nVersion: 4.8.4\nLicense: MIT\n")

    assert "LicenseRef-Intel-Simplified-Software-License" in package_component(package).contains


def test_a_notice_is_keyed_by_the_name_of_its_text() -> None:
    notice = Notice("SDL 3.4.20", "Zlib", "native-sdl.txt")

    assert notice_component(notice) == Component("native-sdl", "SDL 3.4.20", "Zlib")


def test_every_exception_allows_a_license_the_allow_list_does_not_and_says_why() -> None:
    for allowance in EXCEPTIONS:
        assert allowance.license not in ALLOWED
        assert allowance.reason


def test_the_report_names_what_fails() -> None:
    refused = judge(Component("tool", "tool 1.0", "SSPL-1.0"), exceptions=())
    stale = Allowance("removed", "MPL-2.0", "No longer shipped.")

    lines = report([refused], [stale])

    assert lines[0].startswith("NOT ALLOWED") and lines[0].endswith("tool 1.0: SSPL-1.0")
    assert "  tool 1.0: SSPL-1.0" in lines
    assert "  removed: MPL-2.0" in lines
