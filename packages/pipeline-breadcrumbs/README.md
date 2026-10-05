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
| `ArtifactKind`, `Artifact`, `ArtifactSinkProtocol` | A declared kind of file, the complete frozen artifact, and the protocol a sink class implements with `persist(artifact)`. |
| `BreadcrumbFormatter`, `TimeDisplay` | The human rendering of boundary records, and the single switch for time. |
| `AttributeKey` | The names of the attributes every record carries. |
| `ArtifactSinkError`, `ContextualException` | Sink failures, and the shape an exception takes to receive step diagnostics. |

`pipeline_breadcrumbs.hosting` holds local file system helpers (`FileSystemArtifactSink`,
`create_run_folder`, `attached_run_log`). `pipeline_breadcrumbs.testing` holds
`ArtifactRecorder`, an in-memory sink, and `RecordCapture` for acceptance tests. Each sink is a
class that implements `ArtifactSinkProtocol`, so the application picks one and hands it in.

Create a run with `PipelineRun(pipeline_name=..., artifact_sink=...)` and open each item
with `pipeline_run.open_work_item(work_item)`. For deterministic run folders,
pass `supplied_clock` to `create_run_folder`; `Clock.create_system_clock()` supplies
the normal wall and monotonic clocks. `ArtifactRecorder.step_paths()` returns
the distinct emitting step paths in first-emitted order.

Manifest work-item records use `work_item_name`. Step records use `step_path`,
`step_key`, and `step_name`, so each field identifies its domain meaning.

The core knows no paths. A production host replaces the hosting helpers with its own class that
implements `ArtifactSinkProtocol`, such as one that uploads to blob storage.
