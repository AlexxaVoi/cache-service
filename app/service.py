import hashlib

from sqlalchemy import select
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.orm import Session

from .models import Payload, TransformedString
from .transformer import uppercase_transformer

OUTPUT_SEPARATOR = ", "


def create(
    db: Session,
    list_1: list[str],
    list_2: list[str],
) -> str:
    unique_strings = set(list_1 + list_2)
    transformed = _transform_all(db, unique_strings)
    output_items = []

    for first, second in zip(list_1, list_2, strict=True):
        output_items.append(transformed[first])
        output_items.append(transformed[second])

    output = OUTPUT_SEPARATOR.join(output_items)
    payload_id = hashlib.sha256(output.encode()).hexdigest()
    db.execute(
        insert(Payload)
        .values(id=payload_id, output=output)
        .on_conflict_do_nothing(index_elements=["id"])
    )
    db.commit()
    return payload_id


def get_output(db: Session, payload_id: str) -> str | None:
    payload = db.get(Payload, payload_id)
    return payload.output if payload else None


def _transform_all(
    db: Session,
    strings: set[str],
) -> dict[str, str]:
    cached = _load_cached(db, strings)

    fresh = {}
    for source in strings:
        if source not in cached:
            fresh[source] = uppercase_transformer(source)

    _store(db, fresh)

    return {**cached, **fresh}


def _load_cached(
    db: Session,
    strings: set[str],
) -> dict[str, str]:
    rows = db.scalars(select(TransformedString).where(TransformedString.source.in_(strings)))
    cached = {}
    for row in rows:
        cached[row.source] = row.result

    return cached


def _store(
    db: Session,
    fresh: dict[str, str],
) -> None:
    if not fresh:
        return

    db.execute(
        insert(TransformedString)
        .values([{"source": source, "result": result} for source, result in fresh.items()])
        .on_conflict_do_nothing(index_elements=["source"])
    )
    db.commit()
