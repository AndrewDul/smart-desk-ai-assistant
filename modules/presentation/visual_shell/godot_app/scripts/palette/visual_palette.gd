extends Reference

const VisualStates := preload("res://scripts/state/visual_states.gd")


static func color_for_particle(
	particle,
	visual_state: String,
	position: Vector2,
	radius: float,
	alpha: float
) -> Color:
	var gradient_factor := clamp((position.y + radius) / (radius * 2.0), 0.0, 1.0)

	if VisualStates.is_eye_formation_state(visual_state):
		if particle.is_pupil:
			return Color(0.25, 0.72, 1.0, alpha)

		return Color(0.58, 0.92, 1.0, alpha).linear_interpolate(
			Color(0.02, 0.20, 0.75, alpha),
			gradient_factor
		)

	if visual_state == VisualStates.SPEAKING_PULSE:
		return Color(0.32, 0.72, 1.0, alpha).linear_interpolate(
			Color(1.0, 0.48, 0.16, alpha),
			gradient_factor
		)

	if visual_state == VisualStates.THINKING_SWARM:
		return Color(0.60, 1.0, 0.72, alpha).linear_interpolate(
			Color(0.05, 0.45, 0.22, alpha),
			gradient_factor
		)

	if visual_state == VisualStates.LISTENING_CLOUD:
		return Color(0.92, 0.98, 1.0, alpha).linear_interpolate(
			Color(0.38, 0.78, 1.0, alpha),
			gradient_factor
		)

	if visual_state == VisualStates.ERROR_DEGRADED:
		return Color(1.0, 0.48, 0.20, alpha).linear_interpolate(
			Color(0.52, 0.12, 0.05, alpha),
			gradient_factor
		)

	return Color(0.92, 0.96, 1.0, alpha)