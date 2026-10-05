"""The system's view of a model: three questions, each answered with the model's raw text.

A real gateway wraps an LLM service (an Azure OpenAI deployment, say). The replies are raw
strings on purpose: they are untrusted until a processor has parsed and checked them.
"""

from typing import Protocol

from pipeline_breadcrumbs_app.document_analysis.models import ClassificationPrompt


class ModelGatewayProtocol(Protocol):
    async def detect_section(self, page_number: int, page_text: str) -> str:
        """Ask which section a page starts."""
        ...

    async def score_section(self, classification_prompt: ClassificationPrompt) -> str:
        """Ask for a category and a confidence for one section."""
        ...

    async def reconcile_section(self, classification_prompt: ClassificationPrompt) -> str:
        """Ask again about a section the first answer was unsure of."""
        ...
