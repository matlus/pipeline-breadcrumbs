# Acceptance tests for the demo application as a whole: `run_demo` builds the artifact sink, the logger and
# the system (through ServiceLocatorDemo), runs it over the sample documents and returns where the trail
# landed. The observations are the files and the log the run left behind, read the way an engineer
# would. The model service is the demo's in-process simulator, with no delay.

import logging
from pathlib import Path
from typing import Final

import pytest
from analysis_acceptance_support.asserters.asserter_run_folder import (
    BlobNamesAsserter,
    DistinctRunFoldersAsserter,
    ExceptionTelemetryAsserter,
    ExpectedExceptionTelemetry,
    ExpectedHostedBlobs,
    ExpectedRunFailure,
    ExpectedRunOutcome,
    ExpectedWorkItemOutcome,
    FailureLogAsserter,
    RawRepliesAsserter,
    RunFailureAsserter,
    RunFolderEntriesAsserter,
    RunOutcomeAsserter,
    StepOrderAsserter,
    WorkItemContentsAsserter,
    WorkItemFilesAsserter,
)
from analysis_acceptance_support.asserters.asserter_shared_logger import SharedLoggerAsserter
from analysis_acceptance_support.run_folder_reader import RunFolderReader
from breadcrumbs_acceptance_support.asserters.asserter_exception import ExceptionAsserter, ExpectedException
from breadcrumbs_acceptance_support.clock_testing import ClockTesting

from pipeline_breadcrumbs import StepStatus, TimeDisplay
from pipeline_breadcrumbs.testing import RecordCapture
from pipeline_breadcrumbs_app.main import BLOB_CONTAINER_NAME, PIPELINE_NAME, DemoResult, DemoRunRequest, HostProfile, run_demo
from pipeline_breadcrumbs_app.sample_documents import InvalidFailPageException
from pipeline_breadcrumbs_app.telemetry import ExceptionTelemetry

NO_DELAY_SECONDS: Final[float] = 0.0
# The demo's sample documents and the folders the file-system sink gives them: a fixed specification, not incidental data.
CONTRACT_DOCUMENT_NAME: Final[str] = "Contract 12.pdf"
CONTRACT_FOLDER_NAME: Final[str] = "Contract 12"
LEASE_DOCUMENT_NAME: Final[str] = "Lease 4.pdf"
LEASE_FOLDER_NAME: Final[str] = "Lease 4"
MANIFEST_FILENAME: Final[str] = "manifest.json"
# The demo names each run folder `<yyyymmdd_hhmmss>_batch`, from the run's clock.
RUN_FOLDER_LABEL: Final[str] = "batch"
# Step 1 writes each page's text, so every document's first page leaves this file.
FIRST_PAGE_TEXT_FILENAME_SUFFIX: Final[str] = "_step_01_page_text_page_0000.txt"
RUN_LOG_FILENAME: Final[str] = "run.log"
REPORT_HEADING: Final[str] = "# Section analysis"
RECONCILED_SCORES_FRAGMENT: Final[str] = "reconciled_scores"
# The contract's third page is the demo's ambiguous section, and the page a malformed reply is injected on.
MALFORMED_PAGE_NUMBER: Final[int] = 2
CONTRACT_PAGE_COUNT: Final[int] = 4
EVERY_STEP_COMPLETE: Final[dict[str, str]] = {
    "1": "COMPLETE",
    "2": "COMPLETE",
    "3": "COMPLETE",
    "3.1": "COMPLETE",
    "3.2": "COMPLETE",
    "3.3": "COMPLETE",
    "4": "COMPLETE",
}


@pytest.mark.acceptance
class TestDemoRunExpectedPaths:
    async def test_run_demo_WhenTheSampleDocumentsAreAnalyzed_ThenTheRunAndEveryStepComplete(self, tmp_path: Path) -> None:
        # Arrange
        expected_run_outcome: ExpectedRunOutcome = ExpectedRunOutcome(
            pipeline_name=PIPELINE_NAME,
            run_status="COMPLETE",
            failed_work_item_names=[],
            work_item_outcomes=[ExpectedWorkItemOutcome(CONTRACT_DOCUMENT_NAME, "COMPLETE", EVERY_STEP_COMPLETE)],
        )

        # Act
        actual_demo_result: DemoResult = await run_demo(DemoRunRequest(tmp_path, time_display=TimeDisplay.NONE, pace_seconds=NO_DELAY_SECONDS))

        # Assert
        RunOutcomeAsserter.assert_expected_and_actual_are_equal(
            expected_run_outcome, actual_demo_result.failed_work_items, RunFolderReader.read_manifest(actual_demo_result.run_directory)
        )

    async def test_run_demo_WhenNoSectionIsDoubtful_ThenTheConditionalStepIsSkippedAndLeavesNoArtifact(self, tmp_path: Path) -> None:
        # Arrange - the lease has no doubtful section; the contract has one
        expected_run_outcome: ExpectedRunOutcome = ExpectedRunOutcome(
            pipeline_name=PIPELINE_NAME,
            run_status="COMPLETE",
            failed_work_item_names=[],
            work_item_outcomes=[
                ExpectedWorkItemOutcome(
                    LEASE_DOCUMENT_NAME,
                    "COMPLETE",
                    {**EVERY_STEP_COMPLETE, "3.3": "SKIPPED"},
                    absent_artifact_fragments=[RECONCILED_SCORES_FRAGMENT],
                ),
                ExpectedWorkItemOutcome(
                    CONTRACT_DOCUMENT_NAME, "COMPLETE", EVERY_STEP_COMPLETE, present_artifact_fragments=[RECONCILED_SCORES_FRAGMENT]
                ),
            ],
        )

        # Act
        actual_demo_result: DemoResult = await run_demo(DemoRunRequest(tmp_path, time_display=TimeDisplay.NONE, pace_seconds=NO_DELAY_SECONDS))

        # Assert
        RunOutcomeAsserter.assert_expected_and_actual_are_equal(
            expected_run_outcome, actual_demo_result.failed_work_items, RunFolderReader.read_manifest(actual_demo_result.run_directory)
        )

    async def test_run_demo_WhenTheRunFinishes_ThenTheRunFolderHoldsTheLogTheManifestAndAFolderPerWorkItem(self, tmp_path: Path) -> None:
        # Arrange
        expected_entry_names: set[str] = {RUN_LOG_FILENAME, MANIFEST_FILENAME, CONTRACT_FOLDER_NAME, LEASE_FOLDER_NAME}
        expected_file_start_by_filename: dict[str, str] = {
            f"{CONTRACT_FOLDER_NAME}_step_04_analysis_report.md": REPORT_HEADING,
            f"{CONTRACT_FOLDER_NAME}_step_01_page_text_page_0000.txt": "",
            f"{CONTRACT_FOLDER_NAME}_step_02_raw_detection_response_page_0003.txt": "",
        }

        # Act
        actual_demo_result: DemoResult = await run_demo(DemoRunRequest(tmp_path, time_display=TimeDisplay.NONE, pace_seconds=NO_DELAY_SECONDS))

        # Assert
        RunFolderEntriesAsserter.assert_expected_and_actual_are_equal(
            expected_entry_names, RunFolderReader.list_entry_names(actual_demo_result.run_directory)
        )
        WorkItemFilesAsserter.assert_expected_and_actual_are_equal(
            expected_file_start_by_filename, RunFolderReader.read_text_by_filename(actual_demo_result.run_directory / CONTRACT_FOLDER_NAME)
        )

    async def test_run_demo_WhenAWorkItemFolderIsListedAlphabetically_ThenTheFilesAreInStepOrder(self, tmp_path: Path) -> None:
        # Arrange
        expected_first_step_path: tuple[int, ...] = (1,)

        # Act
        actual_demo_result: DemoResult = await run_demo(DemoRunRequest(tmp_path, time_display=TimeDisplay.NONE, pace_seconds=NO_DELAY_SECONDS))

        # Assert - the step path in each filename, read in the order an ordinary file listing shows them, never goes backwards
        actual_contract_folder: Path = actual_demo_result.run_directory / CONTRACT_FOLDER_NAME
        StepOrderAsserter.assert_expected_and_actual_are_equal(
            expected_first_step_path,
            RunFolderReader.list_entry_names(actual_contract_folder),
            RunFolderReader.list_folder_names(actual_contract_folder),
        )

    async def test_run_demo_WhenTheRunFinishes_ThenTheRunLogReadsAsANumberedStory(self, tmp_path: Path) -> None:
        # Arrange
        expected_first_document_boundaries: list[str] = [
            "STEP 1: Load Pages - STARTED",
            "STEP 1: Load Pages - COMPLETE",
            "STEP 2: Detect Sections - STARTED",
            "STEP 2: Detect Sections - COMPLETE",
            "STEP 3: Classify Sections - STARTED",
            "STEP 3.1: Prepare Prompts - STARTED",
            "STEP 3.1: Prepare Prompts - COMPLETE",
            "STEP 3.2: Score Sections - STARTED",
            "STEP 3.2: Score Sections - COMPLETE",
            "STEP 3.3: Reconcile Low-Confidence Scores - STARTED",
            "STEP 3.3: Reconcile Low-Confidence Scores - COMPLETE",
            "STEP 3: Classify Sections - COMPLETE",
            "STEP 4: Assemble Report - STARTED",
            "STEP 4: Assemble Report - COMPLETE",
        ]

        # Act
        actual_demo_result: DemoResult = await run_demo(DemoRunRequest(tmp_path, time_display=TimeDisplay.NONE, pace_seconds=NO_DELAY_SECONDS))

        # Assert
        actual_run_log_lines: list[str] = RunFolderReader.read_run_log(actual_demo_result.run_directory).splitlines()
        actual_first_document_boundaries: list[str] = [actual_line for actual_line in actual_run_log_lines if actual_line.startswith("STEP ")][
            : len(expected_first_document_boundaries)
        ]
        assert actual_first_document_boundaries == expected_first_document_boundaries

    async def test_run_demo_WhenTheSameDemoRunsTwice_ThenEachRunKeepsItsOwnFolder(self, tmp_path: Path) -> None:
        # Arrange
        expected_manifest_filename: str = MANIFEST_FILENAME

        # Act
        actual_first_demo_result: DemoResult = await run_demo(DemoRunRequest(tmp_path, time_display=TimeDisplay.NONE, pace_seconds=NO_DELAY_SECONDS))
        actual_second_demo_result: DemoResult = await run_demo(DemoRunRequest(tmp_path, time_display=TimeDisplay.NONE, pace_seconds=NO_DELAY_SECONDS))

        # Assert
        actual_entry_names_by_run_directory: dict[Path, list[str]] = {
            actual_demo_result.run_directory: RunFolderReader.list_entry_names(actual_demo_result.run_directory)
            for actual_demo_result in (actual_first_demo_result, actual_second_demo_result)
        }
        DistinctRunFoldersAsserter.assert_expected_and_actual_are_equal(
            expected_manifest_filename,
            actual_first_demo_result.run_directory,
            actual_second_demo_result.run_directory,
            actual_entry_names_by_run_directory,
        )


@pytest.mark.acceptance
class TestDemoRunFailures:
    async def test_run_demo_WhenAModelReplyIsMalformed_ThenOnlyThatDocumentFailsAndTheEvidenceIsKept(self, tmp_path: Path) -> None:
        # Arrange
        expected_run_outcome: ExpectedRunOutcome = ExpectedRunOutcome(
            pipeline_name=PIPELINE_NAME,
            run_status="FAILED",
            failed_work_item_names=[CONTRACT_DOCUMENT_NAME],
            work_item_outcomes=[
                ExpectedWorkItemOutcome(
                    CONTRACT_DOCUMENT_NAME, "FAILED", {"1": "COMPLETE", "2": "FAILED"}, failure_phrase="ModelResponseParseException"
                ),
                # The failure did not stop the batch.
                ExpectedWorkItemOutcome(LEASE_DOCUMENT_NAME, "COMPLETE", {**EVERY_STEP_COMPLETE, "3.3": "SKIPPED"}),
            ],
        )
        # Emit-before-validate: all four raw replies, the malformed one included, are on disk beside the replies that parsed.
        raw_reply_filename_prefix: str = f"{CONTRACT_FOLDER_NAME}_step_02_raw_detection_response_page_"
        expected_raw_reply_filenames: list[str] = [f"{raw_reply_filename_prefix}{page_number:04d}.txt" for page_number in range(CONTRACT_PAGE_COUNT)]
        expected_reply_start_by_filename: dict[str, str] = {f"{raw_reply_filename_prefix}{MALFORMED_PAGE_NUMBER:04d}.txt": "Sure! Here is the JSON"}

        # Act
        actual_demo_result: DemoResult = await run_demo(
            DemoRunRequest(tmp_path, fail_page=MALFORMED_PAGE_NUMBER, time_display=TimeDisplay.NONE, pace_seconds=NO_DELAY_SECONDS)
        )

        # Assert
        RunOutcomeAsserter.assert_expected_and_actual_are_equal(
            expected_run_outcome, actual_demo_result.failed_work_items, RunFolderReader.read_manifest(actual_demo_result.run_directory)
        )
        RawRepliesAsserter.assert_expected_and_actual_are_equal(
            expected_raw_reply_filenames,
            expected_reply_start_by_filename,
            RunFolderReader.read_text_by_filename(actual_demo_result.run_directory / CONTRACT_FOLDER_NAME),
        )

    async def test_run_demo_WhenADocumentFails_ThenTheApplicationLogsTheExceptionOnceWithEveryNamedFact(self, tmp_path: Path) -> None:
        # Arrange
        expected_host_log_line: str = f"Work item '{CONTRACT_DOCUMENT_NAME}' failed:"
        expected_facts: list[str] = [
            "FailedAtStepNumber: 2",
            "FailedAtStepKey: detect_sections",
            f"PageNumber: {MALFORMED_PAGE_NUMBER}",
            "STEP 2: Detect Sections - FAILED",
        ]

        # Act
        actual_demo_result: DemoResult = await run_demo(
            DemoRunRequest(tmp_path, fail_page=MALFORMED_PAGE_NUMBER, time_display=TimeDisplay.NONE, pace_seconds=NO_DELAY_SECONDS)
        )

        # Assert - the step and work item breadcrumbs name the failure but never print a traceback; the first one is the application's
        FailureLogAsserter.assert_expected_and_actual_are_equal(
            expected_host_log_line, expected_facts, RunFolderReader.read_run_log(actual_demo_result.run_directory)
        )

    async def test_run_demo_WhenOnlyTheManifestCannotBePersistedAsTheRunCloses_ThenTheRunFailsAndTelemetryReceivesTheFailureOnce(
        self, tmp_path: Path
    ) -> None:
        # Arrange - a folder where the run's manifest blob belongs makes that one upload fail; every document's blobs persist
        clock_testing: ClockTesting = ClockTesting()
        run_folder_name: str = f"{clock_testing.clock.now():%Y%m%d_%H%M%S}_{RUN_FOLDER_LABEL}"
        (tmp_path / BLOB_CONTAINER_NAME / run_folder_name / MANIFEST_FILENAME).mkdir(parents=True)
        expected_run_failure: ExpectedRunFailure = ExpectedRunFailure(
            run_status=StepStatus.FAILED,
            failed_work_item_names=[],
            exception_telemetry=ExpectedExceptionTelemetry(
                severity="ERROR",
                exception_type="ArtifactSinkException",
                stack_trace_phrase="Traceback",
                custom_dimensions={"pipeline.name": PIPELINE_NAME, "ArtifactKind": "manifest", "ArtifactFilename": MANIFEST_FILENAME},
            ),
        )

        # Act
        actual_demo_result: DemoResult = await run_demo(
            DemoRunRequest(
                tmp_path,
                host_profile=HostProfile.HOSTED,
                time_display=TimeDisplay.NONE,
                pace_seconds=NO_DELAY_SECONDS,
                supplied_clock=clock_testing.clock,
            )
        )

        # Assert
        RunFailureAsserter.assert_expected_and_actual_are_equal(
            expected_run_failure,
            actual_demo_result.run_status,
            actual_demo_result.failed_work_items,
            RunFolderReader.read_exception_telemetry(actual_demo_result.run_directory),
        )

    async def test_run_demo_WhenTheFailingPageDoesNotExist_ThenItIsRefusedBeforeAnyFolderIsCreated(self, tmp_path: Path) -> None:
        # Arrange
        missing_page_number: int = 99
        expected_exception: ExpectedException = ExpectedException(
            InvalidFailPageException,
            message_phrases=[f"Page {missing_page_number} does not exist", CONTRACT_DOCUMENT_NAME],
            contextual_data_by_name={
                "ExceptionType": "InvalidFailPageException",
                "DocumentName": CONTRACT_DOCUMENT_NAME,
                "PageNumber": missing_page_number,
                "PageCount": CONTRACT_PAGE_COUNT,
            },
        )
        expected_entry_names: set[str] = set()

        # Act
        with pytest.raises(InvalidFailPageException) as actual_raised:
            await run_demo(DemoRunRequest(tmp_path, fail_page=missing_page_number, time_display=TimeDisplay.NONE, pace_seconds=NO_DELAY_SECONDS))

        # Assert
        ExceptionAsserter.assert_expected_and_actual_are_equal(expected_exception, actual_raised.value)
        RunFolderEntriesAsserter.assert_expected_and_actual_are_equal(expected_entry_names, RunFolderReader.list_entry_names(tmp_path))


@pytest.mark.acceptance
class TestDemoHosts:
    async def test_run_demo_WhenRunLocally_ThenTheRunFolderHoldsARunLogAndNoTelemetry(self, tmp_path: Path) -> None:
        # Arrange - a developer watching a local run keeps every informational line, and nothing is sent to telemetry
        expected_entry_names: set[str] = {RUN_LOG_FILENAME, MANIFEST_FILENAME, CONTRACT_FOLDER_NAME, LEASE_FOLDER_NAME}

        # Act
        actual_demo_result: DemoResult = await run_demo(
            DemoRunRequest(
                tmp_path,
                fail_page=MALFORMED_PAGE_NUMBER,
                host_profile=HostProfile.LOCAL,
                time_display=TimeDisplay.NONE,
                pace_seconds=NO_DELAY_SECONDS,
            )
        )

        # Assert - the exact entries leave no room for a telemetry file
        RunFolderEntriesAsserter.assert_expected_and_actual_are_equal(
            expected_entry_names, RunFolderReader.list_entry_names(actual_demo_result.run_directory)
        )

    async def test_run_demo_WhenRunHosted_ThenEveryArtifactIsStillPersistedExactlyAsItIsLocally(self, tmp_path: Path) -> None:
        # Arrange - the artifacts are the record of what each step did, so where the application runs never changes them
        expected_work_item_folder_names: list[str] = [CONTRACT_FOLDER_NAME, LEASE_FOLDER_NAME]
        expected_hosted_entry_names: set[str] = {MANIFEST_FILENAME, CONTRACT_FOLDER_NAME, LEASE_FOLDER_NAME}

        # Act
        actual_local_demo_result: DemoResult = await run_demo(
            DemoRunRequest(tmp_path / "local", host_profile=HostProfile.LOCAL, time_display=TimeDisplay.NONE, pace_seconds=NO_DELAY_SECONDS)
        )
        actual_hosted_demo_result: DemoResult = await run_demo(
            DemoRunRequest(tmp_path / "hosted", host_profile=HostProfile.HOSTED, time_display=TimeDisplay.NONE, pace_seconds=NO_DELAY_SECONDS)
        )

        # Assert
        actual_local_content_by_filename_by_folder_name: dict[str, dict[str, bytes]] = {
            folder_name: RunFolderReader.read_content_by_filename(actual_local_demo_result.artifact_directory / folder_name)
            for folder_name in RunFolderReader.list_folder_names(actual_local_demo_result.artifact_directory)
        }
        actual_hosted_content_by_filename_by_folder_name: dict[str, dict[str, bytes]] = {
            folder_name: RunFolderReader.read_content_by_filename(actual_hosted_demo_result.artifact_directory / folder_name)
            for folder_name in RunFolderReader.list_folder_names(actual_hosted_demo_result.artifact_directory)
        }
        WorkItemContentsAsserter.assert_expected_and_actual_are_equal(
            expected_work_item_folder_names, actual_local_content_by_filename_by_folder_name, actual_hosted_content_by_filename_by_folder_name
        )
        RunFolderEntriesAsserter.assert_expected_and_actual_are_equal(
            expected_hosted_entry_names, RunFolderReader.list_entry_names(actual_hosted_demo_result.artifact_directory)
        )

    async def test_run_demo_WhenRunHosted_ThenTheArtifactsAreUploadedAsBlobsNamedByRunAndWorkItemWithTheManifestAmongThem(
        self, tmp_path: Path
    ) -> None:
        # Arrange - the manifest sits directly under the run; a work item's blobs sit under its own name
        expected_container: Path = tmp_path / BLOB_CONTAINER_NAME
        expected_hosted_blobs: ExpectedHostedBlobs = ExpectedHostedBlobs(
            container=expected_container,
            blob_names_within_run={
                MANIFEST_FILENAME,
                f"{CONTRACT_FOLDER_NAME}/{CONTRACT_FOLDER_NAME}{FIRST_PAGE_TEXT_FILENAME_SUFFIX}",
                f"{LEASE_FOLDER_NAME}/{LEASE_FOLDER_NAME}{FIRST_PAGE_TEXT_FILENAME_SUFFIX}",
            },
        )

        # Act
        actual_demo_result: DemoResult = await run_demo(
            DemoRunRequest(tmp_path, host_profile=HostProfile.HOSTED, time_display=TimeDisplay.NONE, pace_seconds=NO_DELAY_SECONDS)
        )

        # Assert
        BlobNamesAsserter.assert_expected_and_actual_are_equal(
            expected_hosted_blobs,
            RunFolderReader.read_hosted_run_trail(expected_container, actual_demo_result.run_directory, actual_demo_result.artifact_directory),
        )

    async def test_run_demo_WhenRunHostedWithoutAFailure_ThenNothingIsSentToTelemetry(self, tmp_path: Path) -> None:
        # Arrange - the step started, step complete and timing lines are informational; they never reach telemetry
        expected_telemetry_count: int = 0

        # Act
        actual_demo_result: DemoResult = await run_demo(
            DemoRunRequest(tmp_path, host_profile=HostProfile.HOSTED, time_display=TimeDisplay.NONE, pace_seconds=NO_DELAY_SECONDS)
        )

        # Assert
        actual_exception_telemetry_records: list[ExceptionTelemetry] = RunFolderReader.read_exception_telemetry(actual_demo_result.run_directory)
        assert len(actual_exception_telemetry_records) == expected_telemetry_count

    async def test_run_demo_WhenRunHostedAndADocumentFails_ThenOnlyTheExceptionReachesTelemetryWithItsFacts(self, tmp_path: Path) -> None:
        # Arrange - one exception, even though the failing step and its work item each logged a warning breadcrumb
        expected_exception_telemetry: ExpectedExceptionTelemetry = ExpectedExceptionTelemetry(
            severity="ERROR",
            exception_type="ModelResponseParseException",
            stack_trace_phrase="Traceback",
            custom_dimensions={
                "pipeline.name": PIPELINE_NAME,
                "pipeline.work_item.name": CONTRACT_DOCUMENT_NAME,
                "PageNumber": MALFORMED_PAGE_NUMBER,
                "FailedAtStepNumber": "2",
                "FailedAtStepKey": "detect_sections",
            },
        )

        # Act
        actual_demo_result: DemoResult = await run_demo(
            DemoRunRequest(
                tmp_path,
                fail_page=MALFORMED_PAGE_NUMBER,
                host_profile=HostProfile.HOSTED,
                time_display=TimeDisplay.NONE,
                pace_seconds=NO_DELAY_SECONDS,
            )
        )

        # Assert
        actual_manifest_run_id: str = RunFolderReader.read_manifest(actual_demo_result.artifact_directory)["run_id"]
        ExceptionTelemetryAsserter.assert_expected_and_actual_are_equal(
            expected_exception_telemetry, RunFolderReader.read_exception_telemetry(actual_demo_result.run_directory), actual_manifest_run_id
        )

    async def test_run_demo_WhenTheCallerSuppliesTheLogger_ThenTheSystemSharesThatOneLoggerAndItsHandlersAreRestored(
        self, tmp_path: Path, run_logger: logging.Logger, record_capture: RecordCapture
    ) -> None:
        # Arrange
        expected_handler_count: int = len(run_logger.handlers)
        expected_levels: set[int] = {logging.INFO, logging.WARNING, logging.ERROR}

        # Act
        await run_demo(
            DemoRunRequest(tmp_path, host_profile=HostProfile.HOSTED, fail_page=MALFORMED_PAGE_NUMBER, pace_seconds=NO_DELAY_SECONDS),
            logger=run_logger,
        )

        # Assert - the caller's logger carried every record, the informational ones included, and was left as it was found
        actual_levels: set[int] = {actual_log_record.levelno for actual_log_record in record_capture.records}
        SharedLoggerAsserter.assert_expected_and_actual_are_equal(expected_levels, expected_handler_count, actual_levels, len(run_logger.handlers))
