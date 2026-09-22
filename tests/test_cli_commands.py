from igea_dgs.cli import _parser, main
from igea_dgs.services.pipeline import PipelineService, StageOutcome


def test_all_strict_commands_support_json_flag():
    parser = _parser()
    subparsers = next(action for action in parser._actions if action.dest == "command")
    for command in ("inspect", "validate-input", "convert", "import-pf", "validate-pf", "study", "run", "catalog"):
        assert "--json" in subparsers.choices[command].format_help()


def test_run_uses_injected_pipeline_and_returns_blocking_code(capsys):
    service = PipelineService(
        inspect=lambda c: StageOutcome("inspect"),
        validate_input=lambda c: StageOutcome("validate_input", blocked=True),
    )
    code = main(["run", "--json"], service=service)
    assert code == 2
    assert '"exit_code": 2' in capsys.readouterr().out
