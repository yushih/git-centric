"""Small JSON-RPC 2.0 adapter with an explicit public method registry."""

import logging
from collections.abc import Callable
from typing import Any

from pydantic import ConfigDict, ValidationError, validate_call

from . import library

logger = logging.getLogger(__name__)
METHODS: dict[str, Callable[..., Any]] = {
    "greet": validate_call(config=ConfigDict(strict=True))(library.greet),
}


def error(code: int, message: str, request_id: Any = None) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "error": {"code": code, "message": message}, "id": request_id}


def dispatch(request: Any) -> dict[str, Any] | None:
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
    method = METHODS.get(request["method"])
    if method is None:
        response = error(-32601, "Method not found", request_id)
    else:
        params = request.get("params", {})
        try:
            result = method(*params) if isinstance(params, list) else method(**params)
            response = {"jsonrpc": "2.0", "result": result, "id": request_id}
        except (ValidationError, ValueError):
            response = error(-32602, "Invalid params", request_id)
        except Exception:
            logger.exception("JSON-RPC method failed: %s", request["method"])
            response = error(-32603, "Internal error", request_id)
    return response if "id" in request else None


def handle(payload: Any) -> dict[str, Any] | list[dict[str, Any]] | None:
    if isinstance(payload, list):
        if not payload:
            return error(-32600, "Invalid Request")
        responses = [response for item in payload if (response := dispatch(item)) is not None]
        return responses or None
    return dispatch(payload)
