from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from pygc import greet
from pygc.cli import app
from pygc.web import create_app

client = TestClient(create_app())
runner = CliRunner()


def test_library_and_cli() -> None:
    assert greet(" Ada ") == "Hello, Ada!"
    result = runner.invoke(app, ["greet", "Ada"])
    assert result.exit_code == 0
    assert result.stdout.strip() == greet("Ada")
    assert runner.invoke(app, ["greet", " "]).exit_code == 2
    with pytest.raises(ValueError):
        greet(" ")


def test_help_and_web() -> None:
    for args in (["help"], ["--help"]):
        result = runner.invoke(app, args)
        assert result.exit_code == 0
        assert "greet" in result.stdout and "web" in result.stdout
    with patch("pygc.cli.uvicorn.run") as run:
        assert runner.invoke(app, ["web", "--port", "9000", "--reload"]).exit_code == 0
        run.assert_called_once_with(
            "pygc.web:create_app", factory=True, host="127.0.0.1", port=9000, reload=True
        )


@pytest.mark.parametrize("params", [{"name": "Ada"}, ["Ada"], {}])
def test_rpc_success(params: object) -> None:
    response = client.post(
        "/api/rpc", json={"jsonrpc": "2.0", "method": "greet", "params": params, "id": 1}
    )
    assert response.json() == {
        "jsonrpc": "2.0",
        "result": greet("world" if params == {} else "Ada"),
        "id": 1,
    }


@pytest.mark.parametrize(
    ("payload", "code"),
    [
        ({"jsonrpc": "2.0", "method": "missing", "id": 1}, -32601),
        ({"jsonrpc": "2.0", "method": "greet", "params": {"name": 1}, "id": 1}, -32602),
        ({"jsonrpc": "2.0", "method": "greet", "params": {"extra": 1}, "id": 1}, -32602),
        ({"jsonrpc": "2.0", "method": "greet", "params": [" "], "id": 1}, -32602),
        ({"jsonrpc": "2.0", "method": "greet", "id": True}, -32600),
        ({"jsonrpc": "2.0", "method": "greet", "params": None, "id": 1}, -32600),
        ([], -32600),
        (42, -32600),
    ],
)
def test_rpc_errors(payload: object, code: int) -> None:
    assert client.post("/api/rpc", json=payload).json()["error"]["code"] == code


def test_parse_error() -> None:
    assert client.post("/api/rpc", content="{").json()["error"]["code"] == -32700


def test_notifications_and_batches() -> None:
    notification = {"jsonrpc": "2.0", "method": "greet"}
    for payload in (notification, [notification], {**notification, "method": "missing"}):
        response = client.post("/api/rpc", json=payload)
        assert response.status_code == 204
        assert response.content == b""
    response = client.post("/api/rpc", json=[notification, {**notification, "id": "a"}, 1])
    assert response.json() == [
        {"jsonrpc": "2.0", "result": greet(), "id": "a"},
        {"jsonrpc": "2.0", "error": {"code": -32600, "message": "Invalid Request"}, "id": None},
    ]


def test_internal_error_is_not_leaked() -> None:
    with patch.dict("pygc.rpc.METHODS", {"greet": lambda: 1 / 0}):
        response = client.post("/api/rpc", json={"jsonrpc": "2.0", "method": "greet", "id": 1})
    assert response.json()["error"] == {"code": -32603, "message": "Internal error"}


def test_frontend_hosting(tmp_path) -> None:
    missing = TestClient(create_app(tmp_path))
    assert "npm run build" in missing.get("/").text
    (tmp_path / "index.html").write_text("<h1>SPA</h1>")
    built = TestClient(create_app(tmp_path))
    assert built.get("/").text == "<h1>SPA</h1>"
    assert built.get("/api/missing").status_code == 404
    assert built.get("/missing.js").status_code == 404
