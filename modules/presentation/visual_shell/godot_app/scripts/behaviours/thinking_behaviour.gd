extends Reference


static func state_motion(time: float, base: Vector2, depth: float, state_intensity: float) -> Vector2:
	var tangent = Vector2(-base.y, base.x).normalized()
	var inward = -base.normalized() * 24.0

	var spiral_wave = sin(time * 4.3 + base.length() * 0.052)
	var core_pressure = cos(time * 2.0 + base.x * 0.011)
	var micro_turbulence = Vector2(
		sin(time * 5.1 + base.y * 0.021),
		cos(time * 4.6 + base.x * 0.019)
	) * 5.0

	var swirl = tangent * (38.0 + spiral_wave * 12.0)
	var compression = inward * (0.72 + core_pressure * 0.18)

	return (swirl + compression + micro_turbulence) * state_intensity * depth


static func alpha_bonus(time: float, base: Vector2, state_intensity: float) -> float:
	var processing = sin(time * 5.0 + base.length() * 0.04)
	var normalized = clamp((processing + 1.0) / 2.0, 0.0, 1.0)

	return (0.10 + normalized * 0.12) * state_intensity


static func size_bonus(time: float, base: Vector2, state_intensity: float) -> float:
	var pulse = cos(time * 3.8 + base.x * 0.018)
	var normalized = clamp((pulse + 1.0) / 2.0, 0.0, 1.0)

	return (0.03 + normalized * 0.10) * state_intensity
