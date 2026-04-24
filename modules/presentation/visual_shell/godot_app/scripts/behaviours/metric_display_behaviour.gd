extends Reference

const VisualStates = preload("res://scripts/state/visual_states.gd")

const TEMPERATURE_GLYPH_COLOR = Color(0.72, 0.90, 1.00, 1.0)
const TEMPERATURE_AURA_COLOR = Color(0.78, 0.84, 0.94, 1.0)

const BATTERY_GREEN = Color(0.18, 0.86, 0.34, 1.0)
const BATTERY_BLUE = Color(0.25, 0.55, 1.00, 1.0)
const BATTERY_YELLOW = Color(0.95, 0.82, 0.20, 1.0)
const BATTERY_RED = Color(0.95, 0.22, 0.22, 1.0)
const BATTERY_AURA_BLEND = Color(0.82, 0.88, 0.96, 1.0)


static func formation_strength(base_strength: float, state_intensity: float, is_metric_particle: bool) -> float:
	if is_metric_particle:
		return clamp(0.82 + state_intensity * 0.18, 0.0, 1.0)

	return clamp(base_strength * 0.18, 0.0, 0.22)


static func state_motion(
	time: float,
	base: Vector2,
	depth: float,
	state_intensity: float,
	is_metric_particle: bool
) -> Vector2:
	if is_metric_particle:
		var shimmer = sin(time * 2.3 + base.length() * 0.024)
		return base.normalized() * shimmer * 1.6 * depth * (0.30 + state_intensity * 0.35)

	var aura_motion = Vector2(
		sin(time * 0.95 + base.x * 0.018),
		cos(time * 0.95 + base.y * 0.018)
	)

	return aura_motion * 4.0 * depth * (0.40 + state_intensity * 0.40)


static func alpha_bonus(
	time: float,
	base: Vector2,
	state_intensity: float,
	is_metric_particle: bool
) -> float:
	if is_metric_particle:
		var pulse = (sin(time * 2.1 + base.length() * 0.02) + 1.0) * 0.5
		return 0.20 + pulse * 0.12 + state_intensity * 0.06

	return 0.03 + state_intensity * 0.04


static func size_bonus(state_intensity: float, is_metric_particle: bool) -> float:
	if is_metric_particle:
		return 0.20 + state_intensity * 0.10

	return 0.02 + state_intensity * 0.02


static func color_for_particle(
	visual_state: String,
	is_metric_particle: bool,
	battery_percent: int,
	alpha: float
) -> Color:
	var color = TEMPERATURE_AURA_COLOR

	if visual_state == VisualStates.TEMPERATURE_GLYPH:
		color = TEMPERATURE_AURA_COLOR
		if is_metric_particle:
			color = TEMPERATURE_GLYPH_COLOR

	elif visual_state == VisualStates.BATTERY_GLYPH:
		var base_battery_color = battery_color_for_percent(battery_percent)
		color = base_battery_color.linear_interpolate(BATTERY_AURA_BLEND, 0.72)
		if is_metric_particle:
			color = base_battery_color

	color.a = clamp(alpha, 0.0, 1.0)
	return color


static func battery_color_for_percent(percent: int) -> Color:
	if percent >= 70:
		return BATTERY_GREEN

	if percent >= 50:
		return BATTERY_BLUE

	if percent >= 35:
		return BATTERY_YELLOW

	return BATTERY_RED