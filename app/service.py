import hashlib
import logging

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.orm import Session

from .models import Payload, TransformedString
from .transformer import uppercase_transformer

logger = logging.getLogger(__name__)

OUTPUT_SEPARATOR = ", "


def create(
    db: Session,
    list_1: list[str],
    list_2: list[str],
) -> str:
    logger.debug("Creating payload from %d pairs", len(list_1))

    unique_strings = set(list_1 + list_2)
    transformed = _transform_all(db, unique_strings)
    output_items = []

    for first, second in zip(list_1, list_2, strict=True):
        output_items.append(transformed[first])
        output_items.append(transformed[second])

    output = OUTPUT_SEPARATOR.join(output_items)
    payload_id = hashlib.sha256(output.encode()).hexdigest()
    result = db.execute(
        insert(Payload)
        .values(id=payload_id, output=output)
        .on_conflict_do_nothing(index_elements=["id"])
    )
    db.commit()

    if result.rowcount == 1:
        logger.info("Payload %s created", payload_id)
    else:
        logger.info("Payload %s already exists, reusing it", payload_id)
    return payload_id


def get_output(db: Session, payload_id: str) -> str | None:
    payload = db.get(Payload, payload_id)
    if payload is None:
        logger.info("Payload %s not found", payload_id)
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Payload not found",
        )

    logger.debug("Payload %s found", payload_id)
    return payload.output


def _transform_all(
    db: Session,
    strings: set[str],
) -> dict[str, str]:
    cached = _load_cached(db, strings)

    logger.info(
        "Unique strings: %d total, %d cached, %d to transform",
        len(strings),
        len(cached),
        len(strings) - len(cached),
    )

    fresh = {}
    for source in strings:
        if source not in cached:
            try:
                fresh[source] = uppercase_transformer(source)
            except Exception:
                logger.exception("Transformer failed for a string of length %d", len(source))
                raise

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

    logger.debug("Loaded %d cached results from the database", len(cached))
    return cached


def _store(
    db: Session,
    fresh: dict[str, str],
) -> None:
    if not fresh:
        logger.debug("Nothing new to store")
        return

    db.execute(
        insert(TransformedString)
        .values([{"source": source, "result": result} for source, result in fresh.items()])
        .on_conflict_do_nothing(index_elements=["source"])
    )
    db.commit()
    logger.debug("Stored %d new transformer results", len(fresh))
