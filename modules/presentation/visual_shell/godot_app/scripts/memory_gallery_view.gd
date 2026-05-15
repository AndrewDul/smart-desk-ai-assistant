extends Control

signal close_requested

const PANEL_COLOR = Color(0.004, 0.006, 0.012, 0.90)
const BORDER_COLOR = Color(0.32, 0.58, 0.90, 0.72)
const TITLE_COLOR = Color(0.88, 0.94, 1.0, 1.0)
const SUBTITLE_COLOR = Color(0.58, 0.68, 0.82, 1.0)
const CARD_COLOR = Color(0.018, 0.030, 0.055, 0.88)
const CARD_BORDER_COLOR = Color(0.20, 0.36, 0.62, 0.62)
const CARD_SELECTED_BORDER_COLOR = Color(0.64, 0.84, 1.0, 0.96)
const CAPTION_COLOR = Color(0.94, 0.96, 1.0, 1.0)
const META_COLOR = Color(0.58, 0.68, 0.82, 1.0)
const EMPTY_COLOR = Color(0.64, 0.72, 0.84, 1.0)
const DETAIL_PANEL_COLOR = Color(0.010, 0.017, 0.032, 0.96)
const DETAIL_ROW_COLOR = Color(0.025, 0.039, 0.070, 0.72)
const SCROLLBAR_TRACK_COLOR = Color(0.12, 0.18, 0.30, 0.70)
const SCROLLBAR_THUMB_COLOR = Color(0.52, 0.74, 1.0, 0.92)
const BACK_BUTTON_COLOR = Color(0.08, 0.13, 0.22, 0.92)
const CLOSE_BUTTON_COLOR = Color(0.13, 0.055, 0.075, 0.96)
const CLOSE_BUTTON_BORDER_COLOR = Color(0.98, 0.44, 0.50, 0.88)

const MIN_PANEL_WIDTH = 720.0
const MIN_PANEL_HEIGHT = 430.0
const MAX_PANEL_WIDTH = 1120.0
const MAX_PANEL_HEIGHT = 690.0
const PANEL_MARGIN_X = 46.0
const PANEL_MARGIN_Y = 38.0
const PANEL_PADDING = 28.0
const HEADER_HEIGHT = 76.0
const CARD_WIDTH = 190.0
const CARD_HEIGHT = 220.0
const CARD_GAP = 18.0
const IMAGE_HEIGHT = 146.0
const SCROLLBAR_WIDTH = 10.0
const DETAIL_IMAGE_WIDTH = 330.0
const DETAIL_IMAGE_HEIGHT = 230.0
const DETAIL_ROW_HEIGHT = 34.0

var _language = "en"
var _gallery_kind = "objects"
var _title = "Memory Gallery"
var _subtitle = "Known memory items"
var _items = []
var _panel_rect = Rect2()
var _content_rect = Rect2()
var _back_button_rect = Rect2()
var _close_button_rect = Rect2()
var _scroll_offset = 0.0
var _max_scroll_offset = 0.0
var _detail_scroll_offset = 0.0
var _max_detail_scroll_offset = 0.0
var _selected_index = -1
var _dragging_scrollbar = false
var _dragging_detail_scrollbar = false
var _drag_start_y = 0.0
var _drag_start_scroll = 0.0
var _texture_cache = {}

func _ready() -> void:
    set_process_input(true)
    set_process_unhandled_input(true)
    mouse_filter = Control.MOUSE_FILTER_PASS

func set_gallery_content(language, gallery_kind, title, subtitle, items) -> void:
    _language = String(language if language != null else "en")
    _gallery_kind = String(gallery_kind if gallery_kind != null else "objects")
    _title = String(title if title != null and String(title) != "" else _default_title())
    _subtitle = String(subtitle if subtitle != null and String(subtitle) != "" else _default_subtitle())
    _items = []

    for raw_item in items:
        if typeof(raw_item) == TYPE_DICTIONARY:
            _items.append(raw_item)

    _scroll_offset = 0.0
    _detail_scroll_offset = 0.0
    _selected_index = -1
    _update_scroll_limits()
    update()

func layout_for_viewport(viewport_size) -> void:
    rect_position = Vector2.ZERO
    rect_size = viewport_size

    var panel_width = min(MAX_PANEL_WIDTH, max(MIN_PANEL_WIDTH, viewport_size.x - (PANEL_MARGIN_X * 2.0)))
    var panel_height = min(MAX_PANEL_HEIGHT, max(MIN_PANEL_HEIGHT, viewport_size.y - (PANEL_MARGIN_Y * 2.0)))
    _panel_rect = Rect2(
        Vector2((viewport_size.x - panel_width) * 0.5, (viewport_size.y - panel_height) * 0.5),
        Vector2(panel_width, panel_height)
    )

    _content_rect = Rect2(
        _panel_rect.position + Vector2(PANEL_PADDING, PANEL_PADDING + HEADER_HEIGHT),
        Vector2(
            _panel_rect.size.x - (PANEL_PADDING * 2.0) - SCROLLBAR_WIDTH - 12.0,
            _panel_rect.size.y - (PANEL_PADDING * 2.0) - HEADER_HEIGHT
        )
    )

    _close_button_rect = Rect2(
        Vector2(_panel_rect.position.x + _panel_rect.size.x - PANEL_PADDING - 42.0, _panel_rect.position.y + PANEL_PADDING + 4.0),
        Vector2(42.0, 34.0)
    )

    _back_button_rect = Rect2(
        Vector2(_close_button_rect.position.x - 122.0, _panel_rect.position.y + PANEL_PADDING + 4.0),
        Vector2(112.0, 34.0)
    )

    _update_scroll_limits()
    update()

func _draw() -> void:
    if not visible:
        return

    draw_rect(Rect2(Vector2.ZERO, rect_size), Color(0.0, 0.0, 0.0, 0.34), true)
    draw_rect(_panel_rect, PANEL_COLOR, true)
    draw_rect(_panel_rect, BORDER_COLOR, false, 2.0)

    var font = get_font("font")
    var title_pos = _panel_rect.position + Vector2(PANEL_PADDING, PANEL_PADDING + 24.0)
    draw_string(font, title_pos, _title, TITLE_COLOR)

    var subtitle_pos = _panel_rect.position + Vector2(PANEL_PADDING, PANEL_PADDING + 52.0)
    draw_string(font, subtitle_pos, _subtitle, SUBTITLE_COLOR)
    _draw_close_button(font)

    if _selected_index >= 0 and _selected_index < _items.size():
        _draw_detail(font, _items[_selected_index])
        return

    if _items.empty():
        _draw_empty_state(font)
        return

    _draw_items(font)
    _draw_scrollbar()

func _draw_close_button(font) -> void:
    if _close_button_rect.size.x <= 0.0:
        return
    draw_rect(_close_button_rect, CLOSE_BUTTON_COLOR, true)
    draw_rect(_close_button_rect, CLOSE_BUTTON_BORDER_COLOR, false, 1.0)
    draw_string(font, _close_button_rect.position + Vector2(15.0, 23.0), "X", CAPTION_COLOR)

func _draw_empty_state(font) -> void:
    var text = "No saved items yet."
    if _language.begins_with("pl"):
        text = "Brak zapisanych elementów."
    draw_string(font, _content_rect.position + Vector2(18.0, 48.0), text, EMPTY_COLOR)

func _draw_items(font) -> void:
    var columns = _column_count()
    var x0 = _content_rect.position.x
    var y0 = _content_rect.position.y - _scroll_offset

    for index in range(_items.size()):
        var row = int(index / columns)
        var col = int(index % columns)
        var item_rect = Rect2(
            Vector2(x0 + col * (CARD_WIDTH + CARD_GAP), y0 + row * (CARD_HEIGHT + CARD_GAP)),
            Vector2(CARD_WIDTH, CARD_HEIGHT)
        )

        if item_rect.position.y > _content_rect.position.y + _content_rect.size.y:
            continue
        if item_rect.position.y + item_rect.size.y < _content_rect.position.y:
            continue

        _draw_card(font, item_rect, _items[index], index)

func _draw_card(font, rect, item, index) -> void:
    draw_rect(rect, CARD_COLOR, true)
    var border = CARD_BORDER_COLOR
    if index == _selected_index:
        border = CARD_SELECTED_BORDER_COLOR
    draw_rect(rect, border, false, 1.0)

    var image_rect = Rect2(rect.position + Vector2(10.0, 10.0), Vector2(rect.size.x - 20.0, IMAGE_HEIGHT))
    _draw_image_or_placeholder(font, image_rect, String(item.get("image_path", item.get("path", ""))), "no image")

    var caption = String(item.get("caption", item.get("display_name", item.get("name", "Unknown"))))
    caption = _ellipsize(caption, 22)
    draw_string(font, rect.position + Vector2(12.0, IMAGE_HEIGHT + 36.0), caption, CAPTION_COLOR)

    var meta = String(item.get("kind", _gallery_kind))
    var asset_count = int(item.get("asset_count", 0))
    if asset_count > 0:
        meta += " · " + str(asset_count) + " photo"
        if asset_count != 1:
            meta += "s"
    meta = _ellipsize(meta, 28)
    draw_string(font, rect.position + Vector2(12.0, IMAGE_HEIGHT + 62.0), meta, META_COLOR)

func _draw_detail(font, item) -> void:
    var detail_rect = _content_rect
    draw_rect(detail_rect, DETAIL_PANEL_COLOR, true)
    draw_rect(detail_rect, CARD_SELECTED_BORDER_COLOR, false, 1.0)

    draw_rect(_back_button_rect, BACK_BUTTON_COLOR, true)
    draw_rect(_back_button_rect, CARD_BORDER_COLOR, false, 1.0)
    var back_text = "Back"
    if _language.begins_with("pl"):
        back_text = "Wróć"
    draw_string(font, _back_button_rect.position + Vector2(30.0, 22.0), back_text, CAPTION_COLOR)

    var display_name = String(item.get("display_name", item.get("caption", "Unknown")))
    var kind = String(item.get("kind", _gallery_kind))
    draw_string(font, detail_rect.position + Vector2(22.0, 34.0), _ellipsize(display_name, 38), TITLE_COLOR)
    draw_string(font, detail_rect.position + Vector2(22.0, 62.0), _ellipsize(kind, 60), META_COLOR)

    var image_rect = Rect2(detail_rect.position + Vector2(22.0, 86.0), Vector2(DETAIL_IMAGE_WIDTH, DETAIL_IMAGE_HEIGHT))
    _draw_image_or_placeholder(font, image_rect, String(item.get("image_path", item.get("path", ""))), "no image")

    var facts_rect = Rect2(
        detail_rect.position + Vector2(DETAIL_IMAGE_WIDTH + 48.0, 86.0),
        Vector2(detail_rect.size.x - DETAIL_IMAGE_WIDTH - 78.0, detail_rect.size.y - 116.0)
    )
    _draw_detail_rows(font, facts_rect, item)
    _draw_detail_scrollbar(facts_rect, item)

func _draw_detail_rows(font, facts_rect, item) -> void:
    var rows = _detail_rows_for_item(item)
    if rows.empty():
        var text = "No details saved yet."
        if _language.begins_with("pl"):
            text = "Brak zapisanych szczegółów."
        draw_string(font, facts_rect.position + Vector2(10.0, 28.0), text, EMPTY_COLOR)
        return

    var y = facts_rect.position.y - _detail_scroll_offset
    for row in rows:
        var row_rect = Rect2(Vector2(facts_rect.position.x, y), Vector2(facts_rect.size.x - 18.0, DETAIL_ROW_HEIGHT - 6.0))
        y += DETAIL_ROW_HEIGHT

        if row_rect.position.y > facts_rect.position.y + facts_rect.size.y:
            continue
        if row_rect.position.y + row_rect.size.y < facts_rect.position.y:
            continue

        draw_rect(row_rect, DETAIL_ROW_COLOR, true)
        var label = _ellipsize(String(row.get("label", "")), 18)
        var value = _ellipsize(String(row.get("value", "")), 44)
        draw_string(font, row_rect.position + Vector2(10.0, 21.0), label, META_COLOR)
        draw_string(font, row_rect.position + Vector2(142.0, 21.0), value, CAPTION_COLOR)

func _draw_detail_scrollbar(facts_rect, item) -> void:
    var rows = _detail_rows_for_item(item)
    var content_height = max(float(rows.size()) * DETAIL_ROW_HEIGHT, facts_rect.size.y)
    _max_detail_scroll_offset = max(0.0, content_height - facts_rect.size.y)
    if _max_detail_scroll_offset <= 1.0:
        return

    var track = Rect2(
        Vector2(facts_rect.position.x + facts_rect.size.x - SCROLLBAR_WIDTH, facts_rect.position.y),
        Vector2(SCROLLBAR_WIDTH, facts_rect.size.y)
    )
    draw_rect(track, SCROLLBAR_TRACK_COLOR, true)

    var visible_ratio = clamp(facts_rect.size.y / max(content_height, 1.0), 0.12, 1.0)
    var thumb_height = max(44.0, track.size.y * visible_ratio)
    var scroll_ratio = clamp(_detail_scroll_offset / max(_max_detail_scroll_offset, 1.0), 0.0, 1.0)
    var thumb_y = track.position.y + (track.size.y - thumb_height) * scroll_ratio
    var thumb = Rect2(Vector2(track.position.x, thumb_y), Vector2(track.size.x, thumb_height))
    draw_rect(thumb, SCROLLBAR_THUMB_COLOR, true)

func _draw_image_or_placeholder(font, image_rect, image_path, placeholder) -> void:
    var texture = _texture_for_path(String(image_path))
    if texture != null:
        draw_texture_rect(texture, image_rect, false)
    else:
        draw_rect(image_rect, Color(0.025, 0.035, 0.055, 0.94), true)
        draw_rect(image_rect, Color(0.18, 0.26, 0.42, 0.66), false, 1.0)
        draw_string(font, image_rect.position + Vector2(18.0, image_rect.size.y * 0.5), placeholder, META_COLOR)

func _detail_rows_for_item(item) -> Array:
    var rows = []

    var explicit_rows = item.get("details", [])
    if typeof(explicit_rows) == TYPE_ARRAY:
        for raw_row in explicit_rows:
            if typeof(raw_row) == TYPE_DICTIONARY:
                var label = String(raw_row.get("label", "")).strip_edges()
                var value = String(raw_row.get("value", "")).strip_edges()
                if label != "" and value != "":
                    rows.append({"label": label, "value": value})

    if rows.empty():
        _append_detail_row(rows, "Name", String(item.get("display_name", item.get("caption", "Unknown"))))
        _append_detail_row(rows, "Type", String(item.get("kind", _gallery_kind)))
        var aliases = item.get("aliases", [])
        if typeof(aliases) == TYPE_ARRAY and aliases.size() > 0:
            _append_detail_row(rows, "Aliases", PoolStringArray(aliases).join(", "))
        _append_detail_row(rows, "Photos", str(int(item.get("asset_count", 0))))

    return rows

func _append_detail_row(rows, label, value) -> void:
    var clean_label = String(label).strip_edges()
    var clean_value = String(value).strip_edges()
    if clean_label == "" or clean_value == "":
        return
    rows.append({"label": clean_label, "value": clean_value})

func _texture_for_path(path) -> Texture:
    var cleaned = String(path).strip_edges()
    if cleaned == "":
        return null

    if _texture_cache.has(cleaned):
        return _texture_cache[cleaned]

    var image = Image.new()
    var error = image.load(cleaned)
    if error != OK:
        _texture_cache[cleaned] = null
        return null

    var texture = ImageTexture.new()
    texture.create_from_image(image, Texture.FLAG_FILTER)
    _texture_cache[cleaned] = texture
    return texture

func _input(event) -> void:
    if not visible:
        return

    if event is InputEventMouseButton:
        if event.button_index == BUTTON_WHEEL_UP and event.pressed:
            if _selected_index >= 0:
                _scroll_detail_by(-48.0)
            else:
                _scroll_by(-48.0)
            accept_event()
            return
        if event.button_index == BUTTON_WHEEL_DOWN and event.pressed:
            if _selected_index >= 0:
                _scroll_detail_by(48.0)
            else:
                _scroll_by(48.0)
            accept_event()
            return
        if event.button_index == BUTTON_LEFT:
            if event.pressed:
                if _close_button_rect.has_point(event.position):
                    _request_close()
                    accept_event()
                    return
                if _selected_index >= 0:
                    if _back_button_rect.has_point(event.position):
                        _selected_index = -1
                        _detail_scroll_offset = 0.0
                        update()
                        accept_event()
                        return
                    if _detail_scrollbar_rect().has_point(event.position):
                        _dragging_detail_scrollbar = true
                        _drag_start_y = event.position.y
                        _drag_start_scroll = _detail_scroll_offset
                        accept_event()
                        return
                else:
                    if _scrollbar_rect().has_point(event.position):
                        _dragging_scrollbar = true
                        _drag_start_y = event.position.y
                        _drag_start_scroll = _scroll_offset
                        accept_event()
                        return
                    var clicked_index = _item_index_at_position(event.position)
                    if clicked_index >= 0:
                        _selected_index = clicked_index
                        _detail_scroll_offset = 0.0
                        update()
                        accept_event()
                        return
            else:
                _dragging_scrollbar = false
                _dragging_detail_scrollbar = false

    if event is InputEventKey:
        if event.pressed and not event.echo and event.scancode == KEY_ESCAPE:
            _request_close()
            accept_event()
            return

    if event is InputEventMouseMotion:
        if _dragging_scrollbar:
            var delta = event.position.y - _drag_start_y
            var track_height = max(_scrollbar_rect().size.y, 1.0)
            var content_delta = delta * (_content_height() / track_height)
            _set_scroll(_drag_start_scroll + content_delta)
            accept_event()
            return
        if _dragging_detail_scrollbar:
            var detail_rect = _detail_scrollbar_rect()
            var delta_detail = event.position.y - _drag_start_y
            var track_detail_height = max(detail_rect.size.y, 1.0)
            var detail_delta = delta_detail * ((_max_detail_scroll_offset + detail_rect.size.y) / track_detail_height)
            _set_detail_scroll(_drag_start_scroll + detail_delta)
            accept_event()
            return

func _request_close() -> void:
    _dragging_scrollbar = false
    _dragging_detail_scrollbar = false
    _selected_index = -1
    _scroll_offset = 0.0
    _detail_scroll_offset = 0.0
    emit_signal("close_requested")

func _item_index_at_position(position) -> int:
    var columns = _column_count()
    var x0 = _content_rect.position.x
    var y0 = _content_rect.position.y - _scroll_offset
    for index in range(_items.size()):
        var row = int(index / columns)
        var col = int(index % columns)
        var item_rect = Rect2(
            Vector2(x0 + col * (CARD_WIDTH + CARD_GAP), y0 + row * (CARD_HEIGHT + CARD_GAP)),
            Vector2(CARD_WIDTH, CARD_HEIGHT)
        )
        if item_rect.has_point(position):
            return index
    return -1

func _scroll_by(delta) -> void:
    _set_scroll(_scroll_offset + float(delta))

func _set_scroll(value) -> void:
    _scroll_offset = clamp(float(value), 0.0, _max_scroll_offset)
    update()

func _scroll_detail_by(delta) -> void:
    _set_detail_scroll(_detail_scroll_offset + float(delta))

func _set_detail_scroll(value) -> void:
    _detail_scroll_offset = clamp(float(value), 0.0, _max_detail_scroll_offset)
    update()

func _scrollbar_rect() -> Rect2:
    return Rect2(
        Vector2(_content_rect.position.x + _content_rect.size.x + 8.0, _content_rect.position.y),
        Vector2(SCROLLBAR_WIDTH, _content_rect.size.y)
    )

func _detail_scrollbar_rect() -> Rect2:
    var detail_rect = _content_rect
    var facts_rect = Rect2(
        detail_rect.position + Vector2(DETAIL_IMAGE_WIDTH + 48.0, 86.0),
        Vector2(detail_rect.size.x - DETAIL_IMAGE_WIDTH - 78.0, detail_rect.size.y - 116.0)
    )
    return Rect2(
        Vector2(facts_rect.position.x + facts_rect.size.x - SCROLLBAR_WIDTH, facts_rect.position.y),
        Vector2(SCROLLBAR_WIDTH, facts_rect.size.y)
    )

func _column_count() -> int:
    var calculated = int(floor((_content_rect.size.x + CARD_GAP) / (CARD_WIDTH + CARD_GAP)))
    if calculated < 1:
        return 1
    return calculated

func _content_height() -> float:
    if _items.empty():
        return _content_rect.size.y
    var columns = _column_count()
    var rows = int(ceil(float(_items.size()) / float(columns)))
    return max(_content_rect.size.y, float(rows) * (CARD_HEIGHT + CARD_GAP) - CARD_GAP)

func _update_scroll_limits() -> void:
    _max_scroll_offset = max(0.0, _content_height() - _content_rect.size.y)
    _scroll_offset = clamp(_scroll_offset, 0.0, _max_scroll_offset)

func _draw_scrollbar() -> void:
    if _max_scroll_offset <= 1.0:
        return

    var track = _scrollbar_rect()
    draw_rect(track, SCROLLBAR_TRACK_COLOR, true)

    var content_height = _content_height()
    var visible_ratio = clamp(_content_rect.size.y / max(content_height, 1.0), 0.12, 1.0)
    var thumb_height = max(44.0, track.size.y * visible_ratio)
    var scroll_ratio = clamp(_scroll_offset / max(_max_scroll_offset, 1.0), 0.0, 1.0)
    var thumb_y = track.position.y + (track.size.y - thumb_height) * scroll_ratio
    var thumb = Rect2(Vector2(track.position.x, thumb_y), Vector2(track.size.x, thumb_height))
    draw_rect(thumb, SCROLLBAR_THUMB_COLOR, true)

func _ellipsize(text, max_chars) -> String:
    var clean = String(text)
    if clean.length() <= int(max_chars):
        return clean
    return clean.substr(0, max(0, int(max_chars) - 1)) + "…"

func _default_title() -> String:
    if _gallery_kind == "people":
        if _language.begins_with("pl"):
            return "Znane osoby"
        return "Known people"
    if _language.begins_with("pl"):
        return "Znane obiekty"
    return "Known objects"

func _default_subtitle() -> String:
    if _gallery_kind == "people":
        if _language.begins_with("pl"):
            return "Osoby zapisane w pamięci NeXa. Kliknij kartę, aby zobaczyć szczegóły."
        return "People saved in NeXa memory. Click a card to see details."
    if _language.begins_with("pl"):
        return "Obiekty zapisane w pamięci NeXa. Kliknij kartę, aby zobaczyć szczegóły."
    return "Objects saved in NeXa memory. Click a card to see details."
