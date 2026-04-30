extends Reference

const FULL_SCALE = 1.0
const COMPACT_MIN_SCALE = 0.58
const COMPACT_MAX_SCALE = 0.82
const COMPACT_FILL = 0.92
const COMPACT_VISUAL_DIAMETER_FACTOR = 0.84


static func target_scale(is_compact: bool, viewport_size: Vector2, radius: float) -> float:
	if not is_compact:
		return FULL_SCALE

	var shortest_side = min(viewport_size.x, viewport_size.y)
	var visual_diameter = radius * 2.0 * COMPACT_VISUAL_DIAMETER_FACTOR
	var target_diameter = shortest_side * COMPACT_FILL

	return clamp(target_diameter / visual_diameter, COMPACT_MIN_SCALE, COMPACT_MAX_SCALE)


static func transform_speed(is_returning: bool) -> float:
	if is_returning:
		return 3.2

	return 2.6


static func state_motion(time: float, base: Vector2, depth: float, state_intensity: float) -> Vector2:
	var tangent = Vector2(-base.y, base.x).normalized()
	var slow_orbit = tangent * sin(time * 0.75 + base.length() * 0.01) * 4.2
	var calm_breath = base.normalized() * sin(time * 1.15 + base.length() * 0.012) * 3.0

	return (slow_orbit + calm_breath) * depth * state_intensity


static func alpha_bonus(time: float, base: Vector2, state_intensity: float) -> float:
	var shimmer = sin(time * 1.7 + base.length() * 0.018)
	var normalized = clamp((shimmer + 1.0) / 2.0, 0.0, 1.0)

	return (0.04 + normalized * 0.06) * state_intensity


static func size_bonus(state_intensity: float) -> float:
	return 0.04 * state_intensity


static func particle_size_multiplier(is_compact: bool) -> float:
	if is_compact:
		return 2.15

	return 1.24


static func should_draw_soft_orb(visual_scale: float) -> bool:
	return visual_scale < 1.15


static func orb_alpha(visual_scale: float) -> float:
	return 0.10


static func orb_radius(radius: float, visual_scale: float) -> float:
	return radius * visual_scale * 0.90


static func orb_color(alpha: float) -> Color:
	return Color(0.20, 0.48, 0.85, alpha)
