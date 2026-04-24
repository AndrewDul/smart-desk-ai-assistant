extends Node2D

const VisualStates = preload("res://scripts/state/visual_states.gd")
const EyeFormation = preload("res://scripts/formations/eye_formation.gd")
const FaceContourFormation = preload("res://scripts/formations/face_contour_formation.gd")
const ListeningBehaviour = preload("res://scripts/behaviours/listening_behaviour.gd")
const ThinkingBehaviour = preload("res://scripts/behaviours/thinking_behaviour.gd")
const SpeakingBehaviour = preload("res://scripts/behaviours/speaking_behaviour.gd")
const ScanningBehaviour = preload("res://scripts/behaviours/scanning_behaviour.gd")
const EyeBehaviour = preload("res://scripts/behaviours/eye_behaviour.gd")
const FaceContourBehaviour = preload("res://scripts/behaviours/face_contour_behaviour.gd")
const VisualPalette = preload("res://scripts/palette/visual_palette.gd")

export(int) var particle_count = 2200
export(float) var radius = 265.0
export(float) var particle_size = 0.58

var particles = []
var time = 0.0
var visual_state = VisualStates.IDLE_PARTICLE_CLOUD
var state_intensity = 0.0
var blink_timer = 0.0
var blink_interval = 25.0
var blink_duration = 0.28


class Particle:
	var base_position = Vector2.ZERO
	var target_position = Vector2.ZERO
	var eye_position = Vector2.ZERO
	var face_position = Vector2.ZERO
	var depth = 1.0
	var formation_strength = 1.0
	var is_pupil = false


func _ready() -> void:
	randomize()
	_generate_particles()
	EyeFormation.assign_eye_targets(particles, particle_count)
	FaceContourFormation.assign_face_targets(particles, particle_count)


func _process(delta: float) -> void:
	time += delta
	blink_timer += delta

	if blink_timer > blink_interval:
		blink_timer = 0.0

	_update_state_intensity(delta)
	_update_particles()
	update()


func set_visual_state(new_state: String) -> void:
	var previous_state = visual_state
	visual_state = VisualStates.coerce_state(new_state)

	if visual_state == VisualStates.SHOW_SELF_EYES and previous_state != visual_state:
		blink_timer = 0.0


func _generate_particles() -> void:
	particles.clear()

	for _i in range(particle_count):
		var angle = randf() * PI * 2.0
		var dist = pow(randf(), 0.62) * radius

		var particle = Particle.new()
		particle.base_position = Vector2(cos(angle) * dist, sin(angle) * dist)
		particle.target_position = particle.base_position
		particle.depth = rand_range(0.45, 1.0)

		# Most particles form focused shapes. Some remain as a loose living aura.
		particle.formation_strength = 1.0
		if randf() < 0.16:
			particle.formation_strength = rand_range(0.08, 0.35)

		particles.append(particle)


func _update_state_intensity(delta: float) -> void:
	var target = 0.0

	if visual_state == VisualStates.LISTENING_CLOUD:
		target = 0.78
	elif visual_state == VisualStates.THINKING_SWARM:
		target = 0.94
	elif visual_state == VisualStates.SPEAKING_PULSE:
		target = 0.88
	elif visual_state == VisualStates.SCANNING_EYES:
		target = 1.0
	elif visual_state == VisualStates.SHOW_SELF_EYES:
		target = 0.92
	elif visual_state == VisualStates.FACE_CONTOUR:
		target = 0.82
	elif visual_state == VisualStates.ERROR_DEGRADED:
		target = 0.65

	state_intensity = lerp(state_intensity, target, delta * 2.8)


func _update_particles() -> void:
	for particle in particles:
		var base = particle.base_position

		if VisualStates.is_eye_formation_state(visual_state):
			base = _eye_base_position(particle)

		elif VisualStates.is_face_formation_state(visual_state):
			base = _face_base_position(particle)

		var breathing = sin(time * 0.55 + base.length() * 0.038)
		var organic_noise = Vector2(
			sin(time * 0.75 + base.x * 0.018),
			cos(time * 0.75 + base.y * 0.018)
		) * 2.4 * particle.depth

		var state_motion = _state_motion_for_particle(base, particle.depth)
		var desired_position = base \
			+ organic_noise \
			+ Vector2(breathing, breathing) * 1.8 \
			+ state_motion

		particle.target_position = particle.target_position.linear_interpolate(
			desired_position,
			0.045
		)


func _eye_base_position(particle) -> Vector2:
	var blink_scale = EyeBehaviour.blink_scale(blink_timer, blink_duration)
	var attention_offset = Vector2.ZERO
	var formation_strength = particle.formation_strength

	if visual_state == VisualStates.SCANNING_EYES:
		attention_offset = ScanningBehaviour.attention_offset(
			time,
			particle.base_position
		)
		formation_strength = ScanningBehaviour.formation_strength(
			particle.formation_strength,
			state_intensity
		)
	else:
		attention_offset = EyeBehaviour.attention_offset(
			visual_state,
			time,
			particle.base_position
		)
		formation_strength = EyeBehaviour.formation_strength_for_state(
			particle.formation_strength,
			visual_state,
			state_intensity
		)

	var eye_position = Vector2(
		particle.eye_position.x,
		particle.eye_position.y * blink_scale
	) + attention_offset

	return particle.base_position.linear_interpolate(
		eye_position,
		formation_strength
	)


func _face_base_position(particle) -> Vector2:
	var formation_strength = FaceContourBehaviour.formation_strength(
		particle.formation_strength,
		state_intensity
	)

	return particle.base_position.linear_interpolate(
		particle.face_position,
		formation_strength
	)


func _state_motion_for_particle(base: Vector2, depth: float) -> Vector2:
	if visual_state == VisualStates.LISTENING_CLOUD:
		return ListeningBehaviour.state_motion(
			time,
			base,
			depth,
			state_intensity
		)

	if visual_state == VisualStates.THINKING_SWARM:
		return ThinkingBehaviour.state_motion(
			time,
			base,
			depth,
			state_intensity
		)

	if visual_state == VisualStates.SPEAKING_PULSE:
		return SpeakingBehaviour.state_motion(
			time,
			base,
			depth,
			state_intensity
		)

	if visual_state == VisualStates.SCANNING_EYES:
		return ScanningBehaviour.state_motion(
			time,
			base,
			depth,
			state_intensity
		)

	if VisualStates.is_eye_formation_state(visual_state):
		return EyeBehaviour.state_motion(visual_state, time, base, depth)

	if VisualStates.is_face_formation_state(visual_state):
		return FaceContourBehaviour.state_motion(
			time,
			base,
			depth,
			state_intensity
		)

	if visual_state == VisualStates.ERROR_DEGRADED:
		var weak_drift = sin(time * 0.8 + base.length() * 0.018)
		return base.normalized() * weak_drift * 5.0 * state_intensity * depth

	return Vector2.ZERO


func _draw() -> void:
	for particle in particles:
		var position = particle.target_position
		var alpha = 0.30 + particle.depth * 0.42
		var size = particle_size * particle.depth

		if visual_state == VisualStates.SCANNING_EYES:
			alpha += ScanningBehaviour.alpha_bonus(time, position, state_intensity)
			size += ScanningBehaviour.size_bonus(time, position, state_intensity)

			if particle.is_pupil:
				size += ScanningBehaviour.pupil_size_bonus()
				alpha = 0.94

		elif VisualStates.is_eye_formation_state(visual_state):
			alpha += EyeBehaviour.alpha_bonus(visual_state, state_intensity)

			if particle.is_pupil:
				size += EyeBehaviour.pupil_size_bonus(visual_state)
				alpha = 0.92

		elif VisualStates.is_face_formation_state(visual_state):
			alpha += FaceContourBehaviour.alpha_bonus(state_intensity)
			size += FaceContourBehaviour.size_bonus(state_intensity)

		elif visual_state == VisualStates.LISTENING_CLOUD:
			alpha += ListeningBehaviour.alpha_bonus(time, position, state_intensity)
			size += ListeningBehaviour.size_bonus(time, position, state_intensity)

		elif visual_state == VisualStates.THINKING_SWARM:
			alpha += ThinkingBehaviour.alpha_bonus(time, position, state_intensity)
			size += ThinkingBehaviour.size_bonus(time, position, state_intensity)

		elif visual_state == VisualStates.SPEAKING_PULSE:
			alpha += SpeakingBehaviour.alpha_bonus(time, position, state_intensity)
			size += SpeakingBehaviour.size_bonus(time, position, state_intensity)

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

	if visual_state == VisualStates.SCANNING_EYES:
		_draw_scanning_overlay()


func _draw_scanning_overlay() -> void:
	var alpha = ScanningBehaviour.overlay_alpha(time, state_intensity)
	var y = ScanningBehaviour.overlay_y(time, radius)
	var width = ScanningBehaviour.overlay_width(radius)
	var color = ScanningBehaviour.overlay_color(alpha)

	draw_line(
		Vector2(-width, y),
		Vector2(width, y),
		color,
		1.0,
		true
	)

	draw_line(
		Vector2(-width * 0.62, y + 18.0),
		Vector2(width * 0.62, y + 18.0),
		ScanningBehaviour.overlay_color(alpha * 0.38),
		1.0,
		true
	)