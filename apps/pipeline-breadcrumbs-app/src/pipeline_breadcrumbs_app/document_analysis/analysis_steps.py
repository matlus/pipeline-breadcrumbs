"""The system's table of contents: every step, declared in one place.

Each processor opens its own step on the host it is given, so the processor owns the work
and its identity. The declarations live here so the numbering reads as one list and two
steps can never be given the same number by accident.

Numbers are relative to the parent. The classification steps are 1, 2 and 3 inside step 3,
so they report as 3.1, 3.2 and 3.3. A different system could nest `SectionClassifier` at any
position without changing this file's classification block.
"""

from typing import Final

from pipeline_breadcrumbs import Step

LOAD_PAGES: Final[Step] = Step(1, "Load Pages")
DETECT_SECTIONS: Final[Step] = Step(2, "Detect Sections")
CLASSIFY_SECTIONS: Final[Step] = Step(3, "Classify Sections")
ASSEMBLE_REPORT: Final[Step] = Step(4, "Assemble Report")

# Inside CLASSIFY_SECTIONS.
PREPARE_PROMPTS: Final[Step] = Step(1, "Prepare Prompts")
SCORE_SECTIONS: Final[Step] = Step(2, "Score Sections")
RECONCILE_SCORES: Final[Step] = Step(3, "Reconcile Low-Confidence Scores")
