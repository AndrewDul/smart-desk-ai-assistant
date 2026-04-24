extends Reference


static func assign_face_targets(particles: Array, particle_count: int) -> void:
	var face_targets = build_face_targets(particle_count)

	if face_targets.empty():
		return

	var fallback_size = face_targets.size()
	var index = 0

	for i in range(particles.size()):
		var target = {}

		if i < face_targets.size():
			target = face_targets[i]
		else:
			target = face_targets[index]
			index += 1
			if index >= fallback_size:
				index = 0

		particles[i].face_position = target["position"]


static func build_face_targets(particle_count: int) -> Array:
	var targets = []

	var contour_count = int(particle_count * 0.68)
	var inner_count = int(particle_count * 0.16)
	var brow_count = int(particle_count * 0.08)
	var lower_glow_count = int(particle_count * 0.08)

	targets.append_array(_make_outer_contour(contour_count))
	targets.append_array(_make_inner_focus_lines(inner_count))
	targets.append_array(_make_soft_brow_arcs(brow_count))
	targets.append_array(_make_lower_presence_glow(lower_glow_count))

	return targets


static func _make_outer_contour(point_count: int) -> Array:
	var points = []
	var center = Vector2(0.0, -6.0)
	var width = 158.0
	var height = 214.0

	for i in range(point_count):
		var t = float(i) / float(max(1, point_count - 1))
		var angle = t * PI * 2.0

		var y_factor = sin(angle)
		var jaw_factor = 1.0 - max(0.0, y_factor) * 0.26
		var temple_factor = 1.0 + max(0.0, -y_factor) * 0.05

		var x = cos(angle) * width * jaw_factor * temple_factor
		var y = y_factor * height

		if y > 90.0:
			y += pow((y - 90.0) / 120.0, 2.0) * 18.0

		var jitter = Vector2(rand_range(-2.0, 2.0), rand_range(-2.0, 2.0))

		points.append({
			"position": center + Vector2(x, y) + jitter,
		})

	return points


static func _make_inner_focus_lines(point_count: int) -> Array:
	var points = []

	for i in range(point_count):
		var t = float(i) / float(max(1, point_count - 1))
		var side = -1.0
		if i % 2 == 0:
			side = 1.0

		var y = lerp(-72.0, 82.0, t)
		var curve = sin(t * PI) * 26.0
		var x = side * curve

		var jitter = Vector2(rand_range(-1.4, 1.4), rand_range(-1.4, 1.4))

		points.append({
			"position": Vector2(x, y) + jitter,
		})

	return points


static func _make_soft_brow_arcs(point_count: int) -> Array:
	var points = []
	var half_count = int(max(1, point_count / 2))

	points.append_array(_make_single_brow_arc(Vector2(-70.0, -82.0), half_count))
	points.append_array(_make_single_brow_arc(Vector2(70.0, -82.0), half_count))

	return points


static func _make_single_brow_arc(center: Vector2, point_count: int) -> Array:
	var points = []

	for i in range(point_count):
		var t = float(i) / float(max(1, point_count - 1))
		var x = lerp(-42.0, 42.0, t)
		var y = -sin(t * PI) * 10.0
		var jitter = Vector2(rand_range(-1.6, 1.6), rand_range(-1.2, 1.2))

		points.append({
			"position": center + Vector2(x, y) + jitter,
		})

	return points


static func _make_lower_presence_glow(point_count: int) -> Array:
	var points = []

	for _i in range(point_count):
		var angle = randf() * PI * 2.0
		var dist = sqrt(randf()) * 48.0
		var position = Vector2(cos(angle) * dist, 118.0 + sin(angle) * dist * 0.34)

		points.append({
			"position": position,
		})

	return points