"""Objekte (Haus/Wohnung) finden oder anlegen - siehe homedms/core/addresses.py."""
import uuid

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from homedms.core.addresses import Address
from homedms.models.document import Property


async def property_for(db: AsyncSession, tenant_id: uuid.UUID, address: Address) -> Property:
    """Objekt zu dieser Adresse - "Musterstr. 5" und "Musterstraße 5" sind dasselbe Objekt.
    Gibt es noch keines, wird es angelegt (Name = "<Ort> <Strasse Nr>", in der App aenderbar).
    ON CONFLICT: zwei gleichzeitig laufende Jobs duerfen kein doppeltes Objekt erzeugen."""
    await db.execute(
        insert(Property)
        .values(
            id=uuid.uuid4(), tenant_id=tenant_id, name=address.default_name, street=address.street,
            postal_code=address.postal_code, city=address.city, match_key=address.match_key,
        )
        .on_conflict_do_nothing(constraint="uq_property_tenant_key")
    )
    return await db.scalar(
        select(Property).where(Property.tenant_id == tenant_id, Property.match_key == address.match_key)
    )
