"""Tests for JSON-RPC 2.0 protocol encoding/decoding."""

from __future__ import annotations

import json

import pytest

from codebrain.lsp.protocol import (
    JsonRpcNotification,
    JsonRpcRequest,
    JsonRpcResponse,
    decode_header,
    decode_message,
    encode_message,
    is_notification,
    is_request,
    is_response,
    parse_notification,
    parse_response,
)


class TestEncodeMessage:
    def test_format(self) -> None:
        msg = JsonRpcRequest(id=1, method="initialize", params={"rootUri": "/tmp"})
        encoded = encode_message(msg)
        header, body = encoded.split(b"\r\n\r\n", 1)
        assert header.startswith(b"Content-Length: ")
        content_length = int(header.split(b": ")[1])
        assert content_length == len(body)
        parsed = json.loads(body)
        assert parsed["jsonrpc"] == "2.0"
        assert parsed["method"] == "initialize"
        assert parsed["id"] == 1
        assert parsed["params"] == {"rootUri": "/tmp"}

    def test_excludes_none_fields(self) -> None:
        msg = JsonRpcNotification(method="exit")
        encoded = encode_message(msg)
        _, body = encoded.split(b"\r\n\r\n", 1)
        parsed = json.loads(body)
        assert "params" not in parsed

    def test_response_encoding(self) -> None:
        msg = JsonRpcResponse(id=42, result={"capabilities": {}})
        encoded = encode_message(msg)
        _, body = encoded.split(b"\r\n\r\n", 1)
        parsed = json.loads(body)
        assert parsed["id"] == 42
        assert parsed["result"] == {"capabilities": {}}
        assert "error" not in parsed

    def test_utf8_encoding(self) -> None:
        msg = JsonRpcNotification(method="test", params={"msg": "日本語"})
        encoded = encode_message(msg)
        header, body = encoded.split(b"\r\n\r\n", 1)
        content_length = int(header.split(b": ")[1])
        # UTF-8 bytes may differ from character count
        assert content_length == len(body)
        parsed = json.loads(body)
        assert parsed["params"]["msg"] == "日本語"


class TestDecodeHeader:
    def test_valid_header(self) -> None:
        data = b"Content-Length: 42\r\n\r\nsome content"
        length, offset = decode_header(data)
        assert length == 42
        assert offset == len(b"Content-Length: 42\r\n\r\n")

    def test_case_insensitive(self) -> None:
        data = b"content-length: 10\r\n\r\n0123456789"
        length, offset = decode_header(data)
        assert length == 10

    def test_incomplete_header(self) -> None:
        with pytest.raises(ValueError, match="separator not found"):
            decode_header(b"Content-Length: 42\r\n")

    def test_missing_content_length(self) -> None:
        with pytest.raises(ValueError, match="Missing Content-Length"):
            decode_header(b"Content-Type: application/json\r\n\r\n")

    def test_multiple_headers(self) -> None:
        data = b"Content-Type: json\r\nContent-Length: 5\r\n\r\nhello"
        length, offset = decode_header(data)
        assert length == 5


class TestDecodeMessage:
    def test_round_trip(self) -> None:
        original = JsonRpcRequest(id=1, method="test", params={"key": "value"})
        encoded = encode_message(original)
        parsed, consumed = decode_message(encoded)
        assert consumed == len(encoded)
        assert parsed["method"] == "test"
        assert parsed["id"] == 1
        assert parsed["params"] == {"key": "value"}

    def test_incomplete_body(self) -> None:
        data = b"Content-Length: 100\r\n\r\nshort"
        with pytest.raises(ValueError, match="Incomplete message body"):
            decode_message(data)

    def test_multiple_messages_in_buffer(self) -> None:
        msg1 = JsonRpcNotification(method="a")
        msg2 = JsonRpcNotification(method="b")
        buffer = encode_message(msg1) + encode_message(msg2)
        parsed1, consumed1 = decode_message(buffer)
        assert parsed1["method"] == "a"
        parsed2, consumed2 = decode_message(buffer[consumed1:])
        assert parsed2["method"] == "b"
        assert consumed1 + consumed2 == len(buffer)


class TestMessageTypeDetection:
    def test_is_response(self) -> None:
        assert is_response({"jsonrpc": "2.0", "id": 1, "result": None})
        assert not is_response({"jsonrpc": "2.0", "method": "notify"})
        assert not is_response({"jsonrpc": "2.0", "id": 1, "method": "request"})

    def test_is_notification(self) -> None:
        assert is_notification({"jsonrpc": "2.0", "method": "exit"})
        assert not is_notification({"jsonrpc": "2.0", "id": 1, "result": None})
        assert not is_notification({"jsonrpc": "2.0", "id": 1, "method": "request"})

    def test_is_request(self) -> None:
        assert is_request({"jsonrpc": "2.0", "id": 1, "method": "initialize"})
        assert not is_request({"jsonrpc": "2.0", "method": "exit"})
        assert not is_request({"jsonrpc": "2.0", "id": 1, "result": None})


class TestParsing:
    def test_parse_response_success(self) -> None:
        data = {"jsonrpc": "2.0", "id": 1, "result": {"capabilities": {}}}
        resp = parse_response(data)
        assert isinstance(resp, JsonRpcResponse)
        assert resp.id == 1
        assert resp.result == {"capabilities": {}}
        assert resp.error is None

    def test_parse_response_error(self) -> None:
        data = {
            "jsonrpc": "2.0",
            "id": 1,
            "error": {"code": -32600, "message": "Invalid Request"},
        }
        resp = parse_response(data)
        assert resp.error is not None
        assert resp.error.code == -32600
        assert resp.error.message == "Invalid Request"

    def test_parse_notification(self) -> None:
        data = {
            "jsonrpc": "2.0",
            "method": "textDocument/publishDiagnostics",
            "params": {"uri": "file:///test.py", "diagnostics": []},
        }
        notif = parse_notification(data)
        assert isinstance(notif, JsonRpcNotification)
        assert notif.method == "textDocument/publishDiagnostics"
        assert notif.params == {"uri": "file:///test.py", "diagnostics": []}
