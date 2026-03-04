"""Generic LSP client communicating over stdio via JSON-RPC 2.0."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from pathlib import Path
from typing import Any

from lsprotocol import converters
from lsprotocol import types as lsp

from codebrain.lsp.protocol import (
    JsonRpcNotification,
    JsonRpcRequest,
    JsonRpcResponse,
    LSPError,
    decode_message,
    encode_message,
    is_notification,
    is_response,
    parse_notification,
    parse_response,
)

logger = logging.getLogger(__name__)

_converter = converters.get_converter()


class LSPClient:
    """Language Server Protocol client over stdio."""

    REQUEST_TIMEOUT: float = 30.0

    def __init__(
        self,
        server_command: list[str],
        workspace_root: Path,
        notification_handlers: (
            dict[str, Callable[[dict[str, Any] | list[Any]], None]] | None
        ) = None,
    ) -> None:
        self._server_command = server_command
        self._workspace_root = workspace_root
        self._notification_handlers = notification_handlers or {}
        self._process: asyncio.subprocess.Process | None = None
        self._request_id: int = 0
        self._pending_requests: dict[int, asyncio.Future[Any]] = {}
        self._buffer: bytes = b""
        self._reader_task: asyncio.Task[None] | None = None
        self._initialized: bool = False
        self._server_capabilities: lsp.ServerCapabilities | None = None

    @property
    def is_running(self) -> bool:
        return self._process is not None and self._process.returncode is None

    @property
    def server_capabilities(self) -> lsp.ServerCapabilities | None:
        return self._server_capabilities

    # -- Lifecycle --

    async def start(self) -> None:
        self._process = await asyncio.create_subprocess_exec(
            *self._server_command,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        self._reader_task = asyncio.create_task(self._read_loop())
        await self._initialize()

    async def stop(self) -> None:
        if not self.is_running:
            return
        try:
            await self._request("shutdown", None)
            await self._notify("exit", None)
        except Exception:
            logger.debug("Error during shutdown handshake", exc_info=True)

        if self._reader_task is not None:
            self._reader_task.cancel()
            try:
                await asyncio.wait_for(self._reader_task, timeout=2.0)
            except (asyncio.CancelledError, TimeoutError):
                pass
            self._reader_task = None

        if self._process is not None and self._process.returncode is None:
            self._process.terminate()
            try:
                await asyncio.wait_for(self._process.wait(), timeout=5.0)
            except TimeoutError:
                self._process.kill()
            self._process = None

        self._buffer = b""
        self._pending_requests.clear()
        self._initialized = False
        self._server_capabilities = None

    async def _initialize(self) -> None:
        params = lsp.InitializeParams(
            process_id=None,
            root_uri=self._workspace_root.as_uri(),
            capabilities=lsp.ClientCapabilities(
                text_document=lsp.TextDocumentClientCapabilities(
                    synchronization=lsp.TextDocumentSyncClientCapabilities(
                        did_save=True,
                    ),
                    publish_diagnostics=lsp.PublishDiagnosticsClientCapabilities(
                        related_information=True,
                        tag_support=lsp.ClientDiagnosticsTagOptions(
                            value_set=[
                                lsp.DiagnosticTag.Unnecessary,
                                lsp.DiagnosticTag.Deprecated,
                            ],
                        ),
                        version_support=True,
                    ),
                    hover=lsp.HoverClientCapabilities(
                        content_format=[
                            lsp.MarkupKind.Markdown,
                            lsp.MarkupKind.PlainText,
                        ],
                    ),
                    definition=lsp.DefinitionClientCapabilities(
                        link_support=True,
                    ),
                    references=lsp.ReferenceClientCapabilities(),
                    code_action=lsp.CodeActionClientCapabilities(
                        code_action_literal_support=lsp.ClientCodeActionLiteralOptions(
                            code_action_kind=lsp.ClientCodeActionKindOptions(
                                value_set=[
                                    lsp.CodeActionKind.QuickFix,
                                    lsp.CodeActionKind.SourceOrganizeImports,
                                    lsp.CodeActionKind.Source,
                                ],
                            ),
                        ),
                    ),
                ),
            ),
        )
        result = await self._request("initialize", params)
        init_result = _converter.structure(result, lsp.InitializeResult)
        self._server_capabilities = init_result.capabilities
        await self._notify("initialized", lsp.InitializedParams())
        self._initialized = True

    # -- Internal read/write loop --

    async def _read_loop(self) -> None:
        assert self._process is not None and self._process.stdout is not None
        try:
            while True:
                chunk = await self._process.stdout.read(4096)
                if not chunk:
                    break
                self._buffer += chunk
                await self._process_buffer()
        except asyncio.CancelledError:
            return
        except Exception:
            logger.exception("Error in LSP read loop")

    async def _process_buffer(self) -> None:
        while self._buffer:
            try:
                message, consumed = decode_message(self._buffer)
            except ValueError:
                break
            self._buffer = self._buffer[consumed:]
            await self._handle_message(message)

    async def _handle_message(self, message: dict[str, Any]) -> None:
        if is_response(message):
            await self._handle_response(parse_response(message))
        elif is_notification(message):
            await self._handle_notification(parse_notification(message))
        else:
            logger.warning("Unexpected LSP message: %s", message.get("method", "?"))

    async def _handle_response(self, response: JsonRpcResponse) -> None:
        request_id = response.id
        if request_id is None:
            return
        future = self._pending_requests.pop(int(request_id), None)
        if future is None:
            logger.warning("Response for unknown request id: %s", request_id)
            return
        if response.error is not None:
            future.set_exception(
                LSPError(response.error.code, response.error.message, response.error.data)
            )
        else:
            future.set_result(response.result)

    async def _handle_notification(self, notification: JsonRpcNotification) -> None:
        handler = self._notification_handlers.get(notification.method)
        if handler is not None:
            try:
                handler(notification.params or {})
            except Exception:
                logger.exception("Error in notification handler: %s", notification.method)
        else:
            logger.debug("Unhandled notification: %s", notification.method)

    async def _send(self, message: JsonRpcRequest | JsonRpcNotification) -> None:
        assert self._process is not None and self._process.stdin is not None
        data = encode_message(message)
        self._process.stdin.write(data)
        await self._process.stdin.drain()

    async def _request(
        self, method: str, params: Any, timeout: float | None = None
    ) -> Any:
        self._request_id += 1
        request_id = self._request_id

        if params is not None:
            params = _converter.unstructure(params)

        request = JsonRpcRequest(id=request_id, method=method, params=params)
        loop = asyncio.get_running_loop()
        future: asyncio.Future[Any] = loop.create_future()
        self._pending_requests[request_id] = future

        await self._send(request)

        effective_timeout = timeout or self.REQUEST_TIMEOUT
        try:
            return await asyncio.wait_for(future, timeout=effective_timeout)
        except TimeoutError:
            self._pending_requests.pop(request_id, None)
            msg = f"LSP request {method} timed out after {effective_timeout}s"
            raise TimeoutError(msg) from None

    async def _notify(self, method: str, params: Any) -> None:
        if params is not None:
            params = _converter.unstructure(params)
        notification = JsonRpcNotification(method=method, params=params)
        await self._send(notification)

    # -- Helpers --

    def _text_document_id(self, file_path: Path) -> lsp.TextDocumentIdentifier:
        return lsp.TextDocumentIdentifier(uri=file_path.as_uri())

    def _position(self, line: int, character: int) -> lsp.Position:
        return lsp.Position(line=line, character=character)

    def _text_document_position(
        self, file_path: Path, line: int, character: int
    ) -> lsp.TextDocumentPositionParams:
        return lsp.TextDocumentPositionParams(
            text_document=self._text_document_id(file_path),
            position=self._position(line, character),
        )

    # -- Text document synchronization --

    async def did_open(self, file_path: Path, language_id: str, version: int = 1) -> None:
        content = file_path.read_text(encoding="utf-8")
        params = lsp.DidOpenTextDocumentParams(
            text_document=lsp.TextDocumentItem(
                uri=file_path.as_uri(),
                language_id=language_id,
                version=version,
                text=content,
            ),
        )
        await self._notify("textDocument/didOpen", params)

    async def did_change(self, file_path: Path, content: str, version: int) -> None:
        params = lsp.DidChangeTextDocumentParams(
            text_document=lsp.VersionedTextDocumentIdentifier(
                uri=file_path.as_uri(), version=version
            ),
            content_changes=[lsp.TextDocumentContentChangeWholeDocument(text=content)],
        )
        await self._notify("textDocument/didChange", params)

    async def did_close(self, file_path: Path) -> None:
        params = lsp.DidCloseTextDocumentParams(
            text_document=self._text_document_id(file_path),
        )
        await self._notify("textDocument/didClose", params)

    async def did_save(self, file_path: Path) -> None:
        params = lsp.DidSaveTextDocumentParams(
            text_document=self._text_document_id(file_path),
        )
        await self._notify("textDocument/didSave", params)

    # -- Language features --

    async def get_definition(
        self, file_path: Path, line: int, character: int
    ) -> list[lsp.Location] | list[lsp.LocationLink] | None:
        params = lsp.DefinitionParams(
            text_document=self._text_document_id(file_path),
            position=self._position(line, character),
        )
        result = await self._request("textDocument/definition", params)
        if result is None:
            return None
        if isinstance(result, dict):
            return [_converter.structure(result, lsp.Location)]
        if isinstance(result, list) and result:
            first = result[0]
            if isinstance(first, dict) and "targetUri" in first:
                return [_converter.structure(r, lsp.LocationLink) for r in result]
            return [_converter.structure(r, lsp.Location) for r in result]
        return None

    async def get_references(
        self, file_path: Path, line: int, character: int, include_declaration: bool = True
    ) -> list[lsp.Location]:
        params = lsp.ReferenceParams(
            text_document=self._text_document_id(file_path),
            position=self._position(line, character),
            context=lsp.ReferenceContext(include_declaration=include_declaration),
        )
        result = await self._request("textDocument/references", params)
        if result is None or not isinstance(result, list):
            return []
        return [_converter.structure(r, lsp.Location) for r in result]

    async def get_hover(
        self, file_path: Path, line: int, character: int
    ) -> lsp.Hover | None:
        params = lsp.HoverParams(
            text_document=self._text_document_id(file_path),
            position=self._position(line, character),
        )
        result = await self._request("textDocument/hover", params)
        if result is None:
            return None
        return _converter.structure(result, lsp.Hover)

    async def get_code_actions(
        self,
        file_path: Path,
        range_: lsp.Range,
        diagnostics: list[lsp.Diagnostic] | None = None,
        only: list[lsp.CodeActionKind] | None = None,
    ) -> list[lsp.CodeAction | lsp.Command]:
        params = lsp.CodeActionParams(
            text_document=self._text_document_id(file_path),
            range=range_,
            context=lsp.CodeActionContext(
                diagnostics=diagnostics or [],
                only=only,
            ),
        )
        result = await self._request("textDocument/codeAction", params)
        if result is None or not isinstance(result, list):
            return []
        actions: list[lsp.CodeAction | lsp.Command] = []
        for item in result:
            if not isinstance(item, dict):
                continue
            if "edit" in item or "command" in item or "diagnostics" in item:
                try:
                    actions.append(_converter.structure(item, lsp.CodeAction))
                except Exception:
                    actions.append(_converter.structure(item, lsp.Command))
            else:
                try:
                    actions.append(_converter.structure(item, lsp.Command))
                except Exception:
                    actions.append(_converter.structure(item, lsp.CodeAction))
        return actions

    async def resolve_code_action(self, code_action: lsp.CodeAction) -> lsp.CodeAction:
        result = await self._request("codeAction/resolve", code_action)
        return _converter.structure(result, lsp.CodeAction)

    # -- Document symbols --

    async def get_document_symbols(
        self, file_path: Path
    ) -> list[lsp.DocumentSymbol] | list[lsp.SymbolInformation] | None:
        params = lsp.DocumentSymbolParams(
            text_document=self._text_document_id(file_path),
        )
        result = await self._request("textDocument/documentSymbol", params)
        if result is None or not isinstance(result, list):
            return None
        if not result:
            return []
        first = result[0]
        if isinstance(first, dict) and "children" in first:
            return [_converter.structure(r, lsp.DocumentSymbol) for r in result]
        return [_converter.structure(r, lsp.SymbolInformation) for r in result]

    # -- Call hierarchy --

    async def get_call_hierarchy_incoming(
        self, file_path: Path, line: int, character: int
    ) -> list[lsp.CallHierarchyIncomingCall]:
        prepare_params = lsp.CallHierarchyPrepareParams(
            text_document=self._text_document_id(file_path),
            position=self._position(line, character),
        )
        items = await self._request("textDocument/prepareCallHierarchy", prepare_params)
        if not items or not isinstance(items, list):
            return []
        item = _converter.structure(items[0], lsp.CallHierarchyItem)
        result = await self._request(
            "callHierarchy/incomingCalls",
            lsp.CallHierarchyIncomingCallsParams(item=item),
        )
        if not result or not isinstance(result, list):
            return []
        return [_converter.structure(r, lsp.CallHierarchyIncomingCall) for r in result]

    async def get_call_hierarchy_outgoing(
        self, file_path: Path, line: int, character: int
    ) -> list[lsp.CallHierarchyOutgoingCall]:
        prepare_params = lsp.CallHierarchyPrepareParams(
            text_document=self._text_document_id(file_path),
            position=self._position(line, character),
        )
        items = await self._request("textDocument/prepareCallHierarchy", prepare_params)
        if not items or not isinstance(items, list):
            return []
        item = _converter.structure(items[0], lsp.CallHierarchyItem)
        result = await self._request(
            "callHierarchy/outgoingCalls",
            lsp.CallHierarchyOutgoingCallsParams(item=item),
        )
        if not result or not isinstance(result, list):
            return []
        return [_converter.structure(r, lsp.CallHierarchyOutgoingCall) for r in result]

    # -- Type definition --

    async def get_type_definition(
        self, file_path: Path, line: int, character: int
    ) -> list[lsp.Location] | list[lsp.LocationLink] | None:
        params = lsp.TypeDefinitionParams(
            text_document=self._text_document_id(file_path),
            position=self._position(line, character),
        )
        result = await self._request("textDocument/typeDefinition", params)
        if result is None:
            return None
        if isinstance(result, dict):
            return [_converter.structure(result, lsp.Location)]
        if isinstance(result, list) and result:
            first = result[0]
            if isinstance(first, dict) and "targetUri" in first:
                return [_converter.structure(r, lsp.LocationLink) for r in result]
            return [_converter.structure(r, lsp.Location) for r in result]
        return None

    # -- Rename --

    async def prepare_rename(
        self, file_path: Path, line: int, character: int
    ) -> lsp.PrepareRenameResult | None:
        params = lsp.PrepareRenameParams(
            text_document=self._text_document_id(file_path),
            position=self._position(line, character),
        )
        result = await self._request("textDocument/prepareRename", params)
        if result is None:
            return None
        # PrepareRenameResult is a Union — try each type
        if "placeholder" in result:
            return _converter.structure(result, lsp.PrepareRenamePlaceholder)
        if "defaultBehavior" in result:
            return _converter.structure(result, lsp.PrepareRenameDefaultBehavior)
        return _converter.structure(result, lsp.Range)

    async def rename(
        self, file_path: Path, line: int, character: int, new_name: str
    ) -> lsp.WorkspaceEdit | None:
        params = lsp.RenameParams(
            text_document=self._text_document_id(file_path),
            position=self._position(line, character),
            new_name=new_name,
        )
        result = await self._request("textDocument/rename", params)
        if result is None:
            return None
        return _converter.structure(result, lsp.WorkspaceEdit)
