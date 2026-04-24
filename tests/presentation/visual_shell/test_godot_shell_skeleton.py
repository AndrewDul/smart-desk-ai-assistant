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