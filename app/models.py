from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class TransformedString(Base):
    __tablename__ = "transformed_string"

    source: Mapped[str] = mapped_column(String(1000), primary_key=True)
    result: Mapped[str] = mapped_column(Text, nullable=False)


class Payload(Base):
    __tablename__ = "payload"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    output: Mapped[str] = mapped_column(Text, nullable=False)
