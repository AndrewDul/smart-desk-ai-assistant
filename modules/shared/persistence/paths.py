from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class RuntimeLayout:
    """
    Central definition of the NeXa filesystem layout.

    The runtime state is now canonical under `var/...`.
    Source code, config, docs, assets, and models stay outside runtime data.
    Legacy folders (`data`, `logs`, `cache`) are no longer treated as canonical
    write locations, but I still expose their paths for one-way migration logic.
    """

    project_root: Path
    modules_dir: Path
    config_dir: Path
    docs_dir: Path
    tests_dir: Path
    assets_dir: Path
    models_dir: Path
    scripts_dir: Path
    third_party_dir: Path

    var_dir: Path
    data_dir: Path
    logs_dir: Path
    cache_dir: Path

    legacy_data_dir: Path
    legacy_logs_dir: Path
    legacy_cache_dir: Path

    reminders_path: Path
    memory_path: Path
    session_state_path: Path
    user_profile_path: Path
    system_log_path: Path
    settings_path: Path
    settings_example_path: Path


def _looks_like_project_root(candidate: Path) -> bool:
    """
    Return True when the directory looks like the NeXa project root.
    """
    markers = (
        (candidate / "modules").exists(),
        (candidate / "main.py").exists(),
        (candidate / "config").exists(),
    )
    return sum(bool(marker) for marker in markers) >= 2


def find_project_root(start: Path | None = None) -> Path:
    """
    Resolve the real project root even after refactors.
    """
    current = (start or Path(__file__)).resolve()

    for candidate in [current.parent, *current.parents]:
        if _looks_like_project_root(candidate):
            return candidate

    # Fallback for:
    # modules/shared/persistence/paths.py -> project root
    return current.parents[3]


def build_runtime_layout(project_root: Path | None = None) -> RuntimeLayout:
    """
    Build the full application path layout.

    Important rule:
    - runtime writes always go to `var/...`
    - legacy root folders are only exposed for cleanup / migration
    """
    root = (project_root or find_project_root()).resolve()

    modules_dir = root / "modules"
    config_dir = root / "config"
    docs_dir = root / "docs"
    tests_dir = root / "tests"
    assets_dir = root / "assets"
    models_dir = root / "models"
    scripts_dir = root / "scripts"
    third_party_dir = root / "third_party"

    var_dir = root / "var"
    data_dir = var_dir / "data"
    logs_dir = var_dir / "logs"
    cache_dir = var_dir / "cache"

    legacy_data_dir = root / "data"
    legacy_logs_dir = root / "logs"
    legacy_cache_dir = root / "cache"

    reminders_path = data_dir / "reminders.json"
    memory_path = data_dir / "memory.json"
    session_state_path = data_dir / "session_state.json"
    user_profile_path = data_dir / "user_profile.json"

    settings_path = config_dir / "settings.json"
    settings_example_path = config_dir / "settings.example.json"
    system_log_path = logs_dir / "system.log"

    return RuntimeLayout(
        project_root=root,
        modules_dir=modules_dir,
        config_dir=config_dir,
        docs_dir=docs_dir,
        tests_dir=tests_dir,
        assets_dir=assets_dir,
        models_dir=models_dir,
        scripts_dir=scripts_dir,
        third_party_dir=third_party_dir,
        var_dir=var_dir,
        data_dir=data_dir,
        logs_dir=logs_dir,
        cache_dir=cache_dir,
        legacy_data_dir=legacy_data_dir,
        legacy_logs_dir=legacy_logs_dir,
        legacy_cache_dir=legacy_cache_dir,
        reminders_path=reminders_path,
        memory_path=memory_path,
        session_state_path=session_state_path,
        user_profile_path=user_profile_path,
        system_log_path=system_log_path,
        settings_path=settings_path,
        settings_example_path=settings_example_path,
    )


LAYOUT = build_runtime_layout()

APP_ROOT = LAYOUT.project_root
MODULES_DIR = LAYOUT.modules_dir
CONFIG_DIR = LAYOUT.config_dir
DOCS_DIR = LAYOUT.docs_dir
TESTS_DIR = LAYOUT.tests_dir
ASSETS_DIR = LAYOUT.assets_dir
MODELS_DIR = LAYOUT.models_dir
SCRIPTS_DIR = LAYOUT.scripts_dir
THIRD_PARTY_DIR = LAYOUT.third_party_dir

VAR_DIR = LAYOUT.var_dir
DATA_DIR = LAYOUT.data_dir
LOGS_DIR = LAYOUT.logs_dir
CACHE_DIR = LAYOUT.cache_dir

LEGACY_DATA_DIR = LAYOUT.legacy_data_dir
LEGACY_LOGS_DIR = LAYOUT.legacy_logs_dir
LEGACY_CACHE_DIR = LAYOUT.legacy_cache_dir

REMINDERS_PATH = LAYOUT.reminders_path
MEMORY_PATH = LAYOUT.memory_path
SESSION_STATE_PATH = LAYOUT.session_state_path
USER_PROFILE_PATH = LAYOUT.user_profile_path

SYSTEM_LOG_PATH = LAYOUT.system_log_path
SETTINGS_PATH = LAYOUT.settings_path
SETTINGS_EXAMPLE_PATH = LAYOUT.settings_example_path


def ensure_runtime_directories() -> None:
    """
    Create the canonical runtime directories required by the product.
    """
    for directory in (
        CONFIG_DIR,
        DOCS_DIR,
        ASSETS_DIR,
        MODELS_DIR,
        THIRD_PARTY_DIR,
        VAR_DIR,
        DATA_DIR,
        LOGS_DIR,
        CACHE_DIR,
    ):
        directory.mkdir(parents=True, exist_ok=True)


def runtime_migration_candidates() -> dict[Path, Path]:
    """
    Return legacy -> canonical directory pairs for optional one-way cleanup.

    The caller may use this to move old runtime artifacts into `var/...`.
    """
    return {
        LEGACY_DATA_DIR: DATA_DIR,
        LEGACY_LOGS_DIR: LOGS_DIR,
        LEGACY_CACHE_DIR: CACHE_DIR,
    }


def resolve_from_root(*parts: str | Path) -> Path:
    """
    Join one or more path parts onto the project root.
    """
    candidate = APP_ROOT
    for part in parts:
        candidate = candidate / Path(part)
    return candidate.resolve()


def resolve_optional_path(value: str | Path | None) -> Path | None:
    """
    Resolve a project-relative or absolute path safely.
    """
    if value is None:
        return None

    candidate = Path(value).expanduser()
    if candidate.is_absolute():
        return candidate.resolve()

    return (APP_ROOT / candidate).resolve()


__all__ = [
    "RuntimeLayout",
    "LAYOUT",
    "APP_ROOT",
    "MODULES_DIR",
    "CONFIG_DIR",
    "DOCS_DIR",
    "TESTS_DIR",
    "ASSETS_DIR",
    "MODELS_DIR",
    "SCRIPTS_DIR",
    "THIRD_PARTY_DIR",
    "VAR_DIR",
    "DATA_DIR",
    "LOGS_DIR",
    "CACHE_DIR",
    "LEGACY_DATA_DIR",
    "LEGACY_LOGS_DIR",
    "LEGACY_CACHE_DIR",
    "REMINDERS_PATH",
    "MEMORY_PATH",
    "SESSION_STATE_PATH",
    "USER_PROFILE_PATH",
    "SYSTEM_LOG_PATH",
    "SETTINGS_PATH",
    "SETTINGS_EXAMPLE_PATH",
    "find_project_root",
    "build_runtime_layout",
    "ensure_runtime_directories",
    "runtime_migration_candidates",
    "resolve_from_root",
    "resolve_optional_path",
]