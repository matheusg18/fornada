"""The attendant for FastAPI path operations."""

from typing import Annotated

from fastapi import Depends, Request

from fornada_api.agents.attendant.attendant import Attendant


def get_attendant(request: Request) -> Attendant:
    """The attendant built in the app's lifespan."""
    return request.app.state.attendant


AttendantDep = Annotated[Attendant, Depends(get_attendant)]
