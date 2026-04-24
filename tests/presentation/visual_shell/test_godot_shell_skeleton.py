from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
GODOT_APP_DIR = REPO_ROOT / "modules" / "presentation" / "visual_shell" / "godot_app"


def test_godot_shell_skeleton_files_exist() -> None:
    assert (GODOT_APP_DIR / "project.godot").is_file()
    assert (GODOT_APP_DIR / "scenes" / "main_shell.tscn").is_file()
    assert (GODOT_APP_DIR / "scripts" / "main_shell.gd").is_file()


def test_godot_shell_uses_main_shell_scene() -> None:
    project_file = GODOT_APP_DIR / "project.godot"
    content = project_file.read_text(encoding="utf-8")

    assert 'run/main_scene="res://scenes/main_shell.tscn"' in content


def test_visual_shell_launcher_exists() -> None:
    launcher = (
        REPO_ROOT
        / "modules"
        / "presentation"
        / "visual_shell"
        / "bin"
        / "run_visual_shell.sh"
    )

    assert launcher.is_file()
    assert "godot3 --path ." in launcher.read_text(encoding="utf-8")


def test_godot_shell_has_visual_state_registry() -> None:
    state_registry = GODOT_APP_DIR / "scripts" / "state" / "visual_states.gd"
    content = state_registry.read_text(encoding="utf-8")

    expected_states = {
        "IDLE_PARTICLE_CLOUD",
        "LISTENING_CLOUD",
        "THINKING_SWARM",
        "SPEAKING_PULSE",
        "SCANNING_EYES",
        "SHOW_SELF_EYES",
        "FACE_CONTOUR",
        "BORED_MICRO_ANIMATION",
        "DESKTOP_HIDDEN",
        "DESKTOP_DOCKED",
        "DESKTOP_RETURNING",
        "ERROR_DEGRADED",
    }

    assert state_registry.is_file()
    for state_name in expected_states:
        assert state_name in content


def test_main_shell_routes_manual_keys_through_state_machine() -> None:
    main_shell = (GODOT_APP_DIR / "scripts" / "main_shell.gd").read_text(encoding="utf-8")

    assert "VisualStateMachineScript" in main_shell
    assert "state_machine.set_state" in main_shell
    assert "VisualStates.SHOW_SELF_EYES" in main_shell
    assert "VisualStates.FACE_CONTOUR" in main_shell
    assert "VisualStates.BORED_MICRO_ANIMATION" in main_shell
    assert "KEY_6" in main_shell
    assert "KEY_8" in main_shell
    assert "KEY_9" in main_shell


def test_main_shell_uses_real_docked_window_mode() -> None:
    main_shell = (GODOT_APP_DIR / "scripts" / "main_shell.gd").read_text(encoding="utf-8")
    window_controller = (
        GODOT_APP_DIR / "scripts" / "desktop" / "desktop_window_controller.gd"
    )

    assert window_controller.is_file()
    assert "DesktopWindowController.enter_docked_window()" in main_shell
    assert "DesktopWindowController.enter_fullscreen()" in main_shell
    assert "_enter_desktop_docked_mode" in main_shell
    assert "_return_to_fullscreen_shell" in main_shell
    assert "particle_cloud.set_shell_compact_mode(true)" in main_shell
    assert "particle_cloud.set_shell_compact_mode(false)" in main_shell
    assert "KEY_0" in main_shell
    assert "KEY_MINUS" in main_shell


def test_desktop_window_controller_controls_actual_window() -> None:
    window_controller = (
        GODOT_APP_DIR / "scripts" / "desktop" / "desktop_window_controller.gd"
    ).read_text(encoding="utf-8")

    assert "OS.window_fullscreen = false" in window_controller
    assert "OS.window_size = DOCKED_WINDOW_SIZE" in window_controller
    assert "OS.window_position" in window_controller
    assert "OS.window_fullscreen = true" in window_controller
    assert "DOCKED_WINDOW_SIZE = Vector2(300, 300)" in window_controller


def test_particle_cloud_preserves_visual_state_during_docked_mode() -> None:
    particle_cloud = (GODOT_APP_DIR / "scripts" / "particle_cloud.gd").read_text(
        encoding="utf-8"
    )

    assert "func set_shell_compact_mode(enabled: bool) -> void:" in particle_cloud
    assert "shell_compact_mode = enabled" in particle_cloud
    assert "visual_state = previous_state" in particle_cloud
    assert "VisualStates.DESKTOP_DOCKED" in particle_cloud
    assert "VisualStates.DESKTOP_RETURNING" in particle_cloud


def test_particle_cloud_uses_show_self_eyes_as_eye_formation() -> None:
    particle_cloud = (GODOT_APP_DIR / "scripts" / "particle_cloud.gd").read_text(encoding="utf-8")

    assert "VisualStates.is_eye_formation_state(visual_state)" in particle_cloud
    assert "VisualStates.SHOW_SELF_EYES" in particle_cloud


def test_godot_shell_has_modular_eye_formation() -> None:
    eye_formation = GODOT_APP_DIR / "scripts" / "formations" / "eye_formation.gd"
    particle_cloud = (GODOT_APP_DIR / "scripts" / "particle_cloud.gd").read_text(encoding="utf-8")

    assert eye_formation.is_file()
    assert "assign_eye_targets" in eye_formation.read_text(encoding="utf-8")
    assert 'preload("res://scripts/formations/eye_formation.gd")' in particle_cloud


def test_godot_shell_has_visual_palette_module() -> None:
    visual_palette = GODOT_APP_DIR / "scripts" / "palette" / "visual_palette.gd"
    particle_cloud = (GODOT_APP_DIR / "scripts" / "particle_cloud.gd").read_text(encoding="utf-8")

    assert visual_palette.is_file()
    assert "color_for_particle" in visual_palette.read_text(encoding="utf-8")
    assert 'preload("res://scripts/palette/visual_palette.gd")' in particle_cloud


def test_godot_shell_has_eye_behaviour_module() -> None:
    eye_behaviour = GODOT_APP_DIR / "scripts" / "behaviours" / "eye_behaviour.gd"
    particle_cloud = (GODOT_APP_DIR / "scripts" / "particle_cloud.gd").read_text(encoding="utf-8")

    assert eye_behaviour.is_file()

    eye_behaviour_content = eye_behaviour.read_text(encoding="utf-8")

    assert "attention_offset" in eye_behaviour_content
    assert "formation_strength_for_state" in eye_behaviour_content
    assert "state_motion" in eye_behaviour_content
    assert 'preload("res://scripts/behaviours/eye_behaviour.gd")' in particle_cloud


def test_show_self_eyes_remains_a_calm_eye_behaviour() -> None:
    eye_behaviour = (
        GODOT_APP_DIR / "scripts" / "behaviours" / "eye_behaviour.gd"
    ).read_text(encoding="utf-8")

    assert "VisualStates.SHOW_SELF_EYES" in eye_behaviour
    assert "calm_x" in eye_behaviour
    assert "calm_y" in eye_behaviour


def test_godot_shell_has_face_contour_formation() -> None:
    face_formation = GODOT_APP_DIR / "scripts" / "formations" / "face_contour_formation.gd"
    face_behaviour = GODOT_APP_DIR / "scripts" / "behaviours" / "face_contour_behaviour.gd"
    particle_cloud = (GODOT_APP_DIR / "scripts" / "particle_cloud.gd").read_text(encoding="utf-8")
    visual_states = (GODOT_APP_DIR / "scripts" / "state" / "visual_states.gd").read_text(
        encoding="utf-8"
    )

    assert face_formation.is_file()
    assert face_behaviour.is_file()
    assert "assign_face_targets" in face_formation.read_text(encoding="utf-8")
    assert "is_face_formation_state" in visual_states
    assert 'preload("res://scripts/formations/face_contour_formation.gd")' in particle_cloud
    assert 'preload("res://scripts/behaviours/face_contour_behaviour.gd")' in particle_cloud


def test_godot_shell_has_speaking_behaviour_module() -> None:
    speaking_behaviour = GODOT_APP_DIR / "scripts" / "behaviours" / "speaking_behaviour.gd"
    particle_cloud = (GODOT_APP_DIR / "scripts" / "particle_cloud.gd").read_text(encoding="utf-8")

    assert speaking_behaviour.is_file()

    speaking_content = speaking_behaviour.read_text(encoding="utf-8")

    assert "voice_energy" in speaking_content
    assert "state_motion" in speaking_content
    assert "alpha_bonus" in speaking_content
    assert "size_bonus" in speaking_content
    assert 'preload("res://scripts/behaviours/speaking_behaviour.gd")' in particle_cloud
    assert "SpeakingBehaviour.state_motion" in particle_cloud


def test_godot_shell_has_listening_and_thinking_behaviour_modules() -> None:
    listening_behaviour = GODOT_APP_DIR / "scripts" / "behaviours" / "listening_behaviour.gd"
    thinking_behaviour = GODOT_APP_DIR / "scripts" / "behaviours" / "thinking_behaviour.gd"
    particle_cloud = (GODOT_APP_DIR / "scripts" / "particle_cloud.gd").read_text(encoding="utf-8")

    assert listening_behaviour.is_file()
    assert thinking_behaviour.is_file()

    listening_content = listening_behaviour.read_text(encoding="utf-8")
    thinking_content = thinking_behaviour.read_text(encoding="utf-8")

    assert "state_motion" in listening_content
    assert "alpha_bonus" in listening_content
    assert "size_bonus" in listening_content

    assert "state_motion" in thinking_content
    assert "alpha_bonus" in thinking_content
    assert "size_bonus" in thinking_content

    assert 'preload("res://scripts/behaviours/listening_behaviour.gd")' in particle_cloud
    assert 'preload("res://scripts/behaviours/thinking_behaviour.gd")' in particle_cloud
    assert "ListeningBehaviour.state_motion" in particle_cloud
    assert "ThinkingBehaviour.state_motion" in particle_cloud


def test_godot_shell_has_scanning_behaviour_module() -> None:
    scanning_behaviour = GODOT_APP_DIR / "scripts" / "behaviours" / "scanning_behaviour.gd"
    particle_cloud = (GODOT_APP_DIR / "scripts" / "particle_cloud.gd").read_text(encoding="utf-8")

    assert scanning_behaviour.is_file()

    scanning_content = scanning_behaviour.read_text(encoding="utf-8")

    assert "attention_offset" in scanning_content
    assert "formation_strength" in scanning_content
    assert "state_motion" in scanning_content
    assert "overlay_alpha" in scanning_content
    assert "overlay_y" in scanning_content
    assert "overlay_color" in scanning_content

    assert 'preload("res://scripts/behaviours/scanning_behaviour.gd")' in particle_cloud
    assert "ScanningBehaviour.state_motion" in particle_cloud
    assert "_draw_scanning_overlay" in particle_cloud


def test_godot_shell_has_bored_micro_behaviour_module() -> None:
    bored_micro_behaviour = (
        GODOT_APP_DIR / "scripts" / "behaviours" / "bored_micro_behaviour.gd"
    )
    particle_cloud = (GODOT_APP_DIR / "scripts" / "particle_cloud.gd").read_text(
        encoding="utf-8"
    )

    assert bored_micro_behaviour.is_file()

    bored_content = bored_micro_behaviour.read_text(encoding="utf-8")

    assert "next_delay" in bored_content
    assert "next_duration" in bored_content
    assert "pick_kind" in bored_content
    assert "state_motion" in bored_content
    assert "alpha_bonus" in bored_content
    assert "size_bonus" in bored_content

    assert 'preload("res://scripts/behaviours/bored_micro_behaviour.gd")' in particle_cloud
    assert "_schedule_next_idle_micro" in particle_cloud
    assert "_current_idle_micro_intensity" in particle_cloud
    assert "BoredMicroBehaviour.state_motion" in particle_cloud


def test_godot_shell_has_desktop_dock_behaviour_module() -> None:
    desktop_dock_behaviour = (
        GODOT_APP_DIR / "scripts" / "behaviours" / "desktop_dock_behaviour.gd"
    )
    particle_cloud = (GODOT_APP_DIR / "scripts" / "particle_cloud.gd").read_text(
        encoding="utf-8"
    )

    assert desktop_dock_behaviour.is_file()

    dock_content = desktop_dock_behaviour.read_text(encoding="utf-8")

    assert "target_scale" in dock_content
    assert "COMPACT_FILL" in dock_content
    assert "COMPACT_VISUAL_DIAMETER_FACTOR" in dock_content
    assert "particle_size_multiplier" in dock_content
    assert "state_motion" in dock_content
    assert "orb_alpha" in dock_content
    assert "orb_radius" in dock_content

    assert 'preload("res://scripts/behaviours/desktop_dock_behaviour.gd")' in particle_cloud
    assert "_update_shell_transform" in particle_cloud
    assert "DesktopDockBehaviour.target_scale" in particle_cloud
    assert "DesktopDockBehaviour.particle_size_multiplier" in particle_cloud
    assert "DesktopDockBehaviour.state_motion" in particle_cloud
    assert "_draw_compact_orb_background" in particle_cloud