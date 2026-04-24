extends Reference


static func voice_energy(time: float, base: Vector2) -> float:
	var primary = sin(time * 7.2 + base.length() * 0.035)
	var secondary = sin(time * 12.4 + base.x * 0.014) * 0.36
	var low_envelope = sin(time * 2.1 + base.y * 0.008) * 0.28

	var mixed = primary * 0.62 + secondary + low_envelope

	return clamp((mixed + 1.25) / 2.5, 0.0, 1.0)


static func state_motion(time: float, base: Vector2, depth: float, state_intensity: float) -> Vector2:
	var energy = voice_energy(time, base)
	var outward = base.normalized() * (10.0 + energy * 30.0)
	var tangent = Vector2(-base.y, base.x).normalized() * energy * 3.2
	var vertical_wave = Vector2(0.0, sin(time * 4.4 + base.x * 0.018) * energy * 3.4)

	return (outward + tangent + vertical_wave) * state_intensity * depth


static func alpha_bonus(time: float, base: Vector2, state_intensity: float) -> float:
	var energy = voice_energy(time, base)

	return (0.05 + energy * 0.18) * state_intensity


static func size_bonus(time: float, base: Vector2, state_intensity: float) -> float:
	var energy = voice_energy(time, base)

	return (0.08 + energy * 0.22) * state_intensity