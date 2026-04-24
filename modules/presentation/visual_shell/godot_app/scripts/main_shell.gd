extends Control

const BOOT_STATE := "IDLE_PARTICLE_CLOUD"

onready var status_label: Label = $StatusLabel


func _ready() -> void:
	OS.window_fullscreen = true
	status_label.text = "NEXA VISUAL SHELL\n" + BOOT_STATE