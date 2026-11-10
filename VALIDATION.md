# Validación de MAZMI Ops Copilot con IA local

Medido el 10 de noviembre de 2026 en un MacBook Air M2 de **8 GB**, con Ollama 0.40.7, `qwen3:4b` (Q4_K_M) y `embeddinggemma`, PostgreSQL 17 con pgvector y bases nuevas y vacías. El registro de MAZMI 2.0 (Gemini, demo y mediciones anteriores) está en [docs/HISTORICO-VALIDACION-2.0.md](docs/HISTORICO-VALIDACION-2.0.md); los resultados en bruto, en `backend/evals/v3-*.json`.

## Categorías de evidencia

| Categoría | Qué demuestra | Qué no demuestra |
|---|---|---|
| Pruebas con dobles de modelo (pytest) | Contratos, seguridad, transacciones, autorización, guardas deterministas | Calidad del modelo |
| Integración con PostgreSQL real | Aislamiento por workspace, colecciones, idempotencia, atomicidad | Calidad del modelo |
| Modelo real, pasajes fijos (`evaluate_grounding --live`) | Juicio de suficiencia con casos adversariales | Recuperación ni embeddings |
| Modelo real, pipeline completo (`evaluate_local --live`) | HTTP, base real, embeddings, citas, ASK/DO, aprobaciones, tiempos, memoria | Generalización: los corpus son pequeños y ficticios |

## Resultado principal: pipeline completo con Ollama real

`evaluate_local --live` sobre tres conjuntos, cada uno en una base nueva y vacía. Verifica además, por cada respuesta, que **toda cita entre «» existe literalmente en el fragmento que cita** y que aparecen los datos esperados.

| Conjunto | Correctas | Abstenciones correctas | Falsas abstenciones | Sin soporte / incompletas | Timeouts / errores | Citas literales | Recorridos de seguridad |
|---|---:|---:|---:|---:|---:|:---:|---:|
| 8 casos originales | 4/4 | 4/4 | 0 | 0 | 0 | sí | 13/13 |
| 13 casos reservados (nuevos) | 7/7 | 6/6 | 0 | 0 | 0 | sí | 13/13 |
| 11 casos de desarrollo | 7/7 | 4/4 | 0 | 0 | 0 | sí | 13/13 |

Los 13 casos reservados (`local_holdout_v3.json`) se escribieron y se confirmaron **antes** de cambiar el pipeline y no se usaron para ajustar prompts, guardas ni umbrales. Los 8 originales sí habían servido para optimizar versiones anteriores. El conjunto de desarrollo (`local_dev_v3.json`) se usó para iterar.

Un caso reservado (`h_return_furniture`) agotó el reintento de cita y se abstuvo: es una abstención correcta, pero ilustra que la verificación puede rechazar también un intento legítimo.

### Antes y después (casos reservados)

Mismo conjunto, mismo hardware, el pipeline de MAZMI 2.0 frente al nuevo:

| Configuración | Correctas | Abst. correctas | Falsas abst. | Sin soporte | Error técnico | p50 / p95 |
|---|---:|---:|---:|---:|---:|---:|
| 2.0, razonamiento activado | 3 | 5 | 1 | 2 | 2 (`done_reason=length`) | 43,6 s / 86,4 s |
| 2.0, sin razonamiento | 4 | 3 | 1 | 5 | 0 | 10,5 s / 14,2 s |
| **Nuevo (citas verificadas)** | **7** | **6** | **0** | **0** | **0** | **8,8 s / 13,1 s** |

(“Sin soporte” incluye aceptar evidencia insuficiente y citas no literales.) Ficheros: `v3-baseline-holdout-reasoning-on.json`, `v3-baseline-holdout-no-reasoning.json`, `v3-holdout-13.json`.

### Qué causaba los fallos de Qwen3 4B

1. **Timeouts, respuestas vacías:** con el razonamiento activado el modelo consumía los 2000 tokens pensando (`done_reason=length`, `content` vacío). Solución: `OLLAMA_REASONING=off`.
2. **Evidencia insuficiente aceptada:** sin razonamiento aceptaba pasajes del mismo tema (5 de 13). Solución: citas literales verificadas por el servidor más una segunda comprobación acotada.
3. **Falsa abstención por guarda léxica:** «importe máximo» exigía la palabra «importe» en el documento. Solución: sinónimos (máximo, tope, techo).
4. **Copia defectuosa de cadenas literales:** Qwen3 4B escribe «09:00» como «09:0.0» con cualquier semilla, temperatura o gramática (reproducido de forma sistemática, incluso sin gramática JSON). Solución: una cita casi idéntica (similitud ≥ 0,88) a una frase real se sustituye por el texto almacenado; lo que no se parece se rechaza. En la medición final, un caso de los 8 originales dependió de esto.

Ninguna solución elimina un control: el texto mostrado sale siempre del documento, nunca del modelo.

### Tiempos y memoria

| Conjunto | Latencia por pregunta p50 / p95 / máx | Pico RSS de Ollama | Modelos cargados (Ollama) |
|---|---|---:|---:|
| 8 originales | 7,8 s / 12,0 s / 12,0 s | 3,80 GB | 3,69 GB |
| 13 reservados | 8,8 s / 13,1 s / 17,4 s | 3,84 GB | 3,69 GB |
| 11 de desarrollo | 6,9 s / 10,5 s / 10,5 s | 3,83 GB | 3,69 GB |

La latencia incluye recuperación (unos milisegundos de SQL y ~80 ms de embedding de la consulta), selección de cita y comprobación (dos llamadas al modelo). Las preguntas con abstención temprana por guardas deterministas tardan menos de 1 s. En un Mac de 8 GB, Ollama ocupa casi la mitad de la memoria: no se recomienda ejecutar a la vez compilaciones o Docker pesado.

## Corpus adversarial con pasajes fijos (modelo real)

`evaluate_grounding --live`, 27 casos (conflictos, inyecciones, relaciones falsas, condiciones, negaciones) y 4 casos de recuperación:

| Corpus | Correctos | Abstenciones correctas | Falsas abstenciones | Errores | Citas válidas |
|---|---:|---:|---:|---:|:---:|
| `grounding_cases.json` | **25/27** | 16/17 | 1 | 0 | sí |
| `recovery_holdout.json` | 4/4 | 2/2 | 0 | 0 | sí |

**Fallos abiertos (conservados a propósito, no ocultos):**

- `paraphrased_conflict`: «25 días laborables» frente a «treinta jornadas de descanso». El modelo no detecta el conflicto parafraseado y responde: una **respuesta sin soporte**. Las guardas deterministas solo cubren conflictos literales.
- `instruction_word_legitimate_policy`: la pregunta vaga «¿Qué dicen las vacaciones?» recibe una abstención; es conservador, no peligroso.

## Pruebas automáticas

- Backend: **304 pruebas** (PostgreSQL real con esquemas aislados), `ruff` limpio. Incluye aislamiento por workspace, aprobación única por solicitante, ASK sin mutación, transacciones sin bloqueos durante la inferencia, idempotencia, streaming y 22 pruebas del modo de evidencia verificada (citas inventadas, citas de otro pasaje, reintento, ajuste, instrucciones incrustadas, fallos del evaluador).
- Frontend: **44 pruebas**, `tsc`, ESLint y `next build`. Comprueban que no queda ninguna etiqueta de demo, simulación ni proveedor externo.
- Sin `TEST_DATABASE_URL` las pruebas de integración se omiten y no se dan por pasadas. Las pruebas normales no llaman a ningún modelo ni descargan nada.

## Recuperación con EmbeddingGemma (se mantiene)

22 preguntas con respuesta sobre 8 documentos ficticios, embeddings reales de EmbeddingGemma, búsqueda híbrida (`v3-retrieval-embeddinggemma.json`):

| Configuración | Recall@3 | Recall@6 | Evidencia completa@6 | MRR |
|---|---:|---:|---:|---:|
| Línea base 2.0 (trozos planos, FTS conjuntivo) | 0,955 | 0,977 | 0,955 | 0,977 |
| **Actual (trozos estructurados, FTS por términos, 3 trozos por documento)** | **1,0** | **1,0** | **1,0** | 0,977 |

Embedding de una consulta: p50 77 ms, p95 101 ms. Con estos resultados no hay motivo para cambiar de modelo de embeddings.

## Navegador real

Con el build de producción de Next.js, FastAPI, PostgreSQL y Ollama (sin mocks) se comprobó en un navegador, sobre una cuenta creada desde la pantalla de registro: registro y workspace, subida de tres documentos, respuesta en streaming de varias partes con dos citas literales, inspector con el pasaje completo, abstención en modo ASK, propuesta DO sin ejecutar, confirmación y ticket creado, «Verificar Ollama» completado, tema claro y oscuro y móvil de 390 px sin desbordamiento. Las capturas están en [docs/screenshots](docs/screenshots/README.md).

## Docker Compose (opcional)

Validado el 10 de noviembre con Docker Desktop (VM de 3,8 GB) bajo un nombre de proyecto aparte y su propio volumen, eliminado al terminar:

- `docker compose build` y `up` correctos; PostgreSQL y backend sanos.
- **El contenedor del backend alcanza el Ollama del equipo anfitrión** en `host.docker.internal:11434` (versión devuelta 0.40.7).
- Registro, subida de documento (embeddings en el host), pregunta en streaming (≈9 s) y «Verificar Ollama» (5,5 s) funcionan a través del frontend en Compose.
- Hallazgo corregido: el proxy de Next cortaba a los 30 s las peticiones no-streaming con el modelo en frío; ahora `proxyTimeout` cubre el máximo de turno (330 s). La interfaz usa streaming.
- No se midió Compose bajo carga. En Linux, Ollama debe escuchar en una interfaz alcanzable desde el contenedor.

## Criterios de aceptación del modelo local

Un `v1.0.0` exige cumplirlos **todos**:

| Criterio | Estado |
|---|---|
| Los tres conjuntos de pipeline completo superan `automated_fixture_checks_passed` | ✅ cumplido |
| Cero respuestas sin soporte en los conjuntos de pipeline | ✅ cumplido |
| Toda cita mostrada es literal | ✅ cumplido (todas las respuestas medidas) |
| Cero timeouts y errores técnicos | ✅ cumplido |
| Cero falsas abstenciones en los conjuntos de pipeline | ✅ cumplido |
| Cero respuestas sin soporte en el corpus adversarial de pasajes fijos | ❌ **1 abierto** (`paraphrased_conflict`) |
| Evaluación con corpus mayor o documentos reales de una organización | ❌ no realizada (32 preguntas ficticias) |
| Voz (Faster-Whisper/Piper) comprobada de extremo a extremo | ❌ no verificada |

**Decisión: no se crea tag ni release.** Se han resuelto los fallos del modelo local que bloqueaban 2.0, pero queda una respuesta sin soporte reproducible y la validación es pequeña y sintética.

## Comparación con otros modelos

No se ha descargado ningún modelo. Qwen3 8B (≈5 GB cuantizado) apenas cabría junto a EmbeddingGemma en 8 GB y Qwen3.5 4B no está instalado. Si lo autorizas, la comparación es directa y reproducible: `ollama pull`, `OLLAMA_CHAT_MODEL=<modelo>` y repetir los tres conjuntos y el corpus adversarial en bases nuevas, comparando correctas, falsas abstenciones, respuestas sin soporte, p50/p95 y memoria pico. Instrucciones en [LOCAL_AI.md](LOCAL_AI.md).

## Pendiente y no verificado

- Conflictos parafraseados entre pasajes (`paraphrased_conflict`).
- Corpus mayores y documentos reales; recuperación a gran escala.
- Voz real de extremo a extremo.
- Comparación con un modelo mayor (requiere tu autorización y espacio/memoria).
- Compose bajo carga y despliegue en producción; indexación síncrona, sin RBAC ni invitaciones.
