"""Step 4: assemble the report. A non-model processor that produces the run's real output."""

import asyncio
from collections.abc import Iterable

from pipeline_breadcrumbs import StepHostProtocol
from pipeline_breadcrumbs_app.document_analysis.analysis_steps import ASSEMBLE_REPORT
from pipeline_breadcrumbs_app.document_analysis.artifact_kinds import ANALYSIS_REPORT
from pipeline_breadcrumbs_app.document_analysis.models import ScoredSection


class ReportAssembler:
    def __init__(self, simulated_work_seconds: float) -> None:
        self._simulated_work_seconds: float = simulated_work_seconds

    async def assemble(self, step_host: StepHostProtocol, scored_sections: list[ScoredSection]) -> str:
        async with step_host.step(ASSEMBLE_REPORT) as step_scope:
            step_scope.info("Assembling the report", sections=len(scored_sections))
            # A real processor renders a template, merges tables and checks the result here.
            await asyncio.sleep(self._simulated_work_seconds)
            report: str = self._render_analysis_report(scored_sections)
            await step_scope.emit(ANALYSIS_REPORT, report.encode("utf-8"))
            step_scope.outcome("Report assembled", characters=len(report))
        return report

    @staticmethod
    def _render_analysis_report(scored_sections: Iterable[ScoredSection]) -> str:
        report_lines: list[str] = ["# Section analysis", ""]
        report_lines.extend(
            f"- Page {scored_section.page_number}: {_one_line(scored_section.title)} "
            f"({_one_line(scored_section.category)}, confidence {scored_section.confidence:.2f})"
            for scored_section in scored_sections
        )
        return "\n".join(report_lines) + "\n"


def _one_line(model_text: str) -> str:
    # Titles and categories come from the model, so a stray newline must not break the report's one-line-per-section shape.
    return " ".join(model_text.split())
