extends Reference

const DOT_SPACING = 9.5
const LETTER_SPACING = 5.0
const PARTICLES_PER_DOT = 8

const DOT_OFFSETS = [
	Vector2(-2.4, -2.4),
	Vector2(0.0, -2.9),
	Vector2(2.4, -2.4),
	Vector2(-2.9, 0.0),
	Vector2(0.0, 0.0),
	Vector2(2.9, 0.0),
	Vector2(-2.4, 2.4),
	Vector2(2.4, 2.4),
]

const GLYPHS = {
	"0": [
		"01110",
		"10001",
		"10011",
		"10101",
		"11001",
		"10001",
		"01110",
	],
	"1": [
		"00100",
		"01100",
		"00100",
		"00100",
		"00100",
		"00100",
		"01110",
	],
	"2": [
		"01110",
		"10001",
		"00001",
		"00010",
		"00100",
		"01000",
		"11111",
	],
	"3": [
		"11110",
		"00001",
		"00001",
		"01110",
		"00001",
		"00001",
		"11110",
	],
	"4": [
		"00010",
		"00110",
		"01010",
		"10010",
		"11111",
		"00010",
		"00010",
	],
	"5": [
		"11111",
		"10000",
		"10000",
		"11110",
		"00001",
		"00001",
		"11110",
	],
	"6": [
		"01110",
		"10000",
		"10000",
		"11110",
		"10001",
		"10001",
		"01110",
	],
	"7": [
		"11111",
		"00001",
		"00010",
		"00100",
		"01000",
		"01000",
		"01000",
	],
	"8": [
		"01110",
		"10001",
		"10001",
		"01110",
		"10001",
		"10001",
		"01110",
	],
	"9": [
		"01110",
		"10001",
		"10001",
		"01111",
		"00001",
		"00001",
		"01110",
	],
	"%": [
		"11001",
		"11010",
		"00100",
		"01000",
		"10110",
		"10011",
		"00000",
	],
	"°": [
		"0110",
		"1001",
		"1001",
		"0110",
		"0000",
		"0000",
		"0000",
	],
	" ": [
		"000",
		"000",
		"000",
		"000",
		"000",
		"000",
		"000",
	],
}


static func assign_text_targets(particles: Array, text: String) -> void:
	for particle in particles:
		particle.glyph_position = particle.base_position
		particle.is_metric_particle = false

	var targets = _build_text_targets(text)
	if targets.size() == 0:
		return

	var assignable_particles = []
	for particle in particles:
		if particle.formation_strength >= 0.36:
			assignable_particles.append(particle)

	var count = min(assignable_particles.size(), targets.size())

	for index in range(count):
		assignable_particles[index].glyph_position = targets[index]
		assignable_particles[index].is_metric_particle = true


static func _build_text_targets(text: String) -> Array:
	var positions = []
	var cursor_x = 0.0

	for index in range(text.length()):
		var character = text[index]
		var pattern = _glyph_pattern(character)

		var rows = pattern.size()
		var cols = pattern[0].length()

		for row in range(rows):
			var line = pattern[row]

			for col in range(cols):
				if line[col] != "1":
					continue

				var cell_center = Vector2(
					cursor_x + float(col) * DOT_SPACING,
					float(row) * DOT_SPACING
				)

				for dot_index in range(PARTICLES_PER_DOT):
					positions.append(cell_center + DOT_OFFSETS[dot_index])

		cursor_x += float(cols) * DOT_SPACING + LETTER_SPACING

	if positions.size() == 0:
		return positions

	var min_x = positions[0].x
	var max_x = positions[0].x
	var min_y = positions[0].y
	var max_y = positions[0].y

	for position in positions:
		min_x = min(min_x, position.x)
		max_x = max(max_x, position.x)
		min_y = min(min_y, position.y)
		max_y = max(max_y, position.y)

	var center = Vector2(
		(min_x + max_x) * 0.5,
		(min_y + max_y) * 0.5
	)

	for target_index in range(positions.size()):
		positions[target_index] -= center

	return positions


static func _glyph_pattern(character: String) -> Array:
	if GLYPHS.has(character):
		return GLYPHS[character]

	return GLYPHS[" "]
