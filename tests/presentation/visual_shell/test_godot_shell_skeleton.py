from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
GODOT_APP_DIR = REPO_ROOT / "modules" / "presentation" / "visual_shell" / "godot_app"
VISUAL_SHELL_DIR = REPO_ROOT / "modules" / "presentation" / "visual_shell"


def _read_godot(relative_path: str) -> str:
    return (GODOT_APP_DIR / relative_path).read_text(encoding="utf-8")


def _read_repo(relative_path: str) -> str:
    return (REPO_ROOT / relative_path).read_text(encoding="utf-8")


def test_godot_app_core_files_are_present() -> None:
    required_files = [
        "project.godot",
        "scenes/main_shell.tscn",
        "scripts/main_shell.gd",
        "scripts/particle_cloud.gd",
        "scripts/state/visual_states.gd",
        "scripts/visual_state_machine.gd",
        "scripts/transport/visual_shell_tcp_server.gd",
        "scripts/desktop/desktop_window_controller.gd",
        "scripts/desktop/shell_layout.gd",
    ]

    for relative_path in required_files:
        assert (GODOT_APP_DIR / relative_path).is_file(), relative_path


def test_particle_cloud_is_current_v13_multimesh_renderer() -> None:
    particle_cloud = _read_godot("scripts/particle_cloud.gd")

    assert "production particle cloud renderer (post-migration)" in particle_cloud
    assert "Migration source: preview/idle_nebula_preview.gd (V13)." in particle_cloud
    assert "const PARTICLE_COUNT = 6000" in particle_cloud
    assert "export(int) var particle_count = PARTICLE_COUNT" in particle_cloud
    assert "var multimesh: MultiMesh" in particle_cloud
    assert "var multimesh_instance: MultiMeshInstance2D" in particle_cloud
    assert "multimesh = MultiMesh.new()" in particle_cloud
    assert "multimesh.transform_format = MultiMesh.TRANSFORM_2D" in particle_cloud
    assert "multimesh.color_format = MultiMesh.COLOR_FLOAT" in particle_cloud
    assert "multimesh.instance_count = PARTICLE_COUNT" in particle_cloud
    assert "multimesh_instance = MultiMeshInstance2D.new()" in particle_cloud



def test_particle_cloud_uses_organic_field_motion_without_global_orbit() -> None:
    particle_cloud = _read_godot("scripts/particle_cloud.gd")

    assert "const ORGANIC_FIELD_X_SPREAD = 1.10" in particle_cloud
    assert "const ORGANIC_FIELD_WARP_X = 20.0" in particle_cloud
    assert "const ORGANIC_DRIFT_X_PRIMARY = 14.0" in particle_cloud
    assert "const ORGANIC_DRIFT_Y_PRIMARY = 12.0" in particle_cloud
    assert "var t_field_a: float = time * 0.12" in particle_cloud
    assert "var field_warp_x: float = sin(base_pos.y * 0.006 + t_field_a + phase)" in particle_cloud
    assert "var field_warp_y: float = cos(base_pos.x * 0.005 + t_field_b + phase * 1.3)" in particle_cloud
    assert "var field_shear_x: float = base_pos.y * sin(t_field_c + phase * 0.10) * 0.018" in particle_cloud
    assert "var field_shear_y: float = base_pos.x * cos(t_field_d + phase * 0.12) * 0.010" in particle_cloud
    assert "base_pos.x * swirl_cos - base_pos.y * swirl_sin" not in particle_cloud
    assert "base_pos.x * swirl_sin + base_pos.y * swirl_cos" not in particle_cloud
    assert "Subtle swirl reorganization" not in particle_cloud


def test_particle_cloud_spreads_compact_mode_as_square_field_without_distorting_glyphs() -> None:
    particle_cloud = _read_godot("scripts/particle_cloud.gd")

    assert "const COMPACT_FIELD_X_FILL = 1.20" in particle_cloud
    assert "const COMPACT_FIELD_Y_FILL = 1.18" in particle_cloud
    assert "const COMPACT_CORNER_X_FILL = 0.46" in particle_cloud
    assert "const COMPACT_CORNER_Y_FILL = 0.52" in particle_cloud
    assert "const COMPACT_FIELD_GLYPH_PROTECTION_THRESHOLD = 0.35" in particle_cloud
    assert "func _compact_square_field_position(position: Vector2, glyph_blend_value: float) -> Vector2:" in particle_cloud
    assert "if glyph_blend_value > COMPACT_FIELD_GLYPH_PROTECTION_THRESHOLD:" in particle_cloud
    assert "var normalized_x: float = clamp(position.x / max(1.0, NEBULA_RADIUS * 1.45), -1.0, 1.0)" in particle_cloud
    assert "var normalized_y: float = clamp(position.y / max(1.0, NEBULA_RADIUS * 1.05), -1.0, 1.0)" in particle_cloud
    assert "var x_fill: float = COMPACT_FIELD_X_FILL + abs(normalized_y) * COMPACT_CORNER_X_FILL" in particle_cloud
    assert "var y_fill: float = COMPACT_FIELD_Y_FILL + abs(normalized_x) * COMPACT_CORNER_Y_FILL" in particle_cloud
    assert "var compact_position: Vector2 = _compact_square_field_position(Vector2(pos_x, pos_y), glyph_blend)" in particle_cloud

def test_particle_cloud_scales_current_renderer_for_docked_window() -> None:
    particle_cloud = _read_godot("scripts/particle_cloud.gd")

    assert "var render_scale: Vector2 = Vector2(1.0, 1.0)" in particle_cloud
    assert "func _compact_nebula_render_scale(viewport_size: Vector2) -> Vector2:" in particle_cloud
    assert "target = _compact_nebula_render_scale(get_viewport_rect().size)" in particle_cloud
    assert "render_scale = render_scale.linear_interpolate" in particle_cloud
    assert "func _particle_screen_size_multiplier() -> float:" in particle_cloud
    assert "func _glyph_position_multiplier() -> float:" in particle_cloud
    assert "func _glyph_particle_size_multiplier() -> float:" in particle_cloud
    assert "particle_glyph_positions[i] * glyph_position_multiplier" in particle_cloud
    assert "0.55 * _glyph_particle_size_multiplier()" in particle_cloud
    assert "final_size * render_scale.x" in particle_cloud
    assert "final_size * render_scale.y" in particle_cloud
    assert "pos_x * render_scale.x" in particle_cloud
    assert "pos_y * render_scale.y" in particle_cloud


def test_particle_cloud_public_runtime_api_is_present() -> None:
    particle_cloud = _read_godot("scripts/particle_cloud.gd")

    required_functions = [
        "func set_visual_state(new_state: String) -> void:",
        "func set_shell_compact_mode(enabled: bool) -> void:",
        "func set_temperature_metric(value_c: int) -> void:",
        "func set_battery_metric(percent: int) -> void:",
        "func set_date_metric(text: String) -> void:",
        "func set_time_metric(text: String) -> void:",
    ]

    for function_signature in required_functions:
        assert function_signature in particle_cloud


def test_particle_cloud_keeps_existing_face_and_glyph_state_machine() -> None:
    particle_cloud = _read_godot("scripts/particle_cloud.gd")

    required_tokens = [
        "const FACE_STATE_NONE",
        "const FACE_STATE_EMERGE",
        "const FACE_STATE_HOLD",
        "const FACE_STATE_DISSOLVE",
        "const GLYPH_KIND_NONE",
        "const GLYPH_KIND_TEMPERATURE",
        "const GLYPH_KIND_BATTERY",
        "const GLYPH_KIND_DATE",
        "const GLYPH_KIND_TIME",
        "var face_state: int = FACE_STATE_NONE",
        "var glyph_kind: int = GLYPH_KIND_NONE",
        "var glyph_state: int = FACE_STATE_NONE",
        "_trigger_glyph(GLYPH_KIND_TEMPERATURE)",
        "_trigger_glyph(GLYPH_KIND_BATTERY)",
        "glyph_kind = GLYPH_KIND_DATE",
        "glyph_kind = GLYPH_KIND_TIME",
    ]

    for token in required_tokens:
        assert token in particle_cloud


def test_particle_cloud_preserves_voice_engine_v2_state_contract_comment() -> None:
    particle_cloud = _read_godot("scripts/particle_cloud.gd")

    assert "accepted by set_visual_state() to preserve Voice Engine v2 contract" in particle_cloud


def test_particle_cloud_does_not_depend_on_old_nebula_behaviour_module() -> None:
    particle_cloud = _read_godot("scripts/particle_cloud.gd")
    nebula_behaviour = GODOT_APP_DIR / "scripts" / "behaviours" / "nebula_behaviour.gd"

    assert 'preload("res://scripts/behaviours/nebula_behaviour.gd")' not in particle_cloud
    assert not nebula_behaviour.exists()


def test_particle_cloud_does_not_reintroduce_old_modular_renderer_preloads() -> None:
    particle_cloud = _read_godot("scripts/particle_cloud.gd")

    old_renderer_preloads = [
        'preload("res://scripts/formations/eye_formation.gd")',
        'preload("res://scripts/formations/face_contour_formation.gd")',
        'preload("res://scripts/formations/glyph_formation.gd")',
        'preload("res://scripts/behaviours/eye_behaviour.gd")',
        'preload("res://scripts/behaviours/face_contour_behaviour.gd")',
        'preload("res://scripts/behaviours/listening_behaviour.gd")',
        'preload("res://scripts/behaviours/thinking_behaviour.gd")',
        'preload("res://scripts/behaviours/speaking_behaviour.gd")',
        'preload("res://scripts/behaviours/scanning_behaviour.gd")',
        'preload("res://scripts/behaviours/bored_micro_behaviour.gd")',
        'preload("res://scripts/behaviours/desktop_dock_behaviour.gd")',
        'preload("res://scripts/behaviours/metric_display_behaviour.gd")',
    ]

    for preload in old_renderer_preloads:
        assert preload not in particle_cloud


def test_visual_states_define_current_renderer_states() -> None:
    visual_states = _read_godot("scripts/state/visual_states.gd")

    required_states = [
        'const IDLE_PARTICLE_CLOUD = "IDLE_PARTICLE_CLOUD"',
        'const LISTENING_CLOUD = "LISTENING_CLOUD"',
        'const THINKING_SWARM = "THINKING_SWARM"',
        'const SPEAKING_PULSE = "SPEAKING_PULSE"',
        'const SCANNING_EYES = "SCANNING_EYES"',
        'const SHOW_SELF_EYES = "SHOW_SELF_EYES"',
        'const FACE_CONTOUR = "FACE_CONTOUR"',
        'const BORED_MICRO_ANIMATION = "BORED_MICRO_ANIMATION"',
        'const TEMPERATURE_GLYPH = "TEMPERATURE_GLYPH"',
        'const BATTERY_GLYPH = "BATTERY_GLYPH"',
        'const DATE_GLYPH = "DATE_GLYPH"',
        'const TIME_GLYPH = "TIME_GLYPH"',
        'const DESKTOP_HIDDEN = "DESKTOP_HIDDEN"',
        'const DESKTOP_DOCKED = "DESKTOP_DOCKED"',
        'const DESKTOP_RETURNING = "DESKTOP_RETURNING"',
        'const ERROR_DEGRADED = "ERROR_DEGRADED"',
    ]

    for state in required_states:
        assert state in visual_states

    assert "static func coerce_state(state_name: String) -> String:" in visual_states
    assert "static func is_eye_formation_state(state_name: String) -> bool:" in visual_states
    assert "static func is_face_formation_state(state_name: String) -> bool:" in visual_states
    assert "static func is_metric_display_state(state_name: String) -> bool:" in visual_states


def test_python_visual_state_contract_contains_current_and_future_metric_states() -> None:
    visual_state = _read_repo("modules/presentation/visual_shell/contracts/visual_state.py")

    required_states = [
        'IDLE_PARTICLE_CLOUD = "IDLE_PARTICLE_CLOUD"',
        'LISTENING_CLOUD = "LISTENING_CLOUD"',
        'THINKING_SWARM = "THINKING_SWARM"',
        'SPEAKING_PULSE = "SPEAKING_PULSE"',
        'SCANNING_EYES = "SCANNING_EYES"',
        'SHOW_SELF_EYES = "SHOW_SELF_EYES"',
        'FACE_CONTOUR = "FACE_CONTOUR"',
        'TEMPERATURE_GLYPH = "TEMPERATURE_GLYPH"',
        'BATTERY_GLYPH = "BATTERY_GLYPH"',
        'DATE_GLYPH = "DATE_GLYPH"',
        'TIME_GLYPH = "TIME_GLYPH"',
        'ERROR_DEGRADED = "ERROR_DEGRADED"',
    ]

    for state in required_states:
        assert state in visual_state


def test_visual_command_contract_contains_current_runtime_commands() -> None:
    visual_command = _read_repo("modules/presentation/visual_shell/contracts/visual_command.py")

    required_commands = [
        'SET_STATE = "SET_STATE"',
        'SHOW_DESKTOP = "SHOW_DESKTOP"',
        'HIDE_DESKTOP = "HIDE_DESKTOP"',
        'SHOW_SELF = "SHOW_SELF"',
        'SHOW_EYES = "SHOW_EYES"',
        'SHOW_FACE_CONTOUR = "SHOW_FACE_CONTOUR"',
        'START_SCANNING = "START_SCANNING"',
        'RETURN_TO_IDLE = "RETURN_TO_IDLE"',
        'REPORT_DEGRADED = "REPORT_DEGRADED"',
        'SHOW_TEMPERATURE = "SHOW_TEMPERATURE"',
        'SHOW_BATTERY = "SHOW_BATTERY"',
        'SHOW_DATE = "SHOW_DATE"',
        'SHOW_TIME = "SHOW_TIME"',
    ]

    for command in required_commands:
        assert command in visual_command


def test_main_shell_accepts_current_tcp_command_surface() -> None:
    main_shell = _read_godot("scripts/main_shell.gd")

    required_commands = [
        'command == "SET_STATE"',
        'command == "SHOW_DESKTOP"',
        'command == "HIDE_DESKTOP"',
        'command == "SHOW_SELF"',
        'command == "SHOW_EYES"',
        'command == "SHOW_FACE_CONTOUR"',
        'command == "START_SCANNING"',
        'command == "RETURN_TO_IDLE"',
        'command == "REPORT_DEGRADED"',
        'command == "SHOW_TEMPERATURE"',
        'command == "SHOW_BATTERY"',
        'command == "SHOW_DATE"',
        'command == "SHOW_TIME"',
    ]

    for command in required_commands:
        assert command in main_shell

    assert "_set_visual_state(VisualStates.SHOW_SELF_EYES)" in main_shell
    assert "_set_visual_state(VisualStates.FACE_CONTOUR)" in main_shell
    assert "_set_visual_state(VisualStates.SCANNING_EYES)" in main_shell
    assert "_set_visual_state(VisualStates.IDLE_PARTICLE_CLOUD)" in main_shell
    assert "func display_date_text(text: String) -> void:" in main_shell
    assert "func display_time_text(text: String) -> void:" in main_shell
    assert "particle_cloud.set_date_metric(text)" in main_shell
    assert "particle_cloud.set_time_metric(text)" in main_shell


def test_main_shell_keeps_raspberry_pi_rendering_limits() -> None:
    main_shell = _read_godot("scripts/main_shell.gd")
    project_file = _read_godot("project.godot")

    assert "const TARGET_RENDER_FPS = 24" in main_shell
    assert "Engine.target_fps = TARGET_RENDER_FPS" in main_shell
    assert "OS.low_processor_usage_mode = false" in main_shell
    assert "OS.vsync_enabled = true" in main_shell
    assert "OS.delay_msec" not in main_shell
    assert "const SHOW_DEBUG_STATUS_LABEL = false" in main_shell
    assert 'quality/driver/driver_name="GLES2"' in project_file


def test_visual_shell_tcp_server_keeps_line_delimited_json_transport() -> None:
    tcp_server = _read_godot("scripts/transport/visual_shell_tcp_server.gd")

    assert "127.0.0.1" in tcp_server
    assert "8765" in tcp_server
    assert "JSON" in tcp_server
    assert "\n" in tcp_server or "newline" in tcp_server.lower()
    assert "listen" in tcp_server.lower()


def test_visual_shell_controller_exposes_current_voice_actions() -> None:
    controller = _read_repo("modules/presentation/visual_shell/controller/visual_shell_controller.py")

    required_methods = [
        "def handle_voice_action(",
        "def show_desktop(",
        "def hide_desktop(",
        "def show_self(",
        "def show_eyes(",
        "def show_face_contour(",
        "def start_scanning(",
        "def return_to_idle(",
        "def show_temperature(",
        "def show_battery(",
        "def show_current_temperature(",
        "def show_current_battery(",
        "def show_current_date(",
        "def show_current_time(",
    ]

    for method in required_methods:
        assert method in controller

    required_actions = [
        "VisualVoiceAction.SHOW_TEMPERATURE",
        "VisualVoiceAction.SHOW_BATTERY",
        "VisualVoiceAction.SHOW_DESKTOP",
        "VisualVoiceAction.HIDE_DESKTOP",
        "VisualVoiceAction.SHOW_SELF",
        "VisualVoiceAction.SHOW_EYES",
        "VisualVoiceAction.LOOK_AT_USER",
        "VisualVoiceAction.SHOW_FACE_CONTOUR",
        "VisualVoiceAction.START_SCANNING",
        "VisualVoiceAction.RETURN_TO_IDLE",
    ]

    for action in required_actions:
        assert action in controller


def test_visual_shell_voice_command_router_contains_current_pl_en_aliases() -> None:
    router = _read_repo("modules/presentation/visual_shell/controller/voice_command_router.py")

    required_actions = [
        'SHOW_TEMPERATURE = "SHOW_TEMPERATURE"',
        'SHOW_BATTERY = "SHOW_BATTERY"',
        'SHOW_DESKTOP = "SHOW_DESKTOP"',
        'HIDE_DESKTOP = "HIDE_DESKTOP"',
        'SHOW_FACE_CONTOUR = "SHOW_FACE_CONTOUR"',
        'RETURN_TO_IDLE = "RETURN_TO_IDLE"',
    ]

    for action in required_actions:
        assert action in router

    required_phrases = [
        "pokaz pulpit",
        "schowaj pulpit",
        "pokaz sie",
        "pokaz twarz",
        "show desktop",
        "hide desktop",
        "show yourself",
        "show face",
    ]

    for phrase in required_phrases:
        assert phrase in router

    disabled_phrases = [
        "pokaz oczy",
        "spojrz na mnie",
        "sprawdz pokoj",
        "rozejrzyj sie",
        "co widzisz",
        "show eyes",
        "look at me",
        "scan room",
    ]

    for phrase in disabled_phrases:
        assert phrase not in router


def test_fast_command_lane_still_has_visual_shell_hook() -> None:
    fast_command_lane = _read_repo("modules/core/session/fast_command_lane.py")
    core = _read_repo("modules/core/assistant_impl/core.py")

    assert "VisualShellCommandLane" in fast_command_lane
    assert "visual_shell_lane" in fast_command_lane
    assert "def _try_handle_visual_shell(" in fast_command_lane
    assert "self.visual_shell_lane.try_handle(" in fast_command_lane
    assert "VisualShellCommandLane.from_settings(" in core


def test_voice_engine_v2_current_visual_shell_runtime_candidates_are_preserved() -> None:
    grammar = _read_repo("modules/devices/audio/command_asr/command_grammar.py")
    intents = _read_repo("modules/core/command_intents/visual_shell_intents.py")
    executor = _read_repo("modules/runtime/voice_engine_v2/runtime_candidate_executor.py")
    settings = _read_repo("config/settings.json")

    assert "visual_shell.show_desktop" in grammar
    assert "visual_shell.show_shell" in grammar

    assert '"visual_shell.show_desktop"' in intents
    assert '"visual_shell.show_shell"' in intents
    assert '"visual_shell.show_temperature"' in intents
    assert '"visual_shell.show_battery"' in intents

    assert '"visual_shell.show_desktop": RuntimeCandidateActionSpec' in executor
    assert '"visual_shell.show_shell": RuntimeCandidateActionSpec' in executor

    assert '"visual_shell.show_desktop"' in settings
    assert '"visual_shell.show_shell"' in settings


def test_visual_shell_settings_keep_fast_local_transport() -> None:
    settings = _read_repo("config/settings.json")

    assert '"visual_shell"' in settings
    assert '"enabled": true' in settings
    assert '"voice_commands_enabled": true' in settings
    assert '"speak_acknowledgements_enabled": false' in settings
    assert '"host": "127.0.0.1"' in settings
    assert '"port": 8765' in settings
    assert '"timeout_sec": 0.1' in settings
    assert '"audio_driver": "Dummy"' in settings
    assert '"modules/presentation/visual_shell/bin/run_visual_shell.sh"' in settings


def test_godot_scripts_do_not_mix_tabs_and_spaces_on_the_same_indentation_prefix() -> None:
    gdscript_files = sorted((GODOT_APP_DIR / "scripts").rglob("*.gd"))

    assert gdscript_files

    offenders = []
    for gdscript_file in gdscript_files:
        for line_number, line in enumerate(
            gdscript_file.read_text(encoding="utf-8").splitlines(),
            start=1,
        ):
            leading = line[: len(line) - len(line.lstrip(" \t"))]
            if " " in leading and "\t" in leading:
                offenders.append(f"{gdscript_file.relative_to(GODOT_APP_DIR)}:{line_number}")

    assert offenders == []


def test_scene_references_main_shell_and_particle_cloud() -> None:
    scene = _read_godot("scenes/main_shell.tscn")

    assert "main_shell.gd" in scene
    assert "ParticleCloud" in scene or "particle_cloud" in scene
