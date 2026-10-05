# pipeline-breadcrumbs

Step-numbered progress logs and artifacts for long-running pipelines. See the
[workspace README](../../README.md) for the idea and [the design](../../docs/design.md)
for the reasoning.

## Public API

| Name | Purpose |
|---|---|
| `PipelineRun` | One execution: owns the sink, the logger and the manifest. Open with `async with`. |
| `WorkItem` | The thing being processed: a document, a request, a batch row. |
| `Step`, `StepScope`, `StepHostProtocol` | A step declared once, the scope it runs on, and the protocol an engine accepts. |
| `ArtifactKind`, `Artifact`, `ArtifactSink` | A declared kind of file, the complete frozen artifact, and the host's persistence callback. |
| `BreadcrumbFormatter`, `TimeDisplay` | The human rendering of boundary records, and the single switch for time. |
| `AttributeKey` | The names of the attributes every record carries. |
| `ArtifactSinkError`, `ContextualException` | Sink failures, and the shape an exception takes to receive step diagnostics. |

`pipeline_breadcrumbs.hosting` holds local file system helpers (`FileSystemArtifactSink`,
`create_run_folder`, `attached_run_log`). `pipeline_breadcrumbs.testing` holds
`ArtifactRecorder` and `RecordCapture` for acceptance tests.

Create a run with `PipelineRun(pipeline_name=..., sink=...)` and open each item
with `pipeline_run.open_work_item(work_item)`. For deterministic run folders,
pass `supplied_clock` to `create_run_folder`; `Clock.create_system_clock()` supplies
the normal wall and monotonic clocks. `ArtifactRecorder.step_paths()` returns
the distinct emitting step paths in first-emitted order.

Manifest work-item records use `work_item_name`. Step records use `step_path`,
`step_key`, and `step_name`, so each field identifies its domain meaning.

The core knows no paths. A production host replaces the hosting helpers with its own sink.
