from __future__ import annotations

import json
import os
from typing import Any
from urllib.error import URLError
from urllib.request import Request, urlopen

from modules.runtime.drive_mode.voice_launcher import launch_drive_mode_from_environment

from .models import ResolvedAction, SkillRequest, SkillResult


class ActionDriveModeActionsMixin:
    def _handle_drive_mode_start(
        self,
        *,
        route: Any,
        language: str,
        payload: dict[str, Any],
        resolved: ResolvedAction,
        request: SkillRequest | None = None,
    ) -> SkillResult:
        del route, payload, request

        result = launch_drive_mode_from_environment()
        lang = self.assistant._normalize_lang(language)
        spoken = (
            self._localized(
                lang,
                "Tryb sterowania bazą jest aktywny. Użyj W, A, S, D. Spacja zatrzymuje. Escape wychodzi.",
                "Drive mode is active. Use W, A, S, D. Space stops. Escape exits.",
            )
            if result.ok
            else self._localized(
                lang,
                "Nie mogę uruchomić trybu sterowania bazą.",
                "I cannot start drive mode.",
            )
        )

        delivered = self._deliver_simple_action_response(
            language=lang,
            action="drive_mode_start",
            spoken_text=spoken,
            display_title="DRIVE MODE",
            display_lines=self._display_lines(spoken),
            extra_metadata={
                "url": result.url,
                "pid": result.pid,
                "dry_run": result.dry_run,
                "movement_enabled": result.movement_enabled,
                "command_profile": result.command_profile,
                "error": result.error,
                "resolved_source": resolved.source,
            },
        )
        return SkillResult(
            action="drive_mode_start",
            handled=True,
            response_delivered=bool(delivered),
            status="drive_mode_started" if result.ok else "drive_mode_start_failed",
            metadata={
                "url": result.url,
                "pid": result.pid,
                "dry_run": result.dry_run,
                "movement_enabled": result.movement_enabled,
                "command_profile": result.command_profile,
                "error": result.error,
            },
        )

    def _handle_drive_mode_stop(
        self,
        *,
        route: Any,
        language: str,
        payload: dict[str, Any],
        resolved: ResolvedAction,
        request: SkillRequest | None = None,
    ) -> SkillResult:
        del route, payload, request

        lang = self.assistant._normalize_lang(language)
        stop_result = self._send_drive_mode_stop_request()

        if stop_result["ok"]:
            spoken = self._localized(
                lang,
                "Zatrzymałam bazę mobilną.",
                "I stopped the mobile base.",
            )
            status = "drive_mode_stop_sent"
        else:
            spoken = self._localized(
                lang,
                "Tryb jazdy nie jest aktywny albo panel sterowania nie odpowiada. Komenda stop została obsłużona bezpiecznie.",
                "Drive mode is not active or the control panel is not responding. The stop command was handled safely.",
            )
            status = "drive_mode_stop_unavailable"

        delivered = self._deliver_simple_action_response(
            language=lang,
            action="drive_mode_stop",
            spoken_text=spoken,
            display_title="DRIVE STOP",
            display_lines=self._display_lines(spoken),
            extra_metadata={
                "resolved_source": resolved.source,
                "stop_result": stop_result,
            },
        )

        return SkillResult(
            action="drive_mode_stop",
            handled=True,
            response_delivered=bool(delivered),
            status=status,
            metadata={
                "source": "drive_mode_http_stop",
                "response_kind": "direct_response",
                "stop_result": stop_result,
            },
        )

    def _send_drive_mode_stop_request(self) -> dict[str, Any]:
        host = os.environ.get("NEXA_DRIVE_MODE_HOST", "127.0.0.1")
        port = int(os.environ.get("NEXA_DRIVE_MODE_HTTP_PORT", "8768"))
        url = f"http://{host}:{port}/api/key"
        body = json.dumps({"key": "space", "event": "down"}, separators=(",", ":")).encode("utf-8")

        request = Request(
            url,
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            with urlopen(request, timeout=0.35) as response:
                raw = response.read().decode("utf-8", errors="replace")
        except (OSError, URLError) as error:
            return {
                "ok": False,
                "url": url,
                "error": str(error),
            }

        try:
            data = json.loads(raw or "{}")
        except json.JSONDecodeError:
            data = {"raw": raw}

        return {
            "ok": bool(data.get("ok")),
            "url": url,
            "response": data,
        }
