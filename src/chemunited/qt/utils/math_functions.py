import numpy as np
from numpy import ndarray
from scipy.interpolate import splev, splprep
from scipy.special import voigt_profile

_CURVE_RESOLUTION = 30
_CORNER_RADIUS = 10


def _unit_vector(v: ndarray) -> ndarray:
    norm = np.linalg.norm(v)
    if norm < 1e-10:
        return v
    return v / norm


def _round_corner(
    p0: ndarray, p1: ndarray, p2: ndarray, radius: float
) -> tuple[ndarray, list[ndarray], ndarray]:
    v1 = _unit_vector(p0 - p1)
    v2 = _unit_vector(p2 - p1)

    if np.abs(np.cross(v1, v2)) < 1e-6:
        return p1, [p1], p1  # collinear — no corner needed

    bisector = _unit_vector(v1 + v2)
    angle = np.arccos(np.clip(np.dot(v1, bisector), -1.0, 1.0))
    tangent_length = radius / np.sin(angle / 2)

    p_start = p1 + v1 * tangent_length
    p_end = p1 + v2 * tangent_length

    t_vals = np.linspace(0, 1, _CURVE_RESOLUTION)
    bezier_points = [
        (1 - t) ** 2 * p_start + 2 * (1 - t) * t * p1 + t**2 * p_end for t in t_vals
    ]
    return p_start, bezier_points, p_end


def build_straight_path(
    points: list | ndarray, radius: float = _CORNER_RADIUS
) -> ndarray:
    """Polyline with rounded corners via quadratic Bezier.

    Args:
        points: sequence of (x, y) waypoints — origin, inflections, destination.
        radius: corner rounding radius in scene units.

    Returns:
        ndarray of shape (N, 2) ready to feed into QPainterPath.
    """
    points = np.array(points)
    if len(points) < 2:
        return points

    if len(points) == 2:
        return points  # single segment, no corners to round

    output = [points[0]]
    for i in range(1, len(points) - 1):
        p0, p1, p2 = points[i - 1], points[i], points[i + 1]
        p_start, bezier_points, p_end = _round_corner(p0, p1, p2, radius)
        output.append(p_start)
        output.extend(bezier_points[1:])
    output.append(points[-1])

    return np.array(output)


def build_smooth_path(points: list | ndarray) -> ndarray:
    """Smooth cubic spline through all waypoints.

    Args:
        points: sequence of (x, y) waypoints — origin, inflections, destination.

    Returns:
        ndarray of shape (N, 2) ready to feed into QPainterPath.
    """
    points = np.array(points)
    if len(points) < 2:
        return points

    if len(points) < 4:
        return points  # not enough points for cubic spline, return as-is

    xy = points.T  # shape (2, N)
    tck, _ = splprep(xy, s=0, k=3)
    u = np.linspace(0, 1, _CURVE_RESOLUTION)
    smooth = splev(u, tck)

    return np.array(smooth).T  # back to shape (N, 2)


def multi_peak(x, peaks):
    y = np.zeros_like(x)
    for x0, gamma, sigma, A in peaks:
        y += A * voigt_profile(x - x0, sigma, gamma)
    return y


def build_snake_path(radius: float, length: float, n_circle: int, samples: int = 50):
    # angles (same as your -linspace(np.pi/2, 3*np.pi/2, 50))
    t = -np.linspace(np.pi / 2, 3 * np.pi / 2, samples)

    xs_list, ys_list = [], []
    for n in range(n_circle):
        x0 = n * 2 * radius
        direction = 1 if n % 2 == 0 else -1
        y0 = 0 if n % 2 == 0 else length

        xs = x0 + radius * np.sin(t)
        ys = y0 + direction * radius * np.cos(t)
        xs_list.append(xs)
        ys_list.append(ys)

    xs = np.concatenate(xs_list)
    ys = np.concatenate(ys_list)

    # (1) keep as Nx2 list
    points_array = [xs, ys]

    start_point = (points_array[0][0], points_array[1][1])
    end_point = (points_array[0][-1], points_array[1][-1])

    return points_array, start_point, end_point


def spring(start_pos: tuple[float, float] = (0.0, 0.0), length=50, coils=6, width=25):

    t_max = 2 * np.pi * coils
    t = np.linspace(0, t_max, 1000)
    r = width / 2
    x0, y0 = start_pos

    x = (length / t_max) * t + r * np.sin(t)
    y = y0 + 2 * r * np.cos(t)

    return x, y