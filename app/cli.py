import json
import sys
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from pathlib import Path
from typing import TextIO

import httpx
from pydantic import AliasChoices, AnyHttpUrl, Field, ValidationError, model_validator
from pydantic_settings import BaseSettings, PydanticBaseSettingsSource, SettingsConfigDict

from .schemas import PayloadRequest

STDIO = "-"
EXIT_FAILURE = 1
EXIT_USAGE = 2


class CliSettings(BaseSettings):
    """Exercise the caching service: create a payload, then read it back."""

    model_config = SettingsConfigDict(
        cli_prog_name="cache-cli",
        cli_kebab_case=True,
        case_sensitive=True,
        cli_hide_none_type=True,
    )

    host: AnyHttpUrl = Field(
        default=AnyHttpUrl("http://localhost:8000"),
        validation_alias=AliasChoices("host", "H"),
        description="URL of the caching service",
    )
    repeat: int = Field(
        default=1,
        ge=1,
        validation_alias=AliasChoices("repeat", "r"),
        description="how many times to repeat the create+read cycle",
    )
    input: str | None = Field(
        default=None,
        validation_alias=AliasChoices("input", "i"),
        description="file with the JSON request body ('-' for stdin)",
    )
    json_input: str | None = Field(
        default=None,
        validation_alias=AliasChoices("json", "j"),
        description="JSON request body given inline (properly escaped)",
    )
    output: str = Field(
        default=STDIO,
        validation_alias=AliasChoices("output", "o"),
        description="file to write results to ('-' for stdout)",
    )

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        *args: PydanticBaseSettingsSource,
        **kwargs: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        return (init_settings,)

    @model_validator(mode="after")
    def _exactly_one_input(self) -> "CliSettings":
        if (self.input is None) == (self.json_input is None):
            raise ValueError("provide exactly one of --input and --json")
        return self


def load_request(settings: CliSettings, stdin: TextIO) -> PayloadRequest:
    if settings.json_input is not None:
        raw = settings.json_input
    elif settings.input == STDIO:
        raw = stdin.read()
    else:
        assert settings.input is not None  # guaranteed by _exactly_one_input
        raw = Path(settings.input).read_text(encoding="utf-8")
    return PayloadRequest.model_validate_json(raw)


@contextmanager
def open_output(target: str) -> Iterator[TextIO]:
    if target == STDIO:
        yield sys.stdout
    else:
        with open(target, "w", encoding="utf-8") as stream:
            yield stream


def run(settings: CliSettings, client: httpx.Client, stdin: TextIO = sys.stdin) -> None:
    """Create the payload and read it back, ``settings.repeat`` times.

    Repeating is what demonstrates the cache: later iterations must return the
    same id without extra transformer calls on the server.
    """
    request = load_request(settings, stdin)
    with open_output(settings.output) as out:
        for _ in range(settings.repeat):
            created = client.post("/payload", json=request.model_dump())
            created.raise_for_status()
            payload_id = created.json()["id"]

            read = client.get(f"/payload/{payload_id}")
            read.raise_for_status()
            print(json.dumps({"id": payload_id, **read.json()}), file=out)


def main(argv: Sequence[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else list(argv)
    try:
        settings = CliSettings(_cli_parse_args=args)
    except ValidationError as exc:
        print(f"cache-cli: invalid arguments:\n{exc}", file=sys.stderr)
        return EXIT_USAGE

    try:
        with httpx.Client(base_url=str(settings.host), timeout=30) as client:
            run(settings, client)
    except ValidationError as exc:
        print(f"cache-cli: invalid request body:\n{exc}", file=sys.stderr)
        return EXIT_USAGE
    except (httpx.HTTPError, OSError) as exc:
        print(f"cache-cli: {exc}", file=sys.stderr)
        return EXIT_FAILURE
    return 0


if __name__ == "__main__":
    sys.exit(main())
