import hashlib

import pytest

from app.models import TransformedString

POST_URL = "/payload"
GET_URL = "/payload/{}"


def sha256(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def test_create_returns_201_and_hash_id(client, sample_input, sample_output):
    response = client.post(POST_URL, json=sample_input)

    assert response.status_code == 201
    assert response.json() == {"id": sha256(sample_output["output"])}


def test_create_is_idempotent(client, sample_input):
    first = client.post(POST_URL, json=sample_input)
    second = client.post(POST_URL, json=sample_input)

    assert first.status_code == second.status_code == 201
    assert first.json() == second.json()


def test_different_input_gives_different_id(client):
    a = client.post(POST_URL, json={"list_1": ["a"], "list_2": ["b"]})
    b = client.post(POST_URL, json={"list_1": ["b"], "list_2": ["a"]})

    assert a.json()["id"] != b.json()["id"]


def test_unicode_and_duplicates(client):
    payload = {"list_1": ["Hello", "Hello"], "list_2": ["world", "Hello"]}

    payload_id = client.post(POST_URL, json=payload).json()["id"]

    output = client.get(GET_URL.format(payload_id)).json()["output"]
    assert output == "HELLO, WORLD, HELLO, HELLO"


def test_limits_are_accepted(client):
    payload = {"list_1": ["a" * 10] * 1000, "list_2": ["b"] * 1000}

    assert client.post(POST_URL, json=payload).status_code == 201


def test_unique_strings_are_cached_once(client, db_session):
    payload = {"list_1": ["a", "b", "a"], "list_2": ["b", "c", "c"]}

    client.post(POST_URL, json=payload)
    client.post(POST_URL, json=payload)

    rows = db_session.query(TransformedString).all()
    assert {r.source: r.result for r in rows} == {"a": "A", "b": "B", "c": "C"}


@pytest.mark.parametrize(
    "payload",
    [
        {"list_1": ["a", "b"], "list_2": ["c"]},
        {"list_1": [], "list_2": []},
        {"list_1": ["a"]},
        {"list_1": "abc", "list_2": ["a"]},
        {"list_1": [1], "list_2": ["a"]},
        {"list_1": ["a" * 1001], "list_2": ["a"]},
        {"list_1": ["a"] * 1001, "list_2": ["b"] * 1001},
    ],
    ids=[
        "different_length",
        "empty_lists",
        "missing_field",
        "not_a_list",
        "not_a_string",
        "string_too_long",
        "too_many_items",
    ],
)
def test_invalid_payload_returns_422(client, payload):
    assert client.post(POST_URL, json=payload).status_code == 422


def test_missing_body_returns_422(client):
    assert client.post(POST_URL).status_code == 422


def test_read_returns_created_output(client, sample_input, sample_output):
    payload_id = client.post(POST_URL, json=sample_input).json()["id"]

    response = client.get(GET_URL.format(payload_id))

    assert response.status_code == 200
    assert response.json() == sample_output


def test_read_unknown_id_returns_404(client):
    response = client.get(GET_URL.format("does-not-exist"))

    assert response.status_code == 404
