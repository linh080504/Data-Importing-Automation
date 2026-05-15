import uuid

from sqlalchemy import UUID


UUID_PK = UUID(as_uuid=True)

def new_uuid() -> uuid.UUID:
    return uuid.uuid4()
