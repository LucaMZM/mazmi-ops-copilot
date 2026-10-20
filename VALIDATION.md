# Publication preflight — 20 October 2026

This section is the latest state. Earlier dated sections below are retained as history, including older limitations and instructions not to commit. The current user explicitly authorized first public publication; no production web deployment is authorized or performed.

## Targeted changes

- Workspace now lists only ready, compatible documents under available knowledge. Failed and incompatible documents remain visible in Knowledge. Singular chunk labels, zero-byte metadata and upload success feedback corrected; TXT/DOCX uploads no longer claim reliable page counts.
- Healthcheck identifies both demo generation and demo embeddings honestly. Regression assertion added to the existing real-pipeline test.
- Demo seed generates a fresh random password instead of publishing a shared credential. It still requires development mode and a dedicated *_demo database, refuses populated databases before migrations, and uses real auth and approval paths. Demo instructions explain private local credential handling.
- English portfolio README with architecture, six screenshots, provider verification boundaries, reproducible setup, migration precautions and categorized versioned badges. Sixteen distinct Shields URLs returned HTTP 200 with embedded logo SVGs, including a neutral connector glyph for OpenAI where no official Shields icon exists. GitHub rendering and CI are checked after publication.
- CI uses Ubuntu, isolated PostgreSQL/pgvector 0.8.2-pg17, read-only contents permission, job timeouts and cancellation of superseded runs. No Docker Desktop invocation.

## Checks actually rerun

- Backend: **111 passed, 0 skipped**, 7.08s, against the existing isolated native PostgreSQL instance; Ruff passed.
- Frontend: **27 passed**; TypeScript, ESLint and Next production build passed after the last source change. Dependencies reused, no installation or model downloads. Native Node was 25.8.2; CI/container targets Node 22. Python 3.13.7; PostgreSQL 17.11 / pgvector 0.8.6 locally, distinct from CI image 0.8.2.
- npm audit: **0 production advisories**; **5 high development advisories** in ESLint's braces/micromatch/fast-glob chain remain. The suggested fix downgrades eslint-config-next to 14.2.35; it was not applied against Next 16.4.2. This is a disclosed limitation, not a vulnerability-free claim.
- Fresh demo seed smoke test passed on a new dedicated temporary database: generated-password login, three indexed fictional documents plus one failed empty file, demo configuration and refusal to reseed a populated DB. Credential withheld from shared output. The verification wrapper needed its import path corrected before the successful rerun; no existing data was reset.
- Public-file review found no vendor key/token/private-key signatures, real .env, local DB, backup or log among publication sources. .gitignore additionally excludes backups, venv/env, .local and browser auth state. .env.example keeps both API key values blank. Test credentials and fictional fixtures are not access credentials for a public service. No prior commits/history existed to scan for historical secrets.

## Browser journeys and evidence

Real Next production server on loopback, same-origin proxy to FastAPI and persistent dedicated demo PostgreSQL. No external AI calls. Verified login/logout/login, switch to empty Laboratory workspace (no Operations documents/history), TXT upload through browser file chooser and successful indexing, documentary query with citation, original source and stored chunk inspector, salary-question abstention, DO proposal, rejection, a separate approval creating ticket #2, Activity and effective provider configuration. No approval/security rules bypassed. Existing automated tests also check requester/workspace restrictions, repeated decisions, CSRF and citation validation.

Eight new authentic captures in [docs/screenshots](docs/screenshots/README.md): six main views, source inspector and mobile Copilot. Desktop 1440×1000; mobile 390×844 with clientWidth=scrollWidth=390. Images visually reviewed; only fictional documents, a .local email and demo metadata appear. Browser JPEGs were converted to PNG without retouching; original captures are outside Git. Screenshots show successive walkthrough steps, not one immutable snapshot.

## Remaining boundaries

Gemini/OpenAI/Ollama real calls, real audio, full Compose startup, production deployment and enterprise-scale operations remain unvalidated. No keys requested or added. The documented semantic grounding gap remains: mocked assessment achieves 14/15 negative-case abstentions, not universal entailment or injection resistance. Existing migration 003/004 guidance remains mandatory for databases with data; no migration 005. No paid service or billing enabled.

Local Git metadata was separated with git init --separate-git-dir to ~/Developer/mazmi-ops-copilot.git because iCloud was evicting loose objects and causing mmap timeouts. The working tree remains on Desktop; its .git file points to that durable directory. Existing objects and index were preserved. Keep that local metadata directory when moving this working tree; fresh GitHub clones are ordinary self-contained repositories.

Publication target: https://github.com/LucaMZM/mazmi-ops-copilot. Initial public run 39434279250: frontend job passed npm ci, typecheck, lint, all 27 tests, build and Compose configuration validation. Backend container initialization failed before tests: GitHub runner parsed a single-quoted --health-cmd as separate Docker flags (unknown -U). The workflow was corrected to use double quotes. Backend CI remains pending the next observed run; local backend tests remain 111 passing.

---

# Validación actual: producto y demo sin clave — 20 de octubre de 2026

## Estado inicial y alcance

La aplicación tenía tres vistas en un componente grande, proveedores y flujos técnicos probados con mocks, pero no había vista de configuración, cola global de aprobaciones ni demo navegable sin clave. Knowledge mostraba ready sin distinguir compatibilidad con la colección activa. Se conservó el backend, las migraciones y el pipeline propios.

## Producto implementado

- Sistema visual MAZMI: superficies claras, navegación verde profunda, tipografía editorial, tokens CSS, componentes reutilizables y adaptación móvil sin desbordamiento horizontal a 390 px. Sin fuentes remotas ni dependencias nuevas de UI.
- Workspace operativo con documentos reales, propuestas pendientes y actividad; sin tarjetas KPI artificiales. Se mantiene el selector de workspace y se expone la creación existente desde Configuración.
- Chat ASK/DO con estados separados de carga, streaming y subida; borrador recuperable, cancelación, historial y errores claros. Las respuestas documentales siguen siendo extractivas y solo se muestran tras validación. El inspector distingue citas usadas de fuentes recuperadas sin citar y muestra el texto conservado.
- Knowledge: búsqueda, filtros, compatibilidad por colección, metadatos y reindexación/eliminación explícitas. Inspector paginado (25 chunks), con autorización por workspace y sin vectores. El progreso no inventa porcentaje; polling mientras se indexa. No se almacena ni se ofrece descarga del archivo original.
- Aprobaciones: cola propia, estados pendiente/ejecutada/rechazada, alcance y consecuencia antes de confirmar. Activity presenta hechos permitidos y omite volcados de prompts/argumentos privados.
- Configuración: proveedor/modelo, estado local, colección/dimensión, indexación, workspace y voz. No expone claves/rutas privadas ni afirma conexión real desde un booleano de configuración. Los cambios de proveedor siguen realizándose en `.env` y requieren reiniciar backend.
- Corregido npm start para servir standalone con JS/CSS, en loopback por defecto. Arranque, HTML y recursos estáticos comprobados por HTTP.

## Demo y seguridad

Proveedor determinista pequeño integrado en la misma aplicación: no hay backend falso paralelo. Login, PostgreSQL/pgvector, documentos, retrieval, propuestas, decisiones y auditoría usan código real. Se requiere `APP_ENV=development`, `DEMO_MODE=true` y una base dedicada terminada en `_demo`. El seed rechaza bases con datos antes de migrar. Demo desactivada por defecto y colección `demo:` independiente. Los modelos y respuestas se identifican como fixtures.

Se corrigió la elección arbitraria del workspace al iniciar sesión: ahora elige el más antiguo. Los nuevos endpoints `/api/system`, `/api/actions`, `/api/documents/{id}/chunks` requieren sesión; aprobaciones filtra también por solicitante. Se probaron sesión ausente, workspace ajeno, paginación, información de configuración sin claves, aislamiento y rollback de chat cancelado antes de persistir.

Cancelar corta recepción y señala al worker SSE. La llamada síncrona al proveedor puede continuar hasta timeout y una transacción ya confirmada no se deshace. Antes de repetir una acción hay que revisar historial. No se promete cancelar el procesamiento remoto de un proveedor.

## RAG: comparación verificable

Dataset ampliado de 13 a 19 casos. Comparación ejecutada de extractive_v1 y extractive_v2 sobre los mismos 19, con los mismos veredictos simulados adversariales. Informe completo: [backend/evals/product-grounding-results.json](backend/evals/product-grounding-results.json).

| Control en este dataset | Política anterior | Política actual |
|---|---:|---:|
| Abstenciones correctas entre 15 casos insuficientes/adversariales | 10/15 | 14/15 |
| Falsas abstenciones entre 4 casos respondibles | 0/4 | 0/4 |

Se comprueba ausencia de facetas literales salariales e importe/límite en contexto y selección, y se rechazan algunos patrones explícitos de instrucciones al evaluador en pasajes seleccionados. Ahora se bloquea `model_lies_about_salary`. Se conservan pruebas de respuesta compuesta sustentada en dos pasajes, selección incompleta, contradicciones, citas inventadas y contenido malicioso.

**Fallo restante:** `facet_keyword_wrong_relation`. Un pasaje contiene vacaciones y salario, pero el salario corresponde a otra relación/contexto; un evaluador que declara suficiente ese pasaje todavía puede causar una cita irrelevante. Los controles literales no demuestran entailment ni resuelven conflictos parafraseados. También pueden abstenerse de más con sinónimos no contemplados o textos legítimos que describen un ataque. No se afirma defensa absoluta ante injection.

La evaluación de retrieval se repitió con PostgreSQL real y embeddings sintéticos: Recall@6=1,0, MRR=1,0; latencia media 0,645 ms en esa ejecución pequeña. Es la misma estrategia híbrida existente, **no una mejora nueva de embeddings ni una métrica de Gemini real**. Informe: [backend/evals/product-retrieval-results.json](backend/evals/product-retrieval-results.json).

## Checks y evidencias

- Backend: **111 tests pasados, 0 omitidos**, 8,07s; Ruff correcto. Antes:91.
- Frontend: **27 tests pasados**, typecheck, lint y build de producción correctos. Antes:7. Incluye inspector vacío, cancelación, carga parcial y estados de autenticación.
- `pip check` correcto; dependencias bloqueadas restauradas en entornos temporales porque los anteriores ya no existían. No se añadieron librerías al producto; se reutilizó un formatter instalado.
- PostgreSQL temporal 17.11 / pgvector0.8.6, dos bases aisladas para pruebas y demo. No Docker, modelos locales ni migraciones sobre bases existentes del usuario. No migración005.
- Navegador real: login, cambio de workspace, subida TXT e indexación, pregunta con cita, apertura de fuente y de chunks almacenados, aprobación y estado ejecutado, historial móvil, configuración de demo y persistencia tras reiniciar backend. Viewports 1440×1000 y390×844; ancho390 sin overflow horizontal.
- Capturas auténticas guardadas en evidence: workspace-product-desktop.jpg, knowledge-product-desktop.jpg, approvals-product-desktop.jpg, source-inspector-desktop.jpg, settings-product-desktop.jpg y chat-product-mobile.jpg. No son diseños generados.

## Qué falta

No se realizó ninguna petición Gemini/OpenAI real ni audio/micrófono real. El SDK Gemini 2.31.0 se probó mediante transporte HTTP simulado, incluyendo401/403/429/500/503, timeouts y conexión interrumpida, sin retries/fallback. Identificadores y capacidades se contrastaron con documentación oficial actual. Para Gemini: guardar clave solo en `.env`, desactivar demo, reiniciar, reindexar con la colección real y ejecutar `python -m app.check_gemini`; después medir calidad/latencia/cuota en datos representativos.

La demo visual/funcional sin clave es utilizable siguiendo [DEMO.md](DEMO.md). No equivale a una validación empresarial de la IA real. Voz cloud sigue pendiente; voz local opcional requiere instalación/modelos explícitos. Para producción faltan calibración semántica, validación del proveedor real, cuotas por usuario, recuperación de cuenta/invitaciones/RBAC, cola persistente de ingestión, políticas de retención y pruebas operativas de backup/migraciones con volumen real. La configuración de proveedores es de servidor y no un editor web.

Sin commit ni push. Historial de validaciones anteriores conservado debajo.

---

# Validación anterior: Gemini cloud — 19 de octubre de 2026

## Implementado

Gemini es el proveedor predeterminado de generación (`gemini-3.5-flash-lite`) y embeddings (`gemini-embedding-2`, 768 dimensiones). Modelos seleccionados tras consultar precios, capacidades y deprecaciones oficiales; nivel gratuito sujeto a proyecto/cuota. OpenAI y Ollama se conservan. No se habilitó facturación, no se descargaron modelos ni se usó Docker.

SDK oficial instalado y fijado: `google-genai==2.31.0`, dependencias resueltas en requirements.lock; `pip check` correcto. Solo se añadió el SDK y sus dependencias al virtualenv existente. Su restricción websockets<17 requiere 16.1.1 en el lock. No se reinstaló frontend.

Pruebas utilizan el SDK real sobre httpx.MockTransport: serialización JSON Schema, tool declarations, firmas de pensamiento conservadas entre llamada/resultado, streaming SSE, fin bloqueado/truncado y HTTP 400/403/429/503 sin exponer cuerpo de error. Automatic function calling deshabilitado y un solo intento de red; ningún fallback. El SDK rechazó `auto_truncate` en Developer API durante desarrollo: corregido con límite de entrada de 8000 bytes. Embeddings separados por Content y prefijos de retrieval, cardinalidad/dimensiones comprobadas.

## Resultados ejecutados

- **91 tests backend pasados, 0 omitidos**, 5,50 s. Ruff correcto tras corregir la captura de excepciones del smoke test.
- **7 tests frontend pasados**, typecheck, lint y build de producción correctos. Compilación realizada en copia temporal con fuentes verificadas idénticas; dependencias existentes.
- PostgreSQL temporal **17.11 / pgvector 0.8.6**, sin Docker. Suite de migraciones y seguridad conservada.
- Nuevo recorrido HTTP: documento OpenAI existente excluido por colección Gemini, reindexación a768, retrieval/cita válida, workspace ajeno sin resultados, propuesta DO por streaming, ausencia de ticket antes de aprobar, ejecución una sola vez y auditoría.
- 429 comprobado por HTTP y evento SSE; error saneado sin texto privado y rollback de reindexación manteniendo vectores previos. Los tests unitarios verifican que el SDK no reintenta 429/503 ni ejecuta tools automáticamente.
- Sin migración nueva: **004** permite colecciones Gemini; documentación de backup/espacio/ventana de mantenimiento conservada y ampliada. No se migró ninguna base empresarial existente.

## Pendiente real

No se ejecutaron llamadas a Gemini real ni se pidió/guardó una clave. `python -m app.check_gemini` deja preparada una prueba explícita con texto ficticio, sin herramientas ejecutadas ni escrituras en base. Validar acceso de la cuenta, cuota, respuestas estructuradas y llamadas firmadas del modelo real, calidad de retrieval/suficiencia y latencia. No se declara mejora semántica: sigue vigente el caso adversarial de abstención de la sección histórica.

La voz cloud gratuita se investigó en documentación pero no se implementó; no se prueba audio real. Faster-Whisper/Piper y OpenAI TTS opcionales siguen disponibles. Sin modelos locales, usar la demo cloud por texto; errores de voz no bloquean chat. Ver [GEMINI.md](GEMINI.md) para condiciones gratuitas, configuración, límites, seguridad de claves y procedimiento de prueba. No hay garantía de coste cero con una clave ligada a facturación: usar proyecto Free Tier sin facturación.

Sin commit ni push. Los resultados anteriores se conservan debajo como historial, no como pruebas nuevas con Gemini real.

---

# Validación anterior: proveedores locales — 18 de octubre de 2026

- Ollama predeterminado: Qwen3 4B y EmbeddingGemma; generación/embeddings independientes, OpenAI conservado como opción. API key vacía en pruebas locales. No hay fallback ni descarga automática.
- Adaptador nativo probado con httpx MockTransport: esquema JSON, NDJSON streaming, tools/resultados, fin incompleto, errores, digest y embeddings. No se afirma compatibilidad ejecutada con un servidor real: Ollama no estaba instalado/disponible.
- **79 tests backend pasados, 0 omitidos; Ruff correcto. 7 tests frontend pasados; typecheck, lint y build de producción correctos.** PostgreSQL temporal 17.11 / pgvector 0.8.6. No Docker ni OpenAI real.
- Recorrido HTTP con proveedor local simulado: subida/indexación, RAG citado, DO/propuesta/confirmación/auditoría. Preservados tests de aislamiento, herramientas no autorizadas, citas y suficiencia.
- Colecciones separadas por proveedor/modelo/dimensión/revisión/digest; filtros previos a distancia en ambas ramas. Probadas coexistencia OpenAI1536/local768, reindexación a256, rollback ante vector inválido, cambio de digest y workspace ajeno.
- Migración 004 probada sobre estructura legacy con filas existentes y aplicada dos veces; conserva datos. Aplicación segura: [database/MIGRATIONS.md](database/MIGRATIONS.md). No se migró ninguna base empresarial existente.
- Evaluación offline repetida: retrieval híbrido Recall@6=1,0 y MRR=1,0 con vectores sintéticos; **no son métricas de EmbeddingGemma real**. Grounding conserva 10/11 abstenciones previstas, incluido el fallo semántico documentado abajo. No se declara mejora de precisión por cambiar de proveedor.
- Voz preparada: MediaRecorder → Faster-Whisper local y Piper → WAV; configuración ausente y contrato CLI probados con mocks. No se instalaron motores/modelos de voz ni se probó micrófono/audio real.
- Disponible `python -m app.check_local` para verificar el servidor/modelos instalados sin ejecutar acciones ni modificar la base. Pendientes inferencia real, calidad semántica, latencia/memoria y voz. Con aproximadamente 2,8 GiB libres no se descargó ningún modelo.
- Instrucciones, hardware orientativo y límites: [LOCAL_AI.md](LOCAL_AI.md). Sin commit ni push.

---

# Validación anterior: suficiencia y sustentación RAG — 18 de octubre de 2026

## Diagnóstico y cambio

El fallo original es **«¿Cuántas vacaciones tienen los empleados de Marte?»**. El embedding simulado comparte el tema vacaciones con la política general y retrieval devuelve esa política. La puerta anterior comprobaba presencia de fuentes e índices de citas, no si el ámbito de la pregunta estaba cubierto. Citar [1] no demostraba aplicabilidad a Marte.

Nueva política documental `extractive_v1` en `backend/app/evidence.py`:

- Comprueba ámbitos explícitos (nombres propios no iniciales, códigos/números, textos entre comillas y algunos calificadores locales como «empleados de ...») contra evidencia, sin usar similitud como prueba de suficiencia. Incluye «marte» en minúscula en el caso de empleados.
- Detecta contradicciones literales entre todas las fuentes recuperadas: mismo patrón de frase con cifras o negación diferentes. No resuelve jerarquía, fechas de vigencia ni conflictos parafraseados.
- Pide una decisión estructurada `sufficient/insufficient/conflicting` y IDs de pasajes. Se comprueba que cubra toda la pregunta y sus condiciones mediante instrucciones al evaluador; esta parte **requiere medir acierto semántico con modelo real**.
- Backend valida estrictamente esquema, tipos, IDs, duplicados, respuesta incompleta y ámbito de la selección. No confía en texto generado para redactar hechos: devuelve chunks completos existentes entre comillas, con referencias numeradas creadas en servidor. Esto preserva negaciones y condiciones dentro del chunk y evita inventar cifras, páginas o prosa nueva.
- Números entre corchetes que ya estaban en el documento se muestran como texto literal `〔99〕`, no como citas del servidor.
- Abstenciones y selección se auditan mediante motivos e IDs, sin añadir texto privado a los logs. SSE emite progreso y solo texto validado.
- Las herramientas mantienen su ruta separada: sin documentos/historial, autorización explícita, esquemas estrictos y confirmación humana. El evaluador documental no tiene herramientas.

El formato de salida se comprobó con el SDK instalado y [OpenAI Structured Outputs](https://developers.openai.com/api/docs/guides/structured-outputs?api-mode=responses). No se realizó ninguna llamada OpenAI real.

## Resultados medidos

- **61 tests backend pasados, 0 omitidos**, en 3,34 s; Ruff correcto.
- **5 tests frontend pasados**. Sin cambios de interfaz ni build repetido.
- PostgreSQL temporal **17.11 / pgvector 0.8.6**, sin Docker.
- El caso Marte se probó por HTTP con documento indexado, retrieval real y verificación de que no se invoca generación. Motivo auditado: `missing_question_scope`.
- Los dos casos originales sin respuesta (sin documentos y Marte con política general) pasan de **1/2 a 2/2** para la política de abstención con mocks.

Evaluación adicional reproducible: `python -m app.evaluate_grounding`. Dataset de **13 casos** y resultados en [backend/evals/grounding-results.json](backend/evals/grounding-results.json). Compara la puerta anterior de fuentes/citas con la nueva política mediante respuestas candidatas y veredictos simulados explícitos; no simula que se haya medido inteligencia del modelo.

| Medida de esta evaluación de controles | Antes | Ahora |
|---|---:|---:|
| Abstenciones correctas en 11 casos previstos | 1/11 | 10/11 |
| Falsas abstenciones en 2 casos respondibles | 0/2 | 0/2 |

Desglose actual: **7/7 controles deterministas**, **2/2 respuestas extractivas**, **3/3 propagaciones de veredictos semánticos simulados**, **0/1 caso adversarial semántico restante**. Los tres veredictos simulados cubren salario ausente, pregunta compuesta incompleta y contradicción parafraseada: prueban que se respeta una decisión de insuficiencia/conflicto, **no que OpenAI sepa tomarla**.

## Fallo restante y límites explícitos

`model_lies_about_salary`: pregunta por salario durante vacaciones; solo existe una frase de 25 días de vacaciones; el mock declara falsamente sufficient. El backend devuelve esa frase, que no responde a salario. **No inventa el salario, pero no se abstiene correctamente.** El resultado queda conservado como fallo de la evaluación, con un test que verifica y documenta ese límite.

No está resuelta toda la suficiencia semántica. Los controles literales pueden abstenerse de más por variantes de nombres, acrónimos, versiones o ámbitos implícitos. Una coincidencia literal tampoco demuestra que dos entidades estén relacionadas. Un chunk puede perder condiciones situadas en otro chunk; copiarlo no demuestra verdad ni aplicabilidad. Se mantienen límites de retrieval: ausencia de un documento contradictorio fuera del top-K no puede detectarse aquí. Una cita válida y un pasaje literal no garantizan sustentación semántica completa.

Cambio deliberado de producto: las respuestas documentales son ahora extractivas (chunks completos citados), menos fluidas y potencialmente más largas. No hay paráfrasis libre ni cálculos derivados del modelo. Los fragmentos de documentos siguen siendo datos no fiables; no se afirma inmunidad ante toda manipulación del veredicto semántico.

## Migración 003 y siguiente validación

Prueba real: en el esquema privado de un test se simuló una base anterior a 003 con filas existentes. El runner se ejecutó dos veces: mismos IDs/contenido/embeddings, búsqueda FTS del dato previo correcta y una sola entrada del ledger. Se añadieron límites locales de bloqueo (5 s) y ejecución por sentencia (120 s), manteniendo rollback transaccional y advisory lock.

Aplicación segura documentada en [database/MIGRATIONS.md](database/MIGRATIONS.md): verificar espacio, backup/restauración, ensayo en copia, ventana de mantenimiento y comprobación posterior. STORED + GIN puede reescribir/bloquear tabla; **no aplicar ahora a una base existente con almacenamiento insuficiente**. Solo se modificaron bases temporales de pruebas, detenidas al terminar.

**Preparado para empezar pruebas OpenAI reales supervisadas**, con clave exclusivamente local y una base migrada segura. Validar soporte real del esquema/modelo configurado, negativas/refusals, truncamiento, tiempos y coste, y sobre todo sensibilidad/especificidad del evaluador en datos representativos. No declarar lista para producción la abstención semántica. No se usó Docker, no hubo commit ni push; código, dataset y resultados guardados también en la carpeta del Escritorio.

---

# Revisión anterior: búsqueda híbrida — 18 de octubre de 2026

## Implementado y verificado en esta sesión

- Migración `003_hybrid_retrieval.sql`: tsvector español generado para chunks existentes/nuevos e índice GIN, sin regenerar embeddings.
- Recuperación híbrida por coseno + Full Text Search, RRF con constante 60, candidatos acotados y deduplicación de texto normalizado. Se conserva documento/página/chunk y la similitud coseno separada del score RRF. No se añadió reranker: no hay evidencia suficiente para justificar otro componente.
- Filtros de workspace tanto en chunk como documento, estado ready y modelo en ambas ramas. Vectorial exacta dentro del workspace para evitar candidatos perdidos por postfiltrado de HNSW. Esto debe medirse con corpus grandes antes de escalar.
- Logs/auditoría: estrategia, candidatos por rama, IDs seleccionados, posiciones, puntuaciones, duración y motivo de abstención. No se registran preguntas ni texto documental en estos diagnósticos.
- Sin evidencia, abstención determinista sin generar texto con el proveedor. Respuestas documentales sin citas o con índices inválidos se sustituyen por abstención antes de llegar al cliente.
- Documentos e historial no entran en llamadas con tools; las llamadas documentales tienen tools vacías, incluso en DO. Backend rechaza llamadas no habilitadas aunque el proveedor las emita. La petición actual explícita habilita consulta o propuesta; esquema estricto y confirmación transaccional siguen vigentes.
- Cambio deliberado de experiencia: SSE mantiene estados y respuesta final, pero no expone tokens sin validar. Las peticiones ambiguas de herramientas requieren reformularse (p. ej. «Consulta mis tickets» / «Crea un ticket ...» en DO). No se deriva autorización de documentos ni del historial.

## Comparación reproducida

PostgreSQL **17.11**, pgvector **0.8.6**, instancia temporal local. **13 documentos y 8 preguntas**: 6 con fuente conocida y 2 sin respuesta, incluyendo copias, procedimientos similares, códigos exactos y documento con prompt injection. Mismo corpus y mismos embeddings deterministas para ambas estrategias; baseline reproduce SQL anterior con desempate por ID. Fixtures revertidas por rollback.

| Métrica | Vectorial anterior | Híbrido RRF |
|---|---:|---:|
| Recall@6 (6 casos respondibles) | 66,67% | 100% |
| MRR (6 casos respondibles) | 0,6667 | 1,0000 |
| Primera fuente esperada correcta | 66,67% | 100% |
| Precisión media de fuentes esperadas | 58,33% | 72,22% |
| Sin evidencia en preguntas sin respuesta | 1/2 | 1/2 |
| Falsas abstenciones en preguntas respondibles | 0/6 | 0/6 |
| Latencia media retrieval, una ejecución local | 0,333 ms | 0,483 ms |

Los dos fallos recuperados son códigos exactos entre ocho procedimientos cuyos embeddings simulados son iguales. La precisión de fuentes usa un único archivo canónico esperado por caso: penaliza otros documentos y duplicados aunque puedan repetir el mismo hecho. No es una medida de precisión semántica de respuestas.

**No mejoró la abstención semántica:** «vacaciones de empleados de Marte» sigue recuperando la política genérica de vacaciones. Una cita existente no prueba que sustente la afirmación. La validación evita índices inexistentes, no toda alucinación en el texto (incluidos nombres/páginas mencionados en prosa). Metadatos de las fuentes provienen exclusivamente de la base de datos. Tampoco se afirma inmunidad semántica completa ante prompt injection; sí se verificó la barrera entre documentos y capacidades de herramientas.

Resultados por caso: [backend/evals/latest-results.json](backend/evals/latest-results.json). Reproducir desde backend con base de pruebas migrada: `python -m app.migrate` y `python -m app.evaluate`. Offline no llama a OpenAI. `--live` utiliza embeddings reales y **no se ejecutó**. Estas cifras no se comparan con el antiguo 100% de tres casos fáciles: aquí se volvió a ejecutar el baseline sobre el dataset ampliado. Latencia sin coste de red real, no un SLA.

## Checks finales

- **38 tests backend pasados, 0 omitidos**; Ruff correcto.
- **5 tests frontend pasados**. No hubo cambios frontend ni se repitió su build.
- Migraciones aplicadas dos veces correctamente en la base temporal.
- Tests nuevos: recuperación léxica con embedding no relacionado; deduplicación; aislamiento FTS/vector incluso con metadatos inconsistentes; exclusión de documentos fallidos; comparación baseline/híbrido y rollback; abstención sin generación; citas inválidas nunca emitidas por SSE; proveedor adversarial intentando tools desde documentos en ASK/DO; ausencia de propuestas/tickets persistidos en esos ataques; exclusión del historial contaminado en llamadas con tools.
- Se mantuvieron aprobación concurrente sin duplicados, rechazo humano, argumentos inválidos, historial, autenticación, CSRF y aislamiento de conversaciones/acciones.

No se tocó Docker ni se invocó OpenAI real. No hubo cambios de dependencias, interfaz, commit ni push. Fuentes y resultados sincronizados con la carpeta del Escritorio; `.git` preservado. Instancia PostgreSQL de pruebas detenida al terminar.

## Pendiente prioritario

Calibrar relevancia/abstención con embeddings reales y datos representativos, detectar preguntas no respondibles pero cercanas al tema, evaluar sustentación semántica y ataques sobre el texto de las respuestas, medir escalabilidad y considerar reranking solo con ganancia demostrada. FTS usa español y deduplicación exacta normalizada; no resuelve equivalencia semántica, contradicciones ni vigencia documental. Aplicar migración 003 antes de arrancar esta versión sobre una base existente.

---

# Revisión anterior: UI y producto — 18 de octubre de 2026

## Última revisión

Pulido sobre la base existente, sin cambiar el stack ni añadir integraciones. Código guardado en el workspace y sincronizado con `/Users/lucamazmi/Desktop/mazmi-ops-copilot`. Sin commit ni push.

- Navegación e historial accesibles en móvil, conversación activa identificada, tipografía legible, foco visible y movimiento reducido.
- ASK/DO con explicación y estado accesible; propuestas explícitamente no ejecutadas y confirmación humana conservada.
- Knowledge muestra resumen, estados y errores de subida/indexación, límites y eliminación en curso. Progreso indeterminado real, no porcentajes ficticios.
- Fuentes desplegables muestran el fragmento recuperado completo, documento, página cuando existe y similitud (no confianza). No hay descarga del original: el sistema conserva texto y metadatos, no el archivo original.
- Activity muestra eventos legibles y detalles técnicos desplegables.
- Dictado no soportado y permisos fallidos producen errores visibles sin bloquear el texto. Lectura con estado y botón de parada; solicitudes de audio cancelables.
- Corregidos envío con Enter durante carga, errores de Knowledge invisibles, interferencias del dictado con mensajes en streaming y recorte de espacios de contraseñas. Solicitudes de datos/chat tienen tiempo máximo; al agotar el tiempo de una acción se indica revisar historial antes de repetir.
- No se añadió una pantalla de Settings con controles sin efecto.

## Resultados ejecutados sobre los cambios finales

| Check | Resultado |
|---|---|
| Backend pytest | **26 pasados, 0 omitidos** (3,02 s) |
| Ruff | Correcto |
| Frontend Vitest | **5 pasados** |
| ESLint | Correcto |
| TypeScript | Correcto |
| Next `npm run build` | Build de producción standalone correcto |
| PostgreSQL / pgvector | **17.11 / 0.8.6**, instancia aislada local |
| Migraciones | Ejecutadas correctamente para la instancia de navegador |
| HTTP `/health` | 200, `status=ok`, proveedor simulado configurado |
| Chrome / Playwright | Recorridos de escritorio y móvil completados, sin errores JavaScript |

Las primeras ejecuciones desde sandbox fallaron por bloqueo de TCP (pytest) y apertura de puerto (Turbopack). Repetidas con acceso local y caché generada limpia: todos los checks anteriores pasaron. No se cambiaron dependencias de producción. Playwright se instaló únicamente en una carpeta temporal y usó Chrome ya instalado.

Backend probado desde el workspace. Frontend probado en `/tmp/mazmi-verify` con dependencias existentes y fuentes idénticos a los guardados. La base temporal tiene credenciales aleatorias, escucha solo en loopback y no contiene información empresarial real.

## Navegador: lo que se probó realmente

Frontend Next en `127.0.0.1:3001`, proxy hacia FastAPI en `127.0.0.1:8001`, autenticación y persistencia reales en PostgreSQL. Se sustituyeron únicamente las llamadas externas del proveedor por respuestas y vectores deterministas en un proceso de prueba, sin activar un modo simulado en el código de producción.

1. Registro y sesión mediante cookie.
2. Subida TXT → extracción → chunks → embeddings simulados → pgvector → estado listo.
3. Pregunta → retrieval real → respuesta simulada por streaming → fuente desplegable.
4. DO → propuesta → confirmación → ticket persistido; propuesta posterior rechazada sin ejecutar.
5. Consulta de auditoría y recuperación de conversación después de recargar.
6. Navegación e historial en viewport móvil de 390 × 844, sin desbordamiento horizontal.
7. Dictado no soportado (API del navegador deshabilitada en la prueba) → error claro → nueva consulta escrita completada.
8. PDF inválido → error visible; eliminación de documento completada.

Capturas reales con datos sintéticos y OpenAI simulado:

- [Knowledge](evidence/knowledge-desktop.png)
- [Chat, fuentes y propuesta](evidence/chat-proposal-desktop.png)
- [Auditoría](evidence/activity-desktop.png)
- [Chat móvil](evidence/chat-mobile.png)

Los tests backend cubren además ausencia de API key (503 controlado), argumentos inválidos, consultas vacías, fallos del proveedor sin exponer secretos, aprobación concurrente sin duplicados, aislamiento de workspaces, autenticación, CSRF, extracción PDF/DOCX y eliminación de chunks. La verificación del pipeline no demuestra calidad semántica de modelos reales.

## Docker

Antes del intento había aproximadamente **3,98 GiB libres**. Consultas de estado agotaron su límite; `docker compose up -d --build` devolvió **Docker Desktop is unable to start**. No se borraron datos ni se forzó un reinicio. No se completó el arranque Docker en esta revisión. Compose fija pgvector 0.8.2, mientras la validación nativa usa 0.8.6. Pendiente validar stack y persistencia de volúmenes tras reinicio cuando Desktop arranque.

## Git y secretos

Git funciona en `main` dentro de cada carpeta `mazmi-ops-copilot`. Todos los fuentes siguen como nuevos/sin seguimiento porque no hay commit inicial; por eso `git diff --stat` está vacío. No se hizo commit ni push. El `.git` inaccesible de la carpeta superior del workspace permanece intacto; no usar esa carpeta como raíz del repo.

`.gitignore` excluye `.env` y variantes, claves privadas, dependencias, builds, caches, bases locales y temporales. `.env.example` conserva la API key vacía y credenciales PostgreSQL explícitamente locales de ejemplo. Capturas con datos sintéticos únicamente.

## Estado para presentación

**Apto para demo local supervisada con proveedor simulado. No declarar listo para publicación abierta/producción todavía.**

Pendiente: restaurar Docker Desktop; probar OpenAI con clave exclusivamente local (coste, latencia y calidad RAG); probar TTS y micrófono con permisos reales; validar despliegue HTTPS y `COOKIE_SECURE=true`, límites operativos y restauración de backups. No hay roles empresariales, recuperación de contraseña ni OCR. La ingestión es síncrona; una generación puede terminar en el servidor tras desconectarse el navegador. No se validó cancelación del trabajo en backend ni persistencia tras reinicio del servidor en esta revisión. La auditoría npm anterior registraba 5 avisos high en dependencias de desarrollo ESLint/braces; no se repitió la auditoría de red aquí.
