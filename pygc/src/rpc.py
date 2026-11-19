"""Small JSON-RPC 2.0 adapter with an explicit public method registry."""

import logging
from collections.abc import Callable
from dataclasses import asdict
from pathlib import Path
from typing import Any

from pydantic import ConfigDict, ValidationError, validate_call

from . import library
from .library.source import browse_source

logger = logging.getLogger(__name__)
METHODS: dict[str, Callable[..., Any]] = {
    "greet": validate_call(config=ConfigDict(strict=True))(library.greet),
}


def repository_methods(directory: Path) -> dict[str, Callable[..., Any]]:
    """Capture selection per app, including when multiple apps share a process."""

    @validate_call(config=ConfigDict(strict=True))
    def context() -> Any:
        match library.get_repository(directory):
            case library.Success(value):
                return asdict(value)
            case failure:
                return failure

    @validate_call(config=ConfigDict(strict=True))
    def source(
        branch: str | None = None,
        path: str = "",
        revision: str | None = None,
        history: bool = False,
        offset: int = 0,
    ) -> Any:
        result = browse_source(directory, branch, path, revision, history, offset)
        return result.value if isinstance(result, library.Success) else result

    def listing(pulls: bool) -> Any:
        result = (
            library.list_pull_requests(directory=directory)
            if pulls
            else library.list_issues(directory=directory)
        )
        if isinstance(result, library.Failure):
            return [] if result.reason == library.FailureReason.NOT_INITIALIZED else result
        return [dict(id=item.id, title=item.title, closed=item.closed) for item in result.value]

    return {
        **METHODS,
        "repo.get": context,
        "code.browse": source,
        "issues.list": validate_call(lambda: listing(False)),
        "pulls.list": validate_call(lambda: listing(True)),
    }


def error(code: int, message: str, request_id: Any = None) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "error": {"code": code, "message": message}, "id": request_id}


def dispatch(
    request: Any, methods: dict[str, Callable[..., Any]] = METHODS
) -> dict[str, Any] | None:
    """Execute a single request; notifications intentionally produce no response."""
    if (
        not isinstance(request, dict)
        or request.get("jsonrpc") != "2.0"
        or not isinstance(request.get("method"), str)
        or ("params" in request and not isinstance(request["params"], (dict, list)))
        or ("id" in request and type(request["id"]) not in (str, int, float, type(None)))
    ):
        return error(-32600, "Invalid Request")

    request_id = request.get("id")
    method = methods.get(request["method"])
    if method is None:
        response = error(-32601, "Method not found", request_id)
    else:
        params = request.get("params", {})
        try:
            result = method(*params) if isinstance(params, list) else method(**params)
            if isinstance(result, library.Failure):
                response = error(-32000, "Repository operation failed", request_id)
                response["error"]["data"] = {"reason": result.reason.value}
            else:
                response = {"jsonrpc": "2.0", "result": result, "id": request_id}
        except (ValidationError, ValueError):
            response = error(-32602, "Invalid params", request_id)
        except Exception:
            logger.exception("JSON-RPC method failed: %s", request["method"])
            response = error(-32603, "Internal error", request_id)
    return response if "id" in request else None


def handle(
    payload: Any, methods: dict[str, Callable[..., Any]] = METHODS
) -> dict[str, Any] | list[dict[str, Any]] | None:
    if isinstance(payload, list):
        if not payload:
            return error(-32600, "Invalid Request")
        responses = [
            response for item in payload if (response := dispatch(item, methods)) is not None
        ]
        return responses or None
    return dispatch(payload, methods)
