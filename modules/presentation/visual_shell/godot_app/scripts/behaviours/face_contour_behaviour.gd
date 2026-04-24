extends Reference


static func formation_strength(base_strength: float, state_intensity: float) -> float:
	return clamp(base_strength * (0.86 + state_intensity * 0.12), 0.0, 1.0)


static func state_motion(time: float, base: Vector2, depth: float, state_intensity: float) -> Vector2:
	var vertical_breath = sin(time * 0.85 + base.y * 0.012) * 1.8
	var contour_shimmer = cos(time * 1.15 + base.x * 0.018) * 1.2
	var subtle_pull = -base.normalized() * 1.6 * state_intensity

	return (Vector2(contour_shimmer, vertical_breath) + subtle_pull) * depth


static func alpha_bonus(state_intensity: float) -> float:
	return 0.16 * state_intensity


static func size_bonus(state_intensity: float) -> float:
	return 0.06 * state_intensity