from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from .database import get_db
from .schemas import PayloadCreated, PayloadRequest, PayloadResponse
from .service import create, get_output

router = APIRouter()


@router.get("/payload/{payload_id}", response_model=PayloadResponse)
def read_payload(payload_id: str, db: Session = Depends(get_db)) -> PayloadResponse:
    response_output = get_output(db=db, payload_id=payload_id)
    return PayloadResponse(output=response_output)


@router.post("/payload", status_code=status.HTTP_201_CREATED, response_model=PayloadCreated)
def create_payload(body: PayloadRequest, db: Session = Depends(get_db)) -> PayloadCreated:
    id_payload = create(db=db, list_1=body.list_1, list_2=body.list_2)
    return PayloadCreated(id=id_payload)
