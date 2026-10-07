"""The attendant for FastAPI path operations."""

from typing import Annotated

from fastapi import Depends

from fornada_api.agents.attendant.attendant import Attendant, FixedAttendant


def get_attendant() -> Attendant:
    return FixedAttendant()


AttendantDep = Annotated[Attendant, Depends(get_attendant)]
