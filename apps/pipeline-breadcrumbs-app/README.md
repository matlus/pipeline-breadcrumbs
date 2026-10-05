# pipeline-breadcrumbs-app

A runnable demo of [pipeline-breadcrumbs](../../packages/pipeline-breadcrumbs/README.md).
It runs an offline document-analysis pipeline over two sample documents with a fake
model, so its output is the same every time.

It exercises per-page artifacts from concurrent work, a sub-orchestrator whose processors
report as steps 3.1 to 3.3, a conditional step that is skipped, raw model replies emitted
before they are validated, and a deliberate failure.

```bash
uv run pipeline_breadcrumbs_app                      # local: a clean run
uv run pipeline_breadcrumbs_app --fail-page 2        # Contract 12 gets a malformed reply on page 2
uv run pipeline_breadcrumbs_app --host hosted        # exceptions only go to telemetry
uv run pipeline_breadcrumbs_app --time all           # a time on every line (none | boundaries | all)
```

`main.py` is the application that calls the system, not part of it. It implements the artifact
callback and builds the logger and its handlers. `document_analysis/` is the system, and its entry point is
`DocumentAnalysisManager`. See the [workspace README](../../README.md) for the layout.
