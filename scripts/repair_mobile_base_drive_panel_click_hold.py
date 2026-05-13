from __future__ import annotations

import re
from pathlib import Path

TARGET = Path("scripts/mobile_base_drive_mode.py")
TEST_TARGET = Path("tests/runtime/drive_mode/test_mobile_base_drive_mode_script.py")

POINTER_MARKER = "// NeXa click-hold drive buttons patch"

POINTER_JS = r'''
// NeXa click-hold drive buttons patch
function normalizePanelDriveKey(key) {
  if (!key) return null;
  const lower = key.length === 1 ? key.toLowerCase() : key;
  if (lower === 'arrowup') return 'w';
  if (lower === 'arrowleft') return 'a';
  if (lower === 'arrowdown') return 's';
  if (lower === 'arrowright') return 'd';
  if (['w', 'a', 's', 'd'].includes(lower)) return lower;
  return null;
}
async function pressPanelDriveKey(key) {
  const mapped = normalizePanelDriveKey(key);
  if (!mapped) return;
  const wasPressed = pressed.has(mapped);
  pressed.add(mapped);
  mark(mapped, true);
  if (!wasPressed) {
    await sendState();
  }
}
async function releasePanelDriveKey(key) {
  const mapped = normalizePanelDriveKey(key);
  if (!mapped) return;
  if (!pressed.has(mapped)) return;
  pressed.delete(mapped);
  mark(mapped, false);
  await sendState();
}
for (const node of document.querySelectorAll('.key[data-key]')) {
  const key = node.dataset.key;
  const start = async (event) => {
    event.preventDefault();
    if (event.pointerId !== undefined) node.setPointerCapture?.(event.pointerId);
    await pressPanelDriveKey(key);
  };
  const stop = async (event) => {
    event.preventDefault();
    if (event.pointerId !== undefined) node.releasePointerCapture?.(event.pointerId);
    await releasePanelDriveKey(key);
  };
  node.addEventListener('pointerdown', start);
  node.addEventListener('pointerup', stop);
  node.addEventListener('pointercancel', stop);
  node.addEventListener('pointerleave', async (event) => {
    if (pressed.has(key)) await stop(event);
  });
  node.addEventListener('mousedown', start);
  node.addEventListener('mouseup', stop);
  node.addEventListener('mouseleave', async (event) => {
    if (pressed.has(key)) await stop(event);
  });
  node.addEventListener('touchstart', start, {passive: false});
  node.addEventListener('touchend', stop, {passive: false});
  node.addEventListener('touchcancel', stop, {passive: false});
  node.addEventListener('contextmenu', (event) => event.preventDefault());
}
'''

TEST_MARKER = "test_drive_mode_web_panel_wires_click_hold_buttons_after_repair"

TEST_SNIPPET = r'''


def test_drive_mode_web_panel_wires_click_hold_buttons_after_repair() -> None:
    from scripts.mobile_base_drive_mode import HTML_PAGE

    assert "NeXa click-hold drive buttons patch" in HTML_PAGE
    assert "pointerdown" in HTML_PAGE
    assert "pointerup" in HTML_PAGE
    assert "touchstart" in HTML_PAGE
    assert "pressPanelDriveKey" in HTML_PAGE
    assert "releasePanelDriveKey" in HTML_PAGE
    assert "cursor: pointer" in HTML_PAGE
    assert "touch-action: none" in HTML_PAGE
'''


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if old not in text:
        raise SystemExit(f"[REPAIR ERROR] Could not find target block: {label}")
    return text.replace(old, new, 1)


def patch_panel() -> None:
    text = TARGET.read_text(encoding="utf-8")
    original = text

    if "touch-action: none" not in text:
        pattern = re.compile(r"(\.key\s*\{[^}]*user-select:\s*none;)(\s*\})", re.DOTALL)
        text, count = pattern.subn(r"\1 cursor: pointer; touch-action: none; -webkit-tap-highlight-color: transparent;\2", text, count=1)
        if count != 1:
            raise SystemExit("[REPAIR ERROR] Could not update .key CSS block.")

    if "Click/hold W/A/S/D buttons" not in text:
        text = text.replace(
            "Drive panel loaded. Keep wheels raised for hardware tests.",
            "Drive panel loaded. Click/hold W/A/S/D buttons or use keyboard. Keep wheels raised for hardware tests.",
        )
        text = text.replace(
            "Drive panel loaded. Use W/A/S/D, arrows, Space, or Esc.",
            "Drive panel loaded. Click/hold W/A/S/D buttons or use keyboard. Keep wheels raised for hardware tests.",
        )

    if "hold the on-screen buttons" not in text:
        text = text.replace(
            "Use <code>W/A/S/D</code> or arrow keys. Release the key to STOP.",
            "Use <code>W/A/S/D</code>, arrow keys, or hold the on-screen buttons. Release the key/button to STOP.",
        )

    if POINTER_MARKER not in text:
        insertion_points = [
            "setInterval(() => {",
            "window.addEventListener('blur'",
            "append('Drive panel loaded.",
        ]
        for marker in insertion_points:
            idx = text.find(marker)
            if idx != -1:
                text = text[:idx] + POINTER_JS + "\n" + text[idx:]
                break
        else:
            raise SystemExit("[REPAIR ERROR] Could not find a safe JavaScript insertion point.")

    if text != original:
        TARGET.write_text(text, encoding="utf-8")
        print(f"[REPAIR] patched {TARGET}")
    else:
        print(f"[REPAIR] {TARGET} already patched")


def patch_tests() -> None:
    if not TEST_TARGET.exists():
        print(f"[REPAIR] skipped missing {TEST_TARGET}")
        return
    text = TEST_TARGET.read_text(encoding="utf-8")
    if TEST_MARKER in text:
        print(f"[REPAIR] {TEST_TARGET} already has click-hold test")
        return
    TEST_TARGET.write_text(text.rstrip() + TEST_SNIPPET + "\n", encoding="utf-8")
    print(f"[REPAIR] patched {TEST_TARGET}")


def import_check() -> None:
    import importlib

    module = importlib.import_module("scripts.mobile_base_drive_mode")
    html = getattr(module, "HTML_PAGE")
    required = [
        "NeXa click-hold drive buttons patch",
        "pointerdown",
        "pointerup",
        "touchstart",
        "pressPanelDriveKey",
        "releasePanelDriveKey",
        "cursor: pointer",
        "touch-action: none",
    ]
    missing = [item for item in required if item not in html]
    if missing:
        raise SystemExit(f"[REPAIR ERROR] HTML_PAGE still missing: {missing}")
    print("[REPAIR OK] Drive panel click-hold controls are wired.")


def main() -> None:
    if not TARGET.exists():
        raise SystemExit(f"[REPAIR ERROR] Missing {TARGET}")
    patch_panel()
    patch_tests()
    import_check()


if __name__ == "__main__":
    main()
