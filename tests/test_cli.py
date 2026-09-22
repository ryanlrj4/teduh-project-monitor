import pytest

from teduh_monitor.cli import build_parser


def test_primary_commands_use_operational_names() -> None:
    parser = build_parser()

    assert parser.parse_args(["refresh"]).command == "refresh"
    assert parser.parse_args(["refresh-if-due"]).command == "refresh-if-due"
    assert parser.parse_args(["validate-monitor"]).command == "validate-monitor"


@pytest.mark.parametrize(
    "retired_command",
    [
        "run",
        "validate",
        "validate-phase3",
        "legacy-kl-full-catalog",
        "legacy-kl-validate",
    ],
)
def test_ambiguous_prototype_commands_are_retired(retired_command: str) -> None:
    with pytest.raises(SystemExit):
        build_parser().parse_args([retired_command])
