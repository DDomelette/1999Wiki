"""Crawler-only corpus build package."""

from .artifact_writer import (
    CandidateArtifactInput,
    CandidateWriteResult,
    verify_candidate_manifest,
    write_candidate_artifacts,
)
from .contracts import (
    BuildState,
    CorpusBuildRequest,
    CorpusBuildResult,
    CorpusSourceInventory,
    MEDIA_V3_FIELD_ORDER,
    MEDIA_V3_MANIFEST_SCHEMA_VERSION,
    MEDIA_V3_ROW_SCHEMA_VERSION,
    MEDIA_V3_SCHEMA_VERSION,
    compute_binding_id,
    compute_media_id,
    compute_resource_id,
    validate_media_v3_row,
)
from .media_v3 import (
    LegacyMediaReconciliation,
    MediaV3Assembly,
    MediaV3Config,
    MinioMediaReconciliation,
    VoiceResourcePreparation,
    assemble_media_v3,
    prepare_voice_resource_rows,
    reconcile_active_media_occurrences,
    reconcile_media_v3_minio,
)
from .fidelity import FidelityResult, build_fidelity_ledger
from .orchestrator import HuijiCorpusBuilder
from .projection import CorpusProjection, MediaBindingIntent, project_crawler_semantics
from .voice_stage import VoiceBindingStage

__all__ = [
    "BuildState",
    "CandidateArtifactInput",
    "CandidateWriteResult",
    "CorpusBuildRequest",
    "CorpusBuildResult",
    "CorpusSourceInventory",
    "FidelityResult",
    "HuijiCorpusBuilder",
    "MEDIA_V3_FIELD_ORDER",
    "MEDIA_V3_MANIFEST_SCHEMA_VERSION",
    "MEDIA_V3_ROW_SCHEMA_VERSION",
    "MEDIA_V3_SCHEMA_VERSION",
    "LegacyMediaReconciliation",
    "MediaBindingIntent",
    "MediaV3Assembly",
    "MediaV3Config",
    "MinioMediaReconciliation",
    "CorpusProjection",
    "VoiceBindingStage",
    "VoiceResourcePreparation",
    "assemble_media_v3",
    "build_fidelity_ledger",
    "compute_binding_id",
    "compute_media_id",
    "compute_resource_id",
    "prepare_voice_resource_rows",
    "project_crawler_semantics",
    "reconcile_active_media_occurrences",
    "reconcile_media_v3_minio",
    "validate_media_v3_row",
    "verify_candidate_manifest",
    "write_candidate_artifacts",
]
