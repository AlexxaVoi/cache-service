import io
import json

import httpx
import pytest
from fastapi.testclient import TestClient

from app import cli
from app.models import TransformedString
from main import app

RealClient = httpx.Client


def make_settings(*args: str) -> cli.CliSettings:
    return cli.CliSettings(_cli_parse_args=list(args))


@pytest.fixture
def api_client() -> TestClient:
    return TestClient(app, base_url="http://testserver/")


@pytest.fixture
def use_real_app(monkeypatch, api_client):
    monkeypatch.setattr(cli.httpx, "Client", lambda **kwargs: api_client)


def mock_client(handler) -> httpx.Client:
    return RealClient(base_url="http://test", transport=httpx.MockTransport(handler))


def test_settings_parse_options():
    settings = make_settings(
        "--host", "http://example.com:9000", "--repeat", "3", "--input", "in.json"
    )

    assert str(settings.host) == "http://example.com:9000/"
    assert settings.repeat == 3
    assert settings.input == "in.json"
    assert settings.output == cli.STDIO


@pytest.mark.parametrize("source", ["inline", "file", "stdin"])
def test_load_request_sources(source, tmp_path, sample_input):
    raw = json.dumps(sample_input)
    stdin = io.StringIO("")
    if source == "inline":
        args = ["--json", raw]
    elif source == "file":
        path = tmp_path / "in.json"
        path.write_text(raw, encoding="utf-8")
        args = ["--input", str(path)]
    else:
        args = ["--input", "-"]
        stdin = io.StringIO(raw)

    request = cli.load_request(make_settings(*args), stdin)

    assert request.model_dump() == sample_input


@pytest.mark.parametrize(
    "raw",
    ["not json", '{"list_1": ["a", "b"], "list_2": ["c"]}'],
    ids=["bad_json", "different_length"],
)
def test_load_request_invalid_body(raw):
    with pytest.raises(cli.ValidationError):
        cli.load_request(make_settings("--json", raw), io.StringIO(""))


def test_run_repeat_uses_cache(api_client, tmp_path, sample_input, sample_output, db_session):
    out_path = tmp_path / "out.jsonl"
    settings = make_settings(
        "--json", json.dumps(sample_input), "--repeat", "3", "--output", str(out_path)
    )

    cli.run(settings, api_client)

    lines = [json.loads(line) for line in out_path.read_text(encoding="utf-8").splitlines()]
    assert len(lines) == 3
    assert len({line["id"] for line in lines}) == 1
    assert all(line["output"] == sample_output["output"] for line in lines)
    unique = set(sample_input["list_1"] + sample_input["list_2"])
    assert db_session.query(TransformedString).count() == len(unique)


def test_run_sends_post_then_get(sample_input, capsys):
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append((request.method, request.url.path))
        if request.method == "POST":
            return httpx.Response(201, json={"id": "abc"})
        return httpx.Response(200, json={"output": "X"})

    cli.run(make_settings("--json", json.dumps(sample_input)), mock_client(handler))

    assert calls == [("POST", "/payload"), ("GET", "/payload/abc")]
    assert json.loads(capsys.readouterr().out) == {"id": "abc", "output": "X"}


def test_main_success(use_real_app, capsys, sample_input, sample_output):
    code = cli.main(["--json", json.dumps(sample_input)])

    assert code == 0
    assert json.loads(capsys.readouterr().out)["output"] == sample_output["output"]


@pytest.mark.parametrize(
    "args",
    [
        [],
        ["--input", "a.json", "--json", "{}"],
        ["--json", "{}", "--repeat", "0"],
        ["--json", "{}", "--host", "not a url"],
    ],
    ids=["no_input", "both_inputs", "repeat_zero", "bad_host"],
)
def test_main_invalid_arguments(args, capsys):
    assert cli.main(args) == cli.EXIT_USAGE
    assert "invalid arguments" in capsys.readouterr().err


def test_main_invalid_body(use_real_app, capsys):
    code = cli.main(["--json", '{"list_1": ["a", "b"], "list_2": ["c"]}'])

    assert code == cli.EXIT_USAGE
    assert "invalid request body" in capsys.readouterr().err


def test_main_missing_input_file(use_real_app, tmp_path):
    assert cli.main(["--input", str(tmp_path / "nope.json")]) == cli.EXIT_FAILURE


@pytest.mark.parametrize("failure", ["http_500", "unreachable"])
def test_main_server_failure(failure, monkeypatch, sample_input, capsys):
    def handler(request: httpx.Request) -> httpx.Response:
        if failure == "unreachable":
            raise httpx.ConnectError("connection refused", request=request)
        return httpx.Response(500)

    monkeypatch.setattr(cli.httpx, "Client", lambda **kwargs: mock_client(handler))

    code = cli.main(["--json", json.dumps(sample_input)])

    assert code == cli.EXIT_FAILURE
    assert "cache-cli:" in capsys.readouterr().err
