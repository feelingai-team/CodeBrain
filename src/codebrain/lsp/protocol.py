"""JSON-RPC 2.0 protocol types and encoding/decoding for LSP communication."""

from __future__ import annotations

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
    raise NotImplementedError


def decode_header(data: bytes) -> tuple[int, int]:
    raise NotImplementedError


def decode_message(data: bytes) -> tuple[dict[str, Any], int]:
    raise NotImplementedError


def parse_response(data: dict[str, Any]) -> JsonRpcResponse:
    raise NotImplementedError


def parse_notification(data: dict[str, Any]) -> JsonRpcNotification:
    raise NotImplementedError


def is_response(data: dict[str, Any]) -> bool:
    raise NotImplementedError


def is_notification(data: dict[str, Any]) -> bool:
    raise NotImplementedError


def is_request(data: dict[str, Any]) -> bool:
    raise NotImplementedError
