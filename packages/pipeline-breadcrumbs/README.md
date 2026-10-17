# pipeline-breadcrumbs

Step-numbered progress logs and artifacts for long-running pipelines. See the
[workspace README](../../README.md) for the idea and [the design](../../docs/design.md)
for the reasoning.

## Public API

| Name | Purpose |
|---|---|
| `PipelineRun` | One execution: owns the sink, the logger and the manifest. Open with `async with`; `await pipeline_run.emit(kind, content)` hands over an artifact that belongs to the whole run. |
| `WorkItem` | The thing being processed: a document, a request, a batch row. Its `stem` prefixes artifact filenames; pass `file_stem` for a name that is not a file name. |
| `safe_path_component` | Makes a name safe to store under on any common file system; use it to build a `file_stem`. |
| `Step`, `StepScope`, `StepHostProtocol` | A step declared once, the scope it runs on, and the protocol an engine accepts. |
| `ArtifactKind`, `Artifact`, `ArtifactSinkProtocol` | A declared kind of file, the complete frozen artifact, and the protocol a sink class implements with `persist(artifact)`. |
| `BreadcrumbFormatter`, `TimeDisplay` | The human rendering of boundary records, and the single switch for time. |
| `AttributeKey` | The names of the attributes every record carries. |
| `ArtifactSinkError`, `ContextualExceptionProtocol` | Sink failures, and the shape an exception takes to receive step diagnostics. |
| `InvalidDeclarationError` | A step, artifact kind, work item or run declared with a value the library refuses (a `ValueError`). |
| `WorkItemNotOpenError` | A step opened, entered, skipped or emitted from outside its work item's `async with` block (a `RuntimeError`). |

`pipeline_breadcrumbs.hosting` holds local file system helpers (`ArtifactSinkFileSystem`,
`create_run_folder`, `attached_run_log`, and `safe_path_component` again). `ArtifactSinkFileSystem` raises
`WorkItemFolderCollisionError` (a `ValueError`) when two work items in one run map to the same folder. `pipeline_breadcrumbs.testing` holds
`ArtifactSinkTesting` and `RecordCapture` for acceptance tests.

Create a run with `PipelineRun(pipeline_name=..., artifact_sink=...)` and open each item
with `pipeline_run.open_work_item(work_item)`. For deterministic run folders,
pass `supplied_clock` to `create_run_folder` and `PipelineRun`; `Clock.create_system_clock()` supplies
the normal wall and monotonic clocks. `ArtifactSinkTesting.step_paths()` returns
the distinct emitting step paths in first-emitted order.

Manifest work-item records use `work_item_name`. Step records use `step_path`,
`step_key`, and `step_name`, so each field identifies its domain meaning. Artifacts a run emits
for itself are listed in `run_artifact_records`, each with `filename`, `artifact_type`, `role`
and `byte_count`.

A work item's `stem` is its name without the file extension, with each character a file system
refuses replaced by `_`: `Q3: Plan / Draft.pdf` becomes `Q3_ Plan _ Draft`. A name that is not a
file name, such as the model identifier `publisher/model-1.13`, passes
`file_stem=safe_path_component(name)` to keep its whole name; the library refuses a `file_stem`
that is blank or not file-safe.

The core knows no paths beyond making a work item's filename prefix file-safe. A production host replaces the hosting helpers with its own class that
implements `ArtifactSinkProtocol`, such as one that uploads to blob storage.
