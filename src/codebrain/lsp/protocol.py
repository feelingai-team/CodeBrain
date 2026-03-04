"""JSON-RPC 2.0 protocol types and encoding/decoding for LSP communication."""

from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel


class LSPError(Exception):
    """Error from the language server."""

    def __init__(self, code: int, message: str, data: Any = None) -> None:
        super().__init__(message)
        self.code = code
        self.data = data


class JsonRpcMessage(BaseModel):
    jsonrpc: str = "2.0"


class JsonRpcRequest(JsonRpcMessage):
    id: int | str
    method: str
    params: dict[str, Any] | list[Any] | None = None


class JsonRpcNotification(JsonRpcMessage):
    method: str
    params: dict[str, Any] | list[Any] | None = None


class JsonRpcResponseError(BaseModel):
    code: int
    message: str
    data: Any = None


class JsonRpcResponse(JsonRpcMessage):
    id: int | str | None = None
    result: Any = None
    error: JsonRpcResponseError | None = None


def encode_message(message: JsonRpcMessage) -> bytes:
    """Encode a JSON-RPC message with Content-Length header."""
    content = message.model_dump_json(exclude_none=True).encode("utf-8")
    header = f"Content-Length: {len(content)}\r\n\r\n".encode("ascii")
    return header + content


def decode_header(data: bytes) -> tuple[int, int]:
    """Parse the Content-Length header from raw bytes.

    Returns (content_length, header_end_offset).
    Raises ValueError if header is incomplete or missing Content-Length.
    """
    separator = b"\r\n\r\n"
    idx = data.find(separator)
    if idx == -1:
        msg = "Incomplete header: separator not found"
        raise ValueError(msg)

    header_bytes = data[:idx]
    header_end = idx + len(separator)

    for line in header_bytes.split(b"\r\n"):
        stripped = line.strip()
        if stripped.lower().startswith(b"content-length:"):
            value = stripped[len(b"content-length:") :].strip()
            return int(value), header_end

    msg = "Missing Content-Length header"
    raise ValueError(msg)


def decode_message(data: bytes) -> tuple[dict[str, Any], int]:
    """Decode a complete JSON-RPC message from a buffer.

    Returns (parsed_dict, total_bytes_consumed).
    Raises ValueError if the message is incomplete.
    """
    content_length, header_end = decode_header(data)

    total = header_end + content_length
    if len(data) < total:
        msg = "Incomplete message body"
        raise ValueError(msg)

    content = data[header_end:total]
    parsed: dict[str, Any] = json.loads(content.decode("utf-8"))
    return parsed, total


def parse_response(data: dict[str, Any]) -> JsonRpcResponse:
    """Validate and structure a dict as a JsonRpcResponse."""
    return JsonRpcResponse.model_validate(data)


def parse_notification(data: dict[str, Any]) -> JsonRpcNotification:
    """Validate and structure a dict as a JsonRpcNotification."""
    return JsonRpcNotification.model_validate(data)


def is_response(data: dict[str, Any]) -> bool:
    """Check if a message dict is a response (has id, no method)."""
    return "id" in data and "method" not in data


def is_notification(data: dict[str, Any]) -> bool:
    """Check if a message dict is a notification (has method, no id)."""
    return "method" in data and "id" not in data


def is_request(data: dict[str, Any]) -> bool:
    """Check if a message dict is a request (has both method and id)."""
    return "method" in data and "id" in data
