from igea_dgs.gui import PipelinePresenter
from igea_dgs.services.pipeline import Exclusion, PipelineSummary


def test_gui_presenter_lists_trafomix_exclusions():
    summary = PipelineSummary(
        gate="G4",
        exclusions=(Exclusion("TRAFOMIX-01", "TRAFOMIX"),),
        provenance=("RED.txt",),
        original_case="immutable",
        diagnostic_case="F1__diagnostic__R1",
    )
    view = PipelinePresenter().render(summary)
    assert "TRAFOMIX excluidos" in view
    assert summary.exclusions[0].source_key in view
    assert "original: immutable" in view
