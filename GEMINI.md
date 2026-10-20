# Prueba cloud gratuita con Gemini

Antes de introducir una clave puedes recorrer la aplicación con [DEMO.md](DEMO.md). La vista Configuración distingue demo, valores configurados y conexión real no verificada.

Configuración predeterminada desde el 19 de octubre de 2026:

- Generación: `gemini-3.5-flash-lite`.
- Embeddings: `gemini-embedding-2`, 768 dimensiones.
- SDK oficial `google-genai==2.31.0`, Gemini Developer API. No Vertex AI, agentes gestionados, búsqueda de pago ni trabajos Batch API.

Ambos modelos tienen nivel gratuito publicado en la [tabla oficial](https://ai.google.dev/gemini-api/docs/pricing). Para proyectos nuevos, Google recomienda modelos recientes; el [acceso a 2.5 está restringido a usuarios anteriores](https://ai.google.dev/gemini-api/docs/deprecations). No elegimos 2.5 como valor predeterminado.

**Usa un proyecto en Free Tier sin facturación vinculada.** Una API key no certifica que su proyecto sea gratuito: si pertenece a un proyecto con facturación, las mismas llamadas pueden generar cargos. La aplicación no consulta ni cambia la facturación; no puede imponer un límite monetario desde el SDK. Cuotas, disponibilidad regional y acceso dependen de Google y se consultan en AI Studio. No hay garantía de cuota ilimitada. Ante 429 se muestra un error y no se reintenta ni cambia de modelo/proveedor automáticamente.

Usa documentos ficticios para esta prueba. Revisa los términos aplicables a tu región: el nivel gratuito tiene condiciones de tratamiento de datos distintas del de pago, tal como indica la tabla oficial. No presupongas confidencialidad empresarial para documentación interna sensible.

## Arranque sin descargar modelos

1. En [Google AI Studio](https://aistudio.google.com/apikey), crea una clave para un proyecto gratuito **sin activar facturación**. Guarda la clave únicamente en `.env` de la raíz. No la pegues en chats ni comandos que queden en el historial.
2. Si `.env` ya existe, edítalo; no lo sobrescribas con el ejemplo:

```dotenv
GENERATION_PROVIDER=gemini
EMBEDDING_PROVIDER=gemini
GEMINI_API_KEY=  # asignar aquí exclusivamente la clave local; quitar este comentario
GEMINI_MODEL=gemini-3.5-flash-lite
GEMINI_EMBEDDING_MODEL=gemini-embedding-2
# EMBEDDING_DIMENSIONS=768
```

3. En el virtualenv existente instala solo la dependencia nueva y sus dependencias: `python -m pip install google-genai==2.31.0`. Para entornos nuevos usa `backend/requirements.lock`. No hace falta reinstalar frontend ni instalar Ollama. El SDK y sus dependencias se probaron con `pip check`.
4. Con PostgreSQL + pgvector disponible, revisa primero [la migración 004](database/MIGRATIONS.md). No arranques sobre una base existente casi sin espacio: el backend aplica migraciones pendientes al iniciar. Gemini no requiere migración 005.
5. Desde `backend`, ejecuta `python -m app.check_gemini`. Usa unas pocas solicitudes con texto ficticio para esquema JSON, streaming, propuesta de función y embedding. No crea tickets ni toca la base. Puede agotar cuota; no ejecutarlo en bucle.
6. Desde `backend`: `uvicorn app.main:app --reload`. Desde `frontend`: `npm run dev`. Abre localhost:3000. No se necesita Docker.
7. Crea cuenta, sube un TXT pequeño y pregunta por un hecho literal; comprueba la cita. Pregunta algo ausente y comprueba abstención. En DO pide crear un ticket: debe aparecer una propuesta, sin ticket creado hasta aprobarla. Comprueba Activity y rechazo de una segunda aprobación.

El smoke test **no se ejecutó contra Google** durante esta sesión. Se probó el SDK instalado con transporte HTTP simulado y una base temporal real. Falta verificar tu clave/proyecto, acceso efectivo a modelos, cuota, latencia y calidad semántica del evaluador.

## Contratos y conservación de seguridad

El adaptador utiliza `generate_content`, `generate_content_stream` y `embed_content` del [SDK oficial](https://github.com/googleapis/python-genai). Structured outputs usa JSON Schema y validación posterior del backend. Las llamadas automáticas del SDK están deshabilitadas; las declaraciones de tools no contienen funciones Python ejecutables. El backend conserva autorización ASK/DO y confirmación humana. Las firmas de pensamiento se conservan en memoria al devolver un resultado de tool al modelo, sin incorporarlas a auditoría ni frontend. El resumen de una acción ya confirmada se solicita sin inventar una llamada firmada anterior.

Streaming descarta respuestas incompletas/bloqueadas; las respuestas documentales siguen reteniéndose hasta validar evidencia y citas. Los errores del proveedor se sustituyen por mensajes fijos: no se devuelven cuerpos privados, claves ni trazas. Un 429 llega como HTTP 429; si SSE ya comenzó, llega como evento de error controlado.

Los embeddings de cada chunk se envían como `Content` separado para evitar agregarlos en un solo vector. Prefijos de búsqueda distintos para documento y pregunta, según [la guía oficial](https://ai.google.dev/gemini-api/docs/embeddings). Límite conservador de entrada: 8000 bytes por texto, incluido prefijo; no se usa `auto_truncate`, que el SDK rechaza en Developer API. Se verifican cardinalidad, dimensiones y valores finitos/no nulos.

La colección incluye `gemini`, modelo, dimensión, revisión y versión de prefijos. Ambas ramas de retrieval filtran colección y workspace. Los documentos OpenAI/Ollama se conservan, pero deben reindexarse explícitamente en Knowledge para recuperarlos con Gemini. Reindexación atómica: un fallo de cuota mantiene los vectores anteriores. Cambiar generación no requiere reindexar; cambiar embeddings sí. Si Google cambia pesos bajo el mismo nombre, incrementa `EMBEDDING_REVISION` y reindexa: no hay digest de pesos cloud consultable.

La política extractive_v2 bloquea la ausencia literal de facetas salariales y algunos patrones explícitos de injection. Sigue pendiente la suficiencia relacional: tener las palabras esperadas en un pasaje no demuestra que responda a la pregunta. Ver VALIDATION.md para la comparación con evaluadores simulados.

## Voz sin coste obligatorio

La tabla oficial publica opciones de voz gratuitas sujetas a cuota, incluidas transcripción y modelos Live; también publica Flash Preview TTS, pero su retirada está anunciada para noviembre de 2026. No añadimos una dependencia de ese modelo próximo a retirarse ni afirmamos haber probado voz cloud.

Se conservan Faster-Whisper/Piper y OpenAI TTS opcionales. No se instaló ni descargó ningún modelo local. Con la configuración predeterminada de voz existente, el micrófono/TTS requieren esos modelos locales y, si faltan, muestran un error sin bloquear chat. **La demo cloud de texto/RAG funciona sin voz; la voz cloud no está integrada en esta entrega.** No se llama a OpenAI TTS salvo selección explícita de `TTS_PROVIDER=openai` con clave.

[Preparación local opcional](LOCAL_AI.md). No habilites voz si el objetivo actual es probar solo cloud sin modelos locales.
