extends Reference


static func assign_eye_targets(particles: Array, particle_count: int) -> void:
	var eye_targets := build_eye_targets(particle_count)

	if eye_targets.empty():
		return

	var fallback_size := eye_targets.size()
	var index := 0

	for i in range(particles.size()):
		var target := {}

		if i < eye_targets.size():
			target = eye_targets[i]
		else:
			target = eye_targets[index]
			index += 1
			if index >= fallback_size:
				index = 0

		particles[i].eye_position = target["position"]
		particles[i].is_pupil = target["is_pupil"]


static func build_eye_targets(particle_count: int) -> Array:
	var targets := []

	var left_eye := _make_eye_points(
		Vector2(-105.0, -20.0),
		95.0,
		38.0,
		int(particle_count * 0.42)
	)

	var right_eye := _make_eye_points(
		Vector2(105.0, -20.0),
		95.0,
		38.0,
		int(particle_count * 0.42)
	)

	var pupils := _make_pupil_points(particle_count)

	targets.append_array(left_eye)
	targets.append_array(right_eye)
	targets.append_array(pupils)

	return targets


static func _make_eye_points(center: Vector2, width: float, height: float, point_count: int) -> Array:
	var points := []

	for i in range(point_count):
		var t := float(i) / float(max(1, point_count - 1))
		var angle := t * PI * 2.0

		var outline := Vector2(cos(angle) * width, sin(angle) * height)
		var lid_wave := sin(t * PI * 2.0) * 5.0
		var jitter := Vector2(rand_range(-2.8, 2.8), rand_range(-1.8, 1.8))

		points.append({
			"position": center + outline + Vector2(0.0, lid_wave) + jitter,
			"is_pupil": false,
		})

	return points


static func _make_pupil_points(particle_count: int) -> Array:
	var points := []
	var pupil_count_per_eye := int(particle_count * 0.08)

	points.append_array(_make_single_pupil(Vector2(-105.0, -20.0), 18.0, pupil_count_per_eye))
	points.append_array(_make_single_pupil(Vector2(105.0, -20.0), 18.0, pupil_count_per_eye))

	return points


static func _make_single_pupil(center: Vector2, pupil_radius: float, point_count: int) -> Array:
	var points := []

	for _i in range(point_count):
		var angle := randf() * PI * 2.0
		var dist := sqrt(randf()) * pupil_radius
		var position := center + Vector2(cos(angle) * dist, sin(angle) * dist)

		points.append({
			"position": position,
			"is_pupil": true,
		})

	return points
