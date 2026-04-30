extends Node2D

const VisualStates = preload("res://scripts/state/visual_states.gd")
const EyeFormation = preload("res://scripts/formations/eye_formation.gd")
const FaceContourFormation = preload("res://scripts/formations/face_contour_formation.gd")
const GlyphFormation = preload("res://scripts/formations/glyph_formation.gd")
const ListeningBehaviour = preload("res://scripts/behaviours/listening_behaviour.gd")
const ThinkingBehaviour = preload("res://scripts/behaviours/thinking_behaviour.gd")
const SpeakingBehaviour = preload("res://scripts/behaviours/speaking_behaviour.gd")
const ScanningBehaviour = preload("res://scripts/behaviours/scanning_behaviour.gd")
const EyeBehaviour = preload("res://scripts/behaviours/eye_behaviour.gd")
const FaceContourBehaviour = preload("res://scripts/behaviours/face_contour_behaviour.gd")
const BoredMicroBehaviour = preload("res://scripts/behaviours/bored_micro_behaviour.gd")
const DesktopDockBehaviour = preload("res://scripts/behaviours/desktop_dock_behaviour.gd")
const MetricDisplayBehaviour = preload("res://scripts/behaviours/metric_display_behaviour.gd")
const VisualPalette = preload("res://scripts/palette/visual_palette.gd")
const NebulaBehaviour = preload("res://scripts/behaviours/nebula_behaviour.gd")

export(int) var particle_count = 620
export(float) var radius = 355.0
export(float) var particle_size = 0.88
export(int) var target_update_fps = 24

var particles = []
var time = 0.0
var frame_accumulator = 0.0
var visual_state = VisualStates.IDLE_PARTICLE_CLOUD
var state_intensity = 0.0
var blink_timer = 0.0
var blink_interval = 25.0
var blink_duration = 0.28

var shell_compact_mode = false
var visual_scale = 1.0

var metric_temperature_c = 58
var metric_battery_percent = 82
var metric_text = "58°"

var idle_micro_timer = 0.0
var idle_micro_delay = 32.0
var idle_micro_age = 0.0
var idle_micro_duration = 0.0
var idle_micro_kind = BoredMicroBehaviour.KIND_SOFT_WAVE
var idle_micro_active = false


class Particle:
	var base_position = Vector2.ZERO
	var target_position = Vector2.ZERO
	var eye_position = Vector2.ZERO
	var face_position = Vector2.ZERO
	var glyph_position = Vector2.ZERO
	var depth = 1.0
	var formation_strength = 1.0
	var is_pupil = false
	var is_metric_particle = false


func _ready() -> void:
	randomize()
	_generate_particles()
	EyeFormation.assign_eye_targets(particles, particle_count)
	FaceContourFormation.assign_face_targets(particles, particle_count)
	_assign_metric_targets(metric_text)
	_schedule_next_idle_micro()


func _process(delta: float) -> void:
	frame_accumulator += delta

	var frame_step = 1.0 / max(float(target_update_fps), 1.0)
	if frame_accumulator < frame_step:
		return

	var frame_delta = min(frame_accumulator, frame_step * 2.5)
	frame_accumulator = 0.0

	time += frame_delta
	blink_timer += frame_delta

	if blink_timer > blink_interval:
		blink_timer = 0.0

	_update_idle_micro(frame_delta)
	_update_state_intensity(frame_delta)
	_update_shell_transform(frame_delta)
	_update_particles()
	update()


func set_visual_state(new_state: String) -> void:
	var previous_state = visual_state
	visual_state = VisualStates.coerce_state(new_state)

	if visual_state == VisualStates.DESKTOP_DOCKED \
			or visual_state == VisualStates.DESKTOP_RETURNING \
			or visual_state == VisualStates.DESKTOP_HIDDEN:
		visual_state = previous_state
		return

	if visual_state == VisualStates.SHOW_SELF_EYES and previous_state != visual_state:
		blink_timer = 0.0

	if visual_state == VisualStates.BORED_MICRO_ANIMATION and previous_state != visual_state:
		_start_idle_micro(
			BoredMicroBehaviour.KIND_ORBIT_GLINT,
			4.0
		)


func set_shell_compact_mode(enabled: bool) -> void:
	shell_compact_mode = enabled


func set_temperature_metric(value_c: int) -> void:
	metric_temperature_c = value_c
	metric_text = str(metric_temperature_c) + "°"
	_assign_metric_targets(metric_text)


func set_battery_metric(percent: int) -> void:
	metric_battery_percent = int(clamp(percent, 0, 100))
	metric_text = str(metric_battery_percent) + "%"
	_assign_metric_targets(metric_text)


func _assign_metric_targets(display_text: String) -> void:
	GlyphFormation.assign_text_targets(particles, display_text)


func _generate_particles() -> void:
	particles.clear()

	for _i in range(particle_count):
		var profile = NebulaBehaviour.profile_for_particle(_i, particle_count, radius)

		var particle = Particle.new()
		particle.base_position = profile.get("position", Vector2.ZERO)
		particle.target_position = particle.base_position
		particle.glyph_position = particle.base_position
		particle.depth = profile.get("depth", 1.0)
		particle.formation_strength = profile.get("formation_strength", 1.0)

		particles.append(particle)

func _schedule_next_idle_micro() -> void:
	idle_micro_timer = 0.0
	idle_micro_delay = BoredMicroBehaviour.next_delay()
	idle_micro_age = 0.0
	idle_micro_duration = 0.0
	idle_micro_active = false


func _start_idle_micro(kind: String, duration: float) -> void:
	idle_micro_kind = kind
	idle_micro_duration = duration
	idle_micro_age = 0.0
	idle_micro_timer = 0.0
	idle_micro_active = true


func _update_idle_micro(delta: float) -> void:
	if visual_state != VisualStates.IDLE_PARTICLE_CLOUD \
			and visual_state != VisualStates.BORED_MICRO_ANIMATION:
		idle_micro_active = false
		idle_micro_age = 0.0
		idle_micro_timer = 0.0
		return

	if visual_state == VisualStates.BORED_MICRO_ANIMATION:
		if idle_micro_active:
			idle_micro_age += delta
		return

	if idle_micro_active:
		idle_micro_age += delta

		if idle_micro_age >= idle_micro_duration:
			_schedule_next_idle_micro()

		return

	idle_micro_timer += delta

	if idle_micro_timer >= idle_micro_delay:
		_start_idle_micro(
			BoredMicroBehaviour.pick_kind(),
			BoredMicroBehaviour.next_duration()
		)


func _current_idle_micro_intensity() -> float:
	if not idle_micro_active:
		return 0.0

	return BoredMicroBehaviour.envelope(
		idle_micro_age,
		idle_micro_duration
	)


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
	elif visual_state == VisualStates.BORED_MICRO_ANIMATION:
		target = 0.72
	elif visual_state == VisualStates.TEMPERATURE_GLYPH:
		target = 0.90
	elif visual_state == VisualStates.BATTERY_GLYPH:
		target = 0.92
	elif visual_state == VisualStates.ERROR_DEGRADED:
		target = 0.65

	state_intensity = lerp(state_intensity, target, delta * 2.8)


func _update_shell_transform(delta: float) -> void:
	var viewport_size = get_viewport_rect().size
	var target_scale = DesktopDockBehaviour.target_scale(
		shell_compact_mode,
		viewport_size,
		radius
	)
	var speed = DesktopDockBehaviour.transform_speed(not shell_compact_mode)

	visual_scale = lerp(visual_scale, target_scale, delta * speed)


func _update_particles() -> void:
	for particle in particles:
		var base = particle.base_position

		if VisualStates.is_eye_formation_state(visual_state):
			base = _eye_base_position(particle)

		elif VisualStates.is_face_formation_state(visual_state):
			base = _face_base_position(particle)

		elif VisualStates.is_metric_display_state(visual_state):
			base = _metric_base_position(particle)

		var nebula_motion = NebulaBehaviour.organic_drift(
			time,
			base,
			particle.depth,
			state_intensity
		)

		var state_motion = _state_motion_for_particle(
			base,
			particle.depth,
			particle.is_metric_particle
		)

		var desired_position = base \
			+ nebula_motion \
			+ state_motion

		particle.target_position = particle.target_position.linear_interpolate(
			desired_position,
			0.052
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


func _metric_base_position(particle) -> Vector2:
	var formation_strength = MetricDisplayBehaviour.formation_strength(
		particle.formation_strength,
		state_intensity,
		particle.is_metric_particle
	)

	return particle.base_position.linear_interpolate(
		particle.glyph_position,
		formation_strength
	)


func _state_motion_for_particle(base: Vector2, depth: float, is_metric_particle: bool) -> Vector2:
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

	if VisualStates.is_metric_display_state(visual_state):
		return MetricDisplayBehaviour.state_motion(
			time,
			base,
			depth,
			state_intensity,
			is_metric_particle
		)

	if visual_state == VisualStates.IDLE_PARTICLE_CLOUD and idle_micro_active:
		return BoredMicroBehaviour.state_motion(
			time,
			base,
			depth,
			_current_idle_micro_intensity(),
			idle_micro_kind
		)

	if visual_state == VisualStates.BORED_MICRO_ANIMATION:
		return BoredMicroBehaviour.state_motion(
			time,
			base,
			depth,
			state_intensity,
			idle_micro_kind
		)

	if shell_compact_mode:
		return DesktopDockBehaviour.state_motion(
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
	_draw_nebula_background()
	_draw_compact_orb_background()

	for particle in particles:
		var position = particle.target_position
		var alpha = NebulaBehaviour.base_alpha(particle.depth, position, radius)
		var size = NebulaBehaviour.base_size(particle_size, particle.depth, position, radius)
		var particle_color = Color(1, 1, 1, 1)

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

		elif VisualStates.is_metric_display_state(visual_state):
			alpha += MetricDisplayBehaviour.alpha_bonus(
				time,
				position,
				state_intensity,
				particle.is_metric_particle
			)
			size += MetricDisplayBehaviour.size_bonus(
				state_intensity,
				particle.is_metric_particle
			)

		elif visual_state == VisualStates.LISTENING_CLOUD:
			alpha += ListeningBehaviour.alpha_bonus(time, position, state_intensity)
			size += ListeningBehaviour.size_bonus(time, position, state_intensity)

		elif visual_state == VisualStates.THINKING_SWARM:
			alpha += ThinkingBehaviour.alpha_bonus(time, position, state_intensity)
			size += ThinkingBehaviour.size_bonus(time, position, state_intensity)

		elif visual_state == VisualStates.SPEAKING_PULSE:
			alpha += SpeakingBehaviour.alpha_bonus(time, position, state_intensity)
			size += SpeakingBehaviour.size_bonus(time, position, state_intensity)

		elif visual_state == VisualStates.IDLE_PARTICLE_CLOUD and idle_micro_active:
			var micro_intensity = _current_idle_micro_intensity()
			alpha += BoredMicroBehaviour.alpha_bonus(
				time,
				position,
				micro_intensity,
				idle_micro_kind
			)
			size += BoredMicroBehaviour.size_bonus(
				micro_intensity,
				idle_micro_kind
			)

		elif visual_state == VisualStates.BORED_MICRO_ANIMATION:
			alpha += BoredMicroBehaviour.alpha_bonus(
				time,
				position,
				state_intensity,
				idle_micro_kind
			)
			size += BoredMicroBehaviour.size_bonus(
				state_intensity,
				idle_micro_kind
			)

		elif visual_state == VisualStates.ERROR_DEGRADED:
			alpha *= 0.78

		if shell_compact_mode:
			alpha += DesktopDockBehaviour.alpha_bonus(
				time,
				position,
				state_intensity
			)
			size += DesktopDockBehaviour.size_bonus(state_intensity)

		alpha = clamp(alpha, 0.0, 1.0)

		if VisualStates.is_metric_display_state(visual_state):
			particle_color = MetricDisplayBehaviour.color_for_particle(
				visual_state,
				particle.is_metric_particle,
				metric_battery_percent,
				alpha
			)
		else:
			particle_color = VisualPalette.color_for_particle(
				particle,
				visual_state,
				position,
				radius,
				alpha
			)

		draw_circle(
			_to_visual_position(position),
			_to_visual_size(size),
			particle_color
		)

	if visual_state == VisualStates.SCANNING_EYES:
		_draw_scanning_overlay()

func _to_visual_position(position: Vector2) -> Vector2:
	return position * visual_scale


func _to_visual_size(size: float) -> float:
	var multiplier = DesktopDockBehaviour.particle_size_multiplier(shell_compact_mode)

	return max(size * visual_scale * multiplier, 0.34)


func _draw_nebula_background() -> void:
	if shell_compact_mode:
		return

	if VisualStates.is_metric_display_state(visual_state):
		return

	draw_circle(
		Vector2(-radius * 0.28, -radius * 0.04) * visual_scale,
		radius * visual_scale * 0.48,
		NebulaBehaviour.background_core_color(0.20 + state_intensity * 0.05)
	)

	draw_circle(
		Vector2(radius * 0.32, radius * 0.06) * visual_scale,
		radius * visual_scale * 0.38,
		NebulaBehaviour.background_halo_color(0.13 + state_intensity * 0.04)
	)

	draw_circle(
		Vector2(radius * 0.04, -radius * 0.16) * visual_scale,
		radius * visual_scale * 0.30,
		NebulaBehaviour.background_accent_color(0.09 + state_intensity * 0.03)
	)


func _draw_compact_orb_background() -> void:
	if not shell_compact_mode:
		return

	if VisualStates.is_metric_display_state(visual_state):
		return

	if not DesktopDockBehaviour.should_draw_soft_orb(visual_scale):
		return

	var alpha = DesktopDockBehaviour.orb_alpha(visual_scale)
	var compact_radius = DesktopDockBehaviour.orb_radius(radius, visual_scale)

	draw_circle(
		Vector2.ZERO,
		compact_radius,
		DesktopDockBehaviour.orb_color(alpha)
	)


func _draw_scanning_overlay() -> void:
	var alpha = ScanningBehaviour.overlay_alpha(time, state_intensity)
	var y = ScanningBehaviour.overlay_y(time, radius)
	var width = ScanningBehaviour.overlay_width(radius)
	var color = ScanningBehaviour.overlay_color(alpha)

	draw_line(
		_to_visual_position(Vector2(-width, y)),
		_to_visual_position(Vector2(width, y)),
		color,
		1.0,
		true
	)

	draw_line(
		_to_visual_position(Vector2(-width * 0.62, y + 18.0)),
		_to_visual_position(Vector2(width * 0.62, y + 18.0)),
		ScanningBehaviour.overlay_color(alpha * 0.38),
		1.0,
		true
	)
