from pytest import approx

from chemunited.core.common.constant import PATTERN_DIMENSION
from chemunited.qt.elements.component.component_parts.scene_item import (
    ConnectivityBadge,
)


def _mapped_icon_center(badge: ConnectivityBadge):
    return badge.mapToParent(badge.transformOriginPoint())


def test_connectivity_badge_preserves_icon_center_after_status_change(qapp):
    badge = ConnectivityBadge(dimension=PATTERN_DIMENSION // 3)
    badge.set_icon_center(0, -20)

    center_before = _mapped_icon_center(badge)
    badge.setStatus(True, "BubblePower")
    center_after = _mapped_icon_center(badge)

    assert center_after.x() == approx(center_before.x())
    assert center_after.y() == approx(center_before.y())


def test_connectivity_badge_api_label_is_centered_below_icon(qapp):
    badge = ConnectivityBadge(dimension=PATTERN_DIMENSION // 3)
    badge.setStatus(True, "BubblePower")
    badge.set_api_visible(True)
    badge.set_icon_center(0, -20)

    full_bounds = badge.mapToParent(badge.boundingRect()).boundingRect()
    icon_center = _mapped_icon_center(badge)
    font = badge._api_font()

    assert full_bounds.center().x() == approx(icon_center.x())
    assert full_bounds.bottom() > icon_center.y() + badge.icon_scene_size / 2
    assert font.bold()
    assert font.pixelSize() * badge.scale() == approx(
        badge.API_FONT_PIXEL_SIZE,
        rel=0.02,
    )


def test_connectivity_badge_api_label_is_hidden_by_default(qapp):
    badge = ConnectivityBadge(dimension=PATTERN_DIMENSION // 3)
    badge.setStatus(True, "BubblePower")
    badge.set_icon_center(0, -20)

    full_bounds = badge.mapToParent(badge.boundingRect()).boundingRect()
    icon_bounds = badge.mapToParent(
        super(ConnectivityBadge, badge).boundingRect()
    ).boundingRect()

    assert full_bounds.bottom() == approx(icon_bounds.bottom())

    badge.set_api_visible(True)
    visible_bounds = badge.mapToParent(badge.boundingRect()).boundingRect()

    assert visible_bounds.bottom() > icon_bounds.bottom()
