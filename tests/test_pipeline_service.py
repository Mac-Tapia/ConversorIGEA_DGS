from igea_dgs.services.pipeline import PipelineService, StageOutcome


def test_run_stops_before_dgs_when_g2_blocks():
    calls = []

    def stage(name, blocked=False):
        def invoke(context):
            calls.append(name)
            return StageOutcome(name, blocked=blocked, context=context)
        return invoke

    service = PipelineService(
        inspect=stage("inspect"),
        validate_input=stage("validate_input", blocked=True),
        convert=stage("convert"),
    )

    result = service.run({"fixture": "missing-conductor"})

    assert result.exit_code == 2
    assert calls == ["inspect", "validate_input"]


def test_api_unavailable_maps_to_exit_code_three():
    service = PipelineService(import_pf=lambda context: StageOutcome("import_pf", unavailable=True))
    assert service.import_pf({}).exit_code == 3
