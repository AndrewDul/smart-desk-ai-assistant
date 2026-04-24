extends Node2D

export(int) var particle_count := 1200
export(float) var radius := 250.0
export(float) var particle_size := 0.65

var particles := []
var time := 0.0
var visual_state := "IDLE_PARTICLE_CLOUD"
var state_intensity := 0.0


class Particle:
	var base_position := Vector2.ZERO
	var offset := Vector2.ZERO
	var velocity := Vector2.ZERO
	var depth := 1.0


func _ready() -> void:
	randomize()
	_generate_particles()


func _process(delta: float) -> void:
	time += delta
	_update_state_intensity(delta)
	_update_particles()
	update()


func set_visual_state(new_state: String) -> void:
	visual_state = new_state


func _generate_particles() -> void:
	particles.clear()

	for _i in range(particle_count):
		var angle = randf() * PI * 2.0
		var dist = pow(randf(), 0.55) * radius

		var particle = Particle.new()
		particle.base_position = Vector2(cos(angle) * dist, sin(angle) * dist)
		particle.offset = Vector2.ZERO
		particle.velocity = Vector2(rand_range(-1.0, 1.0), rand_range(-1.0, 1.0))
		particle.depth = rand_range(0.55, 1.0)

		particles.append(particle)


func _update_state_intensity(delta: float) -> void:
	var target := 0.0

	if visual_state == "LISTENING_CLOUD":
		target = 0.35
	elif visual_state == "THINKING_SWARM":
		target = 0.65
	elif visual_state == "SPEAKING_PULSE":
		target = 0.8
	elif visual_state == "SCANNING_EYES":
		target = 1.0

	state_intensity = lerp(state_intensity, target, delta * 3.0)


func _update_particles() -> void:
	for particle in particles:
		var base = particle.base_position

		var breathing = sin(time * 0.65 + base.length() * 0.045)
		var organic_noise = Vector2(
			sin(time * 0.8 + base.x * 0.018),
			cos(time * 0.8 + base.y * 0.018)
		) * 2.8 * particle.depth

		var state_motion = _state_motion_for_particle(base, particle.depth)

		particle.offset = particle.offset.linear_interpolate(
			organic_noise + Vector2(breathing, breathing) * 2.2 + state_motion,
			0.045
		)


func _state_motion_for_particle(base: Vector2, depth: float) -> Vector2:
	if visual_state == "LISTENING_CLOUD":
		return base.normalized() * 18.0 * state_intensity * depth

	if visual_state == "THINKING_SWARM":
		var tangent = Vector2(-base.y, base.x).normalized()
		return tangent * 32.0 * state_intensity * depth

	if visual_state == "SPEAKING_PULSE":
		var pulse = sin(time * 8.0 + base.length() * 0.035)
		return base.normalized() * pulse * 26.0 * state_intensity * depth

	if visual_state == "SCANNING_EYES":
		var scan = sin(time * 2.5 + base.x * 0.02)
		return Vector2(scan * 28.0, 0.0) * state_intensity * depth

	return Vector2.ZERO


func _draw() -> void:
	for particle in particles:
		var position = particle.base_position + particle.offset
		var alpha = 0.35 + particle.depth * 0.45
		var size = particle_size * particle.depth

		if visual_state == "THINKING_SWARM":
			alpha += 0.12 * state_intensity
		elif visual_state == "SPEAKING_PULSE":
			size += 0.18 * state_intensity
		elif visual_state == "SCANNING_EYES":
			alpha += 0.18 * state_intensity

		draw_circle(position, size, Color(0.78, 0.88, 1.0, clamp(alpha, 0.0, 1.0)))