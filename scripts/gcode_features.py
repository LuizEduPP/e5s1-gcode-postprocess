"""Prusa ;TYPE: classification for transform routing."""
from __future__ import annotations

from config import (
    PRESERVE_GEOMETRY_FEATURES,
    TYPE_BOTTOM_SOLID,
    TYPE_BRIDGE,
    TYPE_BRIM,
    TYPE_EXTERNAL,
    TYPE_GAP_FILL,
    TYPE_INTERFACE,
    TYPE_INTERNAL,
    TYPE_IRONING,
    TYPE_OUTER_BRIM,
    TYPE_OVERHANG,
    TYPE_OVERHANG_BRIDGE,
    TYPE_PERIMETER,
    TYPE_SOLID,
    TYPE_SUPPORT,
    TYPE_SUPPORT_MAT,
    TYPE_TOP_SOLID,
)


def type_feature(line: str) -> str | None:
    if TYPE_IRONING in line:
        return "ironing"
    if TYPE_TOP_SOLID in line:
        return "top"
    if TYPE_INTERFACE in line:
        return "interface"
    if TYPE_SUPPORT_MAT in line or (TYPE_SUPPORT in line and TYPE_INTERFACE not in line):
        return "support"
    if TYPE_BOTTOM_SOLID in line:
        return "bottom"
    if TYPE_BRIM in line or TYPE_OUTER_BRIM in line:
        return "brim"
    if TYPE_EXTERNAL in line:
        return "external"
    if TYPE_GAP_FILL in line:
        return "gap_fill"
    if TYPE_PERIMETER in line:
        return "perimeter"
    if TYPE_INTERNAL in line:
        return "internal"
    if TYPE_SOLID in line:
        return "solid"
    if TYPE_OVERHANG_BRIDGE in line or TYPE_OVERHANG in line:
        return "overhang"
    if TYPE_BRIDGE in line:
        return "bridge"
    if ";TYPE:" in line:
        return "other"
    return None


def preserves_geometry(kind: str | None) -> bool:
    return kind in PRESERVE_GEOMETRY_FEATURES
