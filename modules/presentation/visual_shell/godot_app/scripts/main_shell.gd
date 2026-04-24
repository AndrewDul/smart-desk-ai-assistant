extends Control

const BOOT_STATE := "IDLE_PARTICLE_CLOUD"

onready var status_label: Label = $StatusLabel
onready var particle_cloud: Node2D = $ParticleCloud


func _ready() -> void:
	OS.window_fullscreen = true
	_set_state(BOOT_STATE)


func _input(event: InputEvent) -> void:
	if not event is InputEventKey:
		return

	if not event.pressed:
		return

	if event.scancode == KEY_1:
		_set_state("IDLE_PARTICLE_CLOUD")
	elif event.scancode == KEY_2:
		_set_state("LISTENING_CLOUD")
	elif event.scancode == KEY_3:
		_set_state("THINKING_SWARM")
	elif event.scancode == KEY_4:
		_set_state("SPEAKING_PULSE")
	elif event.scancode == KEY_5:
		_set_state("SCANNING_EYES")
	elif event.scancode == KEY_ESCAPE:
		get_tree().quit()


func _set_state(new_state: String) -> void:
	status_label.text = "NEXA VISUAL SHELL\n" + new_state + "\n1 idle  2 listen  3 think  4 speak  5 scan"
	particle_cloud.set_visual_state(new_state)