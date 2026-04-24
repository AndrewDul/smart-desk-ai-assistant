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
    assert "state_machine.set_state(VisualStates.SHOW_SELF_EYES)" in main_shell
    assert "KEY_6" in main_shell


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


def test_show_self_and_scanning_have_separate_eye_behaviour() -> None:
    eye_behaviour = (
        GODOT_APP_DIR / "scripts" / "behaviours" / "eye_behaviour.gd"
    ).read_text(encoding="utf-8")

    assert "VisualStates.SCANNING_EYES" in eye_behaviour
    assert "VisualStates.SHOW_SELF_EYES" in eye_behaviour
    assert "scan_x" in eye_behaviour
    assert "calm_x" in eye_behaviour