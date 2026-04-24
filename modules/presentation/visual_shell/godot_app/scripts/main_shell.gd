extends Control

const VisualStates = preload("res://scripts/state/visual_states.gd")
const VisualStateMachineScript = preload("res://scripts/visual_state_machine.gd")
const DesktopWindowController = preload("res://scripts/desktop/desktop_window_controller.gd")

const BOOT_STATE = VisualStates.IDLE_PARTICLE_CLOUD

onready var background: ColorRect = $Background
onready var status_label: Label = $StatusLabel
onready var particle_cloud: Node2D = $ParticleCloud

var state_machine = null
var shell_docked = false


func _ready() -> void:
	DesktopWindowController.enter_fullscreen()
	_setup_state_machine()
	state_machine.set_state(BOOT_STATE, true)
	_sync_scene_layout()


func _process(_delta: float) -> void:
	_sync_scene_layout()


func _input(event: InputEvent) -> void:
	if not event is InputEventKey:
		return

	if not event.pressed:
		return

	if event.scancode == KEY_1:
		_set_visual_state(VisualStates.IDLE_PARTICLE_CLOUD)
	elif event.scancode == KEY_2:
		_set_visual_state(VisualStates.LISTENING_CLOUD)
	elif event.scancode == KEY_3:
		_set_visual_state(VisualStates.THINKING_SWARM)
	elif event.scancode == KEY_4:
		_set_visual_state(VisualStates.SPEAKING_PULSE)
	elif event.scancode == KEY_5:
		_set_visual_state(VisualStates.SCANNING_EYES)
	elif event.scancode == KEY_6:
		_set_visual_state(VisualStates.SHOW_SELF_EYES)
	elif event.scancode == KEY_7:
		_set_visual_state(VisualStates.ERROR_DEGRADED)
	elif event.scancode == KEY_8:
		_set_visual_state(VisualStates.FACE_CONTOUR)
	elif event.scancode == KEY_9:
		_set_visual_state(VisualStates.BORED_MICRO_ANIMATION)
	elif event.scancode == KEY_0:
		_enter_desktop_docked_mode()
	elif event.scancode == KEY_MINUS:
		_return_to_fullscreen_shell()
	elif event.scancode == KEY_ESCAPE:
		get_tree().quit()


func _setup_state_machine() -> void:
	state_machine = VisualStateMachineScript.new()
	state_machine.name = "VisualStateMachine"
	add_child(state_machine)
	state_machine.connect("visual_state_changed", self, "_on_visual_state_changed")
	state_machine.connect("visual_state_rejected", self, "_on_visual_state_rejected")


func _set_visual_state(new_state: String) -> void:
	if new_state == VisualStates.DESKTOP_DOCKED:
		_enter_desktop_docked_mode()
		return

	if new_state == VisualStates.DESKTOP_RETURNING \
			or new_state == VisualStates.DESKTOP_HIDDEN:
		_return_to_fullscreen_shell()
		return

	state_machine.set_state(new_state)


func _enter_desktop_docked_mode() -> void:
	shell_docked = true
	DesktopWindowController.enter_docked_window()
	particle_cloud.set_shell_compact_mode(true)
	_sync_scene_layout()


func _return_to_fullscreen_shell() -> void:
	shell_docked = false
	DesktopWindowController.enter_fullscreen()
	particle_cloud.set_shell_compact_mode(false)
	_sync_scene_layout()


func _on_visual_state_changed(new_state: String) -> void:
	if new_state == VisualStates.DESKTOP_DOCKED:
		_enter_desktop_docked_mode()
		return

	if new_state == VisualStates.DESKTOP_RETURNING \
			or new_state == VisualStates.DESKTOP_HIDDEN:
		_return_to_fullscreen_shell()
		return

	status_label.text = _build_status_text(new_state)
	particle_cloud.set_visual_state(new_state)


func _on_visual_state_rejected(requested_state: String, fallback_state: String) -> void:
	print("Visual Shell rejected unsupported state: ", requested_state, " -> ", fallback_state)


func _sync_scene_layout() -> void:
	var viewport_size = get_viewport_rect().size
	particle_cloud.position = viewport_size * 0.5

	status_label.visible = not shell_docked
	background.visible = true


func _build_status_text(current_state: String) -> String:
	var layout_label = "FULLSCREEN"

	if shell_docked:
		layout_label = "DOCKED WINDOW"

	return "NEXA VISUAL SHELL\n" \
		+ current_state \
		+ "\nlayout: " \
		+ layout_label \
		+ "\n1 idle  2 listen  3 think  4 speak  5 scan  6 eyes  7 error  8 face  9 micro  0 dock  - return"