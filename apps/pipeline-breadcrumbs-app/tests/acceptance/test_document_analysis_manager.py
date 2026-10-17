# Acceptance tests for the document analysis system, through its one public entry point,
# DocumentAnalysisManager.analyze_document. The application's part is played the way an application
# plays it: open a run, open a work item, hand that scope to the system. The system is built the way
# an application builds it, from a service locator; only the wire to the model service is swapped
# (TestMediatorModelService, through ServiceLocatorTesting). The gateway, the configuration provider,
# the processors, the parsing, the library's scopes and the artifact sink all run for real. The
# observations are what the system returned or raised, what the gateway put on the wire, the artifacts
# handed to the sink, and the breadcrumbs it logged.

import logging
from collections.abc import Sequence
from typing import Final

import pytest
from analysis_acceptance_support.asserters.asserter_analysis_artifacts import AsserterAnalysisArtifacts
from analysis_acceptance_support.asserters.asserter_analyzed_sections import AsserterAnalyzedSections
from analysis_acceptance_support.asserters.asserter_model_service_requests import AsserterModelServiceRequests
from analysis_acceptance_support.data_generators import (
    create_page_texts,
    create_random_category,
    create_random_section_titles,
    create_score_reply,
    create_title_reply,
)
from analysis_acceptance_support.mediator_model_service import (
    HTTP_STATUS_BAD_REQUEST,
    HTTP_STATUS_OK,
    HTTP_STATUS_SERVICE_UNAVAILABLE,
    ScriptedModelServiceResponse,
    SectionDetectionRequest,
    SectionQuestionRequest,
    TestMediatorModelService,
)
from analysis_acceptance_support.service_locator_testing import ServiceLocatorTesting, create_document_analysis_manager
from breadcrumbs_acceptance_support.asserters.asserter_artifacts import AsserterArtifacts
from breadcrumbs_acceptance_support.asserters.asserter_exception import AsserterException, ExpectedException
from breadcrumbs_acceptance_support.asserters.asserter_step_boundaries import AsserterStepBoundaries, ExpectedStepBoundary
from breadcrumbs_acceptance_support.data_generators import create_random_pipeline_name, create_random_work_item

from pipeline_breadcrumbs import PipelineRun, WorkItem
from pipeline_breadcrumbs.testing import ArtifactSinkTesting, RecordCapture
from pipeline_breadcrumbs_app.document_analysis.artifact_kinds import ANALYSIS_REPORT
from pipeline_breadcrumbs_app.document_analysis.configuration_providers.settings_providers.settings_provider_model_service import (
    MODEL_SERVICE_BASE_URL_VARIABLE_NAME,
)
from pipeline_breadcrumbs_app.document_analysis.configuration_providers.settings_providers.settings_provider_simulated_work import (
    SIMULATED_WORK_SECONDS_VARIABLE_NAME,
)
from pipeline_breadcrumbs_app.document_analysis.document_analysis_manager import DocumentAnalysisManager
from pipeline_breadcrumbs_app.document_analysis.exceptions import (
    ConfigurationSettingError,
    DocumentValidationError,
    ModelResponseParseError,
    ModelServiceContractError,
    ModelServiceRequestRejectedError,
    ModelServiceUnavailableError,
)
from pipeline_breadcrumbs_app.document_analysis.models import DocumentAnalysis, ScoredSection
from pipeline_breadcrumbs_app.document_analysis.processors.section_detector import MAX_CONCURRENCY

CONFIDENT: Final[float] = 0.92
DOUBTFUL: Final[float] = 0.55
RECONCILED: Final[float] = 0.81
REPORT_HEADING: Final[str] = "# Section analysis"
MANIFEST_FILENAME: Final[str] = "manifest.json"
DETECT_SECTION_OPERATION: Final[str] = "detect_section"

# The boundaries a fully confident document leaves: the conditional reconciliation step is skipped.
CONFIDENT_RUN_STEP_BOUNDARIES: Final[list[ExpectedStepBoundary]] = [
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
]
# The boundaries a document leaves when step 2 fails: nothing after it runs.
DETECTION_FAILED_STEP_BOUNDARIES: Final[list[ExpectedStepBoundary]] = [
    ExpectedStepBoundary("1", "STARTED"),
    ExpectedStepBoundary("1", "COMPLETE"),
    ExpectedStepBoundary("2", "STARTED"),
    ExpectedStepBoundary("2", "FAILED"),
]
# The step-identity facts the library stamps onto an exception that escapes step 2.
DETECTION_STEP_CONTEXTUAL_DATA: Final[dict[str, object]] = {
    "FailedAtStepNumber": "2",
    "FailedAtStepName": "Detect Sections",
    "FailedAtStepKey": "detect_sections",
}


def create_confident_test_mediator(section_titles: Sequence[str], category: str) -> TestMediatorModelService:
    return TestMediatorModelService(
        detection_reply_by_page_number={page_number: create_title_reply(title) for page_number, title in enumerate(section_titles)},
        score_reply_by_title={title: create_score_reply(category, CONFIDENT) for title in section_titles},
    )


def create_pipeline_run(artifact_sink_testing: ArtifactSinkTesting, run_logger: logging.Logger) -> PipelineRun:
    return PipelineRun(pipeline_name=create_random_pipeline_name(), artifact_sink=artifact_sink_testing, logger=run_logger)


# ==================== EXPECTED PATHS ====================


@pytest.mark.acceptance
class TestAnalyzeDocumentExpectedPaths:
    async def test_analyze_document_WhenEveryScoreIsConfident_ThenTheSectionsAreReturnedAndTheReconcileStepIsSkipped(
        self, artifact_sink_testing: ArtifactSinkTesting, run_logger: logging.Logger, record_capture: RecordCapture
    ) -> None:
        # Arrange
        work_item: WorkItem = create_random_work_item()
        section_titles: list[str] = create_random_section_titles(3)
        category: str = create_random_category()
        test_mediator_model_service: TestMediatorModelService = create_confident_test_mediator(section_titles, category)
        document_analysis_manager: DocumentAnalysisManager = create_document_analysis_manager(test_mediator_model_service)
        pipeline_run: PipelineRun = create_pipeline_run(artifact_sink_testing, run_logger)
        expected_scored_sections: list[ScoredSection] = [
            ScoredSection(page_number, title, category, CONFIDENT) for page_number, title in enumerate(section_titles)
        ]
        expected_reconcile_request_count: int = 0

        # Act
        async with document_analysis_manager, pipeline_run, pipeline_run.open_work_item(work_item) as work_item_scope:
            actual_document_analysis: DocumentAnalysis = await document_analysis_manager.analyze_document(
                work_item_scope, create_page_texts(section_titles)
            )

        # Assert
        AsserterAnalyzedSections.assert_exactly_these_sections(expected_scored_sections, actual_document_analysis.scored_sections)
        AsserterStepBoundaries.assert_exactly_these_step_boundaries(CONFIDENT_RUN_STEP_BOUNDARIES, record_capture.records)
        assert len(test_mediator_model_service.captured_reconcile_section_question_requests) == expected_reconcile_request_count

    async def test_analyze_document_WhenOneScoreIsDoubtful_ThenTheModelIsAskedAgainAndTheReconciledScoreIsReturned(
        self, artifact_sink_testing: ArtifactSinkTesting, run_logger: logging.Logger, record_capture: RecordCapture
    ) -> None:
        # Arrange
        work_item: WorkItem = create_random_work_item()
        section_titles: list[str] = create_random_section_titles(3)
        doubtful_title: str = section_titles[1]
        confident_category: str = create_random_category()
        reconciled_category: str = create_random_category()
        test_mediator_model_service: TestMediatorModelService = TestMediatorModelService(
            detection_reply_by_page_number={page_number: create_title_reply(title) for page_number, title in enumerate(section_titles)},
            score_reply_by_title={
                title: create_score_reply(confident_category, DOUBTFUL if title == doubtful_title else CONFIDENT) for title in section_titles
            },
            reconcile_reply_by_title={doubtful_title: create_score_reply(reconciled_category, RECONCILED)},
        )
        document_analysis_manager: DocumentAnalysisManager = create_document_analysis_manager(test_mediator_model_service)
        pipeline_run: PipelineRun = create_pipeline_run(artifact_sink_testing, run_logger)
        expected_scored_sections: list[ScoredSection] = [
            ScoredSection(0, section_titles[0], confident_category, CONFIDENT),
            ScoredSection(1, doubtful_title, reconciled_category, RECONCILED),
            ScoredSection(2, section_titles[2], confident_category, CONFIDENT),
        ]
        expected_step_boundaries: list[ExpectedStepBoundary] = [
            *CONFIDENT_RUN_STEP_BOUNDARIES[:9],
            ExpectedStepBoundary("3.3", "STARTED"),
            ExpectedStepBoundary("3.3", "COMPLETE"),
            *CONFIDENT_RUN_STEP_BOUNDARIES[10:],
        ]

        # Act
        async with document_analysis_manager, pipeline_run, pipeline_run.open_work_item(work_item) as work_item_scope:
            actual_document_analysis: DocumentAnalysis = await document_analysis_manager.analyze_document(
                work_item_scope, create_page_texts(section_titles)
            )

        # Assert
        AsserterAnalyzedSections.assert_exactly_these_sections(expected_scored_sections, actual_document_analysis.scored_sections)
        AsserterStepBoundaries.assert_exactly_these_step_boundaries(expected_step_boundaries, record_capture.records)

    async def test_analyze_document_WhenSectionsAreAnalyzed_ThenTheGatewayPutsEachQuestionOnTheWireWithItsSection(
        self, artifact_sink_testing: ArtifactSinkTesting, run_logger: logging.Logger
    ) -> None:
        # Arrange
        work_item: WorkItem = create_random_work_item()
        section_titles: list[str] = create_random_section_titles(2)
        page_texts: list[str] = create_page_texts(section_titles)
        doubtful_title: str = section_titles[1]
        category: str = create_random_category()
        test_mediator_model_service: TestMediatorModelService = TestMediatorModelService(
            detection_reply_by_page_number={page_number: create_title_reply(title) for page_number, title in enumerate(section_titles)},
            score_reply_by_title={
                title: create_score_reply(category, DOUBTFUL if title == doubtful_title else CONFIDENT) for title in section_titles
            },
            reconcile_reply_by_title={doubtful_title: create_score_reply(category, RECONCILED)},
        )
        document_analysis_manager: DocumentAnalysisManager = create_document_analysis_manager(test_mediator_model_service)
        pipeline_run: PipelineRun = create_pipeline_run(artifact_sink_testing, run_logger)
        expected_section_detection_requests: list[SectionDetectionRequest] = [
            {"page_number": page_number, "page_text": page_text} for page_number, page_text in enumerate(page_texts)
        ]
        expected_score_section_question_requests: list[SectionQuestionRequest] = [
            {"page_number": page_number, "title": title, "text": f"Classify the section titled '{title}' on page {page_number} into one category."}
            for page_number, title in enumerate(section_titles)
        ]
        expected_reconcile_section_question_requests: list[SectionQuestionRequest] = [
            {"page_number": 1, "title": doubtful_title, "text": f"Reconsider the section titled '{doubtful_title}'."}
        ]

        # Act
        async with document_analysis_manager, pipeline_run, pipeline_run.open_work_item(work_item) as work_item_scope:
            await document_analysis_manager.analyze_document(work_item_scope, page_texts)

        # Assert
        AsserterModelServiceRequests.assert_requests(
            expected_section_detection_requests,
            expected_score_section_question_requests,
            expected_reconcile_section_question_requests,
            test_mediator_model_service.captured_section_detection_requests,
            test_mediator_model_service.captured_score_section_question_requests,
            test_mediator_model_service.captured_reconcile_section_question_requests,
        )

    async def test_analyze_document_WhenTheDocumentIsAnalyzed_ThenEveryArtifactLandsInPipelineOrderWithTheReportAsTheOnlyOutput(
        self, artifact_sink_testing: ArtifactSinkTesting, run_logger: logging.Logger
    ) -> None:
        # Arrange
        work_item: WorkItem = create_random_work_item()
        section_titles: list[str] = create_random_section_titles(2)
        test_mediator_model_service: TestMediatorModelService = create_confident_test_mediator(section_titles, create_random_category())
        document_analysis_manager: DocumentAnalysisManager = create_document_analysis_manager(test_mediator_model_service)
        pipeline_run: PipelineRun = create_pipeline_run(artifact_sink_testing, run_logger)
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
            MANIFEST_FILENAME,
        ]
        expected_output_filenames: list[str] = [expected_analysis_report_filename]

        # Act
        async with document_analysis_manager, pipeline_run, pipeline_run.open_work_item(work_item) as work_item_scope:
            await document_analysis_manager.analyze_document(work_item_scope, create_page_texts(section_titles))

        # Assert
        AsserterAnalysisArtifacts.assert_trail(
            expected_filenames, expected_output_filenames, ANALYSIS_REPORT, REPORT_HEADING, artifact_sink_testing.artifacts
        )

    async def test_analyze_document_WhenManyPagesAreDetected_ThenTheModelIsNeverAskedAboutMoreThanTheConcurrencyLimitAtOnce(
        self, artifact_sink_testing: ArtifactSinkTesting, run_logger: logging.Logger
    ) -> None:
        # Arrange
        work_item: WorkItem = create_random_work_item()
        section_titles: list[str] = create_random_section_titles(MAX_CONCURRENCY * 3)
        test_mediator_model_service: TestMediatorModelService = create_confident_test_mediator(section_titles, create_random_category())
        document_analysis_manager: DocumentAnalysisManager = create_document_analysis_manager(test_mediator_model_service)
        pipeline_run: PipelineRun = create_pipeline_run(artifact_sink_testing, run_logger)
        expected_page_numbers: list[int] = list(range(len(section_titles)))

        # Act
        async with document_analysis_manager, pipeline_run, pipeline_run.open_work_item(work_item) as work_item_scope:
            await document_analysis_manager.analyze_document(work_item_scope, create_page_texts(section_titles))

        # Assert - every page was asked about, and never more than the limit at the same moment
        AsserterModelServiceRequests.assert_detection_concurrency(
            expected_page_numbers,
            MAX_CONCURRENCY,
            test_mediator_model_service.captured_section_detection_requests,
            test_mediator_model_service.maximum_concurrent_detection_count,
        )


# ==================== DOCUMENT VALIDATION ====================


@pytest.mark.acceptance
class TestAnalyzeDocumentValidation:
    async def test_analyze_document_WhenTheDocumentHasNoPages_ThenItIsRefusedBeforeAnyWorkOrArtifact(
        self, artifact_sink_testing: ArtifactSinkTesting, run_logger: logging.Logger, record_capture: RecordCapture
    ) -> None:
        # Arrange
        work_item: WorkItem = create_random_work_item()
        test_mediator_model_service: TestMediatorModelService = TestMediatorModelService()
        document_analysis_manager: DocumentAnalysisManager = create_document_analysis_manager(test_mediator_model_service)
        pipeline_run: PipelineRun = create_pipeline_run(artifact_sink_testing, run_logger)
        expected_exception: ExpectedException = ExpectedException(
            DocumentValidationError,
            message_phrases=["cannot be analyzed", "the document has no pages"],
            contextual_data_by_name={"ExceptionType": "DocumentValidationError", "PageCount": 0},
        )
        expected_step_boundaries: list[ExpectedStepBoundary] = []
        expected_model_service_request_count: int = 0
        expected_filenames: list[str] = [MANIFEST_FILENAME]

        # Act
        with pytest.raises(DocumentValidationError) as actual_raised:
            async with document_analysis_manager, pipeline_run, pipeline_run.open_work_item(work_item) as work_item_scope:
                await document_analysis_manager.analyze_document(work_item_scope, [])

        # Assert - nothing ran: no step, no model question, only the run's own manifest
        AsserterException.assert_exception(expected_exception, actual_raised.value)
        AsserterStepBoundaries.assert_exactly_these_step_boundaries(expected_step_boundaries, record_capture.records)
        assert test_mediator_model_service.captured_model_service_request_count == expected_model_service_request_count
        AsserterArtifacts.assert_exactly_these_filenames_in_order(expected_filenames, artifact_sink_testing.artifacts)

    async def test_analyze_document_WhenSeveralPagesAreBlank_ThenOneErrorNamesAllOfThem(
        self, artifact_sink_testing: ArtifactSinkTesting, run_logger: logging.Logger
    ) -> None:
        # Arrange
        work_item: WorkItem = create_random_work_item()
        section_titles: list[str] = create_random_section_titles(3)
        document_analysis_manager: DocumentAnalysisManager = create_document_analysis_manager(TestMediatorModelService())
        pipeline_run: PipelineRun = create_pipeline_run(artifact_sink_testing, run_logger)
        pages_with_blanks: list[str] = ["", create_page_texts(section_titles)[1], "   "]
        expected_exception: ExpectedException = ExpectedException(
            DocumentValidationError,
            message_phrases=["cannot be analyzed", "pages [0, 2] are blank"],
            contextual_data_by_name={"ExceptionType": "DocumentValidationError", "PageCount": len(pages_with_blanks)},
        )

        # Act
        with pytest.raises(DocumentValidationError) as actual_raised:
            async with document_analysis_manager, pipeline_run, pipeline_run.open_work_item(work_item) as work_item_scope:
                await document_analysis_manager.analyze_document(work_item_scope, pages_with_blanks)

        # Assert
        AsserterException.assert_exception(expected_exception, actual_raised.value)


# ==================== MODEL REPLY FAILURES ====================


@pytest.mark.acceptance
class TestAnalyzeDocumentModelReplyFailures:
    async def test_analyze_document_WhenAPageGetsAMalformedReply_ThenTheStepFailsButEveryRawReplyIsAlreadyOnDisk(
        self, artifact_sink_testing: ArtifactSinkTesting, run_logger: logging.Logger, record_capture: RecordCapture
    ) -> None:
        # Arrange
        work_item: WorkItem = create_random_work_item()
        section_titles: list[str] = create_random_section_titles(4)
        malformed_page_number: int = 2
        malformed_reply: str = 'Sure! Here is the JSON you asked for: {"title": '
        test_mediator_model_service: TestMediatorModelService = TestMediatorModelService(
            detection_reply_by_page_number={
                page_number: malformed_reply if page_number == malformed_page_number else create_title_reply(title)
                for page_number, title in enumerate(section_titles)
            },
        )
        document_analysis_manager: DocumentAnalysisManager = create_document_analysis_manager(test_mediator_model_service)
        pipeline_run: PipelineRun = create_pipeline_run(artifact_sink_testing, run_logger)
        stem: str = work_item.stem
        expected_exception: ExpectedException = ExpectedException(
            ModelResponseParseError,
            message_phrases=[f"model response for page {malformed_page_number}", "could not be parsed"],
            contextual_data_by_name={
                "ExceptionType": "ModelResponseParseError",
                "PageNumber": malformed_page_number,
                **DETECTION_STEP_CONTEXTUAL_DATA,
            },
        )
        # Emit-before-validate: all four raw replies, the malformed one included, reach the sink before the step fails.
        expected_filenames: list[str] = [
            *(f"{stem}_step_01_page_text_page_{page_number:04d}.txt" for page_number in range(4)),
            *(f"{stem}_step_02_raw_detection_response_page_{page_number:04d}.txt" for page_number in range(4)),
            MANIFEST_FILENAME,
        ]

        # Act
        with pytest.raises(ModelResponseParseError) as actual_raised:
            async with document_analysis_manager, pipeline_run, pipeline_run.open_work_item(work_item) as work_item_scope:
                await document_analysis_manager.analyze_document(work_item_scope, create_page_texts(section_titles))

        # Assert - the failing step is named on the exception, and the evidence precedes the failure
        AsserterException.assert_exception(expected_exception, actual_raised.value)
        AsserterArtifacts.assert_exactly_these_filenames_in_order(expected_filenames, artifact_sink_testing.artifacts)
        AsserterStepBoundaries.assert_exactly_these_step_boundaries(DETECTION_FAILED_STEP_BOUNDARIES, record_capture.records)

    async def test_analyze_document_WhenSeveralPagesGetMalformedReplies_ThenTheFirstFailureInPageOrderEndsTheStep(
        self, artifact_sink_testing: ArtifactSinkTesting, run_logger: logging.Logger
    ) -> None:
        # Arrange
        work_item: WorkItem = create_random_work_item()
        section_titles: list[str] = create_random_section_titles(4)
        first_malformed_page_number: int = 1
        test_mediator_model_service: TestMediatorModelService = TestMediatorModelService(
            detection_reply_by_page_number={
                0: create_title_reply(section_titles[0]),
                first_malformed_page_number: "not json",
                2: create_title_reply(section_titles[2]),
                3: "also not json",
            },
        )
        document_analysis_manager: DocumentAnalysisManager = create_document_analysis_manager(test_mediator_model_service)
        pipeline_run: PipelineRun = create_pipeline_run(artifact_sink_testing, run_logger)
        expected_exception: ExpectedException = ExpectedException(
            ModelResponseParseError,
            message_phrases=[f"model response for page {first_malformed_page_number}"],
            contextual_data_by_name={
                "ExceptionType": "ModelResponseParseError",
                "PageNumber": first_malformed_page_number,
                **DETECTION_STEP_CONTEXTUAL_DATA,
            },
        )

        # Act
        with pytest.raises(ModelResponseParseError) as actual_raised:
            async with document_analysis_manager, pipeline_run, pipeline_run.open_work_item(work_item) as work_item_scope:
                await document_analysis_manager.analyze_document(work_item_scope, create_page_texts(section_titles))

        # Assert
        AsserterException.assert_exception(expected_exception, actual_raised.value)

    @pytest.mark.parametrize(
        ("hostile_reply", "expected_reason_phrase"),
        [
            pytest.param('{"title": ' + "9" * 5000 + "}", "Exceeds the limit", id="a_digit_string_beyond_the_integer_limit"),
            # Depending on the platform's parser, deep nesting is reported as a recursion error or as a decode error,
            # so only the promise is asserted: the system refuses it as an unusable reply, with the page.
            pytest.param("[" * 100000, "could not be parsed", id="nesting_deeper_than_the_parser_allows"),
        ],
    )
    async def test_analyze_document_WhenTheReplyIsHostileToTheJsonParser_ThenItIsStillRefusedAsAnUnusableReply(
        self, hostile_reply: str, expected_reason_phrase: str, artifact_sink_testing: ArtifactSinkTesting, run_logger: logging.Logger
    ) -> None:
        # Arrange
        work_item: WorkItem = create_random_work_item()
        section_titles: list[str] = create_random_section_titles(1)
        test_mediator_model_service: TestMediatorModelService = TestMediatorModelService(detection_reply_by_page_number={0: hostile_reply})
        document_analysis_manager: DocumentAnalysisManager = create_document_analysis_manager(test_mediator_model_service)
        pipeline_run: PipelineRun = create_pipeline_run(artifact_sink_testing, run_logger)
        expected_exception: ExpectedException = ExpectedException(
            ModelResponseParseError,
            message_phrases=["model response for page 0", expected_reason_phrase],
            contextual_data_by_name={"ExceptionType": "ModelResponseParseError", "PageNumber": 0, **DETECTION_STEP_CONTEXTUAL_DATA},
        )

        # Act
        with pytest.raises(ModelResponseParseError) as actual_raised:
            async with document_analysis_manager, pipeline_run, pipeline_run.open_work_item(work_item) as work_item_scope:
                await document_analysis_manager.analyze_document(work_item_scope, create_page_texts(section_titles))

        # Assert - the reply ended as the one exception the system promises, naming the page
        AsserterException.assert_exception(expected_exception, actual_raised.value)

    @pytest.mark.parametrize(
        ("score_reply", "expected_reason_phrase"),
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
        self, score_reply: str, expected_reason_phrase: str, artifact_sink_testing: ArtifactSinkTesting, run_logger: logging.Logger
    ) -> None:
        # Arrange
        work_item: WorkItem = create_random_work_item()
        section_titles: list[str] = create_random_section_titles(1)
        test_mediator_model_service: TestMediatorModelService = TestMediatorModelService(
            detection_reply_by_page_number={0: create_title_reply(section_titles[0])},
            score_reply_by_title={section_titles[0]: score_reply},
        )
        document_analysis_manager: DocumentAnalysisManager = create_document_analysis_manager(test_mediator_model_service)
        pipeline_run: PipelineRun = create_pipeline_run(artifact_sink_testing, run_logger)
        expected_exception: ExpectedException = ExpectedException(
            ModelResponseParseError,
            message_phrases=["model response for page 0", expected_reason_phrase],
            contextual_data_by_name={
                "ExceptionType": "ModelResponseParseError",
                "PageNumber": 0,
                "FailedAtStepNumber": "3.2",
                "FailedAtStepName": "Score Sections",
                "FailedAtStepKey": "score_sections",
            },
        )

        # Act
        with pytest.raises(ModelResponseParseError) as actual_raised:
            async with document_analysis_manager, pipeline_run, pipeline_run.open_work_item(work_item) as work_item_scope:
                await document_analysis_manager.analyze_document(work_item_scope, create_page_texts(section_titles))

        # Assert
        AsserterException.assert_exception(expected_exception, actual_raised.value)


# ==================== MODEL SERVICE FAILURES ====================


@pytest.mark.acceptance
class TestAnalyzeDocumentModelServiceFailures:
    async def test_analyze_document_WhenTheModelServiceIsUnreachable_ThenTheStepFailsWithAModelServiceUnavailableError(
        self, artifact_sink_testing: ArtifactSinkTesting, run_logger: logging.Logger, record_capture: RecordCapture
    ) -> None:
        # Arrange
        work_item: WorkItem = create_random_work_item()
        section_titles: list[str] = create_random_section_titles(1)
        test_mediator_model_service: TestMediatorModelService = TestMediatorModelService(simulate_unreachable=True)
        document_analysis_manager: DocumentAnalysisManager = create_document_analysis_manager(test_mediator_model_service)
        pipeline_run: PipelineRun = create_pipeline_run(artifact_sink_testing, run_logger)
        expected_failure_detail: str = "ConnectError: the model service is unreachable (simulated by TestMediatorModelService)"
        expected_exception: ExpectedException = ExpectedException(
            ModelServiceUnavailableError,
            message_phrases=["model service could not answer", DETECT_SECTION_OPERATION, "ConnectError"],
            contextual_data_by_name={
                "ExceptionType": "ModelServiceUnavailableError",
                "ModelService.Operation": DETECT_SECTION_OPERATION,
                "ModelService.FailureDetail": expected_failure_detail,
                **DETECTION_STEP_CONTEXTUAL_DATA,
            },
        )

        # Act
        with pytest.raises(ModelServiceUnavailableError) as actual_raised:
            async with document_analysis_manager, pipeline_run, pipeline_run.open_work_item(work_item) as work_item_scope:
                await document_analysis_manager.analyze_document(work_item_scope, create_page_texts(section_titles))

        # Assert
        AsserterException.assert_exception(expected_exception, actual_raised.value)
        AsserterStepBoundaries.assert_exactly_these_step_boundaries(DETECTION_FAILED_STEP_BOUNDARIES, record_capture.records)

    async def test_analyze_document_WhenTheModelServiceIsUnavailable_ThenTheErrorCarriesTheStatusAndWhatTheServiceSaid(
        self, artifact_sink_testing: ArtifactSinkTesting, run_logger: logging.Logger
    ) -> None:
        # Arrange
        work_item: WorkItem = create_random_work_item()
        section_titles: list[str] = create_random_section_titles(1)
        service_failure_text: str = create_random_category()
        test_mediator_model_service: TestMediatorModelService = TestMediatorModelService(
            scripted_model_service_response=ScriptedModelServiceResponse(HTTP_STATUS_SERVICE_UNAVAILABLE, service_failure_text)
        )
        document_analysis_manager: DocumentAnalysisManager = create_document_analysis_manager(test_mediator_model_service)
        pipeline_run: PipelineRun = create_pipeline_run(artifact_sink_testing, run_logger)
        expected_exception: ExpectedException = ExpectedException(
            ModelServiceUnavailableError,
            message_phrases=["model service could not answer", service_failure_text],
            contextual_data_by_name={
                "ExceptionType": "ModelServiceUnavailableError",
                "ModelService.Operation": DETECT_SECTION_OPERATION,
                "ModelService.HttpStatusCode": HTTP_STATUS_SERVICE_UNAVAILABLE,
                "ModelService.FailureDetail": service_failure_text,
                **DETECTION_STEP_CONTEXTUAL_DATA,
            },
        )

        # Act
        with pytest.raises(ModelServiceUnavailableError) as actual_raised:
            async with document_analysis_manager, pipeline_run, pipeline_run.open_work_item(work_item) as work_item_scope:
                await document_analysis_manager.analyze_document(work_item_scope, create_page_texts(section_titles))

        # Assert
        AsserterException.assert_exception(expected_exception, actual_raised.value)

    async def test_analyze_document_WhenTheModelServiceRejectsTheRequest_ThenAModelServiceRequestRejectedErrorNamesTheStatus(
        self, artifact_sink_testing: ArtifactSinkTesting, run_logger: logging.Logger
    ) -> None:
        # Arrange
        work_item: WorkItem = create_random_work_item()
        section_titles: list[str] = create_random_section_titles(1)
        rejection_text: str = create_random_category()
        test_mediator_model_service: TestMediatorModelService = TestMediatorModelService(
            scripted_model_service_response=ScriptedModelServiceResponse(HTTP_STATUS_BAD_REQUEST, rejection_text)
        )
        document_analysis_manager: DocumentAnalysisManager = create_document_analysis_manager(test_mediator_model_service)
        pipeline_run: PipelineRun = create_pipeline_run(artifact_sink_testing, run_logger)
        expected_exception: ExpectedException = ExpectedException(
            ModelServiceRequestRejectedError,
            message_phrases=["rejected", f"HTTP {HTTP_STATUS_BAD_REQUEST}", rejection_text],
            contextual_data_by_name={
                "ExceptionType": "ModelServiceRequestRejectedError",
                "ModelService.Operation": DETECT_SECTION_OPERATION,
                "ModelService.HttpStatusCode": HTTP_STATUS_BAD_REQUEST,
                "ModelService.FailureDetail": rejection_text,
                **DETECTION_STEP_CONTEXTUAL_DATA,
            },
        )

        # Act
        with pytest.raises(ModelServiceRequestRejectedError) as actual_raised:
            async with document_analysis_manager, pipeline_run, pipeline_run.open_work_item(work_item) as work_item_scope:
                await document_analysis_manager.analyze_document(work_item_scope, create_page_texts(section_titles))

        # Assert
        AsserterException.assert_exception(expected_exception, actual_raised.value)

    @pytest.mark.parametrize(
        ("response_body", "expected_reason_phrase"),
        [
            pytest.param("this is not json", "the response is not JSON (JSONDecodeError)", id="a_body_that_is_not_json"),
            pytest.param('["reply"]', "the response is not a JSON object with a text 'reply' field", id="a_list_instead_of_the_envelope"),
            pytest.param('{"answer": "{}"}', "the response is not a JSON object with a text 'reply' field", id="an_envelope_without_a_reply"),
            pytest.param('{"reply": 7}', "the response is not a JSON object with a text 'reply' field", id="a_reply_that_is_not_text"),
        ],
    )
    async def test_analyze_document_WhenTheModelServiceBreaksItsEnvelope_ThenAModelServiceContractErrorIsRaisedNotAParseError(
        self, response_body: str, expected_reason_phrase: str, artifact_sink_testing: ArtifactSinkTesting, run_logger: logging.Logger
    ) -> None:
        # Arrange
        work_item: WorkItem = create_random_work_item()
        section_titles: list[str] = create_random_section_titles(1)
        test_mediator_model_service: TestMediatorModelService = TestMediatorModelService(
            scripted_model_service_response=ScriptedModelServiceResponse(HTTP_STATUS_OK, response_body)
        )
        document_analysis_manager: DocumentAnalysisManager = create_document_analysis_manager(test_mediator_model_service)
        pipeline_run: PipelineRun = create_pipeline_run(artifact_sink_testing, run_logger)
        expected_exception: ExpectedException = ExpectedException(
            ModelServiceContractError,
            message_phrases=["unexpected shape", expected_reason_phrase],
            contextual_data_by_name={
                "ExceptionType": "ModelServiceContractError",
                "ModelService.Operation": DETECT_SECTION_OPERATION,
                "ModelService.FailureDetail": expected_reason_phrase,
                **DETECTION_STEP_CONTEXTUAL_DATA,
            },
        )

        # Act
        with pytest.raises(ModelServiceContractError) as actual_raised:
            async with document_analysis_manager, pipeline_run, pipeline_run.open_work_item(work_item) as work_item_scope:
                await document_analysis_manager.analyze_document(work_item_scope, create_page_texts(section_titles))

        # Assert
        AsserterException.assert_exception(expected_exception, actual_raised.value)


# ==================== CONFIGURATION ====================


@pytest.mark.acceptance
class TestDocumentAnalysisManagerConfiguration:
    @pytest.mark.parametrize(
        ("setting_value", "expected_reason_phrase"),
        [
            pytest.param("", "but was empty or whitespace", id="an_empty_url"),
            pytest.param("model-service", "not an absolute http or https URL", id="a_relative_url"),
            pytest.param("ftp://models.example.com", "not an absolute http or https URL", id="an_ftp_url"),
        ],
    )
    def test_DocumentAnalysisManager_WhenTheModelServiceUrlIsMalformed_ThenTheSystemRefusesToBuildAndNamesTheSetting(
        self, setting_value: str, expected_reason_phrase: str
    ) -> None:
        # Arrange
        service_locator_testing: ServiceLocatorTesting = ServiceLocatorTesting(
            TestMediatorModelService(), {MODEL_SERVICE_BASE_URL_VARIABLE_NAME: setting_value}
        )
        expected_exception: ExpectedException = ExpectedException(
            ConfigurationSettingError,
            message_phrases=[MODEL_SERVICE_BASE_URL_VARIABLE_NAME, expected_reason_phrase],
            contextual_data_by_name={
                "ExceptionType": "ConfigurationSettingError",
                "Configuration.EnvironmentVariableName": MODEL_SERVICE_BASE_URL_VARIABLE_NAME,
            },
        )

        # Act
        with pytest.raises(ConfigurationSettingError) as actual_raised:
            DocumentAnalysisManager(service_locator_testing)

        # Assert
        AsserterException.assert_exception(expected_exception, actual_raised.value)

    @pytest.mark.parametrize(
        "setting_value",
        [
            pytest.param("soon", id="text"),
            pytest.param("-1", id="negative"),
            pytest.param("inf", id="endless"),
        ],
    )
    def test_DocumentAnalysisManager_WhenTheSimulatedWorkIsNotAFiniteNumberOfSeconds_ThenTheSystemRefusesToBuildAndNamesTheSetting(
        self, setting_value: str
    ) -> None:
        # Arrange
        service_locator_testing: ServiceLocatorTesting = ServiceLocatorTesting(
            TestMediatorModelService(), {SIMULATED_WORK_SECONDS_VARIABLE_NAME: setting_value}
        )
        expected_exception: ExpectedException = ExpectedException(
            ConfigurationSettingError,
            message_phrases=[SIMULATED_WORK_SECONDS_VARIABLE_NAME, "not a number of seconds of 0 or more"],
            contextual_data_by_name={
                "ExceptionType": "ConfigurationSettingError",
                "Configuration.EnvironmentVariableName": SIMULATED_WORK_SECONDS_VARIABLE_NAME,
            },
        )

        # Act
        with pytest.raises(ConfigurationSettingError) as actual_raised:
            DocumentAnalysisManager(service_locator_testing)

        # Assert
        AsserterException.assert_exception(expected_exception, actual_raised.value)
