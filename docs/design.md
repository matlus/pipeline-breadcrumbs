# Pipeline Breadcrumbs: design and features

This document describes what the library does, how it does it, and why each choice was made.
It covers the features that are built, the decisions behind them (including the alternatives
that were rejected), and the changes the design makes easy later, such as restarting a long
run from a given step.

Status: the library (`packages/pipeline-breadcrumbs`) and a runnable demo
(`apps/pipeline-breadcrumbs-app`) are built. 120 acceptance tests pass, strict pyright and ruff
are clean. A full PWI code review of the first version produced 168 findings, and most are fixed
(see "Revisions after the first PWI review"). A quick PWI review of the revised code found three
more, which are also fixed. A full PWI review of the revised code has not been run yet. The
public repository and the articles are not published.

## Contents

1. [What it is](#what-it-is)
2. [A run, as the trail shows it](#a-run-as-the-trail-shows-it)
3. [Why the file names are the point](#why-the-file-names-are-the-point)
4. [Reading a trail without reading code](#reading-a-trail-without-reading-code)
5. [Coding assistants can drive from the trail](#coding-assistants-can-drive-from-the-trail)
6. [Features](#features)
7. [Design](#design)
8. [Decisions: why this, why not that](#decisions-why-this-why-not-that)
9. [What building it taught](#what-building-it-taught)
10. [What the design makes easy later](#what-the-design-makes-easy-later)
11. [The demo](#the-demo)
12. [How the design evolved](#how-the-design-evolved)

## What it is

A multi-step pipeline (document ingestion, a chain of LLM calls, any long run of transforming
steps) raises two questions that exceptions cannot answer: where is the run right now, and what
did each step produce?

The library answers both with two outputs from one source.

1. **Step-numbered progress logs.** Every step announces itself, reports counts as it works, and
   closes with its elapsed time and outcome.
2. **Artifacts.** A step hands a self-describing file to an artifact sink the host chooses. The file
   might be a captured model reply, a prepared prompt, an intermediate result or the final report.

Logs and artifacts are different things, and the library keeps them apart.

- **Logs** are the running commentary. They say where the run is and how long each thing took.
  A developer watches them while the run is going. A per-run log file keeps the whole account.
- **Artifacts** are the record. They are real files that are persisted in every environment,
  because they show what each step did and they could feed a later run (see
  [restarting from a step](#restart-from-a-step)).

Both land in one folder per run, named so that an ordinary alphabetical listing is the order in
which the pipeline ran. That ordering is the feature the rest of this document keeps returning to.

"Structured logging" here is narrower than the usual sense of named properties on a log event.
Both are covered. Every record carries named attributes, and the log reads as an ordered,
step-numbered story.

## A run, as the trail shows it

Everything in this section is real output from the demo, abridged only where marked. The demo
analyzes two documents with a fake model, so the output is the same every time. The timings in the
samples come from one run with the demo's built-in pace.

### The run folder

One folder per run. The timestamp is part of the name, so a repeat run never overwrites an
earlier one, and the folders sort by time.

```
artifacts/20261005_105428_batch/
  manifest.json
  run.log
  Contract 12/
  Lease 4/
```

Inside a work item's folder, every file sits side by side. The listing below is what a file
explorer shows when it sorts by name, which is its default.

```
Contract 12_step_01_page_text_page_0000.txt
Contract 12_step_01_page_text_page_0001.txt
Contract 12_step_01_page_text_page_0002.txt
Contract 12_step_01_page_text_page_0003.txt
Contract 12_step_02_detected_sections.json
Contract 12_step_02_raw_detection_response_page_0000.txt
Contract 12_step_02_raw_detection_response_page_0001.txt
Contract 12_step_02_raw_detection_response_page_0002.txt
Contract 12_step_02_raw_detection_response_page_0003.txt
Contract 12_step_03.01_classification_prompts.json
Contract 12_step_03.02_raw_score_response_page_0000.txt
Contract 12_step_03.02_raw_score_response_page_0001.txt
Contract 12_step_03.02_raw_score_response_page_0002.txt
Contract 12_step_03.02_raw_score_response_page_0003.txt
Contract 12_step_03.02_section_scores.json
Contract 12_step_03.03_raw_reconciliation_response_page_0002.txt
Contract 12_step_03.03_reconciled_scores.json
Contract 12_step_04_analysis_report.md
```

Read top to bottom, this is the pipeline: load the pages, detect sections, prepare prompts, score
the sections, reconcile the doubtful one, assemble the report. Nobody needed the code to see it.

### A step, from start to finish

A step announces itself, reports progress as it goes, and closes with its elapsed time and a
summary of what it did. Step 2 of the first document, abridged:

```
================================================================================
STEP 2: Detect Sections - STARTED (10:54:29)
================================================================================
Detecting sections (pages=4, concurrency=3)
Calling the model (page=0)
Calling the model (page=1)
Calling the model (page=2)
Emitted artifact: Contract 12_step_02_raw_detection_response_page_0001.txt (26 B)
Detected a section (page=1, title=Payment Terms)
Emitted artifact: Contract 12_step_02_raw_detection_response_page_0000.txt (24 B)
Detected a section (page=0, title=Definitions)
Calling the model (page=3)
Emitted artifact: Contract 12_step_02_raw_detection_response_page_0002.txt (26 B)
Detected a section (page=2, title=Miscellaneous)
Emitted artifact: Contract 12_step_02_raw_detection_response_page_0003.txt (24 B)
Detected a section (page=3, title=Termination)
Emitted artifact: Contract 12_step_02_detected_sections.json (238 B)

================================================================================
STEP 2: Detect Sections - COMPLETE (10:54:29)
Detected 4 section(s) in 0.632s (sections=4)
================================================================================
```

Three things to notice:

- The two banners mark the boundary. They carry the step number, the name, the status and the time
  of day. Lines between them carry no time, which keeps the log readable. The time of day is a
  setting on the formatter (see [time is a logging-end decision](#time-is-a-logging-end-decision)).
- The lines between the banners are the progress. They report counts and identifiers, never
  payloads. Here the pages ran three at a time, so page 1 finished before page 0. The log shows
  what really happened, including the order.
- The closing banner has the elapsed time and the outcome. Both are also on the log record as named
  attributes, so a query can find the slow steps.

### A step inside a step

A step can contain other steps. The numbers compose: step 2 inside step 3 reports as 3.2, in the
banner, in the attributes and in the filenames. The classification engine in the demo does not
number itself. It is handed step 3 and opens its own steps 1, 2 and 3 inside it.

```
================================================================================
STEP 3.3: Reconcile Low-Confidence Scores - STARTED (10:54:31)
================================================================================
Reconciling low-confidence sections (sections=1)
Calling the model again (page=2, title=Miscellaneous, was=0.55)
Emitted artifact: Contract 12_step_03.03_raw_reconciliation_response_page_0002.txt (43 B)
Reconciled a section (page=2, title=Miscellaneous, now=0.81)
Emitted artifact: Contract 12_step_03.03_reconciled_scores.json (441 B)

================================================================================
STEP 3.3: Reconcile Low-Confidence Scores - COMPLETE (10:54:31)
Reconciled 1 section(s) in 0.316s (reconciled=1)
================================================================================
```

### A step that did not run

Step 3.3 is conditional. The second document has no doubtful section, so the step is skipped, and
the log says why. The absence of a `reconciled_scores` file in that document's folder says the same.

```
================================================================================
STEP 3.3: Reconcile Low-Confidence Scores - SKIPPED (10:54:33)
Skipped: no sections below the confidence threshold
================================================================================
```

### A step that failed

When a step raises, it logs a failed banner with the elapsed time and the exception, and the
exception continues upward. The work item's banner follows. The application, at its outer boundary,
then logs the exception once, with every named fact the exception carries. The traceback is
shortened here; the real log prints all of it.

```
================================================================================
STEP 2: Detect Sections - FAILED (10:54:35)
Failed after 0.615s: ModelResponseParseError: The model response for page 2 could not be parsed: JSONDecodeError: Expecting value: line 1 column 1 (char 0)
================================================================================

================================================================================
WORK ITEM: Contract 12.pdf - FAILED (10:54:35)
Failed after 1.043s: ModelResponseParseError: The model response for page 2 could not be parsed: JSONDecodeError: Expecting value: line 1 column 1 (char 0)
================================================================================
Work item 'Contract 12.pdf' failed:
  ExceptionType: ModelResponseParseError
  Message: The model response for page 2 could not be parsed: JSONDecodeError: Expecting value: line 1 column 1 (char 0)
  PageNumber: 2
  FailedAtStepNumber: 2
  FailedAtStepName: Detect Sections
  FailedAtStepKey: detect_sections
Traceback (most recent call last):
  (traceback omitted here)
```

`FailedAtStepNumber`, `FailedAtStepName` and `FailedAtStepKey` were added to the exception by
the step it escaped from. The exception never mentioned steps; the library stamped it on the way
out. The failure did not stop the batch: the second document completed.

The folder tells the same story. Step 2 failed, and all four raw model replies, including the
malformed one for page 2, are on disk beside the replies that parsed. The reply that broke the
parser was saved before the parser saw it.

### The end of the run

```
================================================================================
RUN: document-analysis-demo - COMPLETE (10:54:33)
2 work item(s): 2 complete, 0 failed in 5.218s
================================================================================
Emitted artifact: manifest.json (12.3 KB)
```

### The manifest

`manifest.json` is the last artifact, and the first file to read. It lists every work item and
every step with its status, elapsed time and outcome, every artifact with its size, and any
failure. From the failed run, abridged:

```json
{
  "run_status": "FAILED",
  "work_item_records": [
    {
      "work_item_name": "Contract 12.pdf",
      "work_item_status": "FAILED",
      "failure": "ModelResponseParseError: The model response for page 2 could not be parsed: ...",
      "step_records": [
        { "step_path": "1", "step_key": "load_pages", "step_name": "Load Pages",
          "step_status": "COMPLETE", "elapsed_seconds": 0.427, "outcome": "Loaded 4 page(s)" },
        { "step_path": "2", "step_key": "detect_sections", "step_name": "Detect Sections",
          "step_status": "FAILED", "elapsed_seconds": 0.615,
          "failure": "ModelResponseParseError: The model response for page 2 could not be parsed: ..." }
      ],
      "artifact_records": [
        { "filename": "Contract 12_step_01_page_text_page_0000.txt", "artifact_type": "page_text",
          "role": "interim", "byte_count": 50, "step_path": "1" }
      ]
    }
  ]
}
```

### What telemetry receives

A hosted application sends only exceptions to telemetry. The demo's `hosted` profile plays that
role with a handler that writes one JSON line per exception (a real host attaches the Application
Insights handler at the same level). The failed run above produces exactly one record, shown here
with the exception's own `ExceptionType` and `Message` entries and the timestamp left out:

```json
{
  "severity": "ERROR",
  "exception_type": "ModelResponseParseError",
  "custom_dimensions": {
    "pipeline.name": "document-analysis-demo",
    "pipeline.run.id": "20261005_104822_97eb942c",
    "pipeline.work_item.name": "Contract 12.pdf",
    "PageNumber": 2,
    "FailedAtStepNumber": "2",
    "FailedAtStepName": "Detect Sections",
    "FailedAtStepKey": "detect_sections"
  }
}
```

The step lines, the timings and the failed banners stay in the local logs. A clean hosted run sends
nothing.

## Why the file names are the point

Every artifact filename has the same shape:

```
<work item>_step_<step path>_<what it holds>[_<discriminator>].<extension>
```

For example, `Contract 12_step_03.02_raw_score_response_page_0001.txt`. The step path is zero-padded
(`02`, `03.02`), so an alphabetical sort and the pipeline's order are the same thing, including past
step 9 and for sub-steps. The pieces after it say what the file holds and, for per-page files,
which page.

This was built for one reason: the people looking at a run are rarely the people who wrote the code.

In the production applications this pattern came from, the operations team had no access to
the running system and no insight into its insides. What they could see was the folder of artifacts.
That was enough. They reported problems like this: the run failed at step 3; the file from step 2
looks fine; this file from step 3.2 has something odd in it, so the trouble probably started there.
They found the point of failure by reading the filenames in order and opening two or three files.
Nobody had to explain the pipeline to them. The system described itself.

The rule that makes this work is that **the order of the listing is the order of the steps, and
nothing breaks it**. Several choices exist to protect that rule:

- Step numbers are zero-padded, so `10` does not sort before `2`.
- A work item's files sit in one folder. An earlier version of the demo moved page texts and raw
  model replies into `pages/` and `model_responses/` subfolders. A file explorer lists folders
  first and alphabetically, so those folders came before the step 1 files in the work item's folder
  and step 1 no longer read first. The subfolder option is gone from the library, and a test lists a
  folder alphabetically and checks the step numbers never go backwards.
- The step comes right after the work item's name, before anything that describes the file, so the
  step is what the sort sees first.
- Each run has its own folder, so files from different runs never mix.

Two orderings are not yet what a reader might expect. Within one step, files sort by the name of what
they hold, so in step 2 the summary `detected_sections.json` lists before the raw replies that were
written before it. And at the top of a run, the work item folders sort by document name, not by the
order they were processed. Both are small. Either could be fixed with a sequence number in the
name (see [what the design makes easy later](#what-the-design-makes-easy-later)).

## Reading a trail without reading code

Given only a run folder, this is how a person finds a problem:

1. Open `manifest.json`. The run's status and each work item's status are at the top. Find the
   first step whose status is `FAILED`, or whose outcome looks wrong.
2. In that work item's folder, find the step's files. The step number is in every name.
3. Open the step's summary file and its raw replies. The raw replies show what the model said,
   before anything parsed it.
4. Look at the files from the step before. If the output of step 2 was already wrong, the problem
   started there, whatever step 3 reported.
5. Open `run.log` for the account in between: what the step was doing, how many items it had, and
   how long each part took.

None of those steps needs the source code, the language it was written in, or the person who wrote it.

## Coding assistants can drive from the trail

A second benefit showed up after the pattern was in production use. Once the applications were built
with coding assistants, the assistants could discover and use the trail without being told how. An
assistant would run the pipeline, read the log and the artifacts, find the first step whose output was
wrong, change the code and run again. Nobody explained the process to it. In the experience of the
person who built these applications, this was the first time a coding assistant worked that way:
discover, run, inspect, fix, repeat.

It works for reasons that follow from the design:

- **The trail is self-describing.** Step numbers, step names and what each file holds are in the
  names. An assistant does not need a map.
- **The evidence is on disk.** The assistant reads files with its ordinary tools. It does not
  need a debugger or a running process.
- **It can compare runs.** Each run keeps its own folder, so an assistant can set the trail from
  before a change beside the trail from after it and see what the change did. It can also spot
  things a person would miss, such as a step that got slower, or a value that drifts from run to run.
- **Failures arrive with their context.** The failing step's number, name and key are on the
  exception, and the raw input that broke it is on disk.
- **The assistant's work helps people too.** The same files an assistant uses are the ones an
  operations team reads.

The practical result is that the trail pays for itself twice: it makes the system understandable to
people who did not build it, and it makes the system something a coding assistant can improve with
little guidance.

## Features

What is built:

| Feature | What it gives you |
|---|---|
| Step-numbered boundaries | STARTED, COMPLETE, FAILED and SKIPPED for every step, with elapsed time and an outcome |
| Nested steps | Step numbers compose (3.2); an engine runs whole or inside another step unchanged |
| Progress lines | Counts and identifiers between the boundaries, as named attributes on one clean record |
| Artifacts | Self-describing files with derived, step-ordered names, handed to a host-chosen sink |
| Always persisted | Every artifact is kept in every environment; the role (interim or output) is information |
| Emit before validate | Raw model output is saved before it is parsed, so a parse failure leaves its evidence |
| Run folders | One folder per run, timestamp in the name, nothing overwritten |
| Run manifest | An index of every work item, step and artifact, written as the run's last artifact |
| Failure context | The failing step's identity is added to the exception once; the exception is logged once |
| One shared logger | The application owns the logger and its handlers; the system only logs |
| Local and hosted logging | Informational lines to a run log locally; only exceptions to telemetry when hosted |
| Time is a formatter choice | Time of day in the banner by default, off or on every line by one setting |
| Retries and fan-out | A reopened work item or a step opened per page keeps every record |
| OpenTelemetry fit | Attributes travel as standard `extra`; the library has no OpenTelemetry dependency |
| Test helpers | A recording sink and a log capture for acceptance tests |
| Local filesystem hosting | A file-system sink, a run folder helper and a run log attachment, kept apart from the core |

What the design leaves room for: restarting a run from a given step, a sequence number inside a
step, ordered work item folders, trace ids, a production blob storage sink and a C# twin (see
[what the design makes easy later](#what-the-design-makes-easy-later)).

## Design

### The model

```
PipelineRun            one execution; owns the sink, the logger, the manifest
  WorkItemScope        the thing being processed (a document, a request, a batch row)
    StepScope          one step; may contain child StepScopes
```

`WorkItem` is the generic name for whatever a pipeline processes. It can be a document, a request, a
batch row or anything else with an identity and a name.

`StepHostProtocol` is the small protocol that `WorkItemScope` and `StepScope` share. It has two
methods, `step(step) -> StepScope` and `skipped(step, reason)`. A reusable engine accepts a
`StepHostProtocol` and opens its own steps on it, so the same engine can run as the whole pipeline or
inside another step.

A scope travels **as an argument**. It replaces the four parameters every step used to take (logger,
artifact sink, work item and step number), and it is never kept on a long-lived object.

### Step identity

```python
LOAD_PAGES      = Step(1, "Load Pages")
DETECT_SECTIONS = Step(2, "Detect Sections")
```

`Step` is a frozen value: an integer `step_number` relative to its parent, a display `name`, and a
stable machine `key`. The key is derived from the name unless one is requested. The absolute number
is the path of numbers down the scope tree, so a step numbered 3 inside step 2 is 2.3 in banners,
attributes and filenames. Nothing parses the number from text and nothing converts it to a float.

Dashboards and alerts should use `pipeline.step.key`, never the number, so renumbering a pipeline
breaks nothing.

### Boundaries and progress

```python
async with step_host.step(DETECT_SECTIONS) as step_scope:
    step_scope.info("Detecting sections", pages=14, concurrency=5)
    ...
    await step_scope.emit(DETECTED_SECTIONS, payload, discriminator="page_0003")
    step_scope.outcome("Detected 4 sections", sections=4)
```

- STARTED on entry. COMPLETE on a clean exit, with elapsed time and the outcome.
- FAILED when an exception escapes, with elapsed time, the exception type and message, and no
  traceback. The exception is logged once, at the host's outer boundary. A failed step is a
  breadcrumb saying where the run stopped, so it logs at WARNING.
- SKIPPED through `skipped(step, reason)` for conditional steps.
- When the escaping exception has `add_contextual_data`, the failing step's number, name and key are
  added once, innermost step first.

### Log records

One record per event. The message is one clean line. Named attributes ride on the record through
the standard `extra` argument, so any handler receives them.

| Attribute | Example |
|---|---|
| `pipeline.name` | `invoice-field-extraction` |
| `pipeline.run.id` | `20260917_140322_a1b2c3d4` |
| `pipeline.work_item.id` / `.name` | `7f3c...` / `Contract 12.pdf` |
| `pipeline.step.number` | `2.3` |
| `pipeline.step.name` / `.key` | `Metadata Audit` / `metadata_audit` |
| `pipeline.event` | boundary records only: `run`, `work_item` or `step` |
| `pipeline.status` | boundary records only: `STARTED`, `COMPLETE`, `FAILED`, `SKIPPED` |
| `pipeline.elapsed_seconds` | `3.214`, on COMPLETE and FAILED |
| `pipeline.outcome` | the step's summary, or the reason it was skipped |
| `pipeline.artifact.kind` / `.filename` / `.bytes` | on the record written when an artifact is emitted |
| `pipeline.failure.type` / `.message` | on FAILED only |
| `pipeline.detail.<name>` | fields from `info(..., pages=14)`, namespaced so they cannot collide with `LogRecord` attributes |

A query for every failed step is `pipeline.event == "step" and pipeline.status == "FAILED"`.

Caller attributes such as a user name, a trace id or a span id are merged into every record from the
run and work item levels.

The 80-column banner is presentation. `BreadcrumbFormatter` draws it for boundary records only.
The record itself stays one line, so a structured sink never sees separators or embedded newlines.

### Time is a logging-end decision

The core never formats a time and never decides whether one is shown. Every `LogRecord` already
carries its creation time, so the information exists. Whether to display it is the formatter's single
setting, `TimeDisplay`:

- `NONE`: no time anywhere.
- `BOUNDARIES` (the default): the time appears in the banner header only, for example
  `STEP 2: Detect Sections - STARTED (10:54:29)`. Progress lines between boundaries carry nothing extra.
- `ALL`: every line is prefixed with a time, for anyone who wants to spot a stall from a gap.

A host with a different handler (Application Insights, JSON lines) ignores the setting and still
receives the timestamp as the record's own.

### The `pipeline.` prefix

`pipeline` is a namespace this library chose. No standard defines it. It keeps these keys from colliding
with attributes other libraries add (`http.*`, `db.*`), the way OpenTelemetry's own keys are namespaced.
The prefix is fixed on purpose: the value of a shared vocabulary is that one query works across every
pipeline built on it. What differs between pipelines is a value, `pipeline.name`, which the host supplies
once when it creates the run.

### Fit with OpenTelemetry and Application Insights

Application Insights is a feature of Azure Monitor, not a separate service. The "Azure Monitor" in the
Python package name (`azure-monitor-opentelemetry`) is the product family. A host uses the same
Application Insights resource and connection string as before. Billing is by data ingested, with the first
5 GB per month per billing account free and no separate charge for Application Insights or the SDK
(Microsoft pricing page, checked 2026-10-03). Python log records become `traces` rows, and `extra`
entries become custom dimensions (Microsoft Learn, "Add and modify Azure Monitor OpenTelemetry").

- The library has no OpenTelemetry dependency. Attributes travel as `extra`.
- The host calls `configure_azure_monitor(logger_name=...)` once, naming the logger the pipeline logs
  through. That call is the whole integration.
- Trace and span ids are not modelled. `PipelineRun(attributes=...)` is the one seam: add a trace id
  there, or let an OpenTelemetry handler stamp the records, and nothing else changes.
- Exception contextual data keeps its own keys, so the two meet in the same record without renaming either.

### Artifacts

```python
PAGE_EVIDENCE = ArtifactKind("page_evidence", "json", "application/json")
FINAL_REPORT  = ArtifactKind("final_report", "md", "text/markdown", role=ArtifactRole.OUTPUT)
```

- A pipeline declares its `ArtifactKind` values once, as constants. Vague keys (`result`, `output`,
  `data`, `artifact`, `payload`) are refused when the kind is constructed, because a file called
  `result` cannot be found again.
- `role` is `INTERIM` (the default) or `OUTPUT`. It is information about the artifact, recorded in the
  manifest, so a host can apply its own retention rules. It never decides whether the artifact is kept.
- There are two kinds of artifact. A `StepArtifact` belongs to one step of one work item. A `RunArtifact`,
  such as the manifest, belongs to the run. `Artifact` is their union, so a sink never meets an optional
  work item. Both expose `artifact_type`, `content_type`, `content` and `filename`.
- An artifact derives its own filename, so no caller composes names.
- The sink is a class that implements `ArtifactSinkProtocol`, which has one method:
  `async def persist(self, artifact: Artifact) -> None`. The application builds the sink and hands it
  to `PipelineRun`. The library ships `FileSystemArtifactSink` and, for tests, `ArtifactRecorder`. The
  demo adds `BlobStorageArtifactSink`, a stand-in for a storage container. The choice of a class over
  a callback is explained in [the next section](#decision-how-the-host-receives-artifacts).
- A sink that raises is translated to `ArtifactSinkError`, which carries the artifact's identity, so a
  storage outage does not read as a failure in the pipeline's logic. An implementation raises whatever
  error is natural for its destination, and the run does the wrapping.
- Steps never know where a file lands. They call `emit`, and the host owns the sink.
- **Emit before you validate.** Capture a raw model reply before parsing it, so that a parse failure
  leaves its evidence on disk.

### Decision: how the host receives artifacts

A step emits an artifact, and something the host controls has to persist it. The library needs one
contract for that, and there are two reasonable shapes for it.

**Option 1: a callback.** The host passes an async function, `Callable[[Artifact], Awaitable[None]]`.
It is the smallest possible contract, and a lambda or a local function is enough for a test.

**Option 2: a class that implements a protocol.** The host passes an object with one method,
`persist(artifact)`, declared by `ArtifactSinkProtocol`. The file-system sink, the blob-storage sink and
the in-memory test recorder are three classes with the same method.

| | Callback | Class implementing a protocol |
|---|---|---|
| Lifetime and state | None of its own. A claimed-folder registry, a container client or a connection has to be captured in a closure or kept somewhere else. | The class owns that state and has a clear lifetime. |
| Readability | A delegate type with no name for what it does. Finding the implementations means searching for a signature. | A named type with a named method. Implementations are found by name. |
| Swapping | Possible, but the application swaps a function where it swaps every other service as an object. | The application replaces one implementation with another the way it replaces any service it composes. |
| Testing | A lambda that appends to a list. | An in-memory implementation, `ArtifactRecorder`, with helper methods for assertions. |

**Decision: the class.** Lifetime and state decided it. Every real sink keeps something between calls, so
a callback would end up as a closure standing in for a class. The remaining rows point the same way, and
the library already uses protocols for its other seams (`StepHostProtocol`, `ModelGatewayProtocol` and
`ContextualExceptionProtocol`), so a sink follows the same convention.

Consequences:

- The library accepts only the protocol. Offering both forms would give the contract two ways to do one
  thing, and every place that calls the sink would have to handle both.
- The method name is `persist`, and the parameter on `PipelineRun` is `artifact_sink`, so the call site
  names its type.
- A sink raises whatever error is natural for its destination. `RunContext.persist` wraps it in
  `ArtifactSinkError`, which keeps the artifact's identity.

### Run folder and manifest

Each run gets its own folder, `<root>/<yyyymmdd_hhmmss>_<label>/`, holding `run.log` (when the host
attaches one), a folder per work item, and `manifest.json`. The `label` is chosen by the host: the file
name for a single-file run, `batch` for several. If two runs start in the same second, the second folder
gets a numeric suffix. The time is local, so the folder name, the run id and the banner times agree.

A single-file run repeats the file name once inside the run folder. The layout is the same for one file
and for a batch, so no reader has to ask which shape a run took.

The manifest is emitted through the same sink as a run-level artifact. It records, per work item, the
status, each step's number, name, status, elapsed time and outcome, the artifacts produced and their
sizes, and any failure.

Host-side helpers (`FileSystemArtifactSink`, run folder creation, run log attachment) live in
`pipeline_breadcrumbs.hosting`. The core knows no paths.

A hosted run does not keep its artifacts in a run folder. The demo's blob stand-in names each artifact
as a blob, `<run name>/<work item>/<filename>`, with the manifest directly under the run name. The
filenames, and so the step order, are the same as in a local folder.

### Where the run happens: local and hosted

The system behaves identically wherever it runs. The application around it decides two things, and
only these two:

1. **Where artifacts go.** The application picks the sink implementation: the file-system sink while
   developing, a blob-storage sink in production. Either one receives every artifact.
2. **Who listens to the log.** The application creates one logger, or is handed one by a calling
   application, and the system shares that single instance. Each destination is a handler with its own
   level.

| | Local | Hosted |
|---|---|---|
| Artifacts | every one, to the file-system sink | every one, to the blob-storage sink |
| Console or process log | informational and above | informational and above (the platform keeps it) |
| `run.log` beside the artifacts | yes | no |
| Application Insights | not attached | exceptions only, at error level |

Informational lines (step 1 started, timings, progress) stay in local and platform logs. Sending them
to Application Insights is an explicit choice someone makes by attaching a handler for it. The system
never knows which handlers exist.

This follows how long-running pipelines on Azure ML are operated. The platform keeps the pipeline's own
logs, which show where the run is and how long things took, and only exceptions go to Application
Insights. The need for informational logs comes from long runs. A request and response service rarely
needs them.

### Exceptions

The library does not own an exception hierarchy. It works with the one in the Meridian Python codebase
(business and technical branches, severity, action and contextual data) through structure alone: any
exception that has `contextual_data_by_name` and `add_contextual_data` takes part. The protocol is
`ContextualExceptionProtocol`. The library's own exception, `ArtifactSinkError`, has the same shape.

The policy is the one the Meridian reference uses. Steps leave breadcrumbs and do not log tracebacks.
The exception is logged once, at the application's outer boundary, with its traceback and every named
fact it carries.

### Testing

The tests are acceptance tests. Each one runs through a public entry point and checks what the system
returned, the artifacts it handed to the sink and the breadcrumbs it logged. Only the model is
replaced. They follow the PWI guidance for functional acceptance testing at the boundary, using the
Meridian tests as the reference: behavior-style names, Arrange, Act and Assert sections, `expected_` and
`actual_` prefixes, and asserters that report every difference at once.

`pipeline_breadcrumbs.testing` provides `ArtifactRecorder` (use it as the sink, then assert which steps
ran and which artifacts exist) and `RecordCapture` (a logging handler that keeps records for attribute
assertions). Artifact presence is itself a signal: a remediation step that emits only when triggered is
diagnosed by whether its file exists.

## Decisions: why this, why not that

| Decision | Why | What was rejected |
|---|---|---|
| A scope is passed as an argument | One object carries the logger, the sink, the work item and the step position, so a step has one parameter. An engine nests unchanged. | Passing four values to every step; an ambient or global context |
| One logger, shared by the system, owned by the application | There is one place to attach handlers and one place to filter. A calling application can pass its own logger in. | A logger created by each component; a process-wide singleton |
| Step path is a tuple of integers | `float("2.10")` is `2.1`, so a float logs the tenth sub-step as the first. A tuple sorts numerically and never goes through text. | Floats; strings parsed back into numbers |
| `key` is separate from `step_number` | Alerts and dashboards should survive a renumbering. | Using the number as the identity |
| One log record per event; the banner is presentation | A structured sink gets a clean message and attributes. The text banner is drawn only by the formatter. | Four log calls per banner, with embedded newlines and separators |
| Fixed `pipeline.` prefix | One query works across every pipeline built on the vocabulary. | A prefix per pipeline |
| No OpenTelemetry dependency | The library stays small; `extra` already reaches any handler. | Importing the SDK to set span attributes |
| Time is the formatter's setting | A time on every line is clutter. The record already has its time. | Baking a time into the message |
| Filenames derive from the artifact | No caller composes names, so they cannot drift. | A name chosen by each step |
| A work item's files share one folder | An alphabetical listing is the step order. | Subfolders by kind, which split a step's files and put folders ahead of step 1 |
| Zero-padded step path in the name | `02.10` sorts after `02.09`. | Unpadded numbers |
| Artifacts always persisted | They are the record of what a step did, and a later run could start from them. | A production mode that keeps only outputs |
| Role is information | Hosts can apply retention rules, such as colder storage for interim files. | Using the role as a filter |
| Emit before validate | A malformed reply is the evidence you most need. | Emitting only after a successful parse |
| The sink is a class that implements `ArtifactSinkProtocol` | A sink keeps state across calls, and a class owns it. The pipeline never knows whether files go to disk or blob storage. See [the decision](#decision-how-the-host-receives-artifacts). | A bare async callback; a storage path or client inside the steps |
| Sink failures become `ArtifactSinkError` | A storage outage should not read as a bug in the pipeline's logic. | Letting the raw exception escape |
| One folder per run, timestamp in the name | A repeat run never overwrites an earlier one. | A fixed output folder, cleaned by hand |
| The manifest is built from immutable events | No record is edited after it is made. A retry or a per-page step keeps every opening. | Mutable records edited in place, which let a reopened id erase the first attempt |
| Failure context is added to the exception | The failing step's identity travels with the exception to the place it is logged. | Logging at every step, which repeats the traceback |
| The exception is logged once, at the outer boundary | One traceback, with all its facts. | Log and rethrow at each level |
| Exceptions take part by shape | The library works with any hierarchy that offers contextual data. | A base exception class owned by the library |
| Async only | Pipelines of consequence await model calls, and production persistence is network I/O. | A synchronous twin; one of the projects the pattern evolved through was synchronous and would wrap the library |
| Per-page work gathers every result, then raises the first failure in page order | Every raw reply is on disk when the step fails. | A task group, which cancels siblings and wraps the error in an exception group |
| Host helpers are separate from the core | The core knows no paths. | Filesystem code inside the scopes |
| The application is not the system | The application picks the sink and the handlers. The system has one public method that only sequences. | Putting steps in `main.py` |
| Acceptance tests at the boundary | They keep working when the inside is reorganized, which this design did several times. | Unit tests of each class |
| Local time for the run clock | Folder names, run ids and banner times agree. | UTC folder names beside local banner times |

## What building it taught

- **A field named `message` broke `step.info`.** A caller's field shares a namespace with the method's
  own parameters, so `step.info("x", message="y")` failed. The message parameter is now positional-only,
  so any field name works. A test covers `name`, `message` and `filename`.
- **The system clock is local time.** The first run named its folder in UTC while the banner showed local
  time, four hours apart. `Clock.system()` now returns local, timezone-aware time.
- **One leading blank line per banner.** Banners with a blank line on both sides doubled the gap
  between consecutive banners.
- **A cause chain prints two "Traceback" headings.** That is one logged exception, not two log sites.
- **Per-unit steps need all their evidence before they fail.** The demo gathers every page, then raises
  the first failure in page order, so every raw reply is on disk.
- **Subfolders by kind broke the ordering.** See [why the file names are the point](#why-the-file-names-are-the-point).
- **Keying the manifest by id or step path lost history.** A retry replaced the first attempt, and a
  step opened once per page kept only the last page. A quick PWI review caught it. Each opening now has
  its own record.
- **A hostile model reply must still be one error.** A reply with a number thousands of digits long, or
  nesting deeper than the parser allows, raised a different exception than a malformed reply did. All of
  them end as `ModelResponseParseError`, with the page.

### Revisions after the first PWI review

The first full PWI review of this workspace produced 168 findings, which drove these changes.

- Manifest records are frozen. Scopes record immutable events, and the manifest is folded from them.
- `Artifact` is the union of `StepArtifact` and `RunArtifact`.
- `Step` takes `requested_key`, and `key` is always a validated non-empty string.
- Protocols end in `Protocol`.
- Variables are named for their type, and statuses and numbers carry their role.
- In the demo, the three classification processors live one folder below `SectionClassifier`, and
  `ModelReply` is an immutable value object that owns the parsed reply, so no processor depends on a
  parser above it. `DocumentAnalysisManager` validates its input first.
- Acceptance tests replace the unit tests.

Findings left open on purpose, because removing them would cost clarity more than it gains:

- Scopes, `PipelineRun`, `RunRecorder` and `FileSystemArtifactSink` still hold lifecycle state: a start
  time, a step's outcome, an append-only event list, the folder registry. A context manager cannot be
  stateless.
- `ArtifactSinkError` and `DocumentAnalysisError` accumulate contextual data as they propagate, the way
  the Meridian exception base does.
- `StepScope` keeps its run context instead of receiving the artifact sink on every `emit`.

Open: each emitted artifact logs one informational line. That is right for a local trail, and the
manifest lists them all anyway. With hundreds of per-page artifacts per document, a host that sends
informational lines to Application Insights may want to filter those lines at its handler. The
`pipeline.artifact.*` attributes make that a one-line filter.

## What the design makes easy later

### Restart from a step

This is a design option, not a feature of the project. In normal operation, steps pass results to the
next step in memory, as local variables. That is how the code should be written.

For an expensive pipeline, where model calls cost tokens and time, a host may want to resume after a
failure instead of paying for the steps that already succeeded. The change needed is small and local:

1. The orchestrating method accepts the step to start from.
2. For the steps before it, the method reads each step's artifact in place of the in-memory value.
3. The steps from there on run as usual.

```python
# A sketch, not built.
async def analyze_document(self, step_host: StepHostProtocol, pages: list[str], *, start_at_step: int = 1) -> DocumentAnalysis:
    loaded_pages = pages if start_at_step > 1 else await self._page_loader.load(step_host, pages)
    detected_sections = (
        await self._artifact_reader.read_detected_sections(...) if start_at_step > 2
        else await self._section_detector.detect(step_host, loaded_pages)
    )
    ...
```

Three properties of the existing design make this a modest change:

- Every artifact is persisted, in every environment, so the earlier steps' results exist.
- Artifacts are named by work item and step, so the file for a given step is easy to find.
- The step's summary files (`detected_sections.json`, `section_scores.json`) hold complete results.
  The raw replies are evidence rather than inputs.

What the change would add: a way to read an artifact back, and an agreement that a step's saved result is
complete enough to resume from. It is not a rewrite.

### Other changes the design leaves room for

- **A sequence number inside a step**, so the listing order matches the writing order (the raw replies
  before the summary). A small change to how an artifact derives its name.
- **Ordered work item folders**, if the processing order should show at the top of a run.
- **Trace and span ids**, through the existing attribute seam on `PipelineRun`.
- **A production blob storage sink**, as another class that implements `ArtifactSinkProtocol`, built on the
  storage SDK's container client. The demo's `BlobStorageArtifactSink` already shows the shape. Nothing
  else changes.
- **Filtering the per-artifact log line** at an Application Insights handler.
- **A C# twin.** Nothing here depends on Python: a frozen `Step`, `ArtifactKind` and artifact types, an
  async sink interface (an `IArtifactSink` with `Task PersistAsync(Artifact artifact)`), a scope tree
  built on `IAsyncDisposable`, and `ILogger` message templates with named properties, which is how Application Insights receives the same attributes. The articles and the
  two repositories will link to each other.

## The demo

The demo is laid out like a production codebase, because a reference that people copy should show the
levels of abstraction a real system has.

```
main.py                           the application: chooses the sink and the log handlers, calls the system
blob_storage_artifact_sink.py     a stand-in for blob storage: an ArtifactSinkProtocol implementation
telemetry.py                      a stand-in for Application Insights that records exceptions only
document_analysis/                the system
  document_analysis_manager.py    its entry point: validates, then sequences four processors
  analysis_steps.py               every Step, declared in one place
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

- **The application is not the system.** `main.py` chooses the artifact sink and builds the logger, opens the
  run and one work item per document, calls the system and logs a failure once at its outer boundary.
  It contains no steps.
- **The manager has one public method that only sequences.** It passes each processor's result to the next
  and does no work itself.
- **Each processor owns its step.** It opens its step on the host it is given. The `Step` declarations
  stay together in `analysis_steps.py` as the system's table of contents, so the numbers read as one
  list and cannot be duplicated by accident.
- **A sub-orchestrator passes its own step down as the host.** `SectionClassifier` opens step 3 and hands
  that scope to three processors. That is the whole mechanism behind 3.1, 3.2 and 3.3.
- **Realistic processors, no outbound calls.** Model processors call a `ModelGatewayProtocol`. The fake
  sleeps instead of calling out. Non-model processors call `SimulatedWork`. Both mark where real work
  would go. Model processors log the way real ones do: a start line, progress lines with counts and
  identifiers, the raw reply emitted before it is validated, and a closing outcome.
- **Two hosts.** `--host local` is the default. It writes a run log and hands the system the file-system
  sink. `--host hosted` hands it the blob-storage stand-in and sends only exceptions to telemetry. Both
  persist every artifact.

```bash
uv run pipeline_breadcrumbs_app                       # local: a clean run of two documents
uv run pipeline_breadcrumbs_app --fail-page 2         # a malformed model reply fails one document
uv run pipeline_breadcrumbs_app --host hosted         # only exceptions go to telemetry
```

## How the design evolved

The pattern began in one project in late 2025 as a typed artifact enum, an artifact callback and a
step-banner logger. Six more projects reworked it, each fixing something the last one showed. In rough
order, these are the moves that were made and whether they survived into this design:

| Move | Kept? |
|---|---|
| Put the step number in the artifact filename, so the folder sorts in pipeline order | Yes, zero-padded |
| A timing context that logs STARTED and COMPLETE with elapsed time and an outcome | Yes, with FAILED added |
| Emit the raw model output before validating it | Yes, as a stated rule |
| The artifact derives its own filename | Yes |
| Steps own their number and name | Yes, as one declared value |
| A helper that renumbers a child engine's steps under a parent step | Yes, as nesting |
| Inject the logger instead of using a singleton | Yes |
| A discriminator for per-page artifacts | Yes |
| A strict parse error for a malformed step name | No longer needed, because nothing is parsed |
| A test recorder that asserts which steps ran | Yes |

Defects found along the way and designed out:

- The step number was stored twice, once as a constant and once inside the log string.
- `float("2.10")` is `2.1`, so a tenth sub-step logged as the wrong step.
- Step names were parsed out of PascalCase strings, with silent fallbacks on a bad name.
- A step that raised logged nothing at its boundary.
- Files from different runs mixed in one folder.
- Run-level summaries needed a fake zero-GUID document to fit the artifact model.
- Four log calls per banner, so one boundary was four records with embedded newlines.
- Backward-compatibility overloads and legacy enum members.
- The begin, emit, end sequence was repeated by hand nine times in one engine.

Dropped on purpose: the backward-compatibility overloads, legacy enum members, `Stage_`, `Step_` and
`Phase_` vocabulary drift, PascalCase parsing, the process-wide logger singleton, floats as step numbers
and the separate debug-artifact callback. A debug artifact is just an artifact kind.
