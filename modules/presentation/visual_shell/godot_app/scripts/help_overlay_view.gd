extends Control

const SCRIM_COLOR = Color(0.0, 0.0, 0.0, 0.14)
const PANEL_COLOR = Color(0.006, 0.010, 0.024, 0.72)
const PANEL_EDGE_COLOR = Color(0.60, 0.78, 1.0, 0.24)
const PANEL_INNER_EDGE_COLOR = Color(1.0, 1.0, 1.0, 0.055)
const COLUMN_DIVIDER_COLOR = Color(0.62, 0.78, 1.0, 0.16)
const ROW_FILL_COLOR = Color(1.0, 1.0, 1.0, 0.035)
const ROW_ALT_FILL_COLOR = Color(0.38, 0.56, 0.82, 0.040)
const ROW_LINE_COLOR = Color(0.72, 0.84, 1.0, 0.075)
const TITLE_COLOR = Color(0.90, 0.96, 1.0, 1.0)
const SUBTITLE_COLOR = Color(0.58, 0.68, 0.82, 1.0)
const EN_HEADER_COLOR = Color(0.68, 0.86, 1.0, 1.0)
const PL_HEADER_COLOR = Color(0.98, 0.88, 0.62, 1.0)
const COMMAND_COLOR = "#edf6ff"
const DESCRIPTION_COLOR = "#aab7c8"

var _language := "en"
var _english_items := []
var _polish_items := []
var _english_row_labels := []
var _polish_row_labels := []
var _panel_rect := Rect2()
var _left_column_rect := Rect2()
var _right_column_rect := Rect2()
var _rows_top := 0.0
var _row_height := 30.0
var _row_gap := 4.0
var _controls_ready := false
var _title_label: Label = null
var _subtitle_label: Label = null
var _english_header_label: Label = null
var _polish_header_label: Label = null


func _ready() -> void:
    _ensure_controls()


func set_help_content(language: String, english_items: Array, polish_items: Array) -> void:
    _language = String(language).strip_edges().to_lower()
    _english_items = _copy_items(english_items)
    _polish_items = _copy_items(polish_items)
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

    var margin_x = max(38.0, viewport_size.x * 0.052)
    var margin_y = max(32.0, viewport_size.y * 0.055)
    _panel_rect = Rect2(
        Vector2(margin_x, margin_y),
        Vector2(viewport_size.x - (margin_x * 2.0), viewport_size.y - (margin_y * 2.0))
    )

    var padding_x = max(30.0, _panel_rect.size.x * 0.038)
    var padding_y = max(22.0, _panel_rect.size.y * 0.032)
    var title_height = 28.0
    var subtitle_height = 24.0
    var header_height = 28.0
    var header_gap = 14.0
    var column_gap = max(52.0, _panel_rect.size.x * 0.072)
    var column_width = (_panel_rect.size.x - (padding_x * 2.0) - column_gap) * 0.5
    var left_x = _panel_rect.position.x + padding_x
    var right_x = _panel_rect.position.x + _panel_rect.size.x - padding_x - column_width
    var title_y = _panel_rect.position.y + padding_y
    var subtitle_y = title_y + title_height + 3.0
    var header_y = subtitle_y + subtitle_height + header_gap

    _rows_top = header_y + header_height + 10.0
    _left_column_rect = Rect2(Vector2(left_x, _rows_top), Vector2(column_width, 0.0))
    _right_column_rect = Rect2(Vector2(right_x, _rows_top), Vector2(column_width, 0.0))

    var row_count = max(max(_english_items.size(), _polish_items.size()), 1)
    var bottom_padding = max(20.0, _panel_rect.size.y * 0.030)
    var available_rows_height = max(
        120.0,
        _panel_rect.position.y + _panel_rect.size.y - bottom_padding - _rows_top
    )

    _row_gap = 4.0
    _row_height = clamp(
        (available_rows_height - (float(row_count - 1) * _row_gap)) / float(row_count),
        26.0,
        38.0
    )

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

    var divider_x = _panel_rect.position.x + (_panel_rect.size.x * 0.5)
    draw_line(
        Vector2(divider_x, _rows_top - 33.0),
        Vector2(divider_x, _panel_rect.position.y + _panel_rect.size.y - 24.0),
        COLUMN_DIVIDER_COLOR,
        1.0
    )

    var row_count = max(max(_english_items.size(), _polish_items.size()), 1)
    for index in range(row_count):
        var y = _rows_top + float(index) * (_row_height + _row_gap)
        var row_color = ROW_FILL_COLOR
        if index % 2 == 1:
            row_color = ROW_ALT_FILL_COLOR

        draw_rect(Rect2(Vector2(_left_column_rect.position.x, y), Vector2(_left_column_rect.size.x, _row_height)), row_color, true)
        draw_rect(Rect2(Vector2(_right_column_rect.position.x, y), Vector2(_right_column_rect.size.x, _row_height)), row_color, true)


func _ensure_controls() -> void:
    if _controls_ready:
        return

    mouse_filter = Control.MOUSE_FILTER_IGNORE

    _title_label = _make_label("HelpOverlayTitle", Label.ALIGN_CENTER, TITLE_COLOR)
    _subtitle_label = _make_label("HelpOverlaySubtitle", Label.ALIGN_CENTER, SUBTITLE_COLOR)
    _english_header_label = _make_label("HelpOverlayEnglishHeader", Label.ALIGN_LEFT, EN_HEADER_COLOR)
    _polish_header_label = _make_label("HelpOverlayPolishHeader", Label.ALIGN_LEFT, PL_HEADER_COLOR)

    _english_header_label.text = "ENGLISH"
    _polish_header_label.text = "POLSKI"

    add_child(_title_label)
    add_child(_subtitle_label)
    add_child(_english_header_label)
    add_child(_polish_header_label)

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
        add_child(english_label)

    for index in range(_polish_items.size()):
        var polish_label = _make_command_row_label(
            "HelpOverlayPolishRow%d" % index,
            _polish_items[index]
        )
        _polish_row_labels.append(polish_label)
        add_child(polish_label)


func _clear_rows(rows: Array) -> void:
    for row in rows:
        if is_instance_valid(row):
            row.queue_free()

    rows.clear()


func _layout_rows(rows: Array, x: float, width: float) -> void:
    for index in range(rows.size()):
        var row = rows[index]
        if not is_instance_valid(row):
            continue

        var y = _rows_top + float(index) * (_row_height + _row_gap)
        row.rect_position = Vector2(x + 12.0, y + 3.0)
        row.rect_size = Vector2(max(80.0, width - 24.0), max(18.0, _row_height - 4.0))


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
        return "Podstawowe komendy głosowe. Angielski po lewej, polski po prawej."

    return "Core voice commands. English on the left, Polish on the right."
