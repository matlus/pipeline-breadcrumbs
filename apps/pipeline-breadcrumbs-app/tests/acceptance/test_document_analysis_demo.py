# Acceptance tests for the demo application as a whole: `run_demo` builds the callback and the
# logger, runs the system over the sample documents and returns where the trail landed. The
# observations are the files and the log the run left behind, read the way an engineer would.
# The model is the application's fake, with no delay.

import logging
from pathlib import Path
from typing import Any

import pytest
from analysis_acceptance_support.asserters.asserter_run_folder import AsserterRunFolder

from pipeline_breadcrumbs import TimeDisplay
from pipeline_breadcrumbs_app.main import DemoResult, HostProfile, run_demo
from pipeline_breadcrumbs_app.sample_documents import InvalidFailPageError

NO_DELAY_SECONDS: float = 0.0


@pytest.mark.acceptance
class TestDemoRunExpectedPaths:
    async def test_run_demo_WhenTheSampleDocumentsAreAnalyzed_ThenTheTrailIsOrderedAndComplete(self, tmp_path: Path) -> None:
        # Arrange / Act
        actual_demo_result: DemoResult = await run_demo(tmp_path, time_display=TimeDisplay.NONE, pace_seconds=NO_DELAY_SECONDS)

        # Assert
        assert actual_demo_result.failed_work_items == []
        actual_manifest: dict[str, Any] = AsserterRunFolder.read_manifest(actual_demo_result.run_directory)
        assert actual_manifest["run_status"] == "COMPLETE"
        assert actual_manifest["pipeline_name"] == "document-analysis-demo"
        AsserterRunFolder.assert_step_statuses(
            {"1": "COMPLETE", "2": "COMPLETE", "3": "COMPLETE", "3.1": "COMPLETE", "3.2": "COMPLETE", "3.3": "COMPLETE", "4": "COMPLETE"},
            "Contract 12.pdf",
            actual_manifest,
        )

    async def test_run_demo_WhenNoSectionIsDoubtful_ThenTheConditionalStepIsSkippedAndLeavesNoArtifact(self, tmp_path: Path) -> None:
        # Arrange / Act
        actual_demo_result: DemoResult = await run_demo(tmp_path, time_display=TimeDisplay.NONE, pace_seconds=NO_DELAY_SECONDS)

        # Assert - the lease has no doubtful section; the contract has one
        actual_manifest: dict[str, Any] = AsserterRunFolder.read_manifest(actual_demo_result.run_directory)
        actual_lease: dict[str, Any] = AsserterRunFolder.find_work_item("Lease 4.pdf", actual_manifest)
        actual_contract: dict[str, Any] = AsserterRunFolder.find_work_item("Contract 12.pdf", actual_manifest)
        assert {actual_step["path"]: actual_step["step_status"] for actual_step in actual_lease["step_records"]}["3.3"] == "SKIPPED"
        assert not any("reconciled_scores" in actual_artifact["filename"] for actual_artifact in actual_lease["artifact_records"])
        assert any("reconciled_scores" in actual_artifact["filename"] for actual_artifact in actual_contract["artifact_records"])

    async def test_run_demo_WhenTheRunFinishes_ThenTheRunFolderHoldsTheLogTheManifestAndAFolderPerWorkItem(self, tmp_path: Path) -> None:
        # Arrange / Act
        actual_demo_result: DemoResult = await run_demo(tmp_path, time_display=TimeDisplay.NONE, pace_seconds=NO_DELAY_SECONDS)

        # Assert
        AsserterRunFolder.assert_exactly_these_entries({"run.log", "manifest.json", "Contract 12", "Lease 4"}, actual_demo_result.run_directory)
        actual_contract_folder: Path = actual_demo_result.run_directory / "Contract 12"
        assert (actual_contract_folder / "Contract 12_step_04_analysis_report.md").read_text(encoding="utf-8").startswith("# Section analysis")
        assert (actual_contract_folder / "Contract 12_step_01_page_text_page_0000.txt").exists()
        assert (actual_contract_folder / "Contract 12_step_02_raw_detection_response_page_0003.txt").exists()

    async def test_run_demo_WhenAWorkItemFolderIsListedAlphabetically_ThenTheFilesAreInStepOrder(self, tmp_path: Path) -> None:
        # Arrange / Act
        actual_demo_result: DemoResult = await run_demo(tmp_path, time_display=TimeDisplay.NONE, pace_seconds=NO_DELAY_SECONDS)

        # Assert - the step path in each filename, read in the order an ordinary file listing shows them, never goes backwards
        actual_contract_folder: Path = actual_demo_result.run_directory / "Contract 12"
        actual_listing: list[str] = AsserterRunFolder.list_entry_names(actual_contract_folder)
        actual_step_paths: list[tuple[int, ...]] = AsserterRunFolder.read_step_paths_from_filenames(actual_listing)
        assert len(actual_step_paths) == len(actual_listing)
        assert actual_step_paths == sorted(actual_step_paths)
        assert actual_step_paths[0] == (1,)
        assert AsserterRunFolder.all_are_files(actual_contract_folder, actual_listing)

    async def test_run_demo_WhenTheRunFinishes_ThenTheRunLogReadsAsANumberedStory(self, tmp_path: Path) -> None:
        # Arrange / Act
        actual_demo_result: DemoResult = await run_demo(tmp_path, time_display=TimeDisplay.NONE, pace_seconds=NO_DELAY_SECONDS)

        # Assert
        actual_run_log: str = (actual_demo_result.run_directory / "run.log").read_text(encoding="utf-8")
        actual_first_document_boundaries: list[str] = [actual_line for actual_line in actual_run_log.splitlines() if actual_line.startswith("STEP ")][
            :14
        ]
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
        assert actual_first_document_boundaries == expected_first_document_boundaries

    async def test_run_demo_WhenTheSameDemoRunsTwice_ThenEachRunKeepsItsOwnFolder(self, tmp_path: Path) -> None:
        # Arrange / Act
        actual_first_result: DemoResult = await run_demo(tmp_path, time_display=TimeDisplay.NONE, pace_seconds=NO_DELAY_SECONDS)
        actual_second_result: DemoResult = await run_demo(tmp_path, time_display=TimeDisplay.NONE, pace_seconds=NO_DELAY_SECONDS)

        # Assert
        assert actual_first_result.run_directory != actual_second_result.run_directory
        assert (actual_first_result.run_directory / "manifest.json").exists()
        assert (actual_second_result.run_directory / "manifest.json").exists()


@pytest.mark.acceptance
class TestDemoRunFailures:
    async def test_run_demo_WhenAModelReplyIsMalformed_ThenOnlyThatDocumentFailsAndTheEvidenceIsKept(self, tmp_path: Path) -> None:
        # Arrange
        malformed_page_number: int = 2

        # Act
        actual_demo_result: DemoResult = await run_demo(
            tmp_path, fail_page=malformed_page_number, time_display=TimeDisplay.NONE, pace_seconds=NO_DELAY_SECONDS
        )

        # Assert
        assert actual_demo_result.failed_work_items == ["Contract 12.pdf"]
        actual_manifest: dict[str, Any] = AsserterRunFolder.read_manifest(actual_demo_result.run_directory)
        assert actual_manifest["run_status"] == "FAILED"
        AsserterRunFolder.assert_step_statuses({"1": "COMPLETE", "2": "FAILED"}, "Contract 12.pdf", actual_manifest)
        actual_contract: dict[str, Any] = AsserterRunFolder.find_work_item("Contract 12.pdf", actual_manifest)
        assert actual_contract["work_item_status"] == "FAILED"
        assert "ModelResponseParseError" in actual_contract["failure"]
        # Emit-before-validate: all four raw replies, including the malformed one, are on disk beside the replies that parsed.
        actual_contract_folder: Path = actual_demo_result.run_directory / "Contract 12"
        actual_raw_reply_names: list[str] = [
            actual_name for actual_name in AsserterRunFolder.list_entry_names(actual_contract_folder) if "raw_detection_response" in actual_name
        ]
        assert actual_raw_reply_names == [f"Contract 12_step_02_raw_detection_response_page_{page_number:04d}.txt" for page_number in range(4)]
        actual_malformed_reply: str = (actual_contract_folder / "Contract 12_step_02_raw_detection_response_page_0002.txt").read_text(
            encoding="utf-8"
        )
        assert actual_malformed_reply.startswith("Sure! Here is the JSON")
        # The failure did not stop the batch.
        assert AsserterRunFolder.find_work_item("Lease 4.pdf", actual_manifest)["work_item_status"] == "COMPLETE"

    async def test_run_demo_WhenADocumentFails_ThenTheApplicationLogsTheExceptionOnceWithEveryNamedFact(self, tmp_path: Path) -> None:
        # Arrange / Act
        actual_demo_result: DemoResult = await run_demo(tmp_path, fail_page=2, time_display=TimeDisplay.NONE, pace_seconds=NO_DELAY_SECONDS)

        # Assert
        actual_run_log: str = (actual_demo_result.run_directory / "run.log").read_text(encoding="utf-8")
        expected_host_log_line: str = "Work item 'Contract 12.pdf' failed:"
        assert actual_run_log.count(expected_host_log_line) == 1
        # The step and work item breadcrumbs name the failure but never print a traceback; the first one is the application's.
        assert actual_run_log.index("Traceback (most recent call last)") > actual_run_log.index(expected_host_log_line)
        for expected_fact in ("FailedAtStepNumber: 2", "FailedAtStepKey: detect_sections", "PageNumber: 2", "STEP 2: Detect Sections - FAILED"):
            assert expected_fact in actual_run_log

    async def test_run_demo_WhenTheFailingPageDoesNotExist_ThenItIsRefusedBeforeAnyFolderIsCreated(self, tmp_path: Path) -> None:
        # Arrange / Act / Assert
        with pytest.raises(InvalidFailPageError, match="does not exist"):
            await run_demo(tmp_path, fail_page=99, time_display=TimeDisplay.NONE, pace_seconds=NO_DELAY_SECONDS)
        assert AsserterRunFolder.list_entry_names(tmp_path) == []


@pytest.mark.acceptance
class TestDemoHosts:
    async def test_run_demo_WhenRunLocally_ThenTheRunFolderHoldsARunLogAndNoTelemetry(self, tmp_path: Path) -> None:
        # Arrange / Act
        actual_demo_result: DemoResult = await run_demo(
            tmp_path, fail_page=2, host_profile=HostProfile.LOCAL, time_display=TimeDisplay.NONE, pace_seconds=NO_DELAY_SECONDS
        )

        # Assert - a developer watching a local run keeps every informational line, and nothing is sent to telemetry
        AsserterRunFolder.assert_exactly_these_entries({"run.log", "manifest.json", "Contract 12", "Lease 4"}, actual_demo_result.run_directory)
        assert AsserterRunFolder.read_telemetry(actual_demo_result.run_directory) == []

    async def test_run_demo_WhenRunHosted_ThenEveryArtifactIsStillPersistedExactlyAsItIsLocally(self, tmp_path: Path) -> None:
        # Arrange / Act
        actual_local_result: DemoResult = await run_demo(
            tmp_path / "local", host_profile=HostProfile.LOCAL, time_display=TimeDisplay.NONE, pace_seconds=NO_DELAY_SECONDS
        )
        actual_hosted_result: DemoResult = await run_demo(
            tmp_path / "hosted", host_profile=HostProfile.HOSTED, time_display=TimeDisplay.NONE, pace_seconds=NO_DELAY_SECONDS
        )

        # Assert - the artifacts are the record of what each step did, so where the application runs never changes them
        for actual_work_item_folder_name in ("Contract 12", "Lease 4"):
            actual_local_listing: list[str] = AsserterRunFolder.list_entry_names(actual_local_result.run_directory / actual_work_item_folder_name)
            actual_hosted_listing: list[str] = AsserterRunFolder.list_entry_names(actual_hosted_result.run_directory / actual_work_item_folder_name)
            assert actual_hosted_listing == actual_local_listing
        AsserterRunFolder.assert_exactly_these_entries({"manifest.json", "Contract 12", "Lease 4"}, actual_hosted_result.run_directory)

    async def test_run_demo_WhenRunHostedWithoutAFailure_ThenNothingIsSentToTelemetry(self, tmp_path: Path) -> None:
        # Arrange / Act
        actual_demo_result: DemoResult = await run_demo(
            tmp_path, host_profile=HostProfile.HOSTED, time_display=TimeDisplay.NONE, pace_seconds=NO_DELAY_SECONDS
        )

        # Assert - the step started, step complete and timing lines are informational; they never reach telemetry
        assert AsserterRunFolder.read_telemetry(actual_demo_result.run_directory) == []

    async def test_run_demo_WhenRunHostedAndADocumentFails_ThenOnlyTheExceptionReachesTelemetryWithItsFacts(self, tmp_path: Path) -> None:
        # Arrange
        malformed_page_number: int = 2

        # Act
        actual_demo_result: DemoResult = await run_demo(
            tmp_path,
            fail_page=malformed_page_number,
            host_profile=HostProfile.HOSTED,
            time_display=TimeDisplay.NONE,
            pace_seconds=NO_DELAY_SECONDS,
        )

        # Assert - one exception, even though the failing step and its work item each logged a warning breadcrumb
        actual_telemetry: list[dict[str, Any]] = AsserterRunFolder.read_telemetry(actual_demo_result.run_directory)
        assert len(actual_telemetry) == 1
        actual_exception_telemetry: dict[str, Any] = actual_telemetry[0]
        assert actual_exception_telemetry["severity"] == "ERROR"
        assert actual_exception_telemetry["exception_type"] == "ModelResponseParseError"
        assert "Traceback" in actual_exception_telemetry["stack_trace"]
        actual_manifest: dict[str, Any] = AsserterRunFolder.read_manifest(actual_demo_result.run_directory)
        expected_custom_dimensions: dict[str, Any] = {
            "pipeline.name": "document-analysis-demo",
            "pipeline.run.id": actual_manifest["run_id"],
            "pipeline.work_item.name": "Contract 12.pdf",
            "PageNumber": malformed_page_number,
            "FailedAtStepNumber": "2",
            "FailedAtStepKey": "detect_sections",
        }
        actual_custom_dimensions: dict[str, Any] = actual_exception_telemetry["custom_dimensions"]
        for expected_name, expected_value in expected_custom_dimensions.items():
            assert actual_custom_dimensions[expected_name] == expected_value

    async def test_run_demo_WhenTheCallerSuppliesTheLogger_ThenTheSystemSharesThatOneLoggerAndItsHandlersAreRestored(
        self, tmp_path: Path, run_logger: logging.Logger, record_capture: Any
    ) -> None:
        # Arrange
        expected_handler_count: int = len(run_logger.handlers)

        # Act
        await run_demo(tmp_path, logger=run_logger, host_profile=HostProfile.HOSTED, fail_page=2, pace_seconds=NO_DELAY_SECONDS)

        # Assert - the caller's logger carried every record, the informational ones included, and was left as it was found
        actual_levels: set[int] = {actual_record.levelno for actual_record in record_capture.records}
        assert {logging.INFO, logging.WARNING, logging.ERROR} <= actual_levels
        assert len(run_logger.handlers) == expected_handler_count
