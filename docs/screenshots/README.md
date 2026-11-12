# Procedencia de las capturas

Capturas reales tomadas el 12 de noviembre de 2026 con Playwright (Chromium headless, instancia propia) sobre el build de producción de Next.js (127.0.0.1:3000), con FastAPI, PostgreSQL 17 con pgvector, y Qwen3 4B y EmbeddingGemma en Ollama local.

- **Cuenta:** de prueba local, creada con el endpoint de registro de la API (`/api/auth/register`).
- **Documentos:** los diez del corpus ficticio «Aurelia Logística», cargados en su propio workspace con `python -m app.presentation_corpus`.
- **Respuestas:** generadas en el momento por el modelo local.

Sin modo demo, sin claves y sin retoque ni composición: PNG escrito directamente por el navegador. Escritorio a 1440 × 900 en tema oscuro (el predeterminado) y una en claro, que se elige en Configuración; móvil a 390 × 844, sin desbordamiento horizontal medido.

Diseño «Project Glass» en escala de grises: barra lateral flotante con indicador de cristal, robot de MAZMI y conversación como pantalla inicial. Las capturas se tomaron con `prefers-reduced-motion: reduce` para que ninguna transición quede a medias.

Son pasos sucesivos de un mismo recorrido: el ticket del muelle 3 se confirmó antes de las capturas, y la propuesta de `approvals.png` (carretilla del muelle 2) se rechazó justo después de capturarla para no dejar nada pendiente. `panel.png` muestra el panel abierto sobre la vista Workspace.
