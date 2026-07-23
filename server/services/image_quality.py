"""Image sharpness / quality scoring.

Four no-reference blur metrics, each computed on a grayscale frame, combined
into a single 0..1 confidence score via configurable weights and reference
values (config.py). Used both for pre-flight camera validation and for
retrying a blurry in-mission capture before accepting it.
"""
from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np

from config import settings


@dataclass
class QualityScore:
    laplacian: float
    tenengrad: float
    brenner: float
    edge_density: float
    confidence: float
    passed: bool

    def as_dict(self) -> dict:
        return {
            "sharpness_laplacian": round(self.laplacian, 3),
            "sharpness_tenengrad": round(self.tenengrad, 3),
            "sharpness_brenner": round(self.brenner, 3),
            "edge_density": round(self.edge_density, 4),
            "quality_confidence": round(self.confidence, 4),
            "quality_passed": self.passed,
        }


def variance_of_laplacian(gray: np.ndarray) -> float:
    return float(cv2.Laplacian(gray, cv2.CV_64F).var())


def tenengrad(gray: np.ndarray) -> float:
    gx = cv2.Sobel(gray, cv2.CV_64F, 1, 0, ksize=3)
    gy = cv2.Sobel(gray, cv2.CV_64F, 0, 1, ksize=3)
    return float(np.mean(gx * gx + gy * gy))


def brenner(gray: np.ndarray) -> float:
    shifted = np.roll(gray.astype(np.float64), -2, axis=1)
    diff = (shifted - gray.astype(np.float64)) ** 2
    return float(np.mean(diff[:, :-2]))


def edge_density(gray: np.ndarray) -> float:
    edges = cv2.Canny(gray, 100, 200)
    return float(np.count_nonzero(edges)) / float(edges.size)


def _normalised(value: float, reference: float) -> float:
    if reference <= 0:
        return 0.0
    return min(1.0, value / reference)


def score_frame(frame: np.ndarray) -> QualityScore:
    """Score one BGR frame. Higher confidence = sharper."""
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

    lap = variance_of_laplacian(gray)
    ten = tenengrad(gray)
    bren = brenner(gray)
    edges = edge_density(gray)

    confidence = (
        settings.QUALITY_WEIGHT_LAPLACIAN * _normalised(lap, settings.QUALITY_LAPLACIAN_REF)
        + settings.QUALITY_WEIGHT_TENENGRAD * _normalised(ten, settings.QUALITY_TENENGRAD_REF)
        + settings.QUALITY_WEIGHT_BRENNER * _normalised(bren, settings.QUALITY_BRENNER_REF)
        + settings.QUALITY_WEIGHT_EDGE_DENSITY * _normalised(edges, settings.QUALITY_EDGE_DENSITY_REF)
    )

    return QualityScore(
        laplacian=lap,
        tenengrad=ten,
        brenner=bren,
        edge_density=edges,
        confidence=confidence,
        passed=confidence >= settings.QUALITY_CONFIDENCE_THRESHOLD,
    )
