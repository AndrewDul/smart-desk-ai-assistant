extends Reference

const KIND_SOFT_WAVE = "soft_wave"
const KIND_COMPRESS_RELEASE = "compress_release"
const KIND_ORBIT_GLINT = "orbit_glint"


static func next_delay() -> float:
	return rand_range(28.0, 48.0)


static func next_duration() -> float:
	return rand_range(2.4, 4.2)


static func pick_kind() -> String:
	var roll = randf()

	if roll < 0.42:
		return KIND_SOFT_WAVE

	if roll < 0.76:
		return KIND_COMPRESS_RELEASE

	return KIND_ORBIT_GLINT


static func envelope(age: float, duration: float) -> float:
	if duration <= 0.0:
		return 0.0

	var progress = clamp(age / duration, 0.0, 1.0)

	return sin(progress * PI)


static func state_motion(
	time: float,
	base: Vector2,
	depth: float,
	micro_intensity: float,
	kind: String
) -> Vector2:
	if micro_intensity <= 0.0:
		return Vector2.ZERO

	if kind == KIND_SOFT_WAVE:
		return _soft_wave_motion(time, base, depth, micro_intensity)

	if kind == KIND_COMPRESS_RELEASE:
		return _compress_release_motion(time, base, depth, micro_intensity)

	if kind == KIND_ORBIT_GLINT:
		return _orbit_glint_motion(time, base, depth, micro_intensity)

	return Vector2.ZERO


static func alpha_bonus(
	time: float,
	base: Vector2,
	micro_intensity: float,
	kind: String
) -> float:
	if micro_intensity <= 0.0:
		return 0.0

	var shimmer = sin(time * 2.2 + base.length() * 0.018)
	var normalized = clamp((shimmer + 1.0) / 2.0, 0.0, 1.0)

	if kind == KIND_ORBIT_GLINT:
		return (0.03 + normalized * 0.08) * micro_intensity

	return (0.02 + normalized * 0.04) * micro_intensity


static func size_bonus(micro_intensity: float, kind: String) -> float:
	if micro_intensity <= 0.0:
		return 0.0

	if kind == KIND_COMPRESS_RELEASE:
		return 0.07 * micro_intensity

	return 0.04 * micro_intensity


static func _soft_wave_motion(
	time: float,
	base: Vector2,
	depth: float,
	micro_intensity: float
) -> Vector2:
	var wave = sin(time * 1.15 + base.x * 0.018)
	var vertical = Vector2(0.0, wave * 8.0)
	var side = Vector2(cos(time * 0.7 + base.y * 0.01) * 2.4, 0.0)

	return (vertical + side) * depth * micro_intensity


static func _compress_release_motion(
	time: float,
	base: Vector2,
	depth: float,
	micro_intensity: float
) -> Vector2:
	var pulse = sin(time * 1.8 + base.length() * 0.012)
	var radial = base.normalized() * pulse * 13.0

	return radial * depth * micro_intensity


static func _orbit_glint_motion(
	time: float,
	base: Vector2,
	depth: float,
	micro_intensity: float
) -> Vector2:
	var tangent = Vector2(-base.y, base.x).normalized()
	var orbit = tangent * sin(time * 1.2 + base.length() * 0.01) * 7.0
	var inward = -base.normalized() * 2.2

	return (orbit + inward) * depth * micro_intensity
