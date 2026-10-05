# Pipeline Breadcrumbs: Structured Logging for Long-Running Pipelines

A multi-step pipeline (document ingestion, a chain of LLM calls, any long run of
transforming steps) raises a question that exceptions cannot answer: where is it right
now, and what did each step produce?

This library answers it with two outputs from one source.

1. **Step-numbered progress logs.** Every step announces itself, reports counts as it
   works, and closes with its elapsed time and outcome.
2. **Artifacts.** Each step can hand a self-describing file, an interim capture or a real
   output, to a callback the host controls.

Together they leave an ordered trail on disk after every run. A person, or a coding
assistant, reads the trail, finds the first step whose output went wrong, and fixes it.

"Structured logging" here has a narrower meaning than usual. It still covers named
properties on every log record, so any OpenTelemetry handler, Azure Application Insights
included, receives them. It also means the log reads as an ordered, step-numbered story.

## A pipeline step

```python
DETECT_SECTIONS = Step(2, "Detect Sections")
PAGE_EVIDENCE = ArtifactKind("page_evidence", "json", "application/json")

async def analyze(step_host: StepHostProtocol, pages: list[str]) -> None:
    async with step_host.step(DETECT_SECTIONS) as step_scope:
        step_scope.info("Detecting sections", pages=len(pages))
        raw_reply: str = await model.detect(pages[0])
        await step_scope.emit(PAGE_EVIDENCE, raw_reply.encode(), discriminator="page_0000")  # emit before you validate
        step_scope.outcome("Detected 4 sections", sections=4)
```

A step takes one argument, the scope it runs on. The scope carries the logger, the artifact
sink, the work item and the step's position, so none of them is a parameter. Steps nest:
a step numbered 2 inside step 3 is reported everywhere as 3.2, so a reusable engine runs
unchanged as a whole pipeline or inside another step.

## The trail it leaves

```
artifacts/20261003_103049_batch/
  run.log
  manifest.json                          read this first
  Contract 12/
    Contract 12_step_02_detected_sections.json
    Contract 12_step_03.01_classification_prompts.json
    Contract 12_step_03.02_section_scores.json
    Contract 12_step_04_analysis_report.md
    Contract 12_step_01_page_text_page_0000.txt
    Contract 12_step_02_raw_detection_response_page_0000.txt
```

Step numbers are zero-padded in filenames, so the folder sorts in pipeline order past step 9.
Each run gets its own folder with the timestamp in its name, so running the same file again
keeps every run. `manifest.json` lists every work item, every step with its status, elapsed
time and outcome, every artifact with its size, and any failure.

The log, with the time of day in the step header only:

```
================================================================================
STEP 3.3: Reconcile Low-Confidence Scores - COMPLETE (10:30:49)
Reconciled 1 section(s) in 0.001s (reconciled=1)
================================================================================
```

Whether a time appears at all is the formatter's one setting (`TimeDisplay`), so it is easy
to change in a single place. The records themselves always carry their own timestamp.

## What a failure looks like

A step that raises logs a WARNING breadcrumb with its elapsed time and the exception type,
and the exception continues upward. The host logs the exception once, at its outer boundary,
with its traceback and every named fact it carries. When the exception exposes
`add_contextual_data`, the failing step stamps `FailedAtStepNumber`, `FailedAtStepName` and
`FailedAtStepKey` onto it first.

## Application Insights and OpenTelemetry

Every record carries named attributes (`pipeline.step.number`, `pipeline.status`,
`pipeline.elapsed_seconds` and so on) through the standard `extra` argument of `logging`.
The library has no OpenTelemetry dependency. Application Insights is a feature of Azure
Monitor, not a separate service, so the integration is the Azure Monitor OpenTelemetry
distro you would use anyway:

```python
from azure.monitor.opentelemetry import configure_azure_monitor

configure_azure_monitor(logger_name="my_pipeline")   # the logger tree the pipeline logs through
logger = logging.getLogger("my_pipeline")
```

Python log records become `traces` rows and the attributes become custom dimensions. Trace
and span ids are not modelled; pass them once as `PipelineRun(attributes={"trace_id": ...})`
and every record carries them.

## Layout

- `packages/pipeline-breadcrumbs`: the library
- `apps/pipeline-breadcrumbs-app`: a runnable, offline demo, laid out like a production system
- `docs/design.md`: the design, what the earlier projects taught, and why each choice was made

## How the demo is structured

The demo separates the application from the system it calls, the way a production codebase does.

```
main.py                           the application: chooses the callback and the logger, calls the system
document_analysis/                the system
  document_analysis_manager.py    its entry point: one public method that validates, then sequences four processors
  analysis_steps.py               the table of contents: every Step, declared in one place
  model_reply.py                  turns an untrusted model reply into checked values
  validators/                     front-door validation of the document the manager is handed
  processors/
    page_loader.py                step 1, non-model work that takes time
    section_detector.py           step 2, a model processor fanning out across pages
    section_classifier.py         step 3, a sub-orchestrator over three more processors:
      classification/
        prompt_builder.py             3.1, non-model work
        section_scorer.py             3.2, a model processor
        score_reconciler.py           3.3, a conditional model processor
    report_assembler.py           step 4, non-model work that produces the real output
  gateways/                       the model gateway protocol, and a fake that sleeps instead of calling out
```

`main.py` is not the system. It builds the artifact callback and the logger, opens a
`PipelineRun`, opens one work item per document, and hands that scope to the manager. The
manager and the processors never see a path or a handler. Each processor opens its own step on
the host it is given, so it owns its work, and the classifier passes its own step down, which
is why its three processors report as 3.1 to 3.3 without any numbering code.

Nothing here calls a real model. The fake gateway and `SimulatedWork` sleep for a moment,
where a real system would call a service or render a page, so the log appears at a believable
pace and the demo needs no keys or configuration. Every spot where real work would go is
marked with a comment.

## Try it

```bash
uv sync --all-packages --all-groups
uv run pipeline_breadcrumbs_app                      # local: a clean run of two documents
uv run pipeline_breadcrumbs_app --fail-page 2        # a malformed model reply fails one document
uv run pipeline_breadcrumbs_app --host hosted        # exceptions only go to telemetry
```

The failing run exits with code 1, leaves the malformed reply on disk beside the replies
that parsed, and still completes the second document.

Where the application runs is its own choice, made in its artifact callback and its log handlers.
The callback persists every artifact in both: artifacts are the record of what each step did, and
what a later run could start from. The system shares one logger and passes every informational line
to it; the application decides who listens. A local run writes a `run.log` beside the artifacts. A
hosted run leaves informational lines to the platform's process logs (the console here) and sends only
exceptions to telemetry, as a stand-in for Application Insights (`telemetry.jsonl`). The system
runs identically in both.

## Checks

The tests are acceptance tests: each one runs through a system's public entry point
(`PipelineRun` for the library, `DocumentAnalysisManager` and `run_demo` for the demo) and
asserts on what the system returned, the artifacts it handed to the callback and the
breadcrumbs it logged. Only the model is replaced.

```bash
uv run --all-packages --all-groups ruff check packages apps
uv run --all-packages --all-groups pyright
uv run --all-packages --all-groups pytest -q
```

## Status

The Python library and demo are built and tested. A C# equivalent is planned for this
repository. Articles that explain the practice will be linked here when they are published.

## Teaching article

[Pipeline Breadcrumbs](https://matlus.com/writing/pipeline-breadcrumbs/) explains
how numbered steps, progress logs, artifacts and a run manifest help people and
coding assistants investigate failed runs and incorrect results. It includes a
runnable example and the reasoning behind the sink-class design. The setup
commands pin the source revision used by the examples.
