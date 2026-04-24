extends Control

const VisualStates = preload("res://scripts/state/visual_states.gd")
const VisualStateMachineScript = preload("res://scripts/visual_state_machine.gd")
const DesktopWindowController = preload("res://scripts/desktop/desktop_window_controller.gd")
const ShellLayout = preload("res://scripts/desktop/shell_layout.gd")

const BOOT_STATE = VisualStates.IDLE_PARTICLE_CLOUD
const BOOT_LAYOUT = ShellLayout.FULLSCREEN
const TEMPERATURE_DEMO_VALUE_C = 58
const BATTERY_DEMO_PERCENT = 82

onready var background: ColorRect = $Background
onready var status_label: Label = $StatusLabel
onready var particle_cloud: Node2D = $ParticleCloud

var state_machine = null
var shell_layout = BOOT_LAYOUT


func _ready() -> void:
	_setup_state_machine()
	_apply_shell_layout(BOOT_LAYOUT)
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
		_apply_desktop_state(VisualStates.DESKTOP_DOCKED)
	elif event.scancode == KEY_MINUS:
		_apply_desktop_state(VisualStates.DESKTOP_HIDDEN)
	elif event.scancode == KEY_T:
		display_temperature_value(TEMPERATURE_DEMO_VALUE_C)
	elif event.scancode == KEY_B:
		display_battery_percent(BATTERY_DEMO_PERCENT)
	elif event.scancode == KEY_ESCAPE:
		get_tree().quit()


func _setup_state_machine() -> void:
	state_machine = VisualStateMachineScript.new()
	state_machine.name = "VisualStateMachine"
	add_child(state_machine)
	state_machine.connect("visual_state_changed", self, "_on_visual_state_changed")
	state_machine.connect("visual_state_rejected", self, "_on_visual_state_rejected")


func _set_visual_state(new_state: String) -> void:
	if _is_desktop_layout_state(new_state):
		_apply_desktop_state(new_state)
		return

	state_machine.set_state(new_state)


func display_temperature_value(value_c: int) -> void:
	particle_cloud.set_temperature_metric(value_c)
	state_machine.set_state(VisualStates.TEMPERATURE_GLYPH)


func display_battery_percent(percent: int) -> void:
	particle_cloud.set_battery_metric(percent)
	state_machine.set_state(VisualStates.BATTERY_GLYPH)


func _apply_desktop_state(desktop_state: String) -> void:
	if desktop_state == VisualStates.DESKTOP_DOCKED:
		_apply_shell_layout(ShellLayout.DOCKED)
		return

	if desktop_state == VisualStates.DESKTOP_RETURNING \
			or desktop_state == VisualStates.DESKTOP_HIDDEN:
		_apply_shell_layout(ShellLayout.FULLSCREEN)
		return


func _apply_shell_layout(next_layout: String) -> void:
	shell_layout = ShellLayout.coerce(next_layout)

	if ShellLayout.is_docked(shell_layout):
		DesktopWindowController.enter_docked_window()
		particle_cloud.set_shell_compact_mode(true)
	else:
		DesktopWindowController.enter_fullscreen()
		particle_cloud.set_shell_compact_mode(false)

	_sync_scene_layout()


func _is_desktop_layout_state(state_name: String) -> bool:
	return state_name == VisualStates.DESKTOP_DOCKED \
		or state_name == VisualStates.DESKTOP_RETURNING \
		or state_name == VisualStates.DESKTOP_HIDDEN


func _on_visual_state_changed(new_state: String) -> void:
	if _is_desktop_layout_state(new_state):
		_apply_desktop_state(new_state)
		return

	status_label.text = _build_status_text(new_state)
	particle_cloud.set_visual_state(new_state)


func _on_visual_state_rejected(requested_state: String, fallback_state: String) -> void:
	print("Visual Shell rejected unsupported state: ", requested_state, " -> ", fallback_state)


func _sync_scene_layout() -> void:
	var viewport_size = get_viewport_rect().size
	particle_cloud.position = viewport_size * 0.5

	status_label.visible = ShellLayout.is_fullscreen(shell_layout)
	background.visible = true


func _build_status_text(current_state: String) -> String:
	return "NEXA VISUAL SHELL\n" \
		+ current_state \
		+ "\nlayout: " \
		+ shell_layout \
		+ "\n1 idle  2 listen  3 think  4 speak  5 scan  6 eyes  7 error  8 face  9 micro  0 dock  - return  T temp  B battery"