"""Step 1: load the document's pages. A non-model processor that takes real time."""

from pipeline_breadcrumbs import StepHostProtocol, StepScope
from pipeline_breadcrumbs_app.document_analysis.analysis_steps import LOAD_PAGES
from pipeline_breadcrumbs_app.document_analysis.artifact_kinds import PAGE_TEXT, page_discriminator
from pipeline_breadcrumbs_app.document_analysis.simulated_work import SimulatedWork


class PageLoader:
    def __init__(self, simulated_work: SimulatedWork) -> None:
        self._simulated_work: SimulatedWork = simulated_work

    async def load(self, step_host: StepHostProtocol, pages: list[str]) -> list[str]:
        async with step_host.step(LOAD_PAGES) as step_scope:
            step_scope.info("Loading pages", pages=len(pages))
            loaded_pages: list[str] = await self._load_each_page(step_scope, pages)
            step_scope.outcome(f"Loaded {len(loaded_pages)} page(s)", pages=len(loaded_pages))
        return loaded_pages

    async def _load_each_page(self, step_scope: StepScope, pages: list[str]) -> list[str]:
        loaded_pages: list[str] = []
        page_number: int
        page_text: str
        for page_number, page_text in enumerate(pages):
            # A real pipeline renders each PDF page to an image and extracts its text here.
            await self._simulated_work.take_time()
            step_scope.info("Loaded page", page=page_number, characters=len(page_text))
            await step_scope.emit(PAGE_TEXT, page_text.encode("utf-8"), discriminator=page_discriminator(page_number))
            loaded_pages.append(page_text)
        return loaded_pages
