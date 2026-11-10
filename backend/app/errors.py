"""Mapping of provider/domain failures to safe HTTP errors (no upstream bodies)."""

import logging

from fastapi import HTTPException

from .providers import ProviderUnavailable

logger = logging.getLogger(__name__)


def provider_error(exc: Exception) -> HTTPException:
    from .agent import TicketQueryError
    from .db import DatabaseBusy

    if isinstance(exc, HTTPException):
        return exc
    if isinstance(exc, TicketQueryError):
        return HTTPException(400, str(exc))
    if isinstance(exc, (ProviderUnavailable, DatabaseBusy)):
        return HTTPException(503, str(exc))
    # Do not expose upstream errors: they may contain credentials or document content.
    logger.error("Provider failure: %s", type(exc).__name__)
    return HTTPException(502, "El modelo local no pudo completar la solicitud. Inténtalo de nuevo.")
