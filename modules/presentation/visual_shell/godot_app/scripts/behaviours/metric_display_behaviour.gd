extends Reference

const VisualStates = preload("res://scripts/state/visual_states.gd")

const TEMPERATURE_GLYPH_COLOR = Color(0.78, 0.93, 1.00, 1.0)
const TEMPERATURE_AMBIENT_COLOR = Color(0.70, 0.78, 0.88, 1.0)

const BATTERY_GREEN = Color(0.18, 0.86, 0.34, 1.0)
const BATTERY_BLUE = Color(0.25, 0.55, 1.00, 1.0)
const BATTERY_YELLOW = Color(0.95, 0.82, 0.20, 1.0)
const BATTERY_RED = Color(0.95, 0.22, 0.22, 1.0)
const BATTERY_AMBIENT_COLOR = Color(0.72, 0.78, 0.86, 1.0)


static func formation_strength(base_strength: float, state_intensity: float, is_metric_particle: bool) -> float:
	if is_metric_particle:
		return clamp(0.96 + state_intensity * 0.04, 0.0, 1.0)

	return clamp(base_strength * 0.08, 0.0, 0.10)


static func state_motion(
	time: float,
	base: Vector2,
	depth: float,
	state_intensity: float,
	is_metric_particle: bool
) -> Vector2:
	if is_metric_particle:
		var shimmer = sin(time * 1.9 + base.length() * 0.018)
		return base.normalized() * shimmer * 0.55 * depth * (0.12 + state_intensity * 0.14)

	var aura_motion = Vector2(
		sin(time * 0.82 + base.x * 0.014),
		cos(time * 0.82 + base.y * 0.014)
	)

	return aura_motion * 1.8 * depth * (0.10 + state_intensity * 0.10)


static func alpha_bonus(
	time: float,
	base: Vector2,
	state_intensity: float,
	is_metric_particle: bool
) -> float:
	if is_metric_particle:
		var pulse = (sin(time * 1.9 + base.length() * 0.016) + 1.0) * 0.5
		return 0.32 + pulse * 0.08 + state_intensity * 0.07

	return 0.0


static func size_bonus(state_intensity: float, is_metric_particle: bool) -> float:
	if is_metric_particle:
		return 0.38 + state_intensity * 0.14

	return 0.0


static func color_for_particle(
	visual_state: String,
	is_metric_particle: bool,
	battery_percent: int,
	alpha: float
) -> Color:
	var base_color = TEMPERATURE_GLYPH_COLOR

	if visual_state == VisualStates.BATTERY_GLYPH:
		base_color = battery_color_for_percent(battery_percent)

	if is_metric_particle:
		var metric_color = base_color
		metric_color.a = clamp(alpha, 0.0, 1.0)
		return metric_color

	var ambient_color = TEMPERATURE_AMBIENT_COLOR
	if visual_state == VisualStates.BATTERY_GLYPH:
		ambient_color = BATTERY_AMBIENT_COLOR

	ambient_color.a = min(alpha * 0.08, 0.05)
	return ambient_color


static func battery_color_for_percent(percent: int) -> Color:
	if percent >= 70:
		return BATTERY_GREEN

	if percent >= 50:
		return BATTERY_BLUE

	if percent >= 35:
		return BATTERY_YELLOW

	return BATTERY_RED
