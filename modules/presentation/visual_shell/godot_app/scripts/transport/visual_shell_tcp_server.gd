extends Node

signal visual_message_received(message)
signal visual_transport_error(error_message)

export(int) var port = 8765
export(String) var bind_address = "127.0.0.1"
export(int) var max_clients = 8

var server = TCP_Server.new()
var clients = []
var is_running = false


func _ready() -> void:
	start()


func _exit_tree() -> void:
	stop()


func start() -> void:
	if is_running:
		return

	var result = server.listen(port, bind_address)
	if result != OK:
		emit_signal(
			"visual_transport_error",
			"Visual Shell TCP receiver failed to listen on "
				+ bind_address
				+ ":"
				+ str(port)
				+ " error="
				+ str(result)
		)
		return

	is_running = true
	set_process(true)

	print(
		"Visual Shell TCP receiver listening on ",
		bind_address,
		":",
		port
	)


func stop() -> void:
	for client in clients:
		var peer = client.get("peer", null)
		if peer != null:
			peer.disconnect_from_host()

	clients.clear()

	if is_running:
		server.stop()

	is_running = false
	set_process(false)


func _process(_delta: float) -> void:
	if not is_running:
		return

	_accept_pending_clients()
	_poll_clients()


func _accept_pending_clients() -> void:
	while server.is_connection_available():
		if clients.size() >= max_clients:
			var rejected_peer = server.take_connection()
			if rejected_peer != null:
				rejected_peer.disconnect_from_host()

			emit_signal(
				"visual_transport_error",
				"Visual Shell TCP receiver rejected client: max client limit reached."
			)
			return

		var peer = server.take_connection()
		if peer != null:
			clients.append({
				"peer": peer,
				"buffer": "",
			})


func _poll_clients() -> void:
	var remaining_clients = []

	for client in clients:
		var peer = client.get("peer", null)
		if peer == null:
			continue

		var available_bytes = peer.get_available_bytes()
		if available_bytes > 0:
			var chunk = peer.get_utf8_string(available_bytes)
			client["buffer"] = String(client.get("buffer", "")) + chunk
			_consume_client_buffer(client)

		if _should_keep_client(client):
			remaining_clients.append(client)
		else:
			peer.disconnect_from_host()

	clients = remaining_clients


func _should_keep_client(client: Dictionary) -> bool:
	var peer = client.get("peer", null)
	if peer == null:
		return false

	var buffer = String(client.get("buffer", ""))
	if buffer.length() > 0:
		return true

	return peer.get_status() == StreamPeerTCP.STATUS_CONNECTED


func _consume_client_buffer(client: Dictionary) -> void:
	var buffer = String(client.get("buffer", ""))

	while true:
		var newline_index = buffer.find("\n")
		if newline_index < 0:
			break

		var raw_line = buffer.substr(0, newline_index).strip_edges()
		var next_start = newline_index + 1
		buffer = buffer.substr(next_start, buffer.length() - next_start)

		if raw_line.length() > 0:
			_parse_and_emit_message(raw_line)

	client["buffer"] = buffer


func _parse_and_emit_message(raw_line: String) -> void:
	var parse_result = JSON.parse(raw_line)

	if parse_result.error != OK:
		emit_signal(
			"visual_transport_error",
			"Invalid Visual Shell JSON message: " + raw_line
		)
		return

	var message = parse_result.result
	if typeof(message) != TYPE_DICTIONARY:
		emit_signal(
			"visual_transport_error",
			"Visual Shell TCP message must be a JSON object."
		)
		return

	emit_signal("visual_message_received", message)
