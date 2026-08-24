import pytest

from teduh_monitor.cli import build_parser


def test_primary_commands_use_operational_names() -> None:
    parser = build_parser()

    assert parser.parse_args(["refresh"]).command == "refresh"
    assert parser.parse_args(["refresh-if-due"]).command == "refresh-if-due"
    assert parser.parse_args(["validate-monitor"]).command == "validate-monitor"


def test_full_catalog_commands_are_explicitly_legacy_and_kl_scoped() -> None:
    parser = build_parser()

    assert (
        parser.parse_args(["legacy-kl-full-catalog"]).command
        == "legacy-kl-full-catalog"
    )
    assert parser.parse_args(["legacy-kl-validate"]).command == "legacy-kl-validate"


@pytest.mark.parametrize("retired_command", ["run", "validate", "validate-phase3"])
def test_ambiguous_prototype_commands_are_retired(retired_command: str) -> None:
    with pytest.raises(SystemExit):
        build_parser().parse_args([retired_command])
