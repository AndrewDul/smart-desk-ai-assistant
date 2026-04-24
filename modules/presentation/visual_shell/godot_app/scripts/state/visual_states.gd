extends Reference

const IDLE_PARTICLE_CLOUD = "IDLE_PARTICLE_CLOUD"
const LISTENING_CLOUD = "LISTENING_CLOUD"
const THINKING_SWARM = "THINKING_SWARM"
const SPEAKING_PULSE = "SPEAKING_PULSE"
const SCANNING_EYES = "SCANNING_EYES"
const SHOW_SELF_EYES = "SHOW_SELF_EYES"
const FACE_CONTOUR = "FACE_CONTOUR"
const BORED_MICRO_ANIMATION = "BORED_MICRO_ANIMATION"
const DESKTOP_HIDDEN = "DESKTOP_HIDDEN"
const DESKTOP_DOCKED = "DESKTOP_DOCKED"
const DESKTOP_RETURNING = "DESKTOP_RETURNING"
const ERROR_DEGRADED = "ERROR_DEGRADED"

const ALL_STATES = [
	IDLE_PARTICLE_CLOUD,
	LISTENING_CLOUD,
	THINKING_SWARM,
	SPEAKING_PULSE,
	SCANNING_EYES,
	SHOW_SELF_EYES,
	FACE_CONTOUR,
	BORED_MICRO_ANIMATION,
	DESKTOP_HIDDEN,
	DESKTOP_DOCKED,
	DESKTOP_RETURNING,
	ERROR_DEGRADED,
]


static func is_valid_state(value: String) -> bool:
	return ALL_STATES.has(value)


static func coerce_state(value: String) -> String:
	var normalized = String(value).strip_edges().to_upper()

	if is_valid_state(normalized):
		return normalized

	return IDLE_PARTICLE_CLOUD


static func is_eye_formation_state(value: String) -> bool:
	return value == SCANNING_EYES or value == SHOW_SELF_EYES


static func is_face_formation_state(value: String) -> bool:
	return value == FACE_CONTOUR


static func is_reserved_future_state(value: String) -> bool:
	return value == BORED_MICRO_ANIMATION \
		or value == DESKTOP_HIDDEN \
		or value == DESKTOP_DOCKED \
		or value == DESKTOP_RETURNING