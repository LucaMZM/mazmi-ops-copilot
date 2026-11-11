# Gemini, OpenAI y demo determinista: auditoría y recomendación

La PR #2 retiró tres capacidades que el encargo original pedía conservar. Este documento explica qué se perdió, qué cuesta recuperarlo y qué recomiendo. **No se ha restaurado nada**: es una decisión del propietario del proyecto.

## Qué se retiró (commit `9640acb`, merge `5a07059`)

| Capacidad | Código retirado | Dependencias retiradas | Verificada antes de retirarla |
|---|---|---|---|
| Gemini (generación y embeddings, 768 d) | `backend/app/gemini.py` (210 líneas), `check_gemini.py`, `tests/test_gemini.py`, `GEMINI.md` | `google-genai 2.31.0`, `google-auth`, `cryptography`, `pyasn1`… | Solo con dobles de prueba; nunca con una llamada real |
| OpenAI (generación, embeddings 1536 d y voz) | adaptador en `providers.py`, rama TTS en `speech.py` | `openai 3.33.0`, `jiter`, `httpx2`, `distro`… | Solo con dobles de prueba; nunca con una llamada real |
| Demo determinista (`DEMO_MODE`) | `backend/app/demo.py` (160 líneas), cinta y etiquetas de la interfaz, `DEMO.md` | — | Sí, en navegador; no usaba IA real |

En total, 18 paquetes menos en `requirements.lock`. Todo el código sigue en el historial de Git (`git show e657d4e:backend/app/gemini.py`).

## Compatibilidad con lo que hay hoy

- **Base de datos:** no hay que migrar nada. Las colecciones de embeddings ya distinguen proveedor, modelo, dimensiones y revisión. Un documento indexado con otro proveedor sigue guardado y simplemente no se recupera hasta reindexarlo.
- **Pipeline de evidencia:** no depende del proveedor. Citas literales verificadas, guardas, comprobación semántica y aprobaciones funcionan igual con cualquier adaptador que respete el contrato JSON.
- **Interfaz:** habría que volver a mostrar qué proveedor responde y avisar de que los documentos salen del equipo.

## Recomendación

1. **Demo determinista: no recuperarla como modo de producto.** Pediste que la app no pareciera un prototipo, y la demo era justo eso. Sí tiene un uso legítimo: un **proveedor falso solo para pruebas automáticas de extremo a extremo en CI**, donde no hay Ollama. Debería vivir en `tests/`, nunca activable desde `.env` ni visible en la interfaz.
2. **Gemini u OpenAI: recuperar uno solo, opcional y apagado por defecto, y solo si una empresa lo pide.** Argumentos a favor:
   - Un modelo mayor resolvería mejor los fallos semánticos que hoy limitan a Qwen3 4B (roles y conflictos parafraseados; ver `VALIDATION.md`).
   - El pipeline ya está preparado para ello.

   Argumentos en contra:
   - Los documentos saldrían del equipo, que es el principal argumento de venta actual.
   - Coste por uso y necesidad de una clave en el servidor.
   - 18 dependencias más.
   - Ninguno de los dos adaptadores se probó nunca con una llamada real.

   Condiciones si se recupera: `GENERATION_PROVIDER` explícito (Ollama sigue siendo el valor por defecto), sin cambio automático de proveedor, aviso visible de envío de datos en Configuración, y una validación real con los mismos conjuntos (reservados incluidos) antes de anunciarlo.
3. **Antes que la nube, probar un modelo local mayor.** Con tu autorización, Qwen3 8B (unos 5 GB) mantiene la promesa de «nada sale del equipo». En 8 GB de RAM va muy justo; en un equipo de 16 GB es la opción natural.

## Cómo se recuperaría (sin hacerlo)

```bash
git show e657d4e:backend/app/gemini.py > backend/app/gemini.py   # y su test
# Restaurar el Literal de GENERATION_PROVIDER/EMBEDDING_PROVIDER en config.py,
# la rama en providers.generation_client() y la dependencia en requirements.txt.
```

Estimación: medio día para un adaptador con pruebas de contrato, más la validación real (que requiere clave y genera coste).
