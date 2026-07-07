"""Vegetation analysis pipeline — Phase 3 (VARI → Region Extraction).

Public surface:
    VegetationPipeline      — top-level assembler; call process_frame() per frame.
    SynchronizedFrame       — camera frame + telemetry snapshot.
    Region                  — single extracted vegetation region (Phase 3C output).
    MissionSessionContext   — per-session camera + mission metadata snapshot.

Nothing in this package is imported by or coupled to the mission runner,
planners, or any existing API router.  Side-effect: zero at import time.
"""
