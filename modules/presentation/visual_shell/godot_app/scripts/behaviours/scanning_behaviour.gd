extends Reference


static func attention_offset(time: float, base: Vector2) -> Vector2:
	var gaze_x = sin(time * 0.95) * 15.0
	var micro_x = sin(time * 2.25 + base.y * 0.012) * 3.2
	var micro_y = cos(time * 0.72 + base.x * 0.008) * 2.4

	return Vector2(gaze_x + micro_x, micro_y)


static func formation_strength(base_strength: float, state_intensity: float) -> float:
	return clamp(base_strength * (0.90 + state_intensity * 0.10), 0.0, 1.0)


static func state_motion(time: float, base: Vector2, depth: float, state_intensity: float) -> Vector2:
	var scan_wave = sin(time * 3.1 + base.x * 0.025)
	var vertical_trace = cos(time * 1.8 + base.y * 0.017)
	var focus_pull = -base.normalized() * 1.4 * state_intensity

	var scan_motion = Vector2(
		scan_wave * 5.2,
		vertical_trace * 1.8
	)

	return (scan_motion + focus_pull) * depth


static func alpha_bonus(time: float, base: Vector2, state_intensity: float) -> float:
	var scan_band = sin(time * 4.6 + base.y * 0.034)
	var normalized = clamp((scan_band + 1.0) / 2.0, 0.0, 1.0)

	return (0.12 + normalized * 0.15) * state_intensity


static func size_bonus(time: float, base: Vector2, state_intensity: float) -> float:
	var scan_energy = cos(time * 3.4 + base.x * 0.02)
	var normalized = clamp((scan_energy + 1.0) / 2.0, 0.0, 1.0)

	return (0.04 + normalized * 0.10) * state_intensity


static func pupil_size_bonus() -> float:
	return 0.36


static func overlay_alpha(time: float, state_intensity: float) -> float:
	var sweep_energy = clamp((sin(time * 1.15) + 1.0) / 2.0, 0.0, 1.0)

	return (0.04 + sweep_energy * 0.08) * state_intensity


static func overlay_y(time: float, radius: float) -> float:
	return sin(time * 0.78) * radius * 0.36


static func overlay_width(radius: float) -> float:
	return radius * 1.48


static func overlay_color(alpha: float) -> Color:
	return Color(0.34, 0.82, 1.0, alpha)
