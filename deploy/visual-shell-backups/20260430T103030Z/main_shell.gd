extends Control

const VisualStates = preload("res://scripts/state/visual_states.gd")
const VisualStateMachineScript = preload("res://scripts/visual_state_machine.gd")
const DesktopWindowController = preload("res://scripts/desktop/desktop_window_controller.gd")
const ShellLayout = preload("res://scripts/desktop/shell_layout.gd")
const VisualShellTcpServerScript = preload("res://scripts/transport/visual_shell_tcp_server.gd")

const BOOT_STATE = VisualStates.IDLE_PARTICLE_CLOUD
const BOOT_LAYOUT = ShellLayout.FULLSCREEN
const TEMPERATURE_DEMO_VALUE_C = 58
const BATTERY_DEMO_PERCENT = 82
const TARGET_RENDER_FPS = 24
const SHOW_DEBUG_STATUS_LABEL = false

onready var background: ColorRect = $Background
onready var status_label: Label = $StatusLabel
onready var particle_cloud: Node2D = $ParticleCloud

var state_machine = null
var visual_transport_server = null
var shell_layout = BOOT_LAYOUT
var last_viewport_size = Vector2.ZERO

func _ready() -> void:
	_apply_performance_policy()
	_setup_scene_visibility()
	_setup_state_machine()
	_setup_visual_transport()
	_apply_shell_layout(BOOT_LAYOUT)
	state_machine.set_state(BOOT_STATE, true)
	_sync_scene_layout()


func _apply_performance_policy() -> void:
	Engine.target_fps = TARGET_RENDER_FPS
	OS.low_processor_usage_mode = false
	OS.vsync_enabled = true


func _process(_delta: float) -> void:
	_sync_scene_layout_if_needed()



func _setup_scene_visibility() -> void:
	if background != null:
		background.visible = true
		if background is ColorRect:
			background.color = Color(0.002, 0.003, 0.007, 1.0)
		background.show()

	if particle_cloud != null:
		particle_cloud.visible = true
		particle_cloud.show()
		particle_cloud.modulate = Color(1, 1, 1, 1)
		particle_cloud.set_process(true)
		particle_cloud.update()

	if status_label != null:
		status_label.visible = false





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


func _setup_visual_transport() -> void:
	visual_transport_server = VisualShellTcpServerScript.new()
	visual_transport_server.name = "VisualShellTcpServer"
	visual_transport_server.connect(
		"visual_message_received",
		self,
		"_on_visual_transport_message"
	)
	visual_transport_server.connect(
		"visual_transport_error",
		self,
		"_on_visual_transport_error"
	)
	add_child(visual_transport_server)


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


func _on_visual_transport_message(message: Dictionary) -> void:
	var command = String(message.get("command", "")).strip_edges().to_upper()
	var message_type = String(message.get("type", "")).strip_edges().to_lower()
	var payload = _payload_from_message(message)

	if command == "" and message_type == "visual_state":
		_apply_visual_state_message(message, payload)
		return

	if command == "" and message_type == "visual_command":
		command = String(message.get("command", "")).strip_edges().to_upper()

	_apply_visual_command(command, payload, message)


func _payload_from_message(message: Dictionary) -> Dictionary:
	var raw_payload = message.get("payload", {})

	if typeof(raw_payload) == TYPE_DICTIONARY:
		return raw_payload

	return {}


func _apply_visual_state_message(message: Dictionary, payload: Dictionary) -> void:
	var state_name = String(message.get("state", ""))
	if state_name == "":
		state_name = String(payload.get("state", ""))

	_set_visual_state(state_name)


func _apply_visual_command(command: String, payload: Dictionary, raw_message: Dictionary) -> void:
	if command == "SET_STATE":
		var state_name = String(payload.get("state", ""))
		if state_name == "":
			state_name = String(raw_message.get("state", ""))

		_set_visual_state(state_name)
		return

	if command == "SHOW_DESKTOP":
		_apply_desktop_state(VisualStates.DESKTOP_DOCKED)
		return

	if command == "HIDE_DESKTOP":
		_apply_desktop_state(VisualStates.DESKTOP_HIDDEN)
		return

	if command == "SHOW_SELF" or command == "SHOW_EYES":
		_set_visual_state(VisualStates.SHOW_SELF_EYES)
		return

	if command == "SHOW_FACE_CONTOUR":
		_set_visual_state(VisualStates.FACE_CONTOUR)
		return

	if command == "START_SCANNING":
		_set_visual_state(VisualStates.SCANNING_EYES)
		return

	if command == "RETURN_TO_IDLE":
		_set_visual_state(VisualStates.IDLE_PARTICLE_CLOUD)
		return

	if command == "REPORT_DEGRADED":
		_set_visual_state(VisualStates.ERROR_DEGRADED)
		return

	if command == "SHOW_TEMPERATURE":
		display_temperature_value(int(payload.get("value_c", TEMPERATURE_DEMO_VALUE_C)))
		return

	if command == "SHOW_BATTERY":
		display_battery_percent(int(payload.get("percent", BATTERY_DEMO_PERCENT)))
		return

	print("Visual Shell ignored unsupported transport command: ", command)


func _on_visual_transport_error(error_message: String) -> void:
	print("Visual Shell transport warning: ", error_message)


func _sync_scene_layout_if_needed() -> void:
	var viewport_size = get_viewport_rect().size

	if viewport_size == last_viewport_size:
		return

	_sync_scene_layout()


func _sync_scene_layout() -> void:
	var viewport_size = get_viewport_rect().size
	last_viewport_size = viewport_size
	particle_cloud.position = viewport_size * 0.5

	status_label.visible = SHOW_DEBUG_STATUS_LABEL and ShellLayout.is_fullscreen(shell_layout)
	background.visible = true


func _build_status_text(current_state: String) -> String:
	if not SHOW_DEBUG_STATUS_LABEL:
		return ""

	return "NEXA VISUAL SHELL\n" \
		+ current_state \
		+ "\nlayout: " \
		+ shell_layout
