extends Node2D
# NEXA Visual Shell - production particle cloud renderer (post-migration).
#
# Migration source: preview/idle_nebula_preview.gd (V13).
# Public API preserved verbatim:
#   set_visual_state(new_state: String) -> void
#   set_shell_compact_mode(enabled: bool) -> void
#   set_temperature_metric(value_c: int) -> void
#   set_battery_metric(percent: int) -> void
# Public API additions (date/time glyphs from migration):
#   set_date_metric(text: String) -> void
#   set_time_metric(text: String) -> void
#
# All existing VisualState values from contracts/visual_state.py remain
# accepted by set_visual_state() to preserve Voice Engine v2 contract.
# States not yet renderered with custom motion fall back to nebula idle.

const VisualStates = preload("res://scripts/state/visual_states.gd")

# ---- Constants ----
const PARTICLE_COUNT = 6000
const FACE_PARTICLE_TARGET = 4500
const TEXTURE_SIZE = 64
const NEBULA_RADIUS = 480.0
const SAMPLING_OVERSAMPLE = 8
const WARM_ACCENT_FRACTION = 0.04

const COLOR_WHITE_COOL    = Color(0.82, 0.86, 0.98)
const COLOR_WHITE_NEUTRAL = Color(0.92, 0.94, 1.00)
const COLOR_WHITE_WARM    = Color(0.98, 0.96, 0.92)
const COLOR_WARM_DEEP   = Color(0.85, 0.45, 0.20)
const COLOR_WARM_BRIGHT = Color(1.00, 0.72, 0.40)
const BACKGROUND_COLOR  = Color(0.022, 0.020, 0.038)
const GLYPH_NEUTRAL_COLOR = Color(0.95, 0.93, 0.88)

const FACE_EMERGE_DURATION   = 1.6
const FACE_HOLD_DURATION     = 6.0
const FACE_DISSOLVE_DURATION = 1.6
const GLYPH_HOLD_DURATION    = 5.0

const FACE_W = 235.0
const FACE_H = 305.0
const FACE_Y_OFFSET = -8.0

const FACE_STATE_NONE     = 0
const FACE_STATE_EMERGE   = 1
const FACE_STATE_HOLD     = 2
const FACE_STATE_DISSOLVE = 3

const GLYPH_KIND_NONE        = 0
const GLYPH_KIND_TEMPERATURE = 1
const GLYPH_KIND_BATTERY     = 2
const GLYPH_KIND_DATE        = 3
const GLYPH_KIND_TIME        = 4

const GLYPH_CHAR_W = 95.0
const GLYPH_CHAR_H = 165.0
const GLYPH_CHAR_SPACING = 22.0
const GLYPH_STROKE = 18.0

const SEG_DIGITS = {
    "0": [true,  true,  true,  true,  true,  true,  false],
    "1": [false, true,  true,  false, false, false, false],
    "2": [true,  true,  false, true,  true,  false, true],
    "3": [true,  true,  true,  true,  false, false, true],
    "4": [false, true,  true,  false, false, true,  true],
    "5": [true,  false, true,  true,  false, true,  true],
    "6": [true,  false, true,  true,  true,  true,  true],
    "7": [true,  true,  true,  false, false, false, false],
    "8": [true,  true,  true,  true,  true,  true,  true],
    "9": [true,  true,  true,  true,  false, true,  true],
}

# ---- Exports (compat with prior tscn) ----
export(int) var particle_count = PARTICLE_COUNT
export(float) var radius = NEBULA_RADIUS
export(float) var particle_size = 0.88
export(int) var target_update_fps = 24

# ---- Runtime state ----
var multimesh: MultiMesh
var multimesh_instance: MultiMeshInstance2D
var noise: OpenSimplexNoise
var face_noise: OpenSimplexNoise

var particle_phases := []
var particle_base_positions := []
var particle_face_positions := []
var particle_face_alphas := []
var particle_face_sizes := []
var particle_face_active := []
var particle_face_jitter_seeds := []
var particle_glyph_positions := []
var particle_glyph_alphas := []
var particle_glyph_active := []
var particle_base_sizes := []
var particle_base_alphas := []
var particle_base_colors := []

var time := 0.0
var visual_state: String = VisualStates.IDLE_PARTICLE_CLOUD
var shell_compact_mode: bool = false

var face_state: int = FACE_STATE_NONE
var face_state_age: float = 0.0
var face_blend: float = 0.0

var glyph_kind: int = GLYPH_KIND_NONE
var glyph_state: int = FACE_STATE_NONE
var glyph_state_age: float = 0.0
var glyph_blend: float = 0.0
var glyph_text: String = ""
var glyph_color := Color(1, 1, 1, 1)
var glyph_temperature_c: int = 58
var glyph_battery_percent: int = 82

var visual_scale: float = 1.0
var render_scale: Vector2 = Vector2(1.0, 1.0)
const COMPACT_FIELD_X_FILL = 1.20
const COMPACT_FIELD_Y_FILL = 1.18
const COMPACT_CORNER_X_FILL = 0.46
const COMPACT_CORNER_Y_FILL = 0.52
const COMPACT_FIELD_GLYPH_PROTECTION_THRESHOLD = 0.35
const ORGANIC_FIELD_X_SPREAD = 1.10
const ORGANIC_FIELD_Y_SPREAD = 1.00
const ORGANIC_FIELD_WARP_X = 20.0
const ORGANIC_FIELD_WARP_Y = 12.0
const ORGANIC_DRIFT_X_PRIMARY = 14.0
const ORGANIC_DRIFT_X_SECONDARY = 8.0
const ORGANIC_DRIFT_Y_PRIMARY = 12.0
const ORGANIC_DRIFT_Y_SECONDARY = 7.0


func _ready() -> void:
    randomize()
    _setup_noise()
    var texture := _build_soft_particle_texture()
    _setup_multimesh(texture)
    _seed_particles()


func _process(delta: float) -> void:
    time += delta
    _update_face_state(delta)
    _update_glyph_state(delta)
    _update_shell_transform(delta)
    _update_particles()


func _draw() -> void:
    var viewport := get_viewport_rect().size
    draw_rect(Rect2(-viewport * 0.5, viewport), BACKGROUND_COLOR)


# ============================================================================
# PUBLIC API (called from main_shell.gd / runtime)
# ============================================================================

func set_visual_state(new_state: String) -> void:
    var coerced: String = VisualStates.coerce_state(new_state)

    # Desktop layout states are handled by main_shell.gd, not here.
    if coerced == VisualStates.DESKTOP_DOCKED \
            or coerced == VisualStates.DESKTOP_RETURNING \
            or coerced == VisualStates.DESKTOP_HIDDEN:
        return

    var previous: String = visual_state
    visual_state = coerced

    # Trigger face emergence on FACE_CONTOUR / SHOW_SELF_EYES
    if (coerced == VisualStates.FACE_CONTOUR or coerced == VisualStates.SHOW_SELF_EYES) \
            and previous != coerced:
        _trigger_face()
    elif (previous == VisualStates.FACE_CONTOUR or previous == VisualStates.SHOW_SELF_EYES) \
            and coerced != VisualStates.FACE_CONTOUR \
            and coerced != VisualStates.SHOW_SELF_EYES:
        _force_face_dissolve()

    # Trigger glyph on TEMPERATURE_GLYPH / BATTERY_GLYPH / DATE_GLYPH / TIME_GLYPH
    if coerced == VisualStates.TEMPERATURE_GLYPH and previous != coerced:
        _trigger_glyph(GLYPH_KIND_TEMPERATURE)
    elif coerced == VisualStates.BATTERY_GLYPH and previous != coerced:
        _trigger_glyph(GLYPH_KIND_BATTERY)
    elif _state_is_glyph(previous) and not _state_is_glyph(coerced):
        _force_glyph_dissolve()


func set_shell_compact_mode(enabled: bool) -> void:
    shell_compact_mode = enabled


func set_temperature_metric(value_c: int) -> void:
    glyph_temperature_c = value_c
    if glyph_kind == GLYPH_KIND_TEMPERATURE:
        _refresh_glyph_value()
    else:
        _trigger_glyph(GLYPH_KIND_TEMPERATURE)


func set_battery_metric(percent: int) -> void:
    glyph_battery_percent = int(clamp(percent, 0, 100))
    if glyph_kind == GLYPH_KIND_BATTERY:
        _refresh_glyph_value()
    else:
        _trigger_glyph(GLYPH_KIND_BATTERY)


func set_date_metric(text: String) -> void:
    # Called by main_shell from SHOW_DATE TCP command; text already formatted
    # as DD.MM in runtime, we just bake it.
    glyph_text = text if text != "" else _format_local_date()
    glyph_color = GLYPH_NEUTRAL_COLOR
    glyph_kind = GLYPH_KIND_DATE
    _bake_glyph_targets(glyph_text, glyph_color)
    glyph_state = FACE_STATE_EMERGE
    glyph_state_age = 0.0


func set_time_metric(text: String) -> void:
    glyph_text = text if text != "" else _format_local_time()
    glyph_color = GLYPH_NEUTRAL_COLOR
    glyph_kind = GLYPH_KIND_TIME
    _bake_glyph_targets(glyph_text, glyph_color)
    glyph_state = FACE_STATE_EMERGE
    glyph_state_age = 0.0


# ============================================================================
# SETUP
# ============================================================================

func _setup_noise() -> void:
    noise = OpenSimplexNoise.new()
    noise.seed = randi()
    noise.octaves = 4
    noise.period = 240.0
    noise.persistence = 0.55
    noise.lacunarity = 2.0

    face_noise = OpenSimplexNoise.new()
    face_noise.seed = randi()
    face_noise.octaves = 3
    face_noise.period = 70.0
    face_noise.persistence = 0.5
    face_noise.lacunarity = 2.0


func _build_soft_particle_texture() -> ImageTexture:
    var image := Image.new()
    image.create(TEXTURE_SIZE, TEXTURE_SIZE, false, Image.FORMAT_RGBA8)
    image.lock()
    var center := Vector2(TEXTURE_SIZE, TEXTURE_SIZE) * 0.5
    var max_radius: float = TEXTURE_SIZE * 0.5
    for x in range(TEXTURE_SIZE):
        for y in range(TEXTURE_SIZE):
            var d_norm: float = Vector2(x, y).distance_to(center) / max_radius
            var alpha: float = 0.0
            if d_norm <= 1.0:
                alpha = exp(-d_norm * d_norm * 5.5)
            image.set_pixel(x, y, Color(1, 1, 1, alpha))
    image.unlock()
    var texture := ImageTexture.new()
    texture.create_from_image(image, Texture.FLAG_FILTER | Texture.FLAG_MIPMAPS)
    return texture


func _setup_multimesh(texture: ImageTexture) -> void:
    multimesh = MultiMesh.new()
    multimesh.transform_format = MultiMesh.TRANSFORM_2D
    multimesh.color_format = MultiMesh.COLOR_FLOAT
    multimesh.instance_count = PARTICLE_COUNT
    var quad := QuadMesh.new()
    quad.size = Vector2(8, 8)
    multimesh.mesh = quad
    multimesh_instance = MultiMeshInstance2D.new()
    multimesh_instance.multimesh = multimesh
    multimesh_instance.texture = texture
    var material := CanvasItemMaterial.new()
    material.blend_mode = CanvasItemMaterial.BLEND_MODE_ADD
    multimesh_instance.material = material
    add_child(multimesh_instance)


func _pick_cosmic_white() -> Color:
    var roll: float = randf()
    var primary: Color
    var secondary: Color
    if roll < 0.35:
        primary = COLOR_WHITE_COOL
        secondary = COLOR_WHITE_NEUTRAL
    elif roll < 0.80:
        primary = COLOR_WHITE_NEUTRAL
        if randf() < 0.5:
            secondary = COLOR_WHITE_COOL
        else:
            secondary = COLOR_WHITE_WARM
    else:
        primary = COLOR_WHITE_WARM
        secondary = COLOR_WHITE_NEUTRAL
    return primary.linear_interpolate(secondary, randf() * 0.4)


func _seed_particles() -> void:
    particle_phases.resize(PARTICLE_COUNT)
    particle_base_positions.resize(PARTICLE_COUNT)
    particle_face_positions.resize(PARTICLE_COUNT)
    particle_face_alphas.resize(PARTICLE_COUNT)
    particle_face_sizes.resize(PARTICLE_COUNT)
    particle_face_active.resize(PARTICLE_COUNT)
    particle_face_jitter_seeds.resize(PARTICLE_COUNT)
    particle_glyph_positions.resize(PARTICLE_COUNT)
    particle_glyph_alphas.resize(PARTICLE_COUNT)
    particle_glyph_active.resize(PARTICLE_COUNT)
    particle_base_sizes.resize(PARTICLE_COUNT)
    particle_base_alphas.resize(PARTICLE_COUNT)
    particle_base_colors.resize(PARTICLE_COUNT)

    for i in range(PARTICLE_COUNT):
        particle_face_jitter_seeds[i] = randf() * 1000.0
        particle_glyph_positions[i] = Vector2.ZERO
        particle_glyph_alphas[i] = 0.0
        particle_glyph_active[i] = false

    var accepted := 0
    var attempts := 0
    var max_attempts: int = PARTICLE_COUNT * SAMPLING_OVERSAMPLE

    while accepted < PARTICLE_COUNT and attempts < max_attempts:
        attempts += 1
        var angle: float = randf() * TAU
        var r_norm: float = pow(randf(), 0.55)
        var radius_x: float = NEBULA_RADIUS * 1.45
        var radius_y: float = NEBULA_RADIUS * 1.05
        var pos := Vector2(cos(angle) * radius_x * r_norm, sin(angle) * radius_y * r_norm)
        pos += Vector2(-NEBULA_RADIUS * 0.08, NEBULA_RADIUS * 0.03)
        var density: float = _sample_density(pos)
        if density < randf() * 0.85:
            continue

        var is_warm: bool = randf() < WARM_ACCENT_FRACTION
        var color: Color
        var base_alpha: float
        if is_warm:
            var warm_t: float = randf()
            color = COLOR_WARM_DEEP.linear_interpolate(COLOR_WARM_BRIGHT, warm_t)
            base_alpha = lerp(0.50, 0.78, warm_t)
        else:
            color = _pick_cosmic_white()
            base_alpha = lerp(0.32, 0.72, density)

        var size_factor: float
        var roll: float = randf()
        if roll < 0.78:
            size_factor = lerp(0.22, 0.60, randf())
        elif roll < 0.95:
            size_factor = lerp(0.60, 1.20, randf())
        else:
            size_factor = lerp(1.20, 2.40, randf())
        size_factor *= lerp(0.85, 1.25, density)
        if is_warm:
            size_factor *= 0.85

        particle_base_positions[accepted] = pos
        particle_phases[accepted] = randf() * TAU
        particle_base_sizes[accepted] = size_factor
        particle_base_alphas[accepted] = base_alpha
        particle_base_colors[accepted] = color
        accepted += 1

    while accepted < PARTICLE_COUNT:
        var angle: float = randf() * TAU
        particle_base_positions[accepted] = Vector2(cos(angle), sin(angle)) * NEBULA_RADIUS * 1.5
        particle_phases[accepted] = randf() * TAU
        particle_base_sizes[accepted] = 0.30
        particle_base_alphas[accepted] = 0.18
        particle_base_colors[accepted] = COLOR_WHITE_NEUTRAL
        accepted += 1

    _bake_face_targets()


func _sample_density(pos: Vector2) -> float:
    var n1: float = noise.get_noise_2d(pos.x * 0.010, pos.y * 0.010)
    var n2: float = noise.get_noise_2d(pos.x * 0.038, pos.y * 0.038)
    var combined: float = (n1 * 0.65 + n2 * 0.35 + 1.0) * 0.5
    var dist_norm: float = pos.length() / (NEBULA_RADIUS * 1.4)
    var falloff: float = pow(max(0.0, 1.0 - dist_norm), 0.50)
    return clamp(combined * falloff, 0.0, 1.0)


func _gauss(d: float, sigma: float) -> float:
    return exp(-(d * d) / (2.0 * sigma * sigma))


# ============================================================================
# FACE FIELD (V10 baseline)
# ============================================================================

func _face_intensity(p: Vector2) -> float:
    var x: float = p.x
    var y: float = p.y - FACE_Y_OFFSET
    var ax: float = abs(x)

    var oval_x: float = FACE_W
    var oval_y: float = FACE_H
    if y > 0:
        oval_x *= lerp(1.0, 0.74, pow(y / FACE_H, 1.7))
    else:
        oval_x *= lerp(1.0, 0.95, pow(-y / FACE_H, 1.2))
    var oval_norm: float = pow(ax / oval_x, 2.2) + pow(y / oval_y, 2.0)

    if oval_norm > 1.6:
        return _hair_intensity(p)

    var face_base: float
    if oval_norm < 1.0:
        face_base = lerp(0.80, 0.50, pow(oval_norm, 0.7))
    else:
        face_base = lerp(0.50, 0.0, (oval_norm - 1.0) / 0.6)

    var eye_y: float = -45.0
    var eye_x: float = 78.0
    var dx_eye: float = ax - eye_x
    var dy_eye: float = y - eye_y
    var eye_socket_dist: float = sqrt(dx_eye * dx_eye * 1.0 + dy_eye * dy_eye * 1.7)
    face_base -= _gauss(eye_socket_dist, 48.0) * 0.40

    var brow_y: float = -90.0
    var brow_x: float = 78.0
    var brow_arch: float = 8.0 * sin(clamp(ax / 130.0, 0.0, 1.0) * PI)
    var dx_brow: float = ax - brow_x
    var dy_brow: float = y - (brow_y - brow_arch)
    var brow_dist: float = sqrt(dx_brow * dx_brow * 0.45 + dy_brow * dy_brow * 2.5)
    face_base += _gauss(brow_dist, 36.0) * 0.42

    var lid_y: float = -38.0
    var lid_dist: float = sqrt(dx_eye * dx_eye * 0.7 + (y - lid_y) * (y - lid_y) * 4.5)
    if y >= eye_y:
        face_base += _gauss(lid_dist, 22.0) * 0.22

    if ax > 38.0 and ax < 118.0 and y > eye_y and y < eye_y + 28.0:
        var lash_t: float = (y - eye_y) / 28.0
        var lash_fade: float = pow(1.0 - lash_t, 1.2)
        face_base += lash_fade * 0.10

    if ax < 32.0 and y > -45.0 and y < 52.0:
        var ridge_t: float = (y + 45.0) / 97.0
        var ridge_width: float = lerp(12.0, 25.0, pow(ridge_t, 1.3))
        if ax < ridge_width:
            var ridge_strength: float = pow(1.0 - ax / ridge_width, 0.9)
            face_base += ridge_strength * lerp(0.04, 0.10, ridge_t)

    var nostril_y: float = 48.0
    var nostril_x: float = 14.0
    var dx_n: float = ax - nostril_x
    var dy_n: float = y - nostril_y
    var nostril_dist: float = sqrt(dx_n * dx_n * 1.6 + dy_n * dy_n * 2.6)
    face_base -= _gauss(nostril_dist, 11.0) * 0.42

    var lip_y: float = 108.0
    var dy_lip: float = y - lip_y
    if abs(dy_lip) < 16.0 and ax < 92.0:
        var lip_t: float = ax / 92.0
        var lip_horiz_fade: float = pow(1.0 - lip_t, 0.7)
        var lip_line: float = _gauss(dy_lip, 3.0)
        var lip_lower_boost: float = 0.0
        if dy_lip > 1.0 and dy_lip < 9.0:
            lip_lower_boost = pow(1.0 - (dy_lip - 1.0) / 8.0, 0.8) * 0.18
        var upper: float = 0.0
        if dy_lip < -1.0 and dy_lip > -7.0:
            upper = pow(1.0 - (-dy_lip - 1.0) / 6.0, 0.8) * 0.10
        face_base += lip_horiz_fade * (upper + lip_lower_boost - lip_line * 0.20)

    face_base += face_noise.get_noise_2d(x * 0.04, y * 0.04) * 0.04
    var hair: float = _hair_intensity(p)
    face_base = max(face_base, hair)
    return clamp(face_base, 0.0, 1.0)


func _hair_intensity(p: Vector2) -> float:
    var x: float = p.x
    var y: float = p.y - FACE_Y_OFFSET
    var oval_norm: float = pow(abs(x) / FACE_W, 2.2) + pow(y / FACE_H, 2.0)
    if oval_norm < 0.9 and y > -FACE_H * 0.5:
        return 0.0
    var fade: float = 0.0
    if oval_norm > 0.9:
        fade = clamp(1.0 - (oval_norm - 0.9) / 1.0, 0.0, 1.0)
    if y < -FACE_H * 0.5:
        var top_fade: float = clamp(1.0 - (-y - FACE_H * 0.5) / (FACE_H * 0.6), 0.0, 1.0)
        fade = max(fade, top_fade)
    var hair_n: float = (face_noise.get_noise_2d(x * 0.045, y * 0.045) + 1.0) * 0.5
    var hair_n2: float = (face_noise.get_noise_2d(x * 0.12, y * 0.12) + 1.0) * 0.5
    return fade * (hair_n * 0.65 + hair_n2 * 0.35) * 0.55


func _bake_face_targets() -> void:
    var positions := []
    var alphas := []
    var attempts := 0
    var max_attempts: int = FACE_PARTICLE_TARGET * 18
    var sample_w: float = FACE_W * 1.6
    var sample_h: float = FACE_H * 1.7

    while positions.size() < FACE_PARTICLE_TARGET and attempts < max_attempts:
        attempts += 1
        var px: float = (randf() * 2.0 - 1.0) * sample_w
        var py: float = (randf() * 2.0 - 1.0) * sample_h - 30.0
        var intensity: float = _face_intensity(Vector2(px, py))
        if intensity < randf() * 0.75:
            continue
        var jitter := Vector2(
            face_noise.get_noise_2d(px * 0.4, py * 0.4) * 1.4,
            face_noise.get_noise_2d(px * 0.4 + 500.0, py * 0.4) * 1.4
        )
        positions.append(Vector2(px, py) + jitter)
        alphas.append(clamp(lerp(0.30, 1.0, intensity), 0.0, 1.0))

    var indices := range(PARTICLE_COUNT)
    indices.shuffle()
    for i in range(PARTICLE_COUNT):
        var idx: int = indices[i]
        if i < positions.size():
            particle_face_positions[idx] = positions[i]
            particle_face_alphas[idx] = alphas[i]
            particle_face_sizes[idx] = lerp(0.40, 0.85, randf())
            particle_face_active[idx] = true
        else:
            particle_face_positions[idx] = particle_base_positions[idx] * 1.5
            particle_face_alphas[idx] = 0.0
            particle_face_sizes[idx] = particle_base_sizes[idx] * 0.5
            particle_face_active[idx] = false


# ============================================================================
# FACE / GLYPH STATE MACHINES
# ============================================================================

func _trigger_face() -> void:
    _bake_face_targets()
    face_state = FACE_STATE_EMERGE
    face_state_age = 0.0


func _force_face_dissolve() -> void:
    if face_state == FACE_STATE_NONE or face_state == FACE_STATE_DISSOLVE:
        return
    face_state = FACE_STATE_DISSOLVE
    face_state_age = (1.0 - face_blend) * FACE_DISSOLVE_DURATION


func _update_face_state(delta: float) -> void:
    if face_state == FACE_STATE_NONE:
        face_blend = 0.0
        return
    face_state_age += delta
    match face_state:
        FACE_STATE_EMERGE:
            face_blend = clamp(face_state_age / FACE_EMERGE_DURATION, 0.0, 1.0)
            face_blend = _ease_out_cubic(face_blend)
            if face_state_age >= FACE_EMERGE_DURATION:
                face_state = FACE_STATE_HOLD
                face_state_age = 0.0
                face_blend = 1.0
        FACE_STATE_HOLD:
            face_blend = 1.0
        FACE_STATE_DISSOLVE:
            var t: float = clamp(face_state_age / FACE_DISSOLVE_DURATION, 0.0, 1.0)
            face_blend = 1.0 - _ease_in_cubic(t)
            if face_state_age >= FACE_DISSOLVE_DURATION:
                face_state = FACE_STATE_NONE
                face_blend = 0.0


func _trigger_glyph(kind: int) -> void:
    glyph_kind = kind
    _refresh_glyph_value()
    glyph_state = FACE_STATE_EMERGE
    glyph_state_age = 0.0


func _refresh_glyph_value() -> void:
    match glyph_kind:
        GLYPH_KIND_TEMPERATURE:
            glyph_text = str(glyph_temperature_c) + "°"
            glyph_color = _pick_temperature_color(glyph_temperature_c)
        GLYPH_KIND_BATTERY:
            glyph_text = str(glyph_battery_percent) + "%"
            glyph_color = _pick_battery_color(glyph_battery_percent)
        GLYPH_KIND_DATE:
            if glyph_text == "":
                glyph_text = _format_local_date()
            glyph_color = GLYPH_NEUTRAL_COLOR
        GLYPH_KIND_TIME:
            if glyph_text == "":
                glyph_text = _format_local_time()
            glyph_color = GLYPH_NEUTRAL_COLOR
        _:
            glyph_text = ""
            glyph_color = Color(1, 1, 1, 1)
    _bake_glyph_targets(glyph_text, glyph_color)


func _force_glyph_dissolve() -> void:
    if glyph_state == FACE_STATE_NONE or glyph_state == FACE_STATE_DISSOLVE:
        return
    glyph_state = FACE_STATE_DISSOLVE
    glyph_state_age = (1.0 - glyph_blend) * FACE_DISSOLVE_DURATION


func _update_glyph_state(delta: float) -> void:
    if glyph_state == FACE_STATE_NONE:
        glyph_blend = 0.0
        return
    glyph_state_age += delta
    match glyph_state:
        FACE_STATE_EMERGE:
            glyph_blend = clamp(glyph_state_age / FACE_EMERGE_DURATION, 0.0, 1.0)
            glyph_blend = _ease_out_cubic(glyph_blend)
            if glyph_state_age >= FACE_EMERGE_DURATION:
                glyph_state = FACE_STATE_HOLD
                glyph_state_age = 0.0
                glyph_blend = 1.0
        FACE_STATE_HOLD:
            glyph_blend = 1.0
            if glyph_state_age >= GLYPH_HOLD_DURATION:
                glyph_state = FACE_STATE_DISSOLVE
                glyph_state_age = 0.0
        FACE_STATE_DISSOLVE:
            var t: float = clamp(glyph_state_age / FACE_DISSOLVE_DURATION, 0.0, 1.0)
            glyph_blend = 1.0 - _ease_in_cubic(t)
            if glyph_state_age >= FACE_DISSOLVE_DURATION:
                glyph_state = FACE_STATE_NONE
                glyph_blend = 0.0
                glyph_kind = GLYPH_KIND_NONE


func _ease_out_cubic(t: float) -> float:
    var u: float = 1.0 - t
    return 1.0 - u * u * u


func _ease_in_cubic(t: float) -> float:
    return t * t * t


func _state_is_glyph(s: String) -> bool:
    return s == VisualStates.TEMPERATURE_GLYPH \
        or s == VisualStates.BATTERY_GLYPH \
        or s == VisualStates.DATE_GLYPH \
        or s == VisualStates.TIME_GLYPH


# ============================================================================
# COLOR THRESHOLDS
# ============================================================================

func _pick_battery_color(percent: int) -> Color:
    if percent >= 80:
        return Color(0.30, 0.95, 0.40)
    elif percent >= 50:
        return Color(0.30, 0.65, 1.00)
    elif percent >= 30:
        return Color(1.00, 0.85, 0.20)
    else:
        return Color(1.00, 0.30, 0.25)


func _pick_temperature_color(celsius: int) -> Color:
    if celsius <= 55:
        return Color(0.55, 0.85, 1.00)
    elif celsius <= 63:
        return Color(0.30, 0.55, 0.95)
    elif celsius <= 70:
        return Color(1.00, 0.85, 0.20)
    else:
        return Color(1.00, 0.30, 0.25)


func _format_local_date() -> String:
    var dt: Dictionary = OS.get_datetime()
    return "%02d.%02d" % [dt["day"], dt["month"]]


func _format_local_time() -> String:
    var dt: Dictionary = OS.get_datetime()
    return "%02d:%02d" % [dt["hour"], dt["minute"]]


# ============================================================================
# GLYPH RASTERIZER
# ============================================================================

func _is_in_segment(local: Vector2, seg_idx: int) -> bool:
    var hw: float = GLYPH_CHAR_W * 0.5
    var hh: float = GLYPH_CHAR_H * 0.5
    var s: float = GLYPH_STROKE * 0.5
    match seg_idx:
        0: return abs(local.y + hh) <= s and abs(local.x) <= (hw - s * 0.5)
        1: return abs(local.x - hw) <= s and local.y > -hh + s and local.y < 0
        2: return abs(local.x - hw) <= s and local.y > 0 and local.y < hh - s
        3: return abs(local.y - hh) <= s and abs(local.x) <= (hw - s * 0.5)
        4: return abs(local.x + hw) <= s and local.y > 0 and local.y < hh - s
        5: return abs(local.x + hw) <= s and local.y > -hh + s and local.y < 0
        6: return abs(local.y) <= s and abs(local.x) <= (hw - s * 0.5)
    return false


func _is_in_char_at(local: Vector2, ch: String) -> bool:
    if SEG_DIGITS.has(ch):
        var segs = SEG_DIGITS[ch]
        for i in range(7):
            if segs[i] and _is_in_segment(local, i):
                return true
        return false
    if ch == "°":
        var d: float = local.distance_to(Vector2(GLYPH_CHAR_W * 0.05, -GLYPH_CHAR_H * 0.32))
        return d > 14.0 and d < 24.0
    if ch == "%":
        if local.distance_to(Vector2(-GLYPH_CHAR_W * 0.25, -GLYPH_CHAR_H * 0.30)) < 12.0:
            return true
        if local.distance_to(Vector2(GLYPH_CHAR_W * 0.25, GLYPH_CHAR_H * 0.30)) < 12.0:
            return true
        var t: float = (local.x + GLYPH_CHAR_W * 0.4) / (GLYPH_CHAR_W * 0.8)
        if t >= 0 and t <= 1:
            var slash_y: float = lerp(-GLYPH_CHAR_H * 0.4, GLYPH_CHAR_H * 0.4, t)
            if abs(local.y - slash_y) < 7.0:
                return true
        return false
    if ch == ":":
        if local.distance_to(Vector2(0, -GLYPH_CHAR_H * 0.18)) < 11.0: return true
        if local.distance_to(Vector2(0,  GLYPH_CHAR_H * 0.18)) < 11.0: return true
        return false
    if ch == ".":
        return local.distance_to(Vector2(0, GLYPH_CHAR_H * 0.36)) < 12.0
    return false


func _char_width(ch: String) -> float:
    if ch == ":" or ch == ".":
        return GLYPH_CHAR_W * 0.30
    if ch == "°":
        return GLYPH_CHAR_W * 0.55
    return GLYPH_CHAR_W


func _bake_glyph_targets(text: String, _color: Color) -> void:
    if text.length() == 0:
        return
    var widths := []
    var total_w: float = 0.0
    for i in range(text.length()):
        var w: float = _char_width(text[i])
        widths.append(w)
        total_w += w
        if i < text.length() - 1:
            total_w += GLYPH_CHAR_SPACING
    var char_centers := []
    var cursor: float = -total_w * 0.5
    for i in range(text.length()):
        var w: float = widths[i]
        char_centers.append(cursor + w * 0.5)
        cursor += w + GLYPH_CHAR_SPACING

    var positions := []
    var attempts := 0
    var max_attempts: int = FACE_PARTICLE_TARGET * 14
    var target_count: int = int(FACE_PARTICLE_TARGET * 0.7)

    while positions.size() < target_count and attempts < max_attempts:
        attempts += 1
        var px: float = (randf() - 0.5) * (total_w + GLYPH_CHAR_W * 0.3)
        var py: float = (randf() - 0.5) * (GLYPH_CHAR_H * 1.15)
        var cell_idx: int = -1
        for i in range(text.length()):
            var w: float = widths[i]
            var cx: float = char_centers[i]
            if px >= cx - w * 0.5 and px < cx + w * 0.5:
                cell_idx = i
                break
        if cell_idx < 0:
            continue
        var ch: String = text[cell_idx]
        var local: Vector2 = Vector2(px - char_centers[cell_idx], py)
        if not _is_in_char_at(local, ch):
            continue
        var jitter := Vector2((randf() - 0.5) * 3.5, (randf() - 0.5) * 3.5)
        positions.append(Vector2(px, py) + jitter)

    var indices := range(PARTICLE_COUNT)
    indices.shuffle()
    for i in range(PARTICLE_COUNT):
        var idx: int = indices[i]
        if i < positions.size():
            particle_glyph_positions[idx] = positions[i]
            particle_glyph_alphas[idx] = lerp(0.65, 1.0, randf())
            particle_glyph_active[idx] = true
        else:
            particle_glyph_positions[idx] = particle_base_positions[idx] * 1.3
            particle_glyph_alphas[idx] = 0.0
            particle_glyph_active[idx] = false


# ============================================================================
# RENDER LOOP
# ============================================================================

func _update_shell_transform(delta: float) -> void:
    var target := Vector2(1.0, 1.0)
    if shell_compact_mode:
        target = _compact_nebula_render_scale(get_viewport_rect().size)

    render_scale = render_scale.linear_interpolate(target, clamp(delta * 4.0, 0.0, 1.0))
    visual_scale = (render_scale.x + render_scale.y) * 0.5


func _compact_nebula_render_scale(viewport_size: Vector2) -> Vector2:
    var safe_width: float = max(1.0, viewport_size.x)
    var safe_height: float = max(1.0, viewport_size.y)

    var scale_x: float = (safe_width * 0.96) / (NEBULA_RADIUS * 2.90)
    var scale_y: float = (safe_height * 0.96) / (NEBULA_RADIUS * 2.10)

    return Vector2(scale_x, scale_y)



func _compact_square_field_position(position: Vector2, glyph_blend_value: float) -> Vector2:
    if not shell_compact_mode:
        return position

    if glyph_blend_value > COMPACT_FIELD_GLYPH_PROTECTION_THRESHOLD:
        return position

    var normalized_x: float = clamp(position.x / max(1.0, NEBULA_RADIUS * 1.45), -1.0, 1.0)
    var normalized_y: float = clamp(position.y / max(1.0, NEBULA_RADIUS * 1.05), -1.0, 1.0)

    var x_fill: float = COMPACT_FIELD_X_FILL + abs(normalized_y) * COMPACT_CORNER_X_FILL
    var y_fill: float = COMPACT_FIELD_Y_FILL + abs(normalized_x) * COMPACT_CORNER_Y_FILL

    return Vector2(position.x * x_fill, position.y * y_fill)


func _particle_screen_size_multiplier() -> float:
    if shell_compact_mode:
        return 2.05

    return 1.0


func _glyph_position_multiplier() -> float:
    if shell_compact_mode:
        return 2.55

    return 1.0


func _glyph_particle_size_multiplier() -> float:
    if shell_compact_mode:
        return 1.80

    return 1.0


func _update_particles() -> void:
    var t_field_a: float = time * 0.12
    var t_field_b: float = time * 0.10
    var t_field_c: float = time * 0.035
    var t_field_d: float = time * 0.032

    var t_drift_a: float = time * 0.55
    var t_drift_b: float = time * 0.45
    var t_breath: float = time * 0.85
    var t_listen: float = time * 2.2
    var t_speak: float = time * 1.8
    var t_jit_a: float = time * 1.4
    var t_jit_b: float = time * 1.7
    var t_shimmer: float = time * 2.2

    var face_active: bool = (face_blend > 0.001)
    var listen_pulse: float = sin(t_listen) * 22.0

    var is_listening: bool = (visual_state == VisualStates.LISTENING_CLOUD) and not face_active
    var is_speaking: bool = (visual_state == VisualStates.SPEAKING_PULSE) and not face_active
    var is_thinking: bool = (visual_state == VisualStates.THINKING_SWARM) and not face_active
    var is_degraded: bool = (visual_state == VisualStates.ERROR_DEGRADED)

    for i in range(PARTICLE_COUNT):
        var base_pos: Vector2 = particle_base_positions[i]
        var phase: float = particle_phases[i]

        var field_warp_x: float = sin(base_pos.y * 0.006 + t_field_a + phase) * ORGANIC_FIELD_WARP_X
        var field_warp_y: float = cos(base_pos.x * 0.005 + t_field_b + phase * 1.3) * ORGANIC_FIELD_WARP_Y
        var field_shear_x: float = base_pos.y * sin(t_field_c + phase * 0.10) * 0.018
        var field_shear_y: float = base_pos.x * cos(t_field_d + phase * 0.12) * 0.010

        var sw_x: float = base_pos.x * ORGANIC_FIELD_X_SPREAD + field_warp_x + field_shear_x
        var sw_y: float = base_pos.y * ORGANIC_FIELD_Y_SPREAD + field_warp_y + field_shear_y

        var drift_x: float = sin(t_drift_a + phase) * ORGANIC_DRIFT_X_PRIMARY
        drift_x += cos(t_drift_b * 0.77 + phase * 1.9) * ORGANIC_DRIFT_X_SECONDARY

        var drift_y: float = cos(t_drift_b + phase * 1.3) * ORGANIC_DRIFT_Y_PRIMARY
        drift_y += sin(t_drift_a * 0.63 + phase * 2.1) * ORGANIC_DRIFT_Y_SECONDARY

        var mode_offset_x: float = 0.0
        var mode_offset_y: float = 0.0
        var breath_strength: float = 0.18

        if is_listening:
            var s_len_sq: float = sw_x * sw_x + sw_y * sw_y
            if s_len_sq > 0.01:
                var s_len: float = sqrt(s_len_sq)
                var dist_factor: float = clamp(s_len / NEBULA_RADIUS, 0.3, 1.4)
                mode_offset_x = sw_x / s_len * listen_pulse * dist_factor
                mode_offset_y = sw_y / s_len * listen_pulse * dist_factor
            breath_strength = 0.55
        elif is_speaking:
            var wave_phase: float = sw_x * 0.012 - t_speak
            var wave_amp: float = 28.0
            var center_dist: float = sqrt(sw_x * sw_x + sw_y * sw_y) / NEBULA_RADIUS
            wave_amp *= clamp(0.4 + center_dist * 0.9, 0.4, 1.6)
            mode_offset_y = sin(wave_phase) * wave_amp
            mode_offset_x = sin(sw_y * 0.009 - t_speak * 0.7) * wave_amp * 0.35
            breath_strength = 0.42
        elif is_thinking:
            # Organic reorganization without turning the whole nebula into an orbit.
            var th_x: float = sin(t_drift_a * 1.3 + phase * 0.8) * 12.0
            var th_y: float = cos(t_drift_b * 1.1 + phase * 1.4) * 9.0
            mode_offset_x = th_x + cos(sw_y * 0.008 + t_drift_b) * 8.0
            mode_offset_y = th_y + sin(sw_x * 0.007 - t_drift_a) * 6.0
            breath_strength = 0.30

        var nebula_x: float = sw_x + drift_x + mode_offset_x
        var nebula_y: float = sw_y + drift_y + mode_offset_y

        var face_pos: Vector2 = particle_face_positions[i]
        var face_pos_x: float = face_pos.x
        var face_pos_y: float = face_pos.y
        var shimmer_alpha_mod: float = 1.0
        if face_active:
            var jseed: float = particle_face_jitter_seeds[i]
            face_pos_x += sin(t_jit_a + jseed) * 0.85
            face_pos_y += cos(t_jit_b + jseed * 1.3) * 0.75
            shimmer_alpha_mod = 1.0 + sin(t_shimmer + jseed * 1.1) * 0.08

        var pos_x: float = lerp(nebula_x, face_pos_x, face_blend)
        var pos_y: float = lerp(nebula_y, face_pos_y, face_blend)

        var breath: float = 1.0 + sin(t_breath + phase * 0.5) * breath_strength
        var nebula_alpha: float = particle_base_alphas[i] * breath
        var face_alpha: float = particle_face_alphas[i] * shimmer_alpha_mod
        if not particle_face_active[i]:
            face_alpha = 0.0
        var alpha: float = lerp(nebula_alpha, face_alpha, face_blend)
        var size: float = lerp(particle_base_sizes[i], particle_face_sizes[i], face_blend)
        var color: Color = particle_base_colors[i]

        if glyph_blend > 0.001:
            var glyph_position_multiplier: float = _glyph_position_multiplier()
            var gpos: Vector2 = particle_glyph_positions[i] * glyph_position_multiplier
            var galpha: float = particle_glyph_alphas[i] if particle_glyph_active[i] else 0.0
            pos_x = lerp(pos_x, gpos.x, glyph_blend)
            pos_y = lerp(pos_y, gpos.y, glyph_blend)
            alpha = lerp(alpha, galpha, glyph_blend)
            size = lerp(size, 0.55 * _glyph_particle_size_multiplier(), glyph_blend)
            color = color.linear_interpolate(glyph_color, glyph_blend)

        if is_degraded:
            alpha *= 0.78

        color.a = clamp(alpha, 0.0, 1.0)

        var compact_position: Vector2 = _compact_square_field_position(Vector2(pos_x, pos_y), glyph_blend)
        pos_x = compact_position.x
        pos_y = compact_position.y

        var xform := Transform2D()
        var final_size: float = size * _particle_screen_size_multiplier()
        xform[0] = Vector2(final_size * render_scale.x, 0)
        xform[1] = Vector2(0, final_size * render_scale.y)
        xform.origin = Vector2(pos_x * render_scale.x, pos_y * render_scale.y)

        multimesh.set_instance_transform_2d(i, xform)
        multimesh.set_instance_color(i, color)
