# Acceptance tests for the document analysis system, through its one public entry point,
# DocumentAnalysisManager.analyze_document. The application's part is played the way an
# application plays it: open a run, open a work item, hand that scope to the system. Only the
# model is replaced (ModelGatewayTesting); the processors, the parsing, the library's scopes and
# the artifact callback all run for real. The observations are what the system returned, the
# artifacts it handed to the callback, and the breadcrumbs it logged.

import logging
from typing import Final

import pytest
from analysis_acceptance_support.analysis_scenarios import analyze_in_a_run, create_document_analysis_manager
from analysis_acceptance_support.asserters.asserter_analyzed_sections import AsserterAnalyzedSections
from analysis_acceptance_support.data_generators import create_page_texts, create_random_section_titles
from analysis_acceptance_support.model_gateway_testing import ModelGatewayTesting, create_score_reply, create_title_reply
from breadcrumbs_acceptance_support.asserters.asserter_artifacts import AsserterArtifacts
from breadcrumbs_acceptance_support.asserters.asserter_contextual_data import AsserterContextualData
from breadcrumbs_acceptance_support.asserters.asserter_step_boundaries import AsserterStepBoundaries, ExpectedStepBoundary
from breadcrumbs_acceptance_support.data_generators import create_random_work_item

from pipeline_breadcrumbs import ArtifactRole, AttributeKey, EventKind, StepArtifact, WorkItem
from pipeline_breadcrumbs.testing import ArtifactRecorder, RecordCapture
from pipeline_breadcrumbs_app.document_analysis.artifact_kinds import ANALYSIS_REPORT
from pipeline_breadcrumbs_app.document_analysis.document_analysis_manager import DocumentAnalysisManager
from pipeline_breadcrumbs_app.document_analysis.exceptions import DocumentValidationError, ModelResponseParseError
from pipeline_breadcrumbs_app.document_analysis.models import DocumentAnalysis, ScoredSection
from pipeline_breadcrumbs_app.document_analysis.processors.section_detector import MAX_CONCURRENCY

CONFIDENT: Final[float] = 0.92
DOUBTFUL: Final[float] = 0.55
RECONCILED: Final[float] = 0.81


def _create_confident_gateway(section_titles: list[str], category: str = "Legal") -> ModelGatewayTesting:
    return ModelGatewayTesting(
        detection_reply_by_page_number={page_number: create_title_reply(title) for page_number, title in enumerate(section_titles)},
        score_reply_by_title={title: create_score_reply(category, CONFIDENT) for title in section_titles},
    )


@pytest.mark.acceptance
class TestAnalyzeDocumentExpectedPaths:
    async def test_analyze_document_WhenEveryScoreIsConfident_ThenTheSectionsAreReturnedAndTheReconcileStepIsSkipped(
        self, artifact_recorder: ArtifactRecorder, run_logger: logging.Logger, record_capture: RecordCapture
    ) -> None:
        # Arrange
        work_item: WorkItem = create_random_work_item()
        section_titles: list[str] = create_random_section_titles(3)
        model_gateway_testing: ModelGatewayTesting = _create_confident_gateway(section_titles)
        document_analysis_manager: DocumentAnalysisManager = create_document_analysis_manager(model_gateway_testing)
        expected_scored_sections: list[ScoredSection] = [
            ScoredSection(page_number, title, "Legal", CONFIDENT) for page_number, title in enumerate(section_titles)
        ]

        # Act
        actual_document_analysis: DocumentAnalysis = await analyze_in_a_run(
            document_analysis_manager, create_page_texts(section_titles), work_item, artifact_recorder, run_logger
        )

        # Assert
        AsserterAnalyzedSections.assert_exactly_these_sections(expected_scored_sections, actual_document_analysis.sections)
        AsserterStepBoundaries.assert_exactly_these_step_boundaries(
            [
                ExpectedStepBoundary("1", "STARTED"),
                ExpectedStepBoundary("1", "COMPLETE"),
                ExpectedStepBoundary("2", "STARTED"),
                ExpectedStepBoundary("2", "COMPLETE"),
                ExpectedStepBoundary("3", "STARTED"),
                ExpectedStepBoundary("3.1", "STARTED"),
                ExpectedStepBoundary("3.1", "COMPLETE"),
                ExpectedStepBoundary("3.2", "STARTED"),
                ExpectedStepBoundary("3.2", "COMPLETE"),
                ExpectedStepBoundary("3.3", "SKIPPED"),
                ExpectedStepBoundary("3", "COMPLETE"),
                ExpectedStepBoundary("4", "STARTED"),
                ExpectedStepBoundary("4", "COMPLETE"),
            ],
            record_capture.records,
        )
        assert model_gateway_testing.asked_reconcile_titles == []

    async def test_analyze_document_WhenOneScoreIsDoubtful_ThenTheModelIsAskedAgainAndTheReconciledScoreIsReturned(
        self, artifact_recorder: ArtifactRecorder, run_logger: logging.Logger, record_capture: RecordCapture
    ) -> None:
        # Arrange
        work_item: WorkItem = create_random_work_item()
        section_titles: list[str] = create_random_section_titles(3)
        doubtful_title: str = section_titles[1]
        confident_category: str = "Legal"
        model_gateway_testing: ModelGatewayTesting = ModelGatewayTesting(
            detection_reply_by_page_number={page_number: create_title_reply(title) for page_number, title in enumerate(section_titles)},
            score_reply_by_title={
                title: create_score_reply(confident_category, DOUBTFUL if title == doubtful_title else CONFIDENT) for title in section_titles
            },
            reconcile_reply_by_title={doubtful_title: create_score_reply("Commercial", RECONCILED)},
        )
        document_analysis_manager: DocumentAnalysisManager = create_document_analysis_manager(model_gateway_testing)
        expected_scored_sections: list[ScoredSection] = [
            ScoredSection(0, section_titles[0], confident_category, CONFIDENT),
            ScoredSection(1, doubtful_title, "Commercial", RECONCILED),
            ScoredSection(2, section_titles[2], confident_category, CONFIDENT),
        ]

        # Act
        actual_document_analysis: DocumentAnalysis = await analyze_in_a_run(
            document_analysis_manager, create_page_texts(section_titles), work_item, artifact_recorder, run_logger
        )

        # Assert
        AsserterAnalyzedSections.assert_exactly_these_sections(expected_scored_sections, actual_document_analysis.sections)
        assert model_gateway_testing.asked_reconcile_titles == [doubtful_title]
        actual_step_boundaries: list[str] = [
            f"{RecordCapture.attribute(actual_record, AttributeKey.STEP_NUMBER)} {RecordCapture.attribute(actual_record, AttributeKey.STATUS)}"
            for actual_record in record_capture.boundaries(EventKind.STEP)
        ]
        assert "3.3 COMPLETE" in actual_step_boundaries
        assert "3.3 SKIPPED" not in actual_step_boundaries

    async def test_analyze_document_WhenTheDocumentIsAnalyzed_ThenEveryArtifactLandsInPipelineOrderWithTheReportAsTheOnlyOutput(
        self, artifact_recorder: ArtifactRecorder, run_logger: logging.Logger
    ) -> None:
        # Arrange
        work_item: WorkItem = create_random_work_item()
        section_titles: list[str] = create_random_section_titles(2)
        document_analysis_manager: DocumentAnalysisManager = create_document_analysis_manager(_create_confident_gateway(section_titles))
        stem: str = work_item.stem
        expected_analysis_report_filename: str = f"{stem}_step_04_analysis_report.md"
        expected_filenames: list[str] = [
            f"{stem}_step_01_page_text_page_0000.txt",
            f"{stem}_step_01_page_text_page_0001.txt",
            f"{stem}_step_02_raw_detection_response_page_0000.txt",
            f"{stem}_step_02_raw_detection_response_page_0001.txt",
            f"{stem}_step_02_detected_sections.json",
            f"{stem}_step_03.01_classification_prompts.json",
            f"{stem}_step_03.02_raw_score_response_page_0000.txt",
            f"{stem}_step_03.02_raw_score_response_page_0001.txt",
            f"{stem}_step_03.02_section_scores.json",
            expected_analysis_report_filename,
            "manifest.json",
        ]

        # Act
        await analyze_in_a_run(document_analysis_manager, create_page_texts(section_titles), work_item, artifact_recorder, run_logger)

        # Assert
        AsserterArtifacts.assert_exactly_these_filenames_in_order(expected_filenames, artifact_recorder.artifacts)
        actual_output_filenames: list[str] = [
            actual_artifact.filename
            for actual_artifact in artifact_recorder.artifacts
            if isinstance(actual_artifact, StepArtifact) and actual_artifact.artifact_kind.role is ArtifactRole.OUTPUT
        ]
        assert actual_output_filenames == [expected_analysis_report_filename]
        assert artifact_recorder.of_kind(ANALYSIS_REPORT)[0].content.decode("utf-8").startswith("# Section analysis")

    async def test_analyze_document_WhenManyPagesAreDetected_ThenTheModelIsNeverAskedAboutMoreThanTheConcurrencyLimitAtOnce(
        self, artifact_recorder: ArtifactRecorder, run_logger: logging.Logger
    ) -> None:
        # Arrange
        work_item: WorkItem = create_random_work_item()
        section_titles: list[str] = create_random_section_titles(MAX_CONCURRENCY * 3)
        model_gateway_testing: ModelGatewayTesting = _create_confident_gateway(section_titles)
        document_analysis_manager: DocumentAnalysisManager = create_document_analysis_manager(model_gateway_testing)

        # Act
        await analyze_in_a_run(document_analysis_manager, create_page_texts(section_titles), work_item, artifact_recorder, run_logger)

        # Assert - every page was asked about, and never more than the limit at the same moment
        assert sorted(model_gateway_testing.asked_detection_page_numbers) == list(range(len(section_titles)))
        assert model_gateway_testing.maximum_concurrent_detection_count == MAX_CONCURRENCY


@pytest.mark.acceptance
class TestAnalyzeDocumentValidation:
    async def test_analyze_document_WhenTheDocumentHasNoPages_ThenItIsRefusedBeforeAnyWorkOrArtifact(
        self, artifact_recorder: ArtifactRecorder, run_logger: logging.Logger, record_capture: RecordCapture
    ) -> None:
        # Arrange
        work_item: WorkItem = create_random_work_item()
        model_gateway_testing: ModelGatewayTesting = _create_confident_gateway([])
        document_analysis_manager: DocumentAnalysisManager = create_document_analysis_manager(model_gateway_testing)

        # Act
        with pytest.raises(DocumentValidationError, match="the document has no pages") as actual_raised:
            await analyze_in_a_run(document_analysis_manager, [], work_item, artifact_recorder, run_logger)

        # Assert - nothing ran: no step, no model question, only the run's own manifest
        AsserterContextualData.assert_exactly_these_entries(
            {
                "ExceptionType": "DocumentValidationError",
                "Message": str(actual_raised.value),
                "PageCount": 0,
            },
            actual_raised.value,
        )
        assert record_capture.boundaries(EventKind.STEP) == []
        assert model_gateway_testing.total_question_count() == 0
        AsserterArtifacts.assert_exactly_these_filenames_in_order(["manifest.json"], artifact_recorder.artifacts)

    async def test_analyze_document_WhenSeveralPagesAreBlank_ThenOneErrorNamesAllOfThem(
        self, artifact_recorder: ArtifactRecorder, run_logger: logging.Logger
    ) -> None:
        # Arrange
        work_item: WorkItem = create_random_work_item()
        section_titles: list[str] = create_random_section_titles(3)
        document_analysis_manager: DocumentAnalysisManager = create_document_analysis_manager(_create_confident_gateway(section_titles))
        pages_with_blanks: list[str] = ["", create_page_texts(section_titles)[1], "   "]

        # Act
        with pytest.raises(DocumentValidationError) as actual_raised:
            await analyze_in_a_run(document_analysis_manager, pages_with_blanks, work_item, artifact_recorder, run_logger)

        # Assert
        assert "pages [0, 2] are blank" in str(actual_raised.value)


@pytest.mark.acceptance
class TestAnalyzeDocumentModelReplyFailures:
    async def test_analyze_document_WhenAPageGetsAMalformedReply_ThenTheStepFailsButEveryRawReplyIsAlreadyOnDisk(
        self, artifact_recorder: ArtifactRecorder, run_logger: logging.Logger, record_capture: RecordCapture
    ) -> None:
        # Arrange
        work_item: WorkItem = create_random_work_item()
        section_titles: list[str] = create_random_section_titles(4)
        malformed_page_number: int = 2
        malformed_reply: str = 'Sure! Here is the JSON you asked for: {"title": '
        model_gateway_testing: ModelGatewayTesting = ModelGatewayTesting(
            detection_reply_by_page_number={
                page_number: malformed_reply if page_number == malformed_page_number else create_title_reply(title)
                for page_number, title in enumerate(section_titles)
            },
            score_reply_by_title={},
        )
        document_analysis_manager: DocumentAnalysisManager = create_document_analysis_manager(model_gateway_testing)

        # Act
        with pytest.raises(ModelResponseParseError) as actual_raised:
            await analyze_in_a_run(document_analysis_manager, create_page_texts(section_titles), work_item, artifact_recorder, run_logger)

        # Assert - the failing step is named on the exception, and the evidence precedes the failure
        AsserterContextualData.assert_exactly_these_entries(
            {
                "ExceptionType": "ModelResponseParseError",
                "Message": str(actual_raised.value),
                "PageNumber": malformed_page_number,
                "FailedAtStepNumber": "2",
                "FailedAtStepName": "Detect Sections",
                "FailedAtStepKey": "detect_sections",
            },
            actual_raised.value,
        )
        actual_raw_reply_filenames: list[str] = [
            actual_filename for actual_filename in artifact_recorder.filenames() if "raw_detection_response" in actual_filename
        ]
        assert sorted(actual_raw_reply_filenames) == [f"{work_item.stem}_step_02_raw_detection_response_page_{page:04d}.txt" for page in range(4)]
        assert model_gateway_testing.asked_score_titles == []
        AsserterStepBoundaries.assert_exactly_these_step_boundaries(
            [
                ExpectedStepBoundary("1", "STARTED"),
                ExpectedStepBoundary("1", "COMPLETE"),
                ExpectedStepBoundary("2", "STARTED"),
                ExpectedStepBoundary("2", "FAILED"),
            ],
            record_capture.records,
        )

    async def test_analyze_document_WhenSeveralPagesGetMalformedReplies_ThenTheFirstFailureInPageOrderEndsTheStep(
        self, artifact_recorder: ArtifactRecorder, run_logger: logging.Logger
    ) -> None:
        # Arrange
        work_item: WorkItem = create_random_work_item()
        section_titles: list[str] = create_random_section_titles(4)
        model_gateway_testing: ModelGatewayTesting = ModelGatewayTesting(
            detection_reply_by_page_number={
                0: create_title_reply(section_titles[0]),
                1: "not json",
                2: create_title_reply(section_titles[2]),
                3: "also not json",
            },
            score_reply_by_title={},
        )
        document_analysis_manager: DocumentAnalysisManager = create_document_analysis_manager(model_gateway_testing)

        # Act
        with pytest.raises(ModelResponseParseError) as actual_raised:
            await analyze_in_a_run(document_analysis_manager, create_page_texts(section_titles), work_item, artifact_recorder, run_logger)

        # Assert
        assert actual_raised.value.contextual_data_by_name["PageNumber"] == 1

    @pytest.mark.parametrize(
        ("hostile_reply", "expected_reason_start"),
        [
            pytest.param('{"title": ' + "9" * 5000 + "}", "ValueError: Exceeds the limit", id="a_digit_string_beyond_the_integer_limit"),
            # Depending on the platform's parser, deep nesting is reported as a recursion error or as a decode error,
            # so only the promise is asserted: the system refuses it as an unusable reply, with the page.
            pytest.param("[" * 100000, "", id="nesting_deeper_than_the_parser_allows"),
        ],
    )
    async def test_analyze_document_WhenTheReplyIsHostileToTheJsonParser_ThenItIsStillRefusedAsAnUnusableReply(
        self, hostile_reply: str, expected_reason_start: str, artifact_recorder: ArtifactRecorder, run_logger: logging.Logger
    ) -> None:
        # Arrange
        work_item: WorkItem = create_random_work_item()
        section_titles: list[str] = create_random_section_titles(1)
        model_gateway_testing: ModelGatewayTesting = ModelGatewayTesting(
            detection_reply_by_page_number={0: hostile_reply},
            score_reply_by_title={},
        )
        document_analysis_manager: DocumentAnalysisManager = create_document_analysis_manager(model_gateway_testing)

        # Act
        with pytest.raises(ModelResponseParseError) as actual_raised:
            await analyze_in_a_run(document_analysis_manager, create_page_texts(section_titles), work_item, artifact_recorder, run_logger)

        # Assert - the reply ended as the one exception the system promises, naming the page
        expected_message_start: str = f"The model response for page 0 could not be parsed: {expected_reason_start}"
        assert str(actual_raised.value).startswith(expected_message_start)

    @pytest.mark.parametrize(
        ("score_reply", "expected_reason"),
        [
            pytest.param("[1, 2]", "expected a JSON object, got list", id="a_list_instead_of_an_object"),
            pytest.param('{"category": 7, "confidence": 0.9}', "'category' must be non-empty text, got the number 7", id="category_that_is_not_text"),
            pytest.param('{"category": "  ", "confidence": 0.9}', "'category' must be non-empty text, got blank text", id="blank_category"),
            pytest.param('{"confidence": 0.9}', "'category' must be non-empty text, got nothing (the field is missing)", id="missing_category"),
            pytest.param(
                '{"category": "Legal", "confidence": "high"}', "'confidence' must be a number from 0 to 1, got text", id="confidence_that_is_text"
            ),
            pytest.param(
                '{"category": "Legal", "confidence": true}', "'confidence' must be a number from 0 to 1, got a boolean", id="boolean_confidence"
            ),
            pytest.param(
                '{"category": "Legal", "confidence": 1.7}', "'confidence' must be a number from 0 to 1, got the number 1.7", id="confidence_above_one"
            ),
            pytest.param(
                '{"category": "Legal", "confidence": NaN}',
                "'confidence' must be a number from 0 to 1, got the number nan",
                id="confidence_not_a_number",
            ),
        ],
    )
    async def test_analyze_document_WhenTheScoreReplyHasTheWrongShape_ThenItIsRefusedWithAReasonThatNamesTheRejectedValue(
        self, score_reply: str, expected_reason: str, artifact_recorder: ArtifactRecorder, run_logger: logging.Logger
    ) -> None:
        # Arrange
        work_item: WorkItem = create_random_work_item()
        section_titles: list[str] = create_random_section_titles(1)
        model_gateway_testing: ModelGatewayTesting = ModelGatewayTesting(
            detection_reply_by_page_number={0: create_title_reply(section_titles[0])},
            score_reply_by_title={section_titles[0]: score_reply},
        )
        document_analysis_manager: DocumentAnalysisManager = create_document_analysis_manager(model_gateway_testing)

        # Act
        with pytest.raises(ModelResponseParseError) as actual_raised:
            await analyze_in_a_run(document_analysis_manager, create_page_texts(section_titles), work_item, artifact_recorder, run_logger)

        # Assert
        expected_message: str = f"The model response for page 0 could not be parsed: {expected_reason}"
        assert str(actual_raised.value) == expected_message
