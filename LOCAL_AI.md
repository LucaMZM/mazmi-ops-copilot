# IA local: puesta en marcha y límites

Ollama es un proveedor opcional de generación y embeddings. El valor predeterminado actual es Gemini (ver [GEMINI.md](GEMINI.md)); para seguir esta guía configura GENERATION_PROVIDER=ollama y EMBEDDING_PROVIDER=ollama. No necesita `OPENAI_API_KEY`; no hay fallback automático a OpenAI. El código nunca descarga modelos. Esta sesión validó contratos HTTP con mocks, no inferencia real: Ollama no estaba instalado y solo había aproximadamente 2,8 GiB libres.

## Preparación manual, cuando haya espacio

Los modelos publicados ocupan aproximadamente [2,5 GB para Qwen3 4B](https://ollama.com/library/qwen3:4b) y [622 MB para EmbeddingGemma](https://ollama.com/library/embeddinggemma). El espacio actual no basta. Planifica al menos 8–10 GiB libres más datos, backups y modelos de voz; es un margen orientativo, no un mínimo medido. Recomendamos 16 GiB de RAM para todo el stack; 8 GiB puede sufrir presión de memoria. La latencia en CPU debe medirse. No se ha medido rendimiento en este Mac.

1. Instala Ollama desde su distribución oficial. EmbeddingGemma requiere Ollama 0.11.10 o posterior; usa una versión estable actual y ejecuta la prueba de capacidades de abajo.
2. Solo después de disponer de espacio y decidir descargar, ejecuta manualmente:

```bash
ollama serve  # omitir si la aplicación Ollama ya sirve en 11434
# En otra terminal; estos comandos sí descargan modelos:
ollama pull qwen3:4b
ollama pull embeddinggemma
```

3. Copia `.env.example` a `.env` si todavía no existe (no sobrescribas configuración propia). Deja `OPENAI_API_KEY` vacía. Configura PostgreSQL con pgvector y sigue [MIGRATIONS.md](database/MIGRATIONS.md) antes de tocar una base existente.
4. Desde `backend`, con las dependencias existentes en tu virtualenv:

```bash
python -m app.migrate
python -m app.check_local
uvicorn app.main:app --reload
```

5. Desde `frontend`, con dependencias instaladas: `npm run dev`. Abre localhost:3000, crea una cuenta, sube un documento, pregunta por un hecho literal y prueba una pregunta sin respuesta. En DO, comprueba propuesta y confirmación desde Activity. El smoke test comprueba JSON estructurado, streaming, propuesta de tool y embeddings; nunca ejecuta la propuesta ni modifica la base.

`/health` comprueba aplicación/base y declara proveedores; no certifica disponibilidad de modelos. Ollama inaccesible, modelo ausente o respuesta inválida producen errores controlados. Las respuestas documentales retienen deltas hasta validar evidencia/citas; no muestran tokens no validados.

## Proveedores y compatibilidad

`GENERATION_PROVIDER` y `EMBEDDING_PROVIDER` aceptan `ollama`/`openai` independientemente. Solo la operación configurada con OpenAI necesita clave. `TTS_PROVIDER` también es independiente (piper por defecto). Reinicia el backend al cambiar configuración.

Ollama usa HTTP nativo `/api/chat`, `/api/embed` y `/api/tags` mediante httpx; no se presupone compatibilidad con OpenAI Responses. El adaptador convierte JSON Schema (`format`), streaming NDJSON, argumentos de tools y resultados `tool_name` al contrato interno. `think=false`, temperatura 0, contexto 8192 y `keep_alive=0` reducen memoria retenida a costa de recargas/latencia. Esquemas, autorización ASK/DO, citas y confirmación se validan siempre en backend. El soporte del modelo real se debe comprobar con `app.check_local` y los recorridos de producto.

Referencias: [chat](https://docs.ollama.com/api/chat), [embeddings](https://docs.ollama.com/api/embed), [tools](https://docs.ollama.com/capabilities/tool-calling), [structured outputs](https://docs.ollama.com/capabilities/structured-outputs).

## Colecciones y cambio de modelo

EmbeddingGemma usa 768 dimensiones por defecto y prefijos distintos para documento/pregunta según [su ficha](https://huggingface.co/google/embeddinggemma-300m). `truncate=false` evita cortar entradas silenciosamente; superar su contexto de 2048 tokens produce error. Historias/consultas extensas requieren pruebas específicas.

La identidad incluye proveedor, modelo, dimensiones, digest Ollama y versión de prefijos. En OpenAI incluye `EMBEDDING_REVISION` (legacy por defecto para preservar datos); si cambia un despliegue bajo el mismo nombre, cambia esa revisión manualmente. La API no permite detectar cambios internos de pesos OpenAI.

Ambas ramas de retrieval filtran la colección activa y workspace antes de calcular distancias. Un documento de otra colección puede seguir visible como ready, pero no se recupera hasta reindexarlo. Knowledge → Reindexar pide confirmación y vuelve a generar vectores desde chunks guardados. Preserva IDs/textos; reemplaza vectores y metadata en una transacción y revierte todo si falla. No conserva dos versiones vectoriales del mismo documento. No mezcles manualmente metadata o vectores. La migración 004 preserva los vectores OpenAI existentes; no los convierte en vectores locales.

## Voz local opcional

Cuando haya espacio, instala explícitamente `pip install -r requirements-voice.txt` en el virtualenv. Estas dependencias opcionales no se instalaron ni ejecutaron en esta sesión.

- Faster-Whisper: prepara fuera del repositorio un modelo compatible CTranslate2 y asigna su carpeta absoluta a `STT_MODEL_PATH`. El cargador exige archivos locales (`local_files_only=True`), CPU/int8; no descarga por nombre.
- Piper: prepara un modelo `.onnx` y su `.onnx.json` adyacente; configura `PIPER_MODEL_PATH` absoluto y, si procede, `PIPER_EXECUTABLE`. Comprueba licencia de la voz seleccionada.
- El navegador pide permiso, graba hasta 60 segundos y envía audio solo a este backend. Requiere localhost o HTTPS. Tamaño máximo 10 MB; rechazo controlado si falta configuración. No se ha probado audio/micrófono real.

Referencias: [Faster-Whisper](https://github.com/SYSTRAN/faster-whisper), [Piper](https://github.com/OHF-Voice/piper1-gpl).

Compose apunta a Ollama del host mediante host.docker.internal. No se ejecutó Docker en esta sesión. La imagen actual no incluye los extras/modelos de voz: para voz local usa el arranque nativo anterior; una ejecución en contenedor necesitaría instalación y montaje explícitos. No expongas Ollama ni PostgreSQL a Internet.

## Calidad pendiente

El cambio de proveedor conserva las evaluaciones, pero no demuestra calidad semántica de Qwen3 ni EmbeddingGemma. El control de facetas bloquea ahora la falta literal de datos salariales; sigue documentado un caso con palabras presentes y relación equivocada. No se garantiza suficiencia semántica completa. Calibra retrieval y evalúa suficiencia con modelos reales antes de una demo empresarial.
