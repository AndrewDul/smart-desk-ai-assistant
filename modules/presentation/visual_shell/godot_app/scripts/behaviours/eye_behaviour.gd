extends Reference

const VisualStates = preload("res://scripts/state/visual_states.gd")


static func blink_scale(blink_timer: float, blink_duration: float) -> float:
	if blink_timer > blink_duration:
		return 1.0

	var progress = blink_timer / blink_duration
	var close_open = sin(progress * PI)

	return max(0.12, 1.0 - close_open * 0.88)


static func attention_offset(visual_state: String, time: float, base: Vector2) -> Vector2:
	if visual_state == VisualStates.SHOW_SELF_EYES:
		var calm_x = sin(time * 0.55) * 2.2
		var calm_y = cos(time * 0.42) * 1.0
		return Vector2(calm_x, calm_y)

	return Vector2.ZERO


static func formation_strength_for_state(
	base_strength: float,
	visual_state: String,
	state_intensity: float
) -> float:
	if visual_state == VisualStates.SHOW_SELF_EYES:
		return clamp(base_strength * 0.94 + 0.06, 0.0, 1.0)

	return base_strength


static func state_motion(visual_state: String, time: float, base: Vector2, depth: float) -> Vector2:
	if visual_state == VisualStates.SHOW_SELF_EYES:
		var calm_attention = sin(time * 1.2 + base.x * 0.01)
		var breathing_focus = cos(time * 0.9 + base.y * 0.008)
		return Vector2(calm_attention * 1.4, breathing_focus * 0.7) * depth

	return Vector2.ZERO


static func alpha_bonus(visual_state: String, state_intensity: float) -> float:
	if visual_state == VisualStates.SHOW_SELF_EYES:
		return 0.18 * state_intensity

	return 0.0


static func pupil_size_bonus(visual_state: String) -> float:
	if visual_state == VisualStates.SHOW_SELF_EYES:
		return 0.28

	return 0.0
