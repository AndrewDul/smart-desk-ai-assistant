extends Reference

const DOCKED_WINDOW_SIZE = Vector2(300, 300)
const DOCK_MARGIN = 20


static func enter_fullscreen() -> void:
	OS.window_fullscreen = true
	OS.window_borderless = true


static func enter_docked_window() -> void:
	OS.window_fullscreen = false
	OS.window_borderless = true
	OS.window_size = DOCKED_WINDOW_SIZE
	OS.window_position = _top_right_position(DOCKED_WINDOW_SIZE)


static func _top_right_position(window_size: Vector2) -> Vector2:
	var screen_size = OS.get_screen_size()

	return Vector2(
		max(0.0, screen_size.x - window_size.x - DOCK_MARGIN),
		DOCK_MARGIN
	)
