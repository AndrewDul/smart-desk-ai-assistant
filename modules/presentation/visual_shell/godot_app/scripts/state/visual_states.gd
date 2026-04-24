extends Reference

const IDLE_PARTICLE_CLOUD = "IDLE_PARTICLE_CLOUD"
const LISTENING_CLOUD = "LISTENING_CLOUD"
const THINKING_SWARM = "THINKING_SWARM"
const SPEAKING_PULSE = "SPEAKING_PULSE"
const SCANNING_EYES = "SCANNING_EYES"
const SHOW_SELF_EYES = "SHOW_SELF_EYES"
const FACE_CONTOUR = "FACE_CONTOUR"
const BORED_MICRO_ANIMATION = "BORED_MICRO_ANIMATION"
const TEMPERATURE_GLYPH = "TEMPERATURE_GLYPH"
const BATTERY_GLYPH = "BATTERY_GLYPH"
const DESKTOP_HIDDEN = "DESKTOP_HIDDEN"
const DESKTOP_DOCKED = "DESKTOP_DOCKED"
const DESKTOP_RETURNING = "DESKTOP_RETURNING"
const ERROR_DEGRADED = "ERROR_DEGRADED"

const SUPPORTED_STATES = [
	IDLE_PARTICLE_CLOUD,
	LISTENING_CLOUD,
	THINKING_SWARM,
	SPEAKING_PULSE,
	SCANNING_EYES,
	SHOW_SELF_EYES,
	FACE_CONTOUR,
	BORED_MICRO_ANIMATION,
	TEMPERATURE_GLYPH,
	BATTERY_GLYPH,
	DESKTOP_HIDDEN,
	DESKTOP_DOCKED,
	DESKTOP_RETURNING,
	ERROR_DEGRADED,
]


static func coerce_state(state_name: String) -> String:
	var normalized = String(state_name).strip_edges().to_upper()

	if SUPPORTED_STATES.has(normalized):
		return normalized

	return IDLE_PARTICLE_CLOUD


static func is_eye_formation_state(state_name: String) -> bool:
	var normalized = coerce_state(state_name)

	return normalized == SCANNING_EYES or normalized == SHOW_SELF_EYES


static func is_face_formation_state(state_name: String) -> bool:
	return coerce_state(state_name) == FACE_CONTOUR


static func is_metric_display_state(state_name: String) -> bool:
	var normalized = coerce_state(state_name)

	return normalized == TEMPERATURE_GLYPH or normalized == BATTERY_GLYPH