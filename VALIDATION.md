# Validación de MAZMI Ops Copilot con IA local

Medido el 10 y el 11 de noviembre de 2026 en un MacBook Air M2 de **8 GB**, con Ollama 0.40.7, `qwen3:4b` (Q4_K_M) y `embeddinggemma`, PostgreSQL 17 con pgvector y bases nuevas y vacías. El registro de MAZMI 2.0 (Gemini, demo y mediciones anteriores) está en [docs/HISTORICO-VALIDACION-2.0.md](docs/HISTORICO-VALIDACION-2.0.md); los resultados en bruto, en `backend/evals/v3-*.json`, `v4-*.json` y `v5-*.json` (los más recientes).

## Categorías de evidencia

| Categoría | Qué demuestra | Qué no demuestra |
|---|---|---|
| Pruebas con dobles de modelo (pytest) | Contratos, seguridad, transacciones, autorización, guardas deterministas | Calidad del modelo |
| Integración con PostgreSQL real | Aislamiento por workspace, colecciones, idempotencia, atomicidad | Calidad del modelo |
| Modelo real, pasajes fijos (`evaluate_grounding --live`) | Juicio de suficiencia con casos adversariales | Recuperación ni embeddings |
| Modelo real, pipeline completo (`evaluate_local --live`) | HTTP, base real, embeddings, citas, ASK/DO, aprobaciones, tiempos, memoria | Generalización: los corpus son pequeños y ficticios |

## Fase de cierre (11 de noviembre): semántica, navegador y movimiento

### Roles y conflictos parafraseados

Objetivo: que una cita literal no se acepte como respuesta cuando habla de **otra parte** (lo que el transportista cobra a la empresa no es lo que paga un cliente), y que dos documentos con **cantidades distintas dichas con otras palabras** («25 días» frente a «treinta jornadas») se traten como conflicto. Se escribieron 65 casos adversariales en tres conjuntos de pasajes fijos, con controles positivos para detectar falsas abstenciones. Dos conjuntos son reservados: uno se fijó antes de cambiar nada y el segundo antes de corregir los fallos vistos en el primero.

**Dos intentos descartados (con sus resultados guardados):**

| Intento | Semántico de desarrollo | Corpus realista de desarrollo | Decisión |
|---|---:|---:|---|
| Línea base (PR #3) | 18/22 | 34/35 | — |
| El modelo juzga «mismo sujeto» y consistencia | 20/22 | **27/35** | Descartado: Qwen3 4B rechaza preguntas legítimas |
| Campo de pasajes en la selección + comparación numérica sobre valores del modelo | 20/22 | **23/35** | Descartado |
| **Reglas deterministas (final)** | 19/22 | **35/35** | Adoptado |

**Solución adoptada**, sin depender del juicio del modelo:

1. **Parte nombrada:** si la pregunta nombra a una parte que actúa o recibe (cliente, empleado, empresa, proveedor, transportista, becario…), la evidencia, su archivo o su sección deben nombrarla. Los posesivos y adjetivos no cuentan («el portátil de la empresa», «USB personal»), y «el proveedor de transporte» queda nombrado por «transportista».
2. **Conflicto entre documentos:** si el modelo cita dos documentos con cantidades distintas en la misma unidad, aunque estén escritas con letras o como periodos («una semana» = 7 días), se informa de un conflicto. No cuenta en preguntas de varias partes, dentro de un mismo documento, entre versiones de una política, cuando un ámbito nombrado (ciudad, equipo, código) solo aparece en una cita, ni entre documentos de temas distintos (devolución de un pedido frente a reembolso de gastos).

| Conjunto (Ollama real) | Correctos | Sin soporte | Falsas abstenciones |
|---|---:|---:|---:|
| Semántico de desarrollo (22) | 19 | 1 | 2 |
| Semántico reservado 1 (23, analizado tras medirlo) | 20 (antes 18) | 3 (antes 4) | 0 (antes 1) |
| **Semántico reservado 2 (20, nunca visto)** | **18** | **2** | **0** |
| Adversarial de pasajes fijos (27) | **26** (antes 25; `paraphrased_conflict` resuelto) | 0 | 1 |

**Lo que sigue sin resolver** (límite medido de Qwen3 4B; las reglas no lo cubren y no se forzaron):

- Conflictos sin cantidades: «permitido» frente a «prohibido», o quién custodia o autoriza algo.
- Un plazo dicho con otras palabras cuando el modelo solo cita uno de los dos documentos (`d_conf_deadline`, `r2_conf_week_vs_days`).
- Una pregunta que sugiere su propia respuesta («¿quién paga, el inquilino?») se abstiene aunque el documento diga «el propietario».

### Corpus realista con el código final

| Conjunto realista | Resultado | Titulares correctos | Citas literales | Seguridad | p50 / p95 |
|---|---:|---:|:---:|---:|---:|
| Desarrollo (35) | **35/35** (antes 34/35) | 16/16 | sí | 13/13 | 11,2 s / 16,7 s |
| Reservado 1 (25) | **25/25** | 11/11 | sí | 13/13 | 15,5 s / 20,7 s |
| **Reservado 2 (15, nunca visto)** | **15/15** | 9/9 | sí | 13/13 | 11,7 s / 15,6 s |
| Originales (8) | **8/8** | — | sí | 13/13 | 11,6 s / 19,1 s |

La versión intermedia rebajó el reservado 1 a 23/25 («el proveedor de transporte» no se reconocía; dos reembolsos de temas distintos se tomaron por conflicto). Se escribió el reservado 2 antes de corregirlo; con la corrección, ambos quedan completos.

### Regresiones encontradas en navegador y corregidas

- **Titular incorrecto con evidencia correcta.** A «¿quién aprueba un gasto de 800 euros?», el modelo citó la tabla entera y el titular decía «Dirección general» (es Finanzas). Ahora la línea breve solo se muestra si cada cita es una única frase o fila. El evaluador cuenta un titular sin el dato esperado como respuesta incorrecta: tras el cambio, 36/36 titulares correctos.
- **Cita con sintaxis Markdown.** Una cita verificada que abarcaba un encabezado y la línea `|---|` de una tabla se mostraba tal cual. Ahora se muestran las frases almacenadas que cubre.
- **Barra de pestañas del móvil fuera de sitio.** Una regla del indicador de navegación anulaba su `position: fixed`. Detectado en la captura y corregido.

### Navegador real (build de producción, Playwright/Chromium)

- **Flujo completo:** registro, carga del corpus con `python -m app.presentation_corpus` (10/10 documentos listos) y cambio de workspace.
- **Streaming:** estados intermedios visibles y botón «Detener» desde el primer instante. La cancelación retira el borrador en 132 ms y la consulta cancelada no se guarda.
- **Respuestas:** coloquial (15 días naturales), tramo de tabla (Finanzas, en consulta nueva), versión vigente (2 días) e histórica (3 días, marcada como sustituida).
- **Abstenciones:** transportista frente a cliente, y comunicado con instrucción dirigida al asistente.
- **Acciones:** propuesta DO en 5,5 s, confirmación, ticket ejecutado una vez (repetir devuelve 409) y auditoría registrada.
- **Persistencia:** las conversaciones siguen ahí tras recargar.
- **Calentamiento:** sin modelos cargados, el backend los carga al arrancar (`Ollama warm-up: 2 of 2 models loaded`).
- **Presentación:** tema claro y oscuro, móvil 390 × 844 sin desbordamiento, movimiento reducido (sin desplazamientos, solo fundidos) y transparencia reducida.
- **Limitación observada:** en una conversación larga que salta de tema, el historial entra en la recuperación y el sistema puede abstenerse. En una consulta nueva responde.

### Movimiento y rendimiento (frontend nuevo frente a `main`, mismos datos)

Auditoría con las skills de [emilkowalski/skills](https://github.com/emilkowalski/skills) (`review-animations`, `improve-animations`, `animation-performance`, `apple-design`).

| Medida | `main` | Nuevo |
|---|---:|---:|
| Mensajes animados al abrir una conversación de 14 | 14 | **0** |
| Salida del inspector | instantánea | 180 ms interrumpible |
| 30 cambios de vista: fotogramas largos / p95 | 0 / 18,6 ms | 0 / 18,6 ms |
| Inspector abierto y cerrado 4 veces: p95 | 18,3 ms | 18,7 ms |
| Scroll del chat con borde difuminado: p95 | 18,3 ms | 18,7 ms |
| CSS / JS comprimidos | 10,6 / 194,8 KB | 11,5 / 195,2 KB |

Las medidas son de Chromium sin interfaz en el mismo Mac (refresco a 60 Hz) y no sustituyen una prueba en dispositivos reales.

## Prueba con un corpus realista (PDF, DOCX, tablas y versiones)

Para probarlo como lo haría una empresa se creó un corpus ficticio de diez documentos de «Aurelia Logística» (`backend/evals/realistic/`): manual del empleado y procedimiento de TI en **DOCX con tablas**, política de gastos y contrato de transporte en **PDF con tablas**, dos versiones de la política de teletrabajo (la de 2023 declara estar sustituida), políticas en Markdown y una nota con una instrucción dirigida al asistente. Las 60 preguntas están escritas como las haría una persona: coloquiales y sin tildes, de fila de tabla, de tramo («¿quién aprueba un gasto de 800 euros?»), de vigencia, de varias partes y sin respuesta.

| Conjunto realista | Correctas | Abstenciones correctas | Falsas abstenciones | Sin soporte | Citas literales | Seguridad | p50 / p95 |
|---|---:|---:|---:|---:|:---:|---:|---:|
| Desarrollo (35), **antes** de las correcciones | 7/27 | 8/8 | **19** | 1 incorrecta | sí | 13/13 | — |
| Desarrollo (35), final | 27/27 | 7/8 | 0 | **1** | sí | 13/13 | 17,2 s / 28,9 s |
| **Reservado (25), final** | **19/19** | **6/6** | **0** | **0** | sí | 13/13 | 18,2 s / 30,1 s |

El conjunto reservado se escribió antes de medir y no se ejecutó hasta tener el código cerrado con el de desarrollo; después se repitió una vez con el código final (tras corregir una regresión detectada en otro conjunto) con el mismo resultado, 25/25. Ficheros: `v4-realistic-*.json`.

**Qué destapó el corpus realista (todo corregido de forma general, con pruebas):**

1. La guarda de conflictos comparaba todos los fragmentos recuperados, tuvieran o no que ver con la pregunta: con dos versiones de una política en la biblioteca, **19 de 27 preguntas con respuesta se rechazaban**. Ahora solo cuentan las frases relacionadas con la pregunta.
2. Una política sustituida se citaba como vigente. Ahora un documento que declara estar sustituido se ignora salvo que se pregunte por esa versión.
3. Una cantidad en la pregunta («800 euros») se exigía literalmente en el documento. Los códigos y los años siguen siendo obligatorios.
4. **Las propuestas de ticket tardaban 90–120 s** y rozaban el límite: con herramientas nativas el modelo ignora `think=false`. Ahora tardan **≈4 s** (medido en los cinco conjuntos).
5. Una «respuesta» que repetía la pregunta («la responsable del workspace») se aceptaba como dato.

**Fallo abierto del corpus realista:** `neg_customer_shipping_fee`. A «¿Cuánto cuesta el envío estándar a un cliente?» el sistema responde con la tarifa que el transportista cobra a la empresa (4,80 € por bulto), citada literalmente del contrato. La cita es real, pero no responde a lo preguntado: Qwen3 4B no distingue a quién se aplica la tarifa.

Las latencias de este corpus son mayores que las de los conjuntos pequeños porque los pasajes son más largos y el equipo de 8 GB tenía otras aplicaciones abiertas durante la medición.

## Resultado principal: pipeline completo con Ollama real

`evaluate_local --live` sobre tres conjuntos, cada uno en una base nueva y vacía. Verifica además, por cada respuesta, que **toda cita entre «» existe literalmente en el fragmento que cita** y que aparecen los datos esperados.

| Conjunto | Correctas | Abstenciones correctas | Falsas abstenciones | Sin soporte / incompletas | Timeouts / errores | Citas literales | Recorridos de seguridad |
|---|---:|---:|---:|---:|---:|:---:|---:|
| 8 casos originales | 4/4 | 4/4 | 0 | 0 | 0 | sí | 13/13 |
| 13 casos reservados (nuevos) | 7/7 | 6/6 | 0 | 0 | 0 | sí | 13/13 |
| 11 casos de desarrollo | 7/7 | 4/4 | 0 | 0 | 0 | sí | 13/13 |

Estos tres conjuntos se repitieron con el código final de la prueba realista (`v4-original-8.json`, `v4-holdout-13.json`, `v4-dev-11.json`) con el mismo resultado; el corpus adversarial de pasajes fijos sigue en 25/27.

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

- Backend: **371 pruebas** (PostgreSQL real con esquemas aislados), `ruff` limpio. Incluye aislamiento por workspace, aprobación única por solicitante, ASK sin mutación, transacciones sin bloqueos durante la inferencia, idempotencia, streaming y 22 pruebas del modo de evidencia verificada (citas inventadas, citas de otro pasaje, reintento, ajuste, instrucciones incrustadas, fallos del evaluador).
- Frontend: **47 pruebas**, `tsc`, ESLint y `next build`. Comprueban que no queda ninguna etiqueta de demo, simulación ni proveedor externo.
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
| Los conjuntos pequeños y el reservado realista superan `automated_fixture_checks_passed` | ✅ cumplido |
| Cero respuestas sin soporte en los conjuntos de pipeline | ✅ cumplido (35/35, 25/25, 15/15, 8/8) |
| Toda cita mostrada es literal | ✅ cumplido (todas las respuestas medidas) |
| Cero timeouts y errores técnicos | ✅ cumplido |
| Cero falsas abstenciones en los conjuntos de pipeline | ✅ cumplido |
| Cero respuestas sin soporte en el corpus adversarial de pasajes fijos | ✅ cumplido (26/27; el fallo restante es una abstención) |
| Cero respuestas sin soporte en los conjuntos semánticos reservados | ❌ **2 de 20** en el reservado nunca visto (conflictos parafraseados) |
| Evaluación con documentos reales de una organización | ❌ no realizada (corpus realista pero ficticio) |
| Voz (Faster-Whisper/Piper) comprobada de extremo a extremo | ❌ no verificada |

**Decisión: no se crea tag ni release.** El corpus realista y los conjuntos de pipeline no tienen respuestas sin soporte, pero el conjunto semántico reservado aún tiene 2 de 20 (conflictos parafraseados sin cantidades o con una sola cita), y no hay validación con documentos reales de una organización.

## Comparación con otros modelos

No se ha descargado ningún modelo. Qwen3 8B (≈5 GB cuantizado) apenas cabría junto a EmbeddingGemma en 8 GB y Qwen3.5 4B no está instalado. Si lo autorizas, la comparación es directa y reproducible: `ollama pull`, `OLLAMA_CHAT_MODEL=<modelo>` y repetir los tres conjuntos y el corpus adversarial en bases nuevas, comparando correctas, falsas abstenciones, respuestas sin soporte, p50/p95 y memoria pico. Instrucciones en [LOCAL_AI.md](LOCAL_AI.md).

## Pendiente y no verificado

- Conflictos parafraseados sin cantidades («permitido» frente a «prohibido», quién custodia o autoriza algo) y plazos dichos con otras palabras cuando el modelo cita solo un documento.
- Preguntas que sugieren su propia respuesta («¿quién paga, el inquilino?»): abstención falsa.
- Conversaciones largas que saltan de tema: el historial entra en la recuperación y puede provocar abstenciones.
- Corpus mayores y documentos reales; recuperación a gran escala.
- Voz real de extremo a extremo.
- Comparación con un modelo mayor (requiere tu autorización y espacio/memoria).
- Compose bajo carga y despliegue en producción; indexación síncrona, sin RBAC ni invitaciones.
