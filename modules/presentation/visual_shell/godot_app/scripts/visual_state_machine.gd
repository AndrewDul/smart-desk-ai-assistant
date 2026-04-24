extends Node

signal visual_state_changed(new_state)
signal visual_state_rejected(requested_state, fallback_state)

const VisualStates := preload("res://scripts/state/visual_states.gd")

var current_state := VisualStates.IDLE_PARTICLE_CLOUD
var previous_state := VisualStates.IDLE_PARTICLE_CLOUD


func set_state(new_state: String, force_emit := false) -> void:
	var normalized_state := VisualStates.coerce_state(new_state)

	if normalized_state != new_state:
		emit_signal(
			"visual_state_rejected",
			new_state,
			normalized_state
		)

	if normalized_state == current_state and not force_emit:
		return

	previous_state = current_state
	current_state = normalized_state
	emit_signal("visual_state_changed", current_state)


func return_to_idle() -> void:
	set_state(VisualStates.IDLE_PARTICLE_CLOUD)


func is_current_state(state_name: String) -> bool:
	return current_state == VisualStates.coerce_state(state_name)