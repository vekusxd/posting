"""Geometry for resizing the main screen's panels.

Two dividers can be moved: the edge of the collection browser that faces the
rest of the app, and the border between the request editor and the response area.
"""

from typing import Literal

from textual.geometry import Region

ResizeTarget = Literal["sidebar", "split"]

SIDEBAR_MIN_WIDTH = 16
"""The narrowest the collection browser can be made."""
SIDEBAR_MIN_REMAINING = 30
"""Cells that must stay available to the request and response sections."""
SPLIT_MIN = 15
SPLIT_MAX = 85
"""Bounds of the request editor's share of the split, in percent."""
SPLIT_DEFAULT = 50


def clamp_sidebar_width(width: int, body_width: int) -> int:
    """Keep the collection browser between its minimum and what the body can spare."""
    maximum = max(SIDEBAR_MIN_WIDTH, body_width - SIDEBAR_MIN_REMAINING)
    return max(SIDEBAR_MIN_WIDTH, min(width, maximum))


def clamp_split(percent: int) -> int:
    return max(SPLIT_MIN, min(percent, SPLIT_MAX))


def sidebar_width_at(x: int, sidebar: Region, dock: str) -> int:
    """The sidebar width that puts its inner edge under the pointer at column `x`."""
    if dock == "right":
        return sidebar.right - x
    return x - sidebar.x + 1


def split_at(offset: int, request: Region, response: Region, horizontal: bool) -> int:
    """The request editor's share of the split, in percent, for a pointer at `offset`.

    `offset` is the pointer's screen x when the layout is horizontal, y otherwise.
    """
    if horizontal:
        start, end = request.x, response.right
    else:
        start, end = request.y, response.bottom
    total = end - start
    if total <= 0:
        return SPLIT_DEFAULT
    return round((offset - start + 1) / total * 100)


def on_sidebar_edge(x: int, y: int, sidebar: Region, dock: str) -> bool:
    """Whether the pointer is on the sidebar's border that faces the app body."""
    if not sidebar.y <= y < sidebar.bottom:
        return False
    edge = sidebar.x if dock == "right" else sidebar.right - 1
    return x == edge


def on_split_edge(
    x: int, y: int, request: Region, response: Region, horizontal: bool
) -> bool:
    """Whether the pointer is on either border between the request and the response."""
    if horizontal:
        if not request.y <= y < request.bottom:
            return False
        return x in (request.right - 1, response.x)
    if not request.x <= x < request.right:
        return False
    return y in (request.bottom - 1, response.y)
