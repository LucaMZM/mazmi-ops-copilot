from __future__ import annotations

import re
import time
import unicodedata
from collections.abc import Callable
from typing import Literal

from pydantic import Field

from .config import settings
from .evidence import ABSTENTION as ABSTENTION
from .evidence import documentary_answer
from .providers import generation_client
from .schemas import StrictModel, TicketPayload

client = generation_client()

SYSTEM = """Selecciona una única llamada a la herramienta autorizada para la petición.
get_tickets consulta los últimos tickets del workspace actual. Respeta el límite explícito
del usuario; si no indica cantidad usa 5. El límite permitido es de 1 a 20.
create_ticket solo prepara una propuesta para confirmación humana, nunca la ejecuta.
No generes narración, resultados, citas ni llamadas adicionales.
"""


class TicketQuery(StrictModel):
    limit: int = Field(ge=1, le=20, strict=True)


class TicketQueryError(ValueError):
    """Invalid explicit user limit, safe to report without provider details."""


class TicketResult(StrictModel):
    id: int = Field(ge=1, strict=True)
    title: str = Field(min_length=1, max_length=200, strict=True)
    priority: Literal["LOW", "MEDIUM", "HIGH", "URGENT"]
    status: str = Field(min_length=1, max_length=80, strict=True)
    # Older database callbacks include this field. Never send it to a model or render it.
    description: str | None = Field(default=None, max_length=8000, strict=True)


class ExecutionReceipt(StrictModel):
    status: Literal["executed"]
    ticket: TicketResult


def explicit_ticket_limit(message: str) -> int | None:
    """Check numeric counts, without confusing a ticket ID with a list limit."""
    counts = re.findall(
        r"(?<![\w.])([+-]?\d+(?:[.,]\d+)?)\s+(?:tickets?|incidencias?)\b"
        r"|\b(?:límite|limite|limit)\s*(?:de|of|:)?\s*([+-]?\d+(?:[.,]\d+)?)\b",
        message.lower(),
    )
    limits = [left or right for left, right in counts]
    if not limits:
        return None
    if any(not re.fullmatch(r"\d+", value) for value in limits):
        raise TicketQueryError("El límite de tickets debe ser un entero entre 1 y 20.")
    # Bound digit length before int() so maliciously long numbers fail predictably.
    if any(len(value) > 2 or not 1 <= int(value) <= 20 for value in limits):
        raise TicketQueryError("El límite de tickets debe ser un entero entre 1 y 20.")
    if len({int(value) for value in limits}) != 1:
        raise TicketQueryError("Indica un único límite de tickets entre 1 y 20.")
    return int(limits[0])


def safe_ticket_text(value: str) -> str:
    """Plain React text is HTML-escaped by the UI; neutralize its code-fence syntax."""
    value = " ".join(value.split())
    value = "".join(char for char in value if not unicodedata.category(char).startswith("C"))
    return value.replace("`", "｀")


def render_tickets(result: object, limit: int, disclose_scope: bool = False) -> str:
    if not isinstance(result, list) or len(result) > limit:
        raise RuntimeError("Resultado de tickets no válido")
    tickets = [TicketResult.model_validate(row) for row in result]
    if len({ticket.id for ticket in tickets}) != len(tickets):
        raise RuntimeError("Resultado de tickets duplicado")
    scope = "Consulta de últimos tickets del workspace, sin filtros adicionales.\n" if disclose_scope else ""
    if not tickets:
        return scope + "No hay tickets en este workspace."
    lines = [scope + f"Tickets del workspace (últimos {len(tickets)}):"]
    lines.extend(
        f"- #{ticket.id}: {safe_ticket_text(ticket.title)} "
        f"— Prioridad: {ticket.priority}; estado: {safe_ticket_text(ticket.status)}."
        for ticket in tickets
    )
    return "\n".join(lines)


def direct_ticket_query(message: str, limit: int | None) -> TicketQuery | None:
    """Only exact, unfiltered list requests bypass interpretation by a model."""
    text = message.strip().lower().lstrip("¿")
    if not re.fullmatch(
        r"(?:por favor[, ]+)?(?:lista|muestra|consulta)\s+"
        r"(?:(?:los\s+)?(?:últimos|ultimos)\s+)?"
        r"(?:\d+\s+)?(?:(?:los|las|mis)\s+)?(?:tickets|incidencias)"
        r"(?:\s+del\s+workspace)?[.!?]?",
        text,
    ):
        return None
    return TicketQuery(limit=limit if limit is not None else 5)


def function_tool(name, description, schema):
    # Pydantic schemas are the same contract validated on the server.
    return {
        "type": "function",
        "name": name,
        "description": description,
        "parameters": schema.model_json_schema(),
        "strict": True,
    }


READ_TOOL = function_tool("get_tickets", "Consulta los tickets del workspace actual.", TicketQuery)
WRITE_TOOL = function_tool(
    "create_ticket",
    "Propone un ticket interno. Solo se ejecuta tras confirmación humana.",
    TicketPayload,
)


def validate_citations(text: str, sources: list[dict]) -> tuple[str, list[int]]:
    cited = sorted({int(n) for n in re.findall(r"\[(\d+)\]", text) if 1 <= int(n) <= len(sources)})
    text = re.sub(r"\[(\d+)\]", lambda m: m[0] if int(m[1]) in cited else "", text)
    return text, cited


def requested_tools(message: str, mode: str) -> list[dict]:
    """Conservative capability gate based only on the current user message.

    Tool calls never receive retrieved documents or conversation history.
    Ambiguous requests remain documentary queries; no inferred authorization.
    """
    text = message.strip().lower().lstrip("¿")
    if not re.search(r"\b(tickets?|incidencias?)\b", text):
        return []
    if re.match(r"(?:por favor[, ]+)?(?:consulta|muestra|lista|busca|list|show|find)\b", text):
        return [READ_TOOL]
    if re.fullmatch(
        r"(?:por favor[, ]+)?(?:crea|prepara|haz)\s+un\s+resumen\s+"
        r"(?:sobre|de)\s+(?:(?:los|las|mis)\s+)?(?:tickets|incidencias)[.!?]?"
        r"|(?:please[, ]+)?create\s+a\s+summary\s+of\s+(?:the\s+)?tickets[.!?]?",
        text,
    ):
        return [READ_TOOL]
    # A ticket mentioned somewhere in the sentence is not authorization to
    # propose one: "Crea un resumen sobre tickets" requests a summary. Keep the
    # write gate deliberately narrow and require the action's direct object.
    if mode == "DO" and re.match(
        r"(?:por favor[, ]+)?(?:crea|crear|prepara|abre|registra|create|open)\s+"
        r"(?:(?:un|una|el|la|a|an|the)\s+)?(?:(?:nuevo|nueva|new)\s+)?"
        r"(?:ticket|incidencia)\b",
        text,
    ):
        return [WRITE_TOOL]
    return []


def answer(
    message: str,
    sources: list[dict],
    mode: str,
    history: list[dict] | None = None,
    read_tool: Callable | None = None,
    emit: Callable | None = None,
) -> tuple[str, dict | None, dict]:
    allowed_tools = requested_tools(message, mode)
    # Remove both direct and historical document influence from tool-capable calls.
    if allowed_tools:
        sources, history = [], []
    if not allowed_tools:
        if not client:
            raise RuntimeError("Proveedor no disponible")
        return documentary_answer(client, message, sources, history, emit)
    is_read = allowed_tools == [READ_TOOL]
    requested_limit = explicit_ticket_limit(message) if is_read else None
    started = time.perf_counter()
    direct_query = direct_ticket_query(message, requested_limit) if is_read else None
    if direct_query is not None:
        if read_tool is None:
            raise RuntimeError("Herramienta no permitida")
        if emit:
            emit({"type": "status", "text": "Consultando tickets…"})
        result = read_tool(direct_query.limit)
        text = render_tickets(result, direct_query.limit)
        duration_ms = int((time.perf_counter() - started) * 1000)
        if emit:
            emit({"type": "delta", "text": text})
        return text, None, {
            "duration_ms": duration_ms,
            "model": None,
            "model_calls": 0,
            "input_tokens": 0,
            "output_tokens": 0,
            "tools": [{"name": "get_tickets", "arguments": direct_query.model_dump(),
                       "result_count": len(result), "duration_ms": duration_ms}],
            "citations": [],
            "abstention_reason": None,
        }
    if not client:
        raise RuntimeError("Proveedor no disponible")
    inputs = [{"role": "user", "content": f"MODO: {mode}\nPETICIÓN:\n{message}"}]
    tool_events = []
    input_tokens = output_tokens = 0
    pending = None
    kwargs = {
        "model": settings.generation_model,
        "instructions": SYSTEM,
        "input": inputs,
        "store": False,
        "tools": allowed_tools,
        "parallel_tool_calls": False,
        "max_output_tokens": 3000,
    }
    if emit:
        response = None
        with client.responses.create(**kwargs, stream=True) as stream:
            for event in stream:
                # Model text is never evidence of a database result or execution.
                if event.type == "response.completed":
                    response = event.response
                elif event.type in {"error", "response.failed", "response.incomplete"}:
                    raise RuntimeError("Respuesta del proveedor incompleta")
        if response is None:
            raise RuntimeError("Stream interrumpido")
    else:
        response = client.responses.create(**kwargs)
    if getattr(response, "status", "completed") != "completed":
        raise RuntimeError("Respuesta incompleta")
    usage = getattr(response, "usage", None)
    input_tokens = getattr(usage, "input_tokens", 0) or 0
    output_tokens = getattr(usage, "output_tokens", 0) or 0
    calls = [item for item in response.output if item.type == "function_call"]
    if len(calls) > 1:
        raise RuntimeError("Solo se admite una herramienta por petición")
    if not calls:
        text = (
            "No se han consultado los tickets. Inténtalo de nuevo."
            if is_read
            else "No se ha preparado ninguna acción. No se ha ejecutado nada."
        )
    else:
        call = calls[0]
        if call.name not in {tool["name"] for tool in allowed_tools}:
            raise RuntimeError("Herramienta fuera de la autorización del usuario")
        if call.name == "create_ticket":
            if mode != "DO":
                raise RuntimeError("Acción no permitida en ASK")
            pending = {
                "name": "create_ticket",
                "payload": TicketPayload.model_validate_json(call.arguments).model_dump(),
            }
            text = (
                "He preparado una acción que requiere tu confirmación. Todavía no se ha ejecutado."
            )
        else:
            if call.name != "get_tickets" or read_tool is None:
                raise RuntimeError("Herramienta no permitida")
            args = TicketQuery.model_validate_json(call.arguments)
            if requested_limit is not None and args.limit != requested_limit:
                raise RuntimeError("La herramienta no respetó el límite solicitado")
            if emit:
                emit({"type": "status", "text": "Consultando tickets…"})
            tool_start = time.perf_counter()
            result = read_tool(args.limit)
            text = render_tickets(result, args.limit, disclose_scope=True)
            tool_events.append(
                {
                    "name": call.name,
                    "arguments": args.model_dump(),
                    "result_count": len(result),
                    "duration_ms": int((time.perf_counter() - tool_start) * 1000),
                }
            )
    if emit:
        emit({"type": "delta", "text": text})
    return (
        text,
        pending,
        {
            "duration_ms": int((time.perf_counter() - started) * 1000),
            "model": settings.generation_model,
            "model_calls": 1,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "tools": tool_events,
            "citations": [],
            "abstention_reason": "missing_tool_call" if not calls else None,
        },
    )


def describe_execution(name: str, arguments: dict, result: dict) -> str:
    """Render only the committed database receipt; no further provider call."""
    if name != "create_ticket":
        raise RuntimeError("Resultado de ejecución no permitido")
    receipt = ExecutionReceipt.model_validate(result)
    ticket = receipt.ticket
    return (
        f"Ticket #{ticket.id} creado tras tu confirmación: {safe_ticket_text(ticket.title)} "
        f"— Prioridad: {ticket.priority}; estado: {safe_ticket_text(ticket.status)}."
    )
