extends Reference

const FULLSCREEN = "FULLSCREEN"
const DOCKED = "DOCKED"


static func is_valid(layout: String) -> bool:
	return layout == FULLSCREEN or layout == DOCKED


static func coerce(layout: String) -> String:
	var normalized = String(layout).strip_edges().to_upper()

	if is_valid(normalized):
		return normalized

	return FULLSCREEN


static func is_docked(layout: String) -> bool:
	return coerce(layout) == DOCKED


static func is_fullscreen(layout: String) -> bool:
	return coerce(layout) == FULLSCREEN
