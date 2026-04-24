extends Node2D

export(int) var particle_count := 1200
export(float) var radius := 250.0
export(float) var noise_strength := 16.0
export(float) var drift_speed := 0.25
export(float) var particle_size := 0.65

var particles := []
var time := 0.0


class Particle:
	var base_position := Vector2.ZERO
	var offset := Vector2.ZERO
	var velocity := Vector2.ZERO
	var depth := 1.0


func _ready() -> void:
	randomize()
	_generate_particles()


func _process(delta: float) -> void:
	time += delta
	_update_particles(delta)
	update()


func _generate_particles() -> void:
	particles.clear()

	for _i in range(particle_count):
		var angle = randf() * PI * 2.0
		var dist = pow(randf(), 0.55) * radius

		var particle = Particle.new()
		particle.base_position = Vector2(cos(angle) * dist, sin(angle) * dist)
		particle.offset = Vector2.ZERO
		particle.velocity = Vector2(rand_range(-1.0, 1.0), rand_range(-1.0, 1.0))
		particle.depth = rand_range(0.55, 1.0)

		particles.append(particle)


func _update_particles(_delta: float) -> void:
	for particle in particles:
		var wave = sin(time * 0.65 + particle.base_position.length() * 0.045)

		var noise = Vector2(
			sin(time * 0.8 + particle.base_position.x * 0.018),
			cos(time * 0.8 + particle.base_position.y * 0.018)
		) * noise_strength * 0.18 * particle.depth

		particle.offset = particle.offset.linear_interpolate(
			noise + Vector2(wave, wave) * 2.2,
			0.045
		)


func _draw() -> void:
	for particle in particles:
		var position = particle.base_position + particle.offset
		var alpha = 0.35 + particle.depth * 0.45
		var size = particle_size * particle.depth

		draw_circle(position, size, Color(0.78, 0.88, 1.0, alpha))