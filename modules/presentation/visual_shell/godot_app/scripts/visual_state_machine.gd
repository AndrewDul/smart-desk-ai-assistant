extends Node

signal visual_state_changed(new_state)

const IDLE_PARTICLE_CLOUD := "IDLE_PARTICLE_CLOUD"
const LISTENING_CLOUD := "LISTENING_CLOUD"
const THINKING_SWARM := "THINKING_SWARM"
const SPEAKING_PULSE := "SPEAKING_PULSE"
const SCANNING_EYES := "SCANNING_EYES"

var current_state := IDLE_PARTICLE_CLOUD


func set_state(new_state: String) -> void:
	if new_state == current_state:
		return

	current_state = new_state
	emit_signal("visual_state_changed", current_state)


func return_to_idle() -> void:
	set_state(IDLE_PARTICLE_CLOUD)