extends Control

const SCRIM_COLOR = Color(0.0, 0.0, 0.0, 0.20)
const PANEL_COLOR = Color(0.006, 0.010, 0.024, 0.80)
const PANEL_EDGE_COLOR = Color(0.60, 0.78, 1.0, 0.32)
const PANEL_INNER_EDGE_COLOR = Color(1.0, 1.0, 1.0, 0.075)
const COLUMN_DIVIDER_COLOR = Color(0.62, 0.78, 1.0, 0.20)
const ROW_FILL_COLOR = Color(1.0, 1.0, 1.0, 0.048)
const ROW_ALT_FILL_COLOR = Color(0.38, 0.56, 0.82, 0.060)
const ROW_LINE_COLOR = Color(0.72, 0.84, 1.0, 0.095)
const TITLE_COLOR = Color(0.90, 0.96, 1.0, 1.0)
const SUBTITLE_COLOR = Color(0.64, 0.76, 0.90, 1.0)
const EN_HEADER_COLOR = Color(0.68, 0.86, 1.0, 1.0)
const PL_HEADER_COLOR = Color(0.98, 0.88, 0.62, 1.0)
const COMMAND_COLOR = "#f4faff"
const DESCRIPTION_COLOR = "#c8d4e4"

const ROW_HEIGHT = 72.0
const ROW_GAP = 8.0
const ROW_HORIZONTAL_INSET = 14.0
const ROW_VERTICAL_INSET = 8.0
const SCROLLBAR_WIDTH = 26.0
const SCROLLBAR_GAP = 16.0
const SCROLL_WHEEL_STEP_ROWS = 2.0
const SCROLLBAR_TRACK_COLOR = Color(0.58, 0.76, 1.0, 0.24)
const SCROLLBAR_THUMB_COLOR = Color(0.82, 0.96, 1.0, 0.90)
const SCROLLBAR_THUMB_EDGE_COLOR = Color(1.0, 1.0, 1.0, 0.24)

var _language := "en"
var _english_items := []
var _polish_items := []
var _english_row_labels := []
var _polish_row_labels := []
var _panel_rect := Rect2()
var _rows_viewport_rect := Rect2()
var _scrollbar_rect := Rect2()
var _left_column_rect := Rect2()
var _right_column_rect := Rect2()
var _rows_top := 0.0
var _row_height := ROW_HEIGHT
var _row_gap := ROW_GAP
var _content_height := 0.0
var _scroll_offset := 0.0
var _max_scroll_offset := 0.0
var _is_scrollbar_dragging := false
var _is_content_dragging := false
var _drag_start_y := 0.0
var _drag_start_scroll_offset := 0.0
var _controls_ready := false
var _title_label: Label = null
var _subtitle_label: Label = null
var _english_header_label: Label = null
var _polish_header_label: Label = null
var _rows_clip: Control = null
var _scrollbar_hit_area: Control = null


func _ready() -> void:
    _ensure_controls()


func set_help_content(language: String, english_items: Array, polish_items: Array) -> void:
    _language = String(language).strip_edges().to_lower()
    _english_items = _copy_items(english_items)
    _polish_items = _copy_items(polish_items)
    _scroll_offset = 0.0
    _ensure_controls()
    _rebuild_rows()
    layout_for_viewport(get_viewport_rect().size)
    update()


func layout_for_viewport(viewport_size: Vector2) -> void:
    _ensure_controls()

    if viewport_size.x <= 0.0 or viewport_size.y <= 0.0:
        return

    rect_position = Vector2.ZERO
    rect_size = viewport_size

    var margin_x = max(28.0, viewport_size.x * 0.036)
    var margin_y = max(18.0, viewport_size.y * 0.030)
    _panel_rect = Rect2(
        Vector2(margin_x, margin_y),
        Vector2(viewport_size.x - (margin_x * 2.0), viewport_size.y - (margin_y * 2.0))
    )

    var padding_x = max(24.0, _panel_rect.size.x * 0.030)
    var padding_y = max(16.0, _panel_rect.size.y * 0.026)
    var title_height = 24.0
    var subtitle_height = 22.0
    var header_height = 28.0
    var header_gap = 10.0
    var column_gap = max(36.0, _panel_rect.size.x * 0.046)
    var table_width = _panel_rect.size.x - (padding_x * 2.0) - SCROLLBAR_WIDTH - SCROLLBAR_GAP
    var column_width = max(120.0, (table_width - column_gap) * 0.5)
    var left_x = _panel_rect.position.x + padding_x
    var right_x = left_x + column_width + column_gap
    var scrollbar_x = _panel_rect.position.x + _panel_rect.size.x - padding_x - SCROLLBAR_WIDTH
    var title_y = _panel_rect.position.y + padding_y
    var subtitle_y = title_y + title_height + 3.0
    var header_y = subtitle_y + subtitle_height + header_gap

    _rows_top = header_y + header_height + 8.0
    _left_column_rect = Rect2(Vector2(left_x, _rows_top), Vector2(column_width, 0.0))
    _right_column_rect = Rect2(Vector2(right_x, _rows_top), Vector2(column_width, 0.0))

    var bottom_padding = max(18.0, _panel_rect.size.y * 0.026)
    var rows_visible_height = max(
        150.0,
        _panel_rect.position.y + _panel_rect.size.y - bottom_padding - _rows_top
    )

    _row_gap = ROW_GAP
    _row_height = ROW_HEIGHT
    _content_height = _calculate_content_height()
    _rows_viewport_rect = Rect2(Vector2(left_x, _rows_top), Vector2(table_width, rows_visible_height))
    _scrollbar_rect = Rect2(Vector2(scrollbar_x, _rows_top), Vector2(SCROLLBAR_WIDTH, rows_visible_height))
    _max_scroll_offset = max(0.0, _content_height - rows_visible_height)
    _scroll_offset = clamp(_scroll_offset, 0.0, _max_scroll_offset)

    _title_label.text = _title_text()
    _title_label.rect_position = Vector2(_panel_rect.position.x + padding_x, title_y)
    _title_label.rect_size = Vector2(_panel_rect.size.x - (padding_x * 2.0), title_height)

    _subtitle_label.text = _subtitle_text()
    _subtitle_label.rect_position = Vector2(_panel_rect.position.x + padding_x, subtitle_y)
    _subtitle_label.rect_size = Vector2(_panel_rect.size.x - (padding_x * 2.0), subtitle_height)

    _english_header_label.rect_position = Vector2(left_x, header_y)
    _english_header_label.rect_size = Vector2(column_width, header_height)

    _polish_header_label.rect_position = Vector2(right_x, header_y)
    _polish_header_label.rect_size = Vector2(column_width, header_height)

    _rows_clip.rect_position = _rows_viewport_rect.position
    _rows_clip.rect_size = _rows_viewport_rect.size

    _scrollbar_hit_area.rect_position = _scrollbar_rect.position
    _scrollbar_hit_area.rect_size = _scrollbar_rect.size
    _scrollbar_hit_area.visible = _max_scroll_offset > 0.0

    _layout_rows(_english_row_labels, _left_column_rect.position.x, column_width)
    _layout_rows(_polish_row_labels, _right_column_rect.position.x, column_width)
    update()


func _draw() -> void:
    if _panel_rect.size.x <= 0.0 or _panel_rect.size.y <= 0.0:
        return

    draw_rect(Rect2(Vector2.ZERO, rect_size), SCRIM_COLOR, true)
    draw_rect(_panel_rect, PANEL_COLOR, true)
    draw_rect(_panel_rect, PANEL_EDGE_COLOR, false, 1.0)

    var inner_rect = Rect2(_panel_rect.position + Vector2(1.0, 1.0), _panel_rect.size - Vector2(2.0, 2.0))
    draw_rect(inner_rect, PANEL_INNER_EDGE_COLOR, false, 1.0)

    var header_line_y = _rows_top - 9.0
    draw_line(
        Vector2(_panel_rect.position.x + 30.0, header_line_y),
        Vector2(_panel_rect.position.x + _panel_rect.size.x - 30.0, header_line_y),
        ROW_LINE_COLOR,
        1.0
    )

    var divider_x = _left_column_rect.position.x + _left_column_rect.size.x + ((_right_column_rect.position.x - (_left_column_rect.position.x + _left_column_rect.size.x)) * 0.5)
    draw_line(
        Vector2(divider_x, _rows_top - 36.0),
        Vector2(divider_x, _rows_viewport_rect.position.y + _rows_viewport_rect.size.y),
        COLUMN_DIVIDER_COLOR,
        1.0
    )

    draw_rect(_rows_viewport_rect, Color(0.0, 0.0, 0.0, 0.12), true)
    draw_rect(_rows_viewport_rect, ROW_LINE_COLOR, false, 1.0)
    _draw_visible_rows()
    _draw_manual_scrollbar()


func _gui_input(event: InputEvent) -> void:
    if _max_scroll_offset <= 0.0:
        return

    if event is InputEventMouseButton:
        _handle_mouse_button(event)
        return

    if event is InputEventMouseMotion:
        _handle_mouse_motion(event)
        return

    if event is InputEventScreenTouch:
        _handle_screen_touch(event)
        return

    if event is InputEventScreenDrag:
        _handle_screen_drag(event)


func _handle_mouse_button(event: InputEventMouseButton) -> void:
    if event.button_index == BUTTON_WHEEL_UP and _panel_rect.has_point(event.position):
        _set_scroll_offset(_scroll_offset - (_row_height + _row_gap) * SCROLL_WHEEL_STEP_ROWS)
        accept_event()
        return

    if event.button_index == BUTTON_WHEEL_DOWN and _panel_rect.has_point(event.position):
        _set_scroll_offset(_scroll_offset + (_row_height + _row_gap) * SCROLL_WHEEL_STEP_ROWS)
        accept_event()
        return

    if event.button_index != BUTTON_LEFT:
        return

    if event.pressed and _scrollbar_rect.has_point(event.position):
        _is_scrollbar_dragging = true
        _is_content_dragging = false
        _drag_start_y = event.position.y
        _drag_start_scroll_offset = _scroll_offset
        _jump_scrollbar_thumb_to(event.position.y)
        accept_event()
        return

    if event.pressed and _rows_viewport_rect.has_point(event.position):
        _is_content_dragging = true
        _is_scrollbar_dragging = false
        _drag_start_y = event.position.y
        _drag_start_scroll_offset = _scroll_offset
        accept_event()
        return

    if not event.pressed:
        _is_scrollbar_dragging = false
        _is_content_dragging = false
        accept_event()


func _handle_mouse_motion(event: InputEventMouseMotion) -> void:
    if _is_scrollbar_dragging:
        _drag_scrollbar_to(event.position.y)
        accept_event()
        return

    if _is_content_dragging:
        _set_scroll_offset(_drag_start_scroll_offset - (event.position.y - _drag_start_y))
        accept_event()


func _handle_screen_touch(event: InputEventScreenTouch) -> void:
    if event.pressed and (_rows_viewport_rect.has_point(event.position) or _scrollbar_rect.has_point(event.position)):
        _is_content_dragging = true
        _is_scrollbar_dragging = false
        _drag_start_y = event.position.y
        _drag_start_scroll_offset = _scroll_offset
        accept_event()
        return

    if not event.pressed:
        _is_content_dragging = false
        _is_scrollbar_dragging = false
        accept_event()


func _handle_screen_drag(event: InputEventScreenDrag) -> void:
    if not _is_content_dragging:
        return

    _set_scroll_offset(_scroll_offset - event.relative.y)
    accept_event()


func _ensure_controls() -> void:
    if _controls_ready:
        return

    mouse_filter = Control.MOUSE_FILTER_STOP
    rect_clip_content = false

    _title_label = _make_label("HelpOverlayTitle", Label.ALIGN_CENTER, TITLE_COLOR)
    _subtitle_label = _make_label("HelpOverlaySubtitle", Label.ALIGN_CENTER, SUBTITLE_COLOR)
    _english_header_label = _make_label("HelpOverlayEnglishHeader", Label.ALIGN_LEFT, EN_HEADER_COLOR)
    _polish_header_label = _make_label("HelpOverlayPolishHeader", Label.ALIGN_LEFT, PL_HEADER_COLOR)

    _english_header_label.text = "ENGLISH"
    _polish_header_label.text = "POLSKI"

    _rows_clip = Control.new()
    _rows_clip.name = "HelpOverlayRowsClip"
    _rows_clip.mouse_filter = Control.MOUSE_FILTER_IGNORE
    _rows_clip.rect_clip_content = true

    _scrollbar_hit_area = Control.new()
    _scrollbar_hit_area.name = "HelpOverlayScrollBar"
    _scrollbar_hit_area.mouse_filter = Control.MOUSE_FILTER_IGNORE

    add_child(_title_label)
    add_child(_subtitle_label)
    add_child(_english_header_label)
    add_child(_polish_header_label)
    add_child(_rows_clip)
    add_child(_scrollbar_hit_area)

    _controls_ready = true


func _make_label(name: String, alignment: int, color: Color) -> Label:
    var label = Label.new()
    label.name = name
    label.align = alignment
    label.valign = Label.VALIGN_CENTER
    label.clip_text = true
    label.mouse_filter = Control.MOUSE_FILTER_IGNORE
    label.add_color_override("font_color", color)
    return label


func _make_command_row_label(name: String, item: Dictionary) -> RichTextLabel:
    var label = RichTextLabel.new()
    label.name = name
    label.bbcode_enabled = true
    label.scroll_active = false
    label.scroll_following = false
    label.mouse_filter = Control.MOUSE_FILTER_IGNORE
    label.rect_clip_content = true
    label.add_constant_override("line_separation", 3)
    label.bbcode_text = _format_item(item)
    return label


func _copy_items(items: Array) -> Array:
    var copied := []

    for item in items:
        if typeof(item) == TYPE_DICTIONARY:
            copied.append({
                "command": String(item.get("command", "")).strip_edges(),
                "description": String(item.get("description", "")).strip_edges()
            })
        else:
            copied.append({
                "command": String(item).strip_edges(),
                "description": ""
            })

    return copied


func _rebuild_rows() -> void:
    _clear_rows(_english_row_labels)
    _clear_rows(_polish_row_labels)

    for index in range(_english_items.size()):
        var english_label = _make_command_row_label(
            "HelpOverlayEnglishRow%d" % index,
            _english_items[index]
        )
        _english_row_labels.append(english_label)
        _rows_clip.add_child(english_label)

    for index in range(_polish_items.size()):
        var polish_label = _make_command_row_label(
            "HelpOverlayPolishRow%d" % index,
            _polish_items[index]
        )
        _polish_row_labels.append(polish_label)
        _rows_clip.add_child(polish_label)


func _clear_rows(rows: Array) -> void:
    for row in rows:
        if is_instance_valid(row):
            row.queue_free()

    rows.clear()


func _layout_rows(rows: Array, column_x: float, column_width: float) -> void:
    for index in range(rows.size()):
        var row = rows[index]
        if not is_instance_valid(row):
            continue

        var y = float(index) * (_row_height + _row_gap) - _scroll_offset
        row.rect_position = Vector2(
            column_x - _rows_viewport_rect.position.x + ROW_HORIZONTAL_INSET,
            y + ROW_VERTICAL_INSET
        )
        row.rect_size = Vector2(
            max(80.0, column_width - (ROW_HORIZONTAL_INSET * 2.0)),
            max(28.0, _row_height - (ROW_VERTICAL_INSET * 2.0))
        )
        row.rect_clip_content = true
        row.visible = y + _row_height >= 0.0 and y <= _rows_viewport_rect.size.y


func _calculate_content_height() -> float:
    var row_count = max(max(_english_items.size(), _polish_items.size()), 1)
    return (float(row_count) * _row_height) + (float(max(0, row_count - 1)) * _row_gap)


func _draw_visible_rows() -> void:
    if _rows_viewport_rect.size.y <= 0.0:
        return

    var row_count = max(max(_english_items.size(), _polish_items.size()), 1)
    var clip_top = _rows_viewport_rect.position.y
    var clip_bottom = _rows_viewport_rect.position.y + _rows_viewport_rect.size.y

    for index in range(row_count):
        var y = _rows_top + float(index) * (_row_height + _row_gap) - _scroll_offset
        var row_bottom = y + _row_height

        if row_bottom < clip_top or y > clip_bottom:
            continue

        var visible_y = max(y, clip_top)
        var visible_bottom = min(row_bottom, clip_bottom)
        var visible_height = visible_bottom - visible_y

        if visible_height <= 0.0:
            continue

        var row_color = ROW_FILL_COLOR
        if index % 2 == 1:
            row_color = ROW_ALT_FILL_COLOR

        draw_rect(
            Rect2(Vector2(_left_column_rect.position.x, visible_y), Vector2(_left_column_rect.size.x, visible_height)),
            row_color,
            true
        )
        draw_rect(
            Rect2(Vector2(_right_column_rect.position.x, visible_y), Vector2(_right_column_rect.size.x, visible_height)),
            row_color,
            true
        )


func _draw_manual_scrollbar() -> void:
    if _max_scroll_offset <= 0.0:
        return

    draw_rect(_scrollbar_rect, SCROLLBAR_TRACK_COLOR, true)
    draw_rect(_scrollbar_rect, ROW_LINE_COLOR, false, 1.0)

    var thumb_rect = _scrollbar_thumb_rect()
    draw_rect(thumb_rect, SCROLLBAR_THUMB_COLOR, true)
    draw_rect(thumb_rect, SCROLLBAR_THUMB_EDGE_COLOR, false, 1.0)


func _scrollbar_thumb_rect() -> Rect2:
    if _max_scroll_offset <= 0.0 or _content_height <= 0.0:
        return Rect2(_scrollbar_rect.position, Vector2(_scrollbar_rect.size.x, _scrollbar_rect.size.y))

    var thumb_ratio = clamp(_rows_viewport_rect.size.y / max(_content_height, 1.0), 0.14, 1.0)
    var thumb_height = max(54.0, _scrollbar_rect.size.y * thumb_ratio)
    var movable_height = max(1.0, _scrollbar_rect.size.y - thumb_height)
    var thumb_y = _scrollbar_rect.position.y + movable_height * (_scroll_offset / max(_max_scroll_offset, 1.0))

    return Rect2(
        Vector2(_scrollbar_rect.position.x + 5.0, thumb_y),
        Vector2(max(8.0, _scrollbar_rect.size.x - 10.0), thumb_height)
    )


func _jump_scrollbar_thumb_to(global_y: float) -> void:
    var thumb_rect = _scrollbar_thumb_rect()
    var movable_height = max(1.0, _scrollbar_rect.size.y - thumb_rect.size.y)
    var local_y = clamp(global_y - _scrollbar_rect.position.y - (thumb_rect.size.y * 0.5), 0.0, movable_height)
    _set_scroll_offset((local_y / movable_height) * _max_scroll_offset)
    _drag_start_y = global_y
    _drag_start_scroll_offset = _scroll_offset


func _drag_scrollbar_to(global_y: float) -> void:
    var thumb_rect = _scrollbar_thumb_rect()
    var movable_height = max(1.0, _scrollbar_rect.size.y - thumb_rect.size.y)
    var delta = global_y - _drag_start_y
    var next_offset = _drag_start_scroll_offset + ((delta / movable_height) * _max_scroll_offset)
    _set_scroll_offset(next_offset)


func _set_scroll_offset(value: float) -> void:
    var next_offset = clamp(value, 0.0, _max_scroll_offset)

    if abs(next_offset - _scroll_offset) < 0.01:
        return

    _scroll_offset = next_offset
    _layout_rows(_english_row_labels, _left_column_rect.position.x, _left_column_rect.size.x)
    _layout_rows(_polish_row_labels, _right_column_rect.position.x, _right_column_rect.size.x)
    update()


func _format_item(item: Dictionary) -> String:
    var command = _escape_bbcode(String(item.get("command", "")).strip_edges())
    var description = _escape_bbcode(String(item.get("description", "")).strip_edges())

    if description == "":
        return "[b][color=" + COMMAND_COLOR + "]" + command + "[/color][/b]"

    return "[b][color=" + COMMAND_COLOR + "]" + command + "[/color][/b]\n[color=" + DESCRIPTION_COLOR + "]" + description + "[/color]"


func _escape_bbcode(value: String) -> String:
    return value.replace("[", "[lb]").replace("]", "[rb]")


func _title_text() -> String:
    if _language.begins_with("pl"):
        return "KOMENDY NEXA"

    return "NEXA COMMANDS"


func _subtitle_text() -> String:
    if _language.begins_with("pl"):
        return "Komendy głosowe. Angielski po lewej, polski po prawej. Użyj suwaka po prawej stronie tabeli."

    return "Voice commands. English on the left, Polish on the right. Use the scrollbar on the right side of the table."
