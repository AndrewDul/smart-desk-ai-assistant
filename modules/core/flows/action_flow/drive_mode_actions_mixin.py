from __future__ import annotations
from typing import Any
from modules.runtime.drive_mode.voice_launcher import launch_drive_mode_from_environment
from .models import ResolvedAction, SkillRequest, SkillResult
class ActionDriveModeActionsMixin:
    def _handle_drive_mode_start(self, *, route: Any, language: str, payload: dict[str, Any], resolved: ResolvedAction, request: SkillRequest | None = None) -> SkillResult:
        del route, payload, request
        result=launch_drive_mode_from_environment(); lang=self.assistant._normalize_lang(language)
        spoken=self._localized(lang, "Tryb sterowania bazą jest aktywny. Użyj W, A, S, D. Spacja zatrzymuje. Escape wychodzi.", "Drive mode is active. Use W, A, S, D. Space stops. Escape exits.") if result.ok else self._localized(lang, "Nie mogę uruchomić trybu sterowania bazą.", "I cannot start drive mode.")
        delivered=self._deliver_simple_action_response(language=lang, action="drive_mode_start", spoken_text=spoken, display_title="DRIVE MODE", display_lines=self._display_lines(spoken), extra_metadata={"url":result.url,"pid":result.pid,"dry_run":result.dry_run,"movement_enabled":result.movement_enabled,"command_profile":result.command_profile,"error":result.error,"resolved_source":resolved.source})
        return SkillResult(action="drive_mode_start", handled=True, response_delivered=bool(delivered), status="drive_mode_started" if result.ok else "drive_mode_start_failed", metadata={"url":result.url,"pid":result.pid,"dry_run":result.dry_run,"movement_enabled":result.movement_enabled,"command_profile":result.command_profile,"error":result.error})
