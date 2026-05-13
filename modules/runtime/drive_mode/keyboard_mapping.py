from __future__ import annotations
def normalize_key(key: str) -> str:
    if key == " ": return "space"
    value = str(key or "").strip().lower().replace(" ", "")
    return {"arrowup": "w", "arrowdown": "s", "arrowleft": "a", "arrowright": "d", "esc": "escape", "spacebar": "space"}.get(value, value)
def action_from_key_event(key: str) -> str:
    return {"w":"forward","s":"backward","a":"rotate_left","d":"rotate_right","space":"emergency_stop","escape":"exit"}.get(normalize_key(key), "unknown")
def action_from_active_keys(keys) -> str:
    active = {normalize_key(key) for key in keys if normalize_key(key)}
    if "escape" in active: return "exit"
    if "space" in active: return "emergency_stop"
    f,b,l,r = "w" in active, "s" in active, "a" in active, "d" in active
    if f and not b:
        if l and not r: return "forward_left"
        if r and not l: return "forward_right"
        return "forward"
    if b and not f:
        if l and not r: return "backward_left"
        if r and not l: return "backward_right"
        return "backward"
    if l and not r: return "rotate_left"
    if r and not l: return "rotate_right"
    return "stop"
