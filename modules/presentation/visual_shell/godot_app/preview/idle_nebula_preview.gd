extends Node2D
# Standalone preview - V10
#
# V10 changes vs V9:
#   PERFORMANCE:
#   - Reverted from bulk_array experiment (didn't help, possibly hurt on 2D).
#   - Particle count 12000 -> 6000 (safe for GDScript on Pi 5).
#   - Per-frame update timer in HUD to expose actual GDScript bottleneck.
#   - Renderer info in HUD (GLES2/GLES3 visibility).
#   FACE LOOK:
#   - Wider/softer gaussians for facial features (delicate visible contours,
#     not sharp masses).
#   - Boosted brow/eye/lip alpha for visibility on darker base.

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

const MODE_IDLE      = 0
const MODE_LISTENING = 1
const MODE_SPEAKING  = 2

const FACE_STATE_NONE     = 0
const FACE_STATE_EMERGE   = 1
const FACE_STATE_HOLD     = 2
const FACE_STATE_DISSOLVE = 3

# Glyph display mode (temperature / battery)
const GLYPH_NONE        = 0
const GLYPH_TEMPERATURE = 1
const GLYPH_BATTERY     = 2
const GLYPH_DATE        = 3
const GLYPH_TIME        = 4

const GLYPH_HOLD_DURATION = 5.0
const GLYPH_TIME_REFRESH_INTERVAL = 1.0  # tick clock during hold

const GLYPH_NEUTRAL_COLOR = Color(0.95, 0.93, 0.88)

const FACE_EMERGE_DURATION   = 1.6
const FACE_HOLD_DURATION     = 6.0
const FACE_DISSOLVE_DURATION = 1.6

const FACE_W = 235.0
const FACE_H = 305.0
const FACE_Y_OFFSET = -8.0

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
var particle_base_sizes := []
var particle_base_alphas := []
var particle_base_colors := []

var time := 0.0
var paused := false
var motion_intensity := 1.0
var current_mode := MODE_IDLE

var face_state: int = FACE_STATE_NONE
var face_state_age: float = 0.0
var face_preset: int = 1
var face_blend: float = 0.0

# Glyph display state
var glyph_kind: int = GLYPH_NONE
var glyph_state: int = FACE_STATE_NONE
var glyph_state_age: float = 0.0
var glyph_blend: float = 0.0
var glyph_text: String = ""
var glyph_color := Color(1, 1, 1, 1)
var glyph_value: int = 0
var glyph_time_refresh_timer: float = 0.0
var particle_glyph_positions := []
var particle_glyph_alphas := []
var particle_glyph_active := []

# Diagnostic counters
var last_update_ms: float = 0.0
var update_ms_avg: float = 0.0

var hud_visible := false
var fps_label: Label
var hint_label: Label
var face_label: Label
var perf_label: Label


func _ready() -> void:
    randomize()
    _setup_noise()
    var texture := _build_soft_particle_texture()
    _setup_multimesh(texture)
    _seed_particles()
    _setup_dev_overlay()


func _process(delta: float) -> void:
    if not paused:
        time += delta
        _update_face_state(delta)
        _update_glyph_state(delta)

    var t0: int = OS.get_ticks_usec()
    _update_particles()
    var t1: int = OS.get_ticks_usec()
    last_update_ms = (t1 - t0) / 1000.0
    update_ms_avg = update_ms_avg * 0.92 + last_update_ms * 0.08

    if hud_visible:
        fps_label.text = "FPS: " + str(Engine.get_frames_per_second()) \
            + "   particles: " + str(PARTICLE_COUNT) \
            + "   mode: " + _mode_name(current_mode) \
            + "   motion: " + String(motion_intensity).pad_decimals(2) \
            + "   " + ("PAUSED" if paused else "live")
        face_label.text = "face: " + _face_state_name() \
            + "   blend: " + String(face_blend).pad_decimals(2) \
            + "   preset: " + str(face_preset) \
            + "   glyph: " + _glyph_kind_name() + " " + str(glyph_value) \
            + " bl: " + String(glyph_blend).pad_decimals(2)
        perf_label.text = "update: " + String(update_ms_avg).pad_decimals(2) + " ms" \
            + "   render: " + str(OS.get_video_driver_name(OS.get_current_video_driver())) \
            + "   gles: " + str(VisualServer.get_render_info(VisualServer.INFO_USAGE_VIDEO_MEM_TOTAL) >> 20) + "MB"


func _input(event: InputEvent) -> void:
    if not (event is InputEventKey and event.pressed and not event.echo):
        return

    match event.scancode:
        KEY_SPACE:
            paused = not paused
        KEY_R:
            _setup_noise()
            _seed_particles()
        KEY_PLUS, KEY_EQUAL, KEY_KP_ADD:
            motion_intensity = min(motion_intensity * 1.25, 5.0)
        KEY_MINUS, KEY_KP_SUBTRACT:
            motion_intensity = max(motion_intensity * 0.80, 0.10)
        KEY_1:
            current_mode = MODE_IDLE
        KEY_2:
            current_mode = MODE_LISTENING
        KEY_3:
            current_mode = MODE_SPEAKING
        KEY_F:
            _trigger_face(2 if event.shift else 1)
        KEY_X:
            _force_dissolve()
            _force_glyph_dissolve()
        KEY_T:
            _trigger_glyph(GLYPH_TEMPERATURE)
        KEY_B:
            _trigger_glyph(GLYPH_BATTERY)
        KEY_D:
            _trigger_glyph(GLYPH_DATE)
        KEY_G:
            _trigger_glyph(GLYPH_TIME)
        KEY_Y:
            # Cycle test value to preview color thresholds
            if glyph_kind == GLYPH_TEMPERATURE:
                glyph_value = (glyph_value + 8) % 90
                _refresh_glyph_value()
            elif glyph_kind == GLYPH_BATTERY:
                glyph_value = (glyph_value + 15) % 105
                _refresh_glyph_value()
        KEY_H:
            hud_visible = not hud_visible
            fps_label.visible = hud_visible
            hint_label.visible = hud_visible
            face_label.visible = hud_visible
            perf_label.visible = hud_visible
        KEY_M:
            if event.control:
                _toggle_minimized()
            else:
                _toggle_maximized()
        KEY_F11:
            OS.window_fullscreen = not OS.window_fullscreen
        KEY_ESCAPE:
            if OS.window_fullscreen:
                OS.window_fullscreen = false


func _toggle_maximized() -> void:
    if OS.window_fullscreen:
        OS.window_fullscreen = false
    OS.window_maximized = not OS.window_maximized


func _toggle_minimized() -> void:
    OS.window_minimized = not OS.window_minimized


func _draw() -> void:
    var viewport := get_viewport_rect().size
    draw_rect(Rect2(Vector2.ZERO, viewport), BACKGROUND_COLOR)


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
    multimesh_instance.position = get_viewport_rect().size * 0.5


func _setup_dev_overlay() -> void:
    fps_label = Label.new()
    fps_label.rect_position = Vector2(12, 8)
    fps_label.add_color_override("font_color", Color(1, 1, 1, 0.85))
    fps_label.visible = false
    add_child(fps_label)

    hint_label = Label.new()
    hint_label.rect_position = Vector2(12, 28)
    hint_label.add_color_override("font_color", Color(0.85, 0.85, 0.95, 0.65))
    hint_label.text = "SPACE pause | R reseed | +/- motion | 1/2/3 modes | F face | T temp B batt D date G time Y cycle | X dissolve | M max F11 fs | H hud"
    hint_label.visible = false
    add_child(hint_label)

    face_label = Label.new()
    face_label.rect_position = Vector2(12, 48)
    face_label.add_color_override("font_color", Color(1.0, 0.85, 0.65, 0.85))
    face_label.visible = false
    add_child(face_label)

    perf_label = Label.new()
    perf_label.rect_position = Vector2(12, 68)
    perf_label.add_color_override("font_color", Color(0.7, 1.0, 0.7, 0.85))
    perf_label.visible = false
    add_child(perf_label)


func _mode_name(mode: int) -> String:
    match mode:
        MODE_LISTENING: return "LISTENING"
        MODE_SPEAKING:  return "SPEAKING"
        _:              return "IDLE"


func _face_state_name() -> String:
    match face_state:
        FACE_STATE_EMERGE:   return "EMERGE"
        FACE_STATE_HOLD:     return "HOLD"
        FACE_STATE_DISSOLVE: return "DISSOLVE"
        _:                   return "none"


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
        particle_glyph_positions[i] = Vector2.ZERO
        particle_glyph_alphas[i] = 0.0
        particle_glyph_active[i] = false

    for i in range(PARTICLE_COUNT):
        particle_face_jitter_seeds[i] = randf() * 1000.0

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


# ============================================================================
# FACE SHADING - V10 - Soft visible contours, wider gaussians
# ============================================================================

func _gauss(d: float, sigma: float) -> float:
    return exp(-(d * d) / (2.0 * sigma * sigma))


func _face_intensity(p: Vector2, preset: int) -> float:
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

    # Eye sockets - WIDER soft (sigma 38 -> 48 for diffuse look)
    var eye_y: float = -45.0
    var eye_x: float = 78.0
    var dx_eye: float = ax - eye_x
    var dy_eye: float = y - eye_y
    var eye_socket_dist: float = sqrt(dx_eye * dx_eye * 1.0 + dy_eye * dy_eye * 1.7)
    var eye_socket: float = _gauss(eye_socket_dist, 48.0)
    face_base -= eye_socket * 0.40

    # Eyebrows - WIDER softer arc (sigma 28 -> 36, alpha 0.30 -> 0.42)
    var brow_y: float = -90.0
    var brow_x: float = 78.0
    var brow_arch: float = 8.0 * sin(clamp(ax / 130.0, 0.0, 1.0) * PI)
    var dx_brow: float = ax - brow_x
    var dy_brow: float = y - (brow_y - brow_arch)
    var brow_dist: float = sqrt(dx_brow * dx_brow * 0.45 + dy_brow * dy_brow * 2.5)
    var brow: float = _gauss(brow_dist, 36.0)
    face_base += brow * (0.42 if preset == 1 else 0.55)

    # Eyelid hint - softer (sigma 16 -> 22)
    var lid_y: float = -38.0
    var lid_dist: float = sqrt(dx_eye * dx_eye * 0.7 + (y - lid_y) * (y - lid_y) * 4.5)
    var lid: float = _gauss(lid_dist, 22.0)
    if y >= eye_y:
        face_base += lid * 0.22

    # Lashes - subtle
    if ax > 38.0 and ax < 118.0 and y > eye_y and y < eye_y + 28.0:
        var lash_t: float = (y - eye_y) / 28.0
        var lash_fade: float = pow(1.0 - lash_t, 1.2)
        face_base += lash_fade * 0.10

    # Nose - soft ridge
    if ax < 32.0 and y > -45.0 and y < 52.0:
        var ridge_t: float = (y + 45.0) / 97.0
        var ridge_width: float = lerp(12.0, 25.0, pow(ridge_t, 1.3))
        if ax < ridge_width:
            var ridge_strength: float = pow(1.0 - ax / ridge_width, 0.9)
            face_base += ridge_strength * lerp(0.04, 0.10, ridge_t)

    # Nostrils - softer (sigma 8 -> 11)
    var nostril_y: float = 48.0
    var nostril_x: float = 14.0
    var dx_n: float = ax - nostril_x
    var dy_n: float = y - nostril_y
    var nostril_dist: float = sqrt(dx_n * dx_n * 1.6 + dy_n * dy_n * 2.6)
    var nostril: float = _gauss(nostril_dist, 11.0)
    face_base -= nostril * 0.42

    # Lips - more visible, softer line (sigma 1.8 -> 3.0)
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

    # Skin micro-noise
    var skin_noise: float = face_noise.get_noise_2d(x * 0.04, y * 0.04)
    face_base += skin_noise * 0.04

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
    var hair_combined: float = hair_n * 0.65 + hair_n2 * 0.35

    return fade * hair_combined * 0.55


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
        var intensity: float = _face_intensity(Vector2(px, py), face_preset)
        if intensity < randf() * 0.75:
            continue

        var jitter := Vector2(
            face_noise.get_noise_2d(px * 0.4, py * 0.4) * 1.4,
            face_noise.get_noise_2d(px * 0.4 + 500.0, py * 0.4) * 1.4
        )

        positions.append(Vector2(px, py) + jitter)
        # Stronger contrast: brighter highlights
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


func _trigger_face(preset: int) -> void:
    if face_state == FACE_STATE_HOLD and preset == face_preset:
        _force_dissolve()
        return
    face_preset = preset
    _bake_face_targets()
    face_state = FACE_STATE_EMERGE
    face_state_age = 0.0


func _force_dissolve() -> void:
    if face_state == FACE_STATE_NONE:
        return
    if face_state == FACE_STATE_DISSOLVE:
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
            if face_state_age >= FACE_HOLD_DURATION:
                face_state = FACE_STATE_DISSOLVE
                face_state_age = 0.0
        FACE_STATE_DISSOLVE:
            var t: float = clamp(face_state_age / FACE_DISSOLVE_DURATION, 0.0, 1.0)
            face_blend = 1.0 - _ease_in_cubic(t)
            if face_state_age >= FACE_DISSOLVE_DURATION:
                face_state = FACE_STATE_NONE
                face_blend = 0.0


func _ease_out_cubic(t: float) -> float:
    var u: float = 1.0 - t
    return 1.0 - u * u * u


func _ease_in_cubic(t: float) -> float:
    return t * t * t


func _update_particles() -> void:
    var swirl: float = time * 0.05
    var swirl_cos: float = cos(swirl)
    var swirl_sin: float = sin(swirl)

    var t_drift_a: float = time * 0.55
    var t_drift_b: float = time * 0.45
    var t_breath: float = time * 0.85
    var t_listen: float = time * 2.2
    var t_speak: float = time * 1.8
    var t_jit_a: float = time * 1.4
    var t_jit_b: float = time * 1.7
    var t_shimmer: float = time * 2.2

    var face_active: bool = (face_blend > 0.001)
    var listen_pulse: float = sin(t_listen) * 22.0 * motion_intensity

    for i in range(PARTICLE_COUNT):
        var base_pos: Vector2 = particle_base_positions[i]
        var phase: float = particle_phases[i]

        var sw_x: float = base_pos.x * swirl_cos - base_pos.y * swirl_sin
        var sw_y: float = base_pos.x * swirl_sin + base_pos.y * swirl_cos

        var drift_x: float = sin(t_drift_a + phase) * 5.0 * motion_intensity
        var drift_y: float = cos(t_drift_b + phase * 1.3) * 4.5 * motion_intensity

        var mode_offset_x: float = 0.0
        var mode_offset_y: float = 0.0
        var breath_strength: float = 0.18

        if not face_active:
            if current_mode == MODE_LISTENING:
                var s_len_sq: float = sw_x * sw_x + sw_y * sw_y
                if s_len_sq > 0.01:
                    var s_len: float = sqrt(s_len_sq)
                    # Distance-scaled pulse: outer particles move more than inner
                    var dist_factor: float = clamp(s_len / NEBULA_RADIUS, 0.3, 1.4)
                    mode_offset_x = sw_x / s_len * listen_pulse * dist_factor
                    mode_offset_y = sw_y / s_len * listen_pulse * dist_factor
                breath_strength = 0.55
            elif current_mode == MODE_SPEAKING:
                var wave_phase: float = sw_x * 0.012 - t_speak
                # Stronger wave with depth-modulated amplitude
                var wave_amp: float = 28.0 * motion_intensity
                # Distance from center scales it - edges move more than core
                var center_dist: float = sqrt(sw_x * sw_x + sw_y * sw_y) / NEBULA_RADIUS
                wave_amp *= clamp(0.4 + center_dist * 0.9, 0.4, 1.6)
                mode_offset_y = sin(wave_phase) * wave_amp
                # Secondary cross-wave for richness
                mode_offset_x = sin(sw_y * 0.009 - t_speak * 0.7) * wave_amp * 0.35
                breath_strength = 0.42

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

        # Blend: nebula -> face -> glyph (glyph takes priority over face)
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

        # Glyph layer (temperature / battery)
        if glyph_blend > 0.001:
            var gpos: Vector2 = particle_glyph_positions[i]
            var galpha: float = particle_glyph_alphas[i] if particle_glyph_active[i] else 0.0
            pos_x = lerp(pos_x, gpos.x, glyph_blend)
            pos_y = lerp(pos_y, gpos.y, glyph_blend)
            alpha = lerp(alpha, galpha, glyph_blend)
            size = lerp(size, 0.55, glyph_blend)
            color = color.linear_interpolate(glyph_color, glyph_blend)

        color.a = clamp(alpha, 0.0, 1.0)

        var xform := Transform2D()
        xform[0] = Vector2(size, 0)
        xform[1] = Vector2(0, size)
        xform.origin = Vector2(pos_x, pos_y)

        multimesh.set_instance_transform_2d(i, xform)
        multimesh.set_instance_color(i, color)


# ============================================================================
# GLYPH SYSTEM - Temperature / Battery digit display
# ============================================================================

func _read_cpu_temperature() -> int:
    # Reads from Linux thermal zone. Pi 5 exposes CPU temp at thermal_zone0.
    var f := File.new()
    if f.open("/sys/class/thermal/thermal_zone0/temp", File.READ) == OK:
        var raw: String = f.get_as_text().strip_edges()
        f.close()
        if raw.is_valid_integer():
            return int(int(raw) / 1000.0)
    # Fallback for non-Pi development environments
    return 45 + (randi() % 30)


func _read_battery_percent() -> int:
    # ADAPTER: Replace this body with real I2C/UART read when hardware ready.
    # The function signature stays the same; only the implementation changes.
    return randi() % 101


func _pick_battery_color(percent: int) -> Color:
    if percent >= 80:
        return Color(0.30, 0.95, 0.40)   # green
    elif percent >= 50:
        return Color(0.30, 0.65, 1.00)   # blue
    elif percent >= 30:
        return Color(1.00, 0.85, 0.20)   # yellow
    else:
        return Color(1.00, 0.30, 0.25)   # red


func _pick_temperature_color(celsius: int) -> Color:
    if celsius <= 55:
        return Color(0.55, 0.85, 1.00)   # light blue
    elif celsius <= 63:
        return Color(0.30, 0.55, 0.95)   # medium blue
    elif celsius <= 70:
        return Color(1.00, 0.85, 0.20)   # yellow
    else:
        return Color(1.00, 0.30, 0.25)   # red


func _glyph_kind_name() -> String:
    match glyph_kind:
        GLYPH_TEMPERATURE: return "TEMP"
        GLYPH_BATTERY:     return "BATT"
        GLYPH_DATE:        return "DATE"
        GLYPH_TIME:        return "TIME"
        _:                 return "none"


func _trigger_glyph(kind: int) -> void:
    # Toggle: same kind already active = dissolve
    if glyph_kind == kind and (glyph_state == FACE_STATE_HOLD or glyph_state == FACE_STATE_EMERGE):
        _force_glyph_dissolve()
        return

    glyph_kind = kind
    if kind == GLYPH_TEMPERATURE:
        glyph_value = _read_cpu_temperature()
    elif kind == GLYPH_BATTERY:
        glyph_value = _read_battery_percent()
    # DATE / TIME read inside _refresh_glyph_value (system time)

    glyph_time_refresh_timer = 0.0
    _refresh_glyph_value()
    glyph_state = FACE_STATE_EMERGE
    glyph_state_age = 0.0


func _refresh_glyph_value() -> void:
    # Update text + color based on current glyph_kind / glyph_value
    if glyph_kind == GLYPH_TEMPERATURE:
        glyph_text = str(glyph_value) + "°"
        glyph_color = _pick_temperature_color(glyph_value)
    elif glyph_kind == GLYPH_BATTERY:
        glyph_text = str(glyph_value) + "%"
        glyph_color = _pick_battery_color(glyph_value)
    elif glyph_kind == GLYPH_DATE:
        glyph_text = _format_date_string()
        glyph_color = GLYPH_NEUTRAL_COLOR
    elif glyph_kind == GLYPH_TIME:
        glyph_text = _format_time_string()
        glyph_color = GLYPH_NEUTRAL_COLOR
    else:
        glyph_text = ""
        glyph_color = Color(1, 1, 1, 1)
    _bake_glyph_targets(glyph_text, glyph_color)


func _format_date_string() -> String:
    var dt: Dictionary = OS.get_datetime()
    return "%02d.%02d" % [dt["day"], dt["month"]]


func _format_time_string() -> String:
    var dt: Dictionary = OS.get_datetime()
    return "%02d:%02d" % [dt["hour"], dt["minute"]]


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
            # Live refresh for DATE/TIME so the clock ticks while held
            if glyph_kind == GLYPH_TIME or glyph_kind == GLYPH_DATE:
                glyph_time_refresh_timer += delta
                if glyph_time_refresh_timer >= GLYPH_TIME_REFRESH_INTERVAL:
                    glyph_time_refresh_timer = 0.0
                    var prev_text: String = glyph_text
                    var new_text: String
                    if glyph_kind == GLYPH_TIME:
                        new_text = _format_time_string()
                    else:
                        new_text = _format_date_string()
                    # Only re-bake if text changed (avoid tearing every second
                    # during DATE which rarely changes)
                    if new_text != prev_text:
                        glyph_text = new_text
                        _bake_glyph_targets(glyph_text, glyph_color)
            if glyph_state_age >= GLYPH_HOLD_DURATION:
                glyph_state = FACE_STATE_DISSOLVE
                glyph_state_age = 0.0
        FACE_STATE_DISSOLVE:
            var t: float = clamp(glyph_state_age / FACE_DISSOLVE_DURATION, 0.0, 1.0)
            glyph_blend = 1.0 - _ease_in_cubic(t)
            if glyph_state_age >= FACE_DISSOLVE_DURATION:
                glyph_state = FACE_STATE_NONE
                glyph_blend = 0.0
                glyph_kind = GLYPH_NONE


# ----------------------------------------------------------------------------
# 7-segment-style glyph rasterization with particle scatter.
# Each character occupies a cell; particles are sampled within stroke regions.
# ----------------------------------------------------------------------------

const GLYPH_CHAR_W = 95.0
const GLYPH_CHAR_H = 165.0
const GLYPH_CHAR_SPACING = 22.0
const GLYPH_STROKE = 18.0

# 7-segment definitions for digits 0-9 plus ° and %
# Segments: top, top-right, bottom-right, bottom, bottom-left, top-left, middle
# Encoded as 7 bools per character
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


func _is_in_segment(local: Vector2, seg_idx: int) -> bool:
    # local is in [-CHAR_W/2, CHAR_W/2] x [-CHAR_H/2, CHAR_H/2]
    var hw: float = GLYPH_CHAR_W * 0.5
    var hh: float = GLYPH_CHAR_H * 0.5
    var s: float = GLYPH_STROKE * 0.5

    match seg_idx:
        0:  # top horizontal
            return abs(local.y + hh) <= s and abs(local.x) <= (hw - s * 0.5)
        1:  # top-right vertical
            return abs(local.x - hw) <= s and local.y > -hh + s and local.y < 0
        2:  # bottom-right vertical
            return abs(local.x - hw) <= s and local.y > 0 and local.y < hh - s
        3:  # bottom horizontal
            return abs(local.y - hh) <= s and abs(local.x) <= (hw - s * 0.5)
        4:  # bottom-left vertical
            return abs(local.x + hw) <= s and local.y > 0 and local.y < hh - s
        5:  # top-left vertical
            return abs(local.x + hw) <= s and local.y > -hh + s and local.y < 0
        6:  # middle horizontal
            return abs(local.y) <= s and abs(local.x) <= (hw - s * 0.5)
    return false


func _is_in_char_at(local: Vector2, ch: String) -> bool:
    if SEG_DIGITS.has(ch):
        var segs = SEG_DIGITS[ch]
        for i in range(7):
            if segs[i] and _is_in_segment(local, i):
                return true
        return false

    # Special: degree symbol - small circle top-right of cell
    if ch == "°":
        var cx: float = GLYPH_CHAR_W * 0.05
        var cy: float = -GLYPH_CHAR_H * 0.32
        var d: float = local.distance_to(Vector2(cx, cy))
        return d > 14.0 and d < 24.0

    # Special: percent sign - two dots and a slash
    if ch == "%":
        # top-left dot
        if local.distance_to(Vector2(-GLYPH_CHAR_W * 0.25, -GLYPH_CHAR_H * 0.30)) < 12.0:
            return true
        # bottom-right dot
        if local.distance_to(Vector2(GLYPH_CHAR_W * 0.25, GLYPH_CHAR_H * 0.30)) < 12.0:
            return true
        # diagonal slash
        var t: float = (local.x + GLYPH_CHAR_W * 0.4) / (GLYPH_CHAR_W * 0.8)
        if t >= 0 and t <= 1:
            var slash_y: float = lerp(-GLYPH_CHAR_H * 0.4, GLYPH_CHAR_H * 0.4, t)
            if abs(local.y - slash_y) < 7.0:
                return true
        return false

    # Colon (time separator): two stacked dots
    if ch == ":":
        if local.distance_to(Vector2(0, -GLYPH_CHAR_H * 0.18)) < 11.0:
            return true
        if local.distance_to(Vector2(0, GLYPH_CHAR_H * 0.18)) < 11.0:
            return true
        return false

    # Period (date separator): single low dot
    if ch == ".":
        if local.distance_to(Vector2(0, GLYPH_CHAR_H * 0.36)) < 12.0:
            return true
        return false

    return false


func _char_width(ch: String) -> float:
    # Narrow characters: ":" and "." are about 25% of digit width
    if ch == ":" or ch == ".":
        return GLYPH_CHAR_W * 0.30
    if ch == "°":
        return GLYPH_CHAR_W * 0.55
    return GLYPH_CHAR_W


func _bake_glyph_targets(text: String, color: Color) -> void:
    if text.length() == 0:
        return

    # Compute character widths and centers (variable-width layout)
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

        # Find character cell containing px
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
        var char_center_x: float = char_centers[cell_idx]
        var local: Vector2 = Vector2(px - char_center_x, py)

        if not _is_in_char_at(local, ch):
            continue

        var jitter := Vector2(
            (randf() - 0.5) * 3.5,
            (randf() - 0.5) * 3.5
        )
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

