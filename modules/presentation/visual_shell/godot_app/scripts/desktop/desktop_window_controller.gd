extends Node

const DEFAULT_FULL_WINDOW_SIZE = Vector2(1280, 800)
const DOCKED_WINDOW_WIDTH = 300
const DOCKED_WINDOW_HEIGHT = 300
const DOCKED_WINDOW_SIZE = Vector2(DOCKED_WINDOW_WIDTH, DOCKED_WINDOW_HEIGHT)
const DOCKED_WINDOW_MARGIN = Vector2(18, 18)


static func enter_fullscreen() -> void:
    var screen_size = OS.get_screen_size()
    var target_size = Vector2(
        min(float(DEFAULT_FULL_WINDOW_SIZE.x), float(screen_size.x)),
        min(float(DEFAULT_FULL_WINDOW_SIZE.y), float(screen_size.y))
    )

    OS.window_fullscreen = false
    OS.window_borderless = true
    OS.set_window_size(target_size)
    OS.set_window_position(Vector2(0, 0))
    OS.set_window_position(Vector2(0, 0))

    print(
        "Visual Shell full borderless window applied: position=",
        OS.get_window_position(),
        " size=",
        OS.get_window_size()
    )


static func enter_docked_window() -> void:
    OS.window_fullscreen = false
    OS.window_borderless = true
    OS.set_window_size(DOCKED_WINDOW_SIZE)
    OS.set_window_position(_top_right_position(DOCKED_WINDOW_SIZE))

    print(
        "Visual Shell docked window applied: position=",
        OS.get_window_position(),
        " size=",
        OS.get_window_size()
    )


static func _top_right_position(window_size: Vector2) -> Vector2:
    var screen_size = OS.get_screen_size()
    return Vector2(
        max(0.0, float(screen_size.x) - float(window_size.x) - float(DOCKED_WINDOW_MARGIN.x)),
        max(0.0, float(DOCKED_WINDOW_MARGIN.y))
    )
