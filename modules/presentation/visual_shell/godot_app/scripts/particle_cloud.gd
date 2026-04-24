extends Node2D

const VisualStates := preload("res://scripts/state/visual_states.gd")
const EyeFormation := preload("res://scripts/formations/eye_formation.gd")
const VisualPalette := preload("res://scripts/palette/visual_palette.gd")

export(int) var particle_count := 2200
export(float) var radius := 265.0
export(float) var particle_size := 0.58

var particles := []
var time := 0.0
var visual_state := VisualStates.IDLE_PARTICLE_CLOUD
var state_intensity := 0.0
var blink_timer := 0.0
var blink_interval := 25.0
var blink_duration := 0.28


class Particle:
	var base_position := Vector2.ZERO
	var target_position := Vector2.ZERO
	var eye_position := Vector2.ZERO
	var depth := 1.0
	var formation_strength := 1.0
	var is_pupil := false


func _ready() -> void:
	randomize()
	_generate_particles()
	EyeFormation.assign_eye_targets(particles, particle_count)


func _process(delta: float) -> void:
	time += delta
	blink_timer += delta

	if blink_timer > blink_interval:
		blink_timer = 0.0

	_update_state_intensity(delta)
	_update_particles()
	update()


func set_visual_state(new_state: String) -> void:
	visual_state = VisualStates.coerce_state(new_state)


func _generate_particles() -> void:
	particles.clear()

	for _i in range(particle_count):
		var angle := randf() * PI * 2.0
		var dist := pow(randf(), 0.62) * radius

		var particle := Particle.new()
		particle.base_position = Vector2(cos(angle) * dist, sin(angle) * dist)
		particle.target_position = particle.base_position
		particle.depth = rand_range(0.45, 1.0)

		# Most particles form the eyes. Some remain as a loose living aura.
		particle.formation_strength = 1.0
		if randf() < 0.16:
			particle.formation_strength = rand_range(0.08, 0.35)

		particles.append(particle)


func _update_state_intensity(delta: float) -> void:
	var target := 0.0

	if visual_state == VisualStates.LISTENING_CLOUD:
		target = 0.75
	elif visual_state == VisualStates.THINKING_SWARM:
		target = 0.9
	elif visual_state == VisualStates.SPEAKING_PULSE:
		target = 0.85
	elif visual_state == VisualStates.SCANNING_EYES:
		target = 1.0
	elif visual_state == VisualStates.SHOW_SELF_EYES:
		target = 0.92
	elif visual_state == VisualStates.ERROR_DEGRADED:
		target = 0.65

	state_intensity = lerp(state_intensity, target, delta * 2.8)


func _update_particles() -> void:
	for particle in particles:
		var base := particle.base_position

		if VisualStates.is_eye_formation_state(visual_state):
			var blink_scale := _blink_scale()
			var eye_position := Vector2(
				particle.eye_position.x,
				particle.eye_position.y * blink_scale
			)

			base = particle.base_position.linear_interpolate(
				eye_position,
				particle.formation_strength
			)

		var breathing := sin(time * 0.55 + base.length() * 0.038)
		var organic_noise := Vector2(
			sin(time * 0.75 + base.x * 0.018),
			cos(time * 0.75 + base.y * 0.018)
		) * 2.4 * particle.depth

		var state_motion := _state_motion_for_particle(base, particle.depth)
		var desired_position := base \
			+ organic_noise \
			+ Vector2(breathing, breathing) * 1.8 \
			+ state_motion

		particle.target_position = particle.target_position.linear_interpolate(
			desired_position,
			0.045
		)


func _blink_scale() -> float:
	if blink_timer > blink_duration:
		return 1.0

	var progress := blink_timer / blink_duration
	var close_open := sin(progress * PI)

	return max(0.12, 1.0 - close_open * 0.88)


func _state_motion_for_particle(base: Vector2, depth: float) -> Vector2:
	if visual_state == VisualStates.LISTENING_CLOUD:
		var ring_wave := sin(time * 3.4 + base.length() * 0.035)
		var outward := base.normalized() * (22.0 + ring_wave * 14.0)
		var vertical_attention := Vector2(
			0.0,
			sin(time * 2.2 + base.x * 0.025) * 8.0
		)

		return (outward + vertical_attention) * state_intensity * depth

	if visual_state == VisualStates.THINKING_SWARM:
		var tangent := Vector2(-base.y, base.x).normalized()
		var inward := -base.normalized() * 20.0
		var spiral_wave := sin(time * 4.0 + base.length() * 0.05)

		return (
			(tangent * 44.0)
			+ inward
			+ (base.normalized() * spiral_wave * 18.0)
		) * state_intensity * depth

	if visual_state == VisualStates.SPEAKING_PULSE:
		var pulse := sin(time * 8.0 + base.length() * 0.035)
		return base.normalized() * pulse * 26.0 * state_intensity * depth

	if visual_state == VisualStates.SCANNING_EYES:
		var scan := sin(time * 2.5 + base.x * 0.02)
		return Vector2(scan * 4.0, 0.0) * depth

	if visual_state == VisualStates.SHOW_SELF_EYES:
		var calm_attention := sin(time * 1.6 + base.x * 0.012)
		return Vector2(calm_attention * 1.8, 0.0) * depth

	if visual_state == VisualStates.ERROR_DEGRADED:
		var weak_drift := sin(time * 0.8 + base.length() * 0.018)
		return base.normalized() * weak_drift * 5.0 * state_intensity * depth

	return Vector2.ZERO


func _draw() -> void:
	for particle in particles:
		var position := particle.target_position
		var alpha := 0.30 + particle.depth * 0.42
		var size := particle_size * particle.depth

		if VisualStates.is_eye_formation_state(visual_state):
			alpha += 0.22 * state_intensity
			if particle.is_pupil:
				size += 0.32
				alpha = 0.92
		elif visual_state == VisualStates.THINKING_SWARM:
			alpha += 0.16 * state_intensity
		elif visual_state == VisualStates.SPEAKING_PULSE:
			size += 0.16 * state_intensity
		elif visual_state == VisualStates.LISTENING_CLOUD:
			alpha += 0.10 * state_intensity
		elif visual_state == VisualStates.ERROR_DEGRADED:
			alpha *= 0.78

		draw_circle(
			position,
			size,
			VisualPalette.color_for_particle(
				particle,
				visual_state,
				position,
				radius,
				clamp(alpha, 0.0, 1.0)
			)
		)