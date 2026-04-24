extends Control

const VisualStates = preload("res://scripts/state/visual_states.gd")
const VisualStateMachineScript = preload("res://scripts/visual_state_machine.gd")

const BOOT_STATE = VisualStates.IDLE_PARTICLE_CLOUD

onready var status_label: Label = $StatusLabel
onready var particle_cloud: Node2D = $ParticleCloud

var state_machine = null


func _ready() -> void:
	OS.window_fullscreen = true
	_setup_state_machine()
	state_machine.set_state(BOOT_STATE, true)


func _input(event: InputEvent) -> void:
	if not event is InputEventKey:
		return

	if not event.pressed:
		return

	if event.scancode == KEY_1:
		state_machine.set_state(VisualStates.IDLE_PARTICLE_CLOUD)
	elif event.scancode == KEY_2:
		state_machine.set_state(VisualStates.LISTENING_CLOUD)
	elif event.scancode == KEY_3:
		state_machine.set_state(VisualStates.THINKING_SWARM)
	elif event.scancode == KEY_4:
		state_machine.set_state(VisualStates.SPEAKING_PULSE)
	elif event.scancode == KEY_5:
		state_machine.set_state(VisualStates.SCANNING_EYES)
	elif event.scancode == KEY_6:
		state_machine.set_state(VisualStates.SHOW_SELF_EYES)
	elif event.scancode == KEY_7:
		state_machine.set_state(VisualStates.ERROR_DEGRADED)
	elif event.scancode == KEY_8:
		state_machine.set_state(VisualStates.FACE_CONTOUR)
	elif event.scancode == KEY_ESCAPE:
		get_tree().quit()


func _setup_state_machine() -> void:
	state_machine = VisualStateMachineScript.new()
	state_machine.name = "VisualStateMachine"
	add_child(state_machine)
	state_machine.connect("visual_state_changed", self, "_on_visual_state_changed")
	state_machine.connect("visual_state_rejected", self, "_on_visual_state_rejected")


func _on_visual_state_changed(new_state: String) -> void:
	status_label.text = _build_status_text(new_state)
	particle_cloud.set_visual_state(new_state)


func _on_visual_state_rejected(requested_state: String, fallback_state: String) -> void:
	print("Visual Shell rejected unsupported state: ", requested_state, " -> ", fallback_state)


func _build_status_text(current_state: String) -> String:
	return "NEXA VISUAL SHELL\n" \
		+ current_state \
		+ "\n1 idle  2 listen  3 think  4 speak  5 scan  6 eyes  7 error  8 face"