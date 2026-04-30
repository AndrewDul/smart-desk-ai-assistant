extends Reference


static func state_motion(time: float, base: Vector2, depth: float, state_intensity: float) -> Vector2:
	var radial_wave = sin(time * 2.8 + base.length() * 0.034)
	var attention_wave = sin(time * 4.2 + base.y * 0.018)
	var outward_strength = 14.0 + radial_wave * 10.0

	var outward = base.normalized() * outward_strength
	var vertical_attention = Vector2(
		0.0,
		attention_wave * 6.0
	)

	var side_focus = Vector2(
		sin(time * 1.4 + base.x * 0.01) * 2.8,
		0.0
	)

	return (outward + vertical_attention + side_focus) * state_intensity * depth


static func alpha_bonus(time: float, base: Vector2, state_intensity: float) -> float:
	var attention = sin(time * 3.0 + base.length() * 0.026)
	var normalized = clamp((attention + 1.0) / 2.0, 0.0, 1.0)

	return (0.06 + normalized * 0.08) * state_intensity


static func size_bonus(time: float, base: Vector2, state_intensity: float) -> float:
	var attention = sin(time * 2.4 + base.y * 0.014)
	var normalized = clamp((attention + 1.0) / 2.0, 0.0, 1.0)

	return normalized * 0.06 * state_intensity
