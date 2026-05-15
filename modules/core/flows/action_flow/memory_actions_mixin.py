from __future__ import annotations

from typing import Any

from modules.runtime.contracts import RouteDecision, RouteKind

from .models import ResolvedAction, SkillRequest


class ActionMemoryActionsMixin:
    def _handle_memory_store(
        self,
        *,
        route: RouteDecision,
        language: str,
        payload: dict[str, Any],
        resolved: ResolvedAction,
        request: SkillRequest | None = None,
    ) -> bool:
        del route, resolved

        guided = bool(payload.get("guided", False))
        person_enrollment = bool(payload.get("person_enrollment", False))
        object_enrollment = bool(payload.get("object_enrollment", False))
        object_hint = str(payload.get("object_hint", "") or "").strip()
        memory_text = self._first_present(payload, "memory_text", "message", "content", "text")
        key, value = self._resolve_memory_store_fields(payload)

        if object_enrollment:
            self.assistant.pending_follow_up = {
                "type": "memory_object_name",
                "language": language,
                "object_hint": object_hint,
            }
            return self.assistant.deliver_text_response(
                self.assistant._localized(
                    language,
                    "Dobrze. Jak mam nazwać ten obiekt?",
                    "Okay. What should I call this object?",
                ),
                language=language,
                route_kind=RouteKind.CONVERSATION,
                source="action_memory_object_name_prompt",
                metadata={
                    "follow_up_type": "memory_object_name",
                    "action": "memory_store",
                    "object_hint": object_hint,
                },
            )

        if person_enrollment:
            self.assistant.pending_follow_up = {
                "type": "memory_person_name",
                "language": language,
            }
            return self.assistant.deliver_text_response(
                self.assistant._localized(
                    language,
                    "Dobrze. Jak mam Cię nazywać?",
                    "Okay. What should I call you?",
                ),
                language=language,
                route_kind=RouteKind.CONVERSATION,
                source="action_memory_person_name_prompt",
                metadata={
                    "follow_up_type": "memory_person_name",
                    "action": "memory_store",
                },
            )

        if guided or (not str(memory_text or "").strip() and (not key or not value)):
            self.assistant.pending_follow_up = {
                "type": "memory_message",
                "language": language,
            }
            return self.assistant.deliver_text_response(
                self.assistant._localized(
                    language,
                    "Jasne. Co mam zapamiętać?",
                    "Sure. What should I remember?",
                ),
                language=language,
                route_kind=RouteKind.CONVERSATION,
                source="action_memory_guided_message_prompt",
                metadata={
                    "follow_up_type": "memory_message",
                    "action": "memory_store",
                },
            )

        if str(memory_text or "").strip():
            outcome = self._get_memory_skill_executor().store_text(
                text=memory_text,
                language=language,
                source="memory_service.store_text",
            )
        else:
            outcome = self._get_memory_skill_executor().store(
                key=key,
                value=value,
                language=language,
            )

        if outcome.status == "unavailable":
            return self._deliver_feature_unavailable(language=language, action="memory_store")

        spec = self._get_memory_response_builder().build_store_response(
            language=language,
            action=request.action if request is not None else "memory_store",
            outcome_status=outcome.status,
            resolved_source="action_memory_store",
            key=str(outcome.data.get("key", key or "")).strip(),
            value=str(outcome.data.get("value", value or "")).strip(),
            metadata=dict(outcome.metadata or {}),
        )
        return self._deliver_action_response_spec(language=language, spec=spec)

    def _handle_memory_recall(
        self,
        *,
        route: RouteDecision,
        language: str,
        payload: dict[str, Any],
        resolved: ResolvedAction,
        request: SkillRequest | None = None,
    ) -> bool:
        del route
        key = self._first_present(payload, "key", "subject", "item", "name", "query")
        effective_language = self._memory_recall_effective_language(key=key, language=language)
        outcome = self._get_memory_skill_executor().recall(key=key, language=effective_language)

        if outcome.status == "unavailable":
            return self._deliver_feature_unavailable(language=effective_language, action="memory_recall")

        found_key = str(outcome.data.get("key", key or "")).strip()
        found_value = str(outcome.data.get("value", "")).strip()
        spec = self._get_memory_response_builder().build_recall_response(
            language=effective_language,
            action=request.action if request is not None else "memory_recall",
            outcome_status=outcome.status,
            resolved_source=resolved.source,
            key=found_key,
            value=found_value,
            metadata=dict(outcome.metadata or {}),
        )
        self._maybe_show_memory_gallery_for_recall(
            key=key,
            value=found_value,
            language=effective_language,
        )
        return self._deliver_action_response_spec(language=effective_language, spec=spec)


    @classmethod
    def _memory_recall_effective_language(cls, *, key: str, language: str) -> str:
        normalized = cls._memory_gallery_normalize_text(key)
        current_language = str(language or "").strip().lower()

        polish_prefixes = (
            "kogo ",
            "jakie ",
            "jaki ",
            "jaka ",
            "gdzie ",
            "czyj ",
            "czyja ",
            "czyje ",
            "co ",
            "pokaz ",
            "pokaż ",
            "przypomnij ",
        )
        english_prefixes = (
            "who ",
            "what ",
            "where ",
            "whose ",
            "show ",
            "list ",
            "tell ",
            "remind ",
        )

        polish_exact = {
            "kogo znasz",
            "kogo z nasz",
            "kogo z nas",
            "kogo znas",
            "kogoznasz",
            "kogo z nasz",
            "kogo z nas",
            "kogo znas",
            "kogoznasz",
            "jakie osoby znasz",
            "jakie obiekty znasz",
            "jakie obiekty z nasz",
            "jakie obiekty z nas",
            "jakie obiekty znas",
            "jakie obiekty z nasz",
            "jakie rzeczy znasz",
            "pokaz kogo znasz",
            "pokaz znane osoby",
            "pokaz obiekty ktore znasz",
            "pokaz zapamietane obiekty",
        }
        english_exact = {
            "who do you know",
            "show known people",
            "what objects do you know",
            "show known objects",
            "show remembered objects",
        }

        if normalized in polish_exact or any(normalized.startswith(prefix) for prefix in polish_prefixes):
            return "pl"
        if normalized in english_exact or any(normalized.startswith(prefix) for prefix in english_prefixes):
            return "en"
        if current_language in {"pl", "en"}:
            return current_language
        return "pl"


    def _maybe_show_memory_gallery_for_recall(
        self,
        *,
        key: str,
        value: str,
        language: str,
    ) -> None:
        gallery_kind = self._memory_gallery_kind_from_query(key)
        if not gallery_kind:
            return

        assistant = getattr(self, "assistant", None)
        memory = getattr(assistant, "memory", None) if assistant is not None else None
        if memory is None:
            return

        items = self._memory_gallery_items(memory=memory, gallery_kind=gallery_kind, language=language)
        if not items:
            return

        visual_shell_lane = self._memory_gallery_visual_shell_lane()
        if visual_shell_lane is None:
            return

        show_memory_gallery = getattr(visual_shell_lane, "show_memory_gallery", None)
        if not callable(show_memory_gallery):
            return

        title, subtitle = self._memory_gallery_titles(gallery_kind=gallery_kind, language=language)

        try:
            handled = bool(
                show_memory_gallery(
                    gallery_kind=gallery_kind,
                    items=items,
                    language=language,
                    title=title,
                    subtitle=subtitle,
                    assistant=assistant,
                )
            )
        except Exception as error:  # pragma: no cover - defensive runtime guard
            logger = getattr(self, "LOGGER", None)
            if logger is not None:
                logger.warning("Visual Shell memory gallery dispatch failed safely: %s", error)
            return

        if assistant is not None:
            assistant._last_memory_gallery_dispatch = {
                "handled": handled,
                "gallery_kind": gallery_kind,
                "item_count": len(items),
                "language": str(language or "").strip().lower(),
                "source": "action_memory_recall",
                "key": str(key or "").strip(),
                "value": str(value or "").strip(),
            }

    @classmethod
    def _memory_gallery_kind_from_query(cls, query: str) -> str:
        normalized = cls._memory_gallery_normalize_text(query)
        people_queries = {
            "kogo znasz",
            "kogo z nasz",
            "kogo z nas",
            "kogo znas",
            "jakie osoby znasz",
            "pokaz kogo znasz",
            "pokaz znane osoby",
            "pokaz osoby ktore znasz",
            "who do you know",
            "who you know",
            "who do you remember",
            "who can you remember",
            "who is in your memory",
            "show known people",
            "show people you know",
            "show remembered people",
            "list known people",
            "list people you know",
            "tell me who you know",
            "what people do you know",
            "which people do you know",
            "known people",
            "jakie osoby pamietasz",
            "kogo pamietasz",
            "pokaz znane osoby",
            "lista osob",
            "lista znanych osob",
            "osoby ktore znasz",
            "znane osoby",
        }
        object_queries = {
            "jakie obiekty znasz",
            "jakie obiektyznaz",
            "jakie obiekty z nasz",
            "jakie rzeczy znasz",
            "jakie przedmioty znasz",
            "jakie obiekty pamietasz",
            "jakie rzeczy pamietasz",
            "jakie przedmioty pamietasz",
            "pokaz obiekty",
            "pokaz obiekty ktore znasz",
            "pokaz zapamietane obiekty",
            "pokaz znane obiekty",
            "what objects do you know",
            "what object do you know",
            "what objects do you need",
            "what object do you need",
            "what objects you know",
            "what object you know",
            "what objects",
            "what object",
            "what objects do you remember",
            "what object do you remember",
            "what items do you know",
            "what item do you know",
            "what items do you remember",
            "what item do you remember",
            "what things do you know",
            "what thing do you know",
            "what things do you remember",
            "what thing do you remember",
            "which objects do you know",
            "which items do you know",
            "which things do you know",
            "what object now",
            "show known objects",
            "show remembered objects",
            "show objects you know",
            "show my objects",
            "show items you know",
            "show known items",
            "show things you know",
            "list objects",
            "list known objects",
            "list my objects",
            "list remembered objects",
            "list items",
            "list known items",
            "list things",
            "known objects",
            "known items",
            "remembered objects",
            "remembered items",
            "objects you know",
            "items you know",
            "things you know",
            "pokaz moje obiekty",
            "pokaz rzeczy ktore znasz",
            "pokaz przedmioty ktore znasz",
            "lista obiektow",
            "lista rzeczy",
            "lista przedmiotow",
            "znane obiekty",
            "znane rzeczy",
            "znane przedmioty",
            "obiekty ktore znasz",
            "rzeczy ktore znasz",
            "przedmioty ktore znasz",
        }
        if normalized in people_queries:
            return "people"
        if normalized in object_queries:
            return "objects"
        return ""

    @staticmethod
    def _memory_gallery_normalize_text(text: str) -> str:
        normalized = str(text or "").strip().lower()
        table = str.maketrans(
            {
                "ą": "a",
                "ć": "c",
                "ę": "e",
                "ł": "l",
                "ń": "n",
                "ó": "o",
                "ś": "s",
                "ź": "z",
                "ż": "z",
            }
        )
        normalized = normalized.translate(table)
        for char in ".,!?:;\"'":
            normalized = normalized.replace(char, " ")
        return " ".join(normalized.split())

    def _memory_gallery_items(
        self,
        *,
        memory: Any,
        gallery_kind: str,
        language: str,
    ) -> list[dict[str, Any]]:
        if gallery_kind == "people":
            entries = self._memory_gallery_call_list(memory, "list_people", language=language)
            return [
                self._memory_gallery_person_item(memory=memory, entry=entry, language=language)
                for entry in entries
                if isinstance(entry, dict)
            ]

        if gallery_kind == "objects":
            entries = self._memory_gallery_call_list(memory, "list_objects", language=language)
            return [
                self._memory_gallery_object_item(memory=memory, entry=entry, language=language)
                for entry in entries
                if isinstance(entry, dict)
            ]

        return []

    @staticmethod
    def _memory_gallery_call_list(memory: Any, method_name: str, *, language: str) -> list[dict[str, Any]]:
        method = getattr(memory, method_name, None)
        if not callable(method):
            return []
        try:
            result = method(language=language)
        except TypeError:
            result = method()
        except Exception:
            return []
        return [dict(item) for item in list(result or []) if isinstance(item, dict)]

    def _memory_gallery_person_item(
        self,
        *,
        memory: Any,
        entry: dict[str, Any],
        language: str,
    ) -> dict[str, Any]:
        display_name = self._memory_gallery_display_name(entry)
        assets = self._memory_gallery_assets(
            memory=memory,
            method_name="list_person_face_assets",
            display_name=display_name,
            language=language,
        )
        image_path = self._memory_gallery_first_existing_asset_path(assets)
        details = self._memory_gallery_detail_rows(
            entry=entry,
            assets=assets,
            gallery_kind="person",
            language=language,
        )
        return {
            "id": str(entry.get("id", "") or ""),
            "display_name": display_name,
            "caption": display_name,
            "kind": "person",
            "aliases": self._memory_gallery_aliases(entry),
            "asset_count": len(assets),
            "image_path": image_path,
            "details": details,
        }

    def _memory_gallery_object_item(
        self,
        *,
        memory: Any,
        entry: dict[str, Any],
        language: str,
    ) -> dict[str, Any]:
        display_name = self._memory_gallery_display_name(entry)
        assets = self._memory_gallery_assets(
            memory=memory,
            method_name="list_object_image_assets",
            display_name=display_name,
            language=language,
        )
        image_path = self._memory_gallery_first_existing_asset_path(assets)
        details = self._memory_gallery_detail_rows(
            entry=entry,
            assets=assets,
            gallery_kind="object",
            language=language,
        )
        return {
            "id": str(entry.get("id", "") or ""),
            "display_name": display_name,
            "caption": display_name,
            "kind": "object",
            "aliases": self._memory_gallery_aliases(entry),
            "asset_count": len(assets),
            "image_path": image_path,
            "details": details,
        }

    @staticmethod
    def _memory_gallery_aliases(entry: dict[str, Any]) -> list[str]:
        aliases = entry.get("aliases", [])
        if not isinstance(aliases, (list, tuple)):
            return []
        return [str(alias).strip() for alias in aliases if str(alias).strip()]

    @staticmethod
    def _memory_gallery_assets(
        *,
        memory: Any,
        method_name: str,
        display_name: str,
        language: str,
    ) -> list[dict[str, Any]]:
        method = getattr(memory, method_name, None)
        if not callable(method):
            return []
        try:
            result = method(display_name=display_name, language=language)
        except TypeError:
            result = method(display_name=display_name)
        except Exception:
            return []
        return [dict(asset) for asset in list(result or []) if isinstance(asset, dict)]

    @staticmethod
    def _memory_gallery_first_existing_asset_path(assets: list[dict[str, Any]]) -> str:
        from pathlib import Path as _Path

        fallback_path = ""
        for asset in assets:
            path_text = str(asset.get("path", "") or "").strip()
            if not path_text:
                continue
            path = _Path(path_text)
            resolved = path if path.is_absolute() else (_Path.cwd() / path)
            if resolved.exists():
                return str(resolved.resolve())
            if not fallback_path:
                fallback_path = str(resolved)
        return fallback_path

    def _memory_gallery_detail_rows(
        self,
        *,
        entry: dict[str, Any],
        assets: list[dict[str, Any]],
        gallery_kind: str,
        language: str,
    ) -> list[dict[str, str]]:
        is_polish = str(language or "").strip().lower().startswith("pl")
        rows: list[dict[str, str]] = []

        display_name = self._memory_gallery_display_name(entry)
        aliases = self._memory_gallery_aliases(entry)
        metadata = entry.get("metadata", {})
        if not isinstance(metadata, dict):
            metadata = {}

        if gallery_kind == "person":
            self._memory_gallery_append_detail(rows, "Typ" if is_polish else "Type", "Osoba" if is_polish else "Person")
        else:
            self._memory_gallery_append_detail(rows, "Typ" if is_polish else "Type", "Obiekt" if is_polish else "Object")

        self._memory_gallery_append_detail(rows, "Nazwa" if is_polish else "Name", display_name)
        if aliases:
            self._memory_gallery_append_detail(rows, "Aliasy" if is_polish else "Aliases", ", ".join(aliases))
        self._memory_gallery_append_detail(rows, "Zdjęcia" if is_polish else "Photos", str(len(assets)))

        owner = metadata.get("owner") or metadata.get("owned_by") or metadata.get("object_owner")
        if owner:
            self._memory_gallery_append_detail(rows, "Właściciel" if is_polish else "Owner", str(owner))

        person_scope = metadata.get("person_scope") or metadata.get("relationship")
        if person_scope:
            self._memory_gallery_append_detail(rows, "Relacja" if is_polish else "Relationship", str(person_scope))

        for key, value in metadata.items():
            if len(rows) >= 18:
                break
            if key in {
                "source_record_id",
                "source",
                "asset_role",
                "person_faces_dir",
                "object_assets_dir",
                "has_face_asset",
                "has_object_asset",
            }:
                continue
            if key in {"owner", "owned_by", "object_owner", "person_scope", "relationship"}:
                continue
            if isinstance(value, (dict, list, tuple, set)):
                continue
            value_text = str(value).strip()
            if not value_text:
                continue
            self._memory_gallery_append_detail(
                rows,
                self._memory_gallery_human_label(str(key), language=language),
                value_text,
            )

        if not rows:
            self._memory_gallery_append_detail(rows, "Informacje" if is_polish else "Info", display_name)

        return rows

    @staticmethod
    def _memory_gallery_append_detail(rows: list[dict[str, str]], label: str, value: str) -> None:
        clean_label = str(label or "").strip()
        clean_value = str(value or "").strip()
        if not clean_label or not clean_value:
            return
        rows.append({"label": clean_label, "value": clean_value})

    @staticmethod
    def _memory_gallery_human_label(key: str, *, language: str) -> str:
        normalized = str(key or "").strip().replace("_", " ")
        if not normalized:
            return "Info"
        known_pl = {
            "display name": "Nazwa",
            "object display name": "Nazwa obiektu",
            "normalized from asr": "Poprawione z ASR",
            "asr correction": "Korekta ASR",
            "language": "Język",
            "confidence": "Pewność",
            "created at": "Utworzono",
            "updated at": "Zaktualizowano",
        }
        if str(language or "").strip().lower().startswith("pl"):
            return known_pl.get(normalized.lower(), normalized.capitalize())
        return normalized.capitalize()


    @staticmethod
    def _memory_gallery_display_name(entry: dict[str, Any]) -> str:
        for key in ("display_name", "name", "full_name", "title", "id"):
            value = str(entry.get(key, "") or "").strip()
            if value:
                return value
        return "Unknown"

    @staticmethod
    def _memory_gallery_first_asset_path(
        *,
        memory: Any,
        method_name: str,
        display_name: str,
        language: str,
    ) -> str:
        method = getattr(memory, method_name, None)
        if not callable(method):
            return ""
        try:
            assets = method(display_name=display_name, language=language)
        except TypeError:
            assets = method(display_name=display_name)
        except Exception:
            return ""

        fallback_path = ""
        for asset in list(assets or []):
            if not isinstance(asset, dict):
                continue
            path_text = str(asset.get("path", "") or "").strip()
            if not path_text:
                continue
            from pathlib import Path as _Path

            path = _Path(path_text)
            resolved = path if path.is_absolute() else (_Path.cwd() / path)
            if resolved.exists():
                return str(resolved.resolve())
            if not fallback_path:
                fallback_path = str(resolved)
        return fallback_path

    @staticmethod
    def _memory_gallery_titles(*, gallery_kind: str, language: str) -> tuple[str, str]:
        normalized_language = str(language or "").strip().lower()
        is_polish = normalized_language.startswith("pl")
        if gallery_kind == "people":
            if is_polish:
                return "Znane osoby", "Osoby zapisane w pamięci NeXa."
            return "Known people", "People saved in NeXa memory."
        if is_polish:
            return "Znane obiekty", "Obiekty zapisane w pamięci NeXa."
        return "Known objects", "Objects saved in NeXa memory."

    def _memory_gallery_visual_shell_lane(self) -> Any | None:
        assistant = getattr(self, "assistant", None)
        if assistant is None:
            return None

        fast_command_lane = getattr(assistant, "fast_command_lane", None)
        visual_shell_lane = getattr(fast_command_lane, "visual_shell_lane", None)
        if visual_shell_lane is not None:
            return visual_shell_lane

        return getattr(assistant, "visual_shell_lane", None)

    def _handle_memory_forget(
        self,
        *,
        route: RouteDecision,
        language: str,
        payload: dict[str, Any],
        resolved: ResolvedAction,
        request: SkillRequest | None = None,
    ) -> bool:
        del route
        key = self._first_present(payload, "key", "subject", "item", "name", "query")
        outcome = self._get_memory_skill_executor().forget(key=key, language=language)

        if outcome.status == "unavailable":
            return self._deliver_feature_unavailable(language=language, action="memory_forget")

        removed_key = str(outcome.data.get("key", key or "")).strip()
        spec = self._get_memory_response_builder().build_forget_response(
            language=language,
            action=request.action if request is not None else "memory_forget",
            outcome_status=outcome.status,
            resolved_source=resolved.source,
            key=removed_key,
            metadata=dict(outcome.metadata or {}),
        )
        return self._deliver_action_response_spec(language=language, spec=spec)

    def _handle_memory_list(
        self,
        *,
        route: RouteDecision,
        language: str,
        payload: dict[str, Any],
        resolved: ResolvedAction,
        request: SkillRequest | None = None,
    ) -> bool:
        del route, payload
        outcome = self._get_memory_skill_executor().list_items(language=language)
        if outcome.status == "unavailable":
            return self._deliver_feature_unavailable(language=language, action="memory_list")

        items = dict(outcome.data.get("items", {}) or {})
        count = int(outcome.data.get("count", len(items)) or 0)
        spec = self._get_memory_response_builder().build_list_response(
            language=language,
            action=request.action if request is not None else "memory_list",
            resolved_source=resolved.source,
            items=items,
            count=count,
            metadata=dict(outcome.metadata or {}),
        )
        return self._deliver_action_response_spec(language=language, spec=spec)

    def _handle_memory_clear(
        self,
        *,
        route: RouteDecision,
        language: str,
        payload: dict[str, Any],
        resolved: ResolvedAction,
        request: SkillRequest | None = None,
    ) -> bool:
        del route, payload
        self.assistant.pending_follow_up = {
            "type": "confirm_memory_clear",
            "language": language,
        }
        spec = self._get_memory_response_builder().build_clear_confirmation(
            language=language,
            action=request.action if request is not None else "memory_clear",
            resolved_source=resolved.source,
        )
        return self._deliver_action_follow_up_prompt_spec(language=language, spec=spec)

    @staticmethod
    def _route_kind_conversation():
        from modules.runtime.contracts import RouteKind

        return RouteKind.CONVERSATION
