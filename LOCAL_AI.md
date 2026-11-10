# IA local con Ollama

MAZMI genera respuestas y embeddings **únicamente con Ollama**, en tu equipo. No hay claves, proveedores de pago ni cambio automático a otro servicio. Esta página explica cómo se usa el motor, qué modelos requiere, cómo se gestiona el razonamiento de Qwen3 y cómo comprobar que todo funciona de verdad.

## Requisitos

- Ollama (probado con 0.40.7) escuchando en `http://127.0.0.1:11434`.
- Modelos ya instalados: `qwen3:4b` (generación, ≈2,5 GB) y `embeddinggemma` (embeddings 768 d, ≈0,6 GB).
- La aplicación **nunca descarga modelos**. Si falta uno, devuelve un 503 explícito.

```bash
ollama list                         # modelos instalados
curl --fail http://127.0.0.1:11434/api/version
make check-local                    # capacidades reales: JSON estructurado, streaming, embeddings
```

## Configuración

Las variables están en [.env.example](.env.example). Las relevantes:

| Variable | Valor por defecto | Efecto |
|---|---|---|
| `OLLAMA_CHAT_MODEL` | `qwen3:4b` | Modelo de generación |
| `OLLAMA_EMBEDDING_MODEL` | `embeddinggemma` | Modelo de embeddings (768 d) |
| `OLLAMA_REASONING` | `off` | `off` desactiva la fase de razonamiento de Qwen3; `on` la mantiene |
| `OLLAMA_KEEP_ALIVE` | `5m` | Tiempo que el modelo permanece en memoria |
| `OLLAMA_WARMUP` | `true` | Carga los dos modelos al arrancar el backend para evitar el arranque en frío |
| `OLLAMA_NUM_CTX` | `4096` | Contexto por petición |
| `OLLAMA_TIMEOUT_SECONDS` | `120` | Límite de cada llamada al modelo |
| `CHAT_MAX_CONCURRENT` | `1` | Consultas de IA simultáneas |
| `EVIDENCE_MODE` | `quoted_v6` | Evidencia con citas verificadas (ver abajo) |
| `ANSWER_LEAD` | `true` | Línea «Respuesta: …» sobre la evidencia, solo si el dato aparece literal en la cita |

Los valores antiguos `model_default` y `no_think_directive` de `OLLAMA_REASONING` se siguen aceptando.

## Por qué Qwen3 4B fallaba y qué se cambió

El diagnóstico de MAZMI 2.0 (resultados en [el histórico](docs/HISTORICO-VALIDACION-2.0.md)) mostró tres causas independientes:

1. **Timeouts y respuestas vacías: razonamiento.** Con la fase de razonamiento activada, Qwen3 4B gastaba casi todo el presupuesto de 2000 tokens «pensando» antes de escribir el JSON (`done_reason=length`, `content` vacío). Ahora el razonamiento está desactivado por defecto con el conmutador oficial de Qwen3 (`think=false`, `/no_think`) y su muestreo recomendado (temperatura 0,7, top_p 0,8, top_k 20; nunca decodificación voraz).
2. **Evidencia insuficiente aceptada.** Sin razonamiento, el modelo marcaba como suficientes pasajes del mismo tema que no contenían el dato. Un único ID de pasaje no es comprobable. Ahora el modelo debe **copiar una cita literal por cada parte de la pregunta**; el servidor comprueba que cada cita existe en el pasaje que nombra y una segunda llamada, con solo la pregunta y las citas verificadas, confirma que contienen el dato pedido. Las guardas deterministas (alcance, hechos, condiciones, contradicciones literales, instrucciones incrustadas) se mantienen antes y después.
3. **Falsas abstenciones por una guarda léxica.** La guarda de «límite/importe» exigía esas palabras exactas en el documento y rechazaba «alojamiento máximo». Se amplió con sinónimos (máximo, tope, techo).

4. **Propuestas de ticket lentas (90–120 s).** Con herramientas nativas, Qwen3 4B ignora `think=false` y escribe unos 900 tokens de razonamiento como texto antes de la llamada. Ahora los argumentos de la única herramienta que el servidor ha autorizado se piden con la misma gramática JSON que la evidencia: 2–4 s por propuesta. La autorización, la validación y la confirmación humana no cambian.
5. **Documentos reales.** Las pruebas con un corpus realista (PDF, DOCX, tablas, versiones) destaparon tres defectos generales, ya corregidos: la guarda de conflictos comparaba fragmentos que no tenían que ver con la pregunta; una política sustituida se citaba como vigente; y una cantidad en la pregunta («un gasto de 800 euros») se exigía literalmente en el documento.

El texto mostrado al usuario sale siempre del pasaje almacenado, nunca del modelo. La línea «Respuesta: …» solo aparece cuando el dato que propone el modelo está escrito tal cual en la cita mostrada.

## Versiones de un documento

Si un documento dice de sí mismo que está «sustituido por…», «derogado» o que «ya no está en vigor», MAZMI no lo usa para responder preguntas sobre la situación actual. Sí lo usa cuando la pregunta mira hacia atrás (un año, «la versión anterior»), y entonces lo indica junto a la cita. No hay fechas de vigencia ni un campo de estado: depende de que el propio documento lo declare.

## Memoria y recursos

Qwen3 4B (Q4_K_M) y EmbeddingGemma ocupan ≈3 GB residentes juntos con contexto 4096. En un Mac de 8 GB deja poco margen: ejecuta una consulta de IA a la vez, cierra aplicaciones pesadas y no lances compilaciones durante una evaluación. `OLLAMA_KEEP_ALIVE=5m` evita recargar el modelo entre preguntas; usa `0` si prefieres liberar memoria al instante.

## Comprobar que funciona (evidencia real)

```bash
cd backend
# Pipeline completo (HTTP, PostgreSQL real, Ollama real) en una base NUEVA y vacía *_eval o *_local:
DATABASE_URL=postgresql://…/mi_prueba_eval APP_ENV=development \
  python -m app.evaluate_local --live --cases evals/local_cases.json --output /ruta/resultado.json
```

El evaluador verifica además que **cada cita entre «» existe literalmente** en el fragmento que cita, comprueba datos esperados en la respuesta y registra latencias p50/p95 y memoria pico de Ollama. Conjuntos disponibles: `local_cases.json` (los 8 originales), `local_dev_v3.json` (desarrollo) y `local_holdout_v3.json` (reservado, no usado para ajustar nada). Resultados y fallos: [VALIDATION.md](VALIDATION.md).

## Comparar otro modelo

No se ha descargado ningún modelo adicional. Para evaluar Qwen3 8B o Qwen3.5 4B hace falta tu autorización (descarga y disco) y espacio libre; en este equipo hay poco. La comparación sería idéntica y medible: `ollama pull <modelo>` y, con `OLLAMA_CHAT_MODEL=<modelo>`, repetir los tres conjuntos anteriores en bases nuevas, comparando respuestas correctas, falsas abstenciones, respuestas sin soporte, p50/p95 y memoria pico.

## Voz opcional

Faster-Whisper (dictado) y Piper (lectura) son opcionales y locales; nunca se descargan solos. Configura `STT_MODEL_PATH` y `PIPER_MODEL_PATH` con rutas absolutas a modelos ya descargados. La voz no está verificada en este equipo; sin ella el chat escrito funciona igual.

## Docker (opcional)

Docker Compose levanta PostgreSQL, backend y frontend, pero **Ollama sigue en el equipo anfitrión**: el backend lo alcanza en `http://host.docker.internal:11434`. En Linux, Ollama debe escuchar en una interfaz accesible desde el contenedor (`OLLAMA_HOST=0.0.0.0`) y conviene proteger el puerto con el cortafuegos. No es necesario Docker para ejecutar el modelo local.
