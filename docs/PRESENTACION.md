# Demostración de MAZMI en cinco minutos

Para enseñar MAZMI a una empresa tecnológica sin tener que explicar antes la arquitectura. Todo es reproducible con datos **ficticios**: los diez documentos de «Aurelia Logística», una empresa inventada (`backend/evals/realistic/corpus`). Las respuestas esperadas de abajo son las que se midieron con el modelo local real (ver [VALIDATION.md](../VALIDATION.md)).

## La idea en una frase

MAZMI responde preguntas sobre los documentos de un equipo **con frases literales que el servidor ha verificado**, prefiere decir «no lo sé» a inventar, y prepara acciones que **solo se ejecutan cuando una persona las aprueba**. Todo funciona en el portátil, con Ollama: ningún documento sale del equipo.

## Preparación (10 minutos, una vez)

1. Arranca PostgreSQL y Ollama, y lanza backend y frontend según el [README](../README.md). El backend carga los modelos al arrancar.
2. Abre http://127.0.0.1:3000 y crea tu cuenta.
3. Carga el corpus ficticio en un workspace propio, marcado como ficticio. No toca tus otros workspaces:

   ```bash
   cd backend
   python -m app.presentation_corpus --email tu@correo.example
   ```

4. En la aplicación, cambia al workspace «Aurelia Logística (ficticio)» y haz una pregunta de prueba.

Usa **«Nueva consulta»** entre temas distintos: el historial de una conversación forma parte de la búsqueda, y saltar de tema en la misma conversación puede provocar una abstención.

## Recorrido

| Min. | Qué haces | Qué debe pasar | Qué demuestra |
|---|---|---|---|
| 0:00 | *Conocimiento*: abre «Fragmentos» del manual (DOCX) | Cada fragmento conserva su sección; las tablas se conservan | Ingesta estructurada de PDF y DOCX |
| 0:40 | Pregunta: `cuantos dias libres me dan si me caso` | **Respuesta: 15 días naturales**, citado de la fila de la tabla | Lenguaje coloquial, sin tildes, dato en una tabla |
| 1:20 | Pulsa la cita | El inspector muestra el pasaje completo almacenado | Cada cita es verificable |
| 1:40 | `¿Quién tiene que aprobar un gasto de 800 euros?` | **Finanzas**, desde la tabla de tramos del PDF | Razonar sobre un tramo, no solo buscar palabras |
| 2:10 | `¿Cuántos días de teletrabajo puedo hacer?` | **2 días**; ignora la política de 2023, que está sustituida | Vigencia de documentos |
| 2:30 | `¿Cuántos días de teletrabajo permitía la política de 2023?` | **3 días**, marcado como «documento sustituido» | La versión antigua se usa solo si se pide |
| 2:50 | `¿Cuánto cuesta el envío estándar a un cliente?` | **Se abstiene.** El contrato fija lo que el transportista cobra a la empresa, no lo que paga un cliente | Una cita literal no basta: tiene que ser sobre quien se pregunta |
| 3:20 | `¿Cuánto cuesta el menú del comedor?` | **Se abstiene.** El comunicado contiene una instrucción dirigida al asistente | Los documentos son datos, nunca órdenes |
| 3:40 | Cambia a **DO**: `Crea un ticket para revisar el lector de códigos del muelle 3, es urgente` | Propuesta en unos 5 s, con prioridad «Urgente» y sin ejecutar | El modelo propone; no actúa |
| 4:10 | Pulsa **Confirmar** | Ticket creado; repetir la decisión no ejecuta otra vez | Aprobación humana, una sola vez |
| 4:30 | *Actividad* | Consulta, propuesta, decisión y ejecución registradas | Auditoría |
| 4:45 | Cambia a tu otro workspace | No hay documentos ni conversaciones de Aurelia | Aislamiento por workspace |

## Preguntas que suelen hacer, con respuestas honestas

- **¿Qué modelo usa?** Qwen3 4B para generar y EmbeddingGemma para buscar, ambos en Ollama, en local.
- **¿Cuánto tarda?** En un MacBook Air M2 de 8 GB, una respuesta documental tiene una mediana de 11 a 15 s, según el tamaño de los pasajes. Las abstenciones por reglas son casi instantáneas. Una propuesta de ticket tarda unos 5 s.
- **¿Se equivoca?** Sí, y está medido: en un conjunto realista reservado que nunca se había ejecutado acierta 15 de 15. En un conjunto semántico adversarial reservado da 2 respuestas sin soporte de 20, por contradicciones expresadas sin números (por ejemplo «permitido» frente a «prohibido»). Cuando duda, se abstiene.
- **¿Puede usar GPT o Gemini?** Hoy no. Se retiraron para que nada salga del equipo; la recomendación para recuperarlos está en [ALTERNATIVAS-PROVEEDORES.md](ALTERNATIVAS-PROVEEDORES.md).

## Qué está verificado y qué es experimental

| Verificado con pruebas reales | Experimental o sin verificar |
|---|---|
| Citas literales verificadas por el servidor, abstenciones y vigencia de documentos | Voz (dictado y lectura en voz alta) |
| ASK/DO, aprobación única por solicitante, auditoría, aislamiento por workspace | Rendimiento con miles de documentos o muchos usuarios a la vez |
| Ollama real, PostgreSQL real, navegador real (claro, oscuro, móvil) | Conflictos parafraseados sin números; preguntas que sugieren su propia respuesta |
| Docker Compose como despliegue opcional | Gemini u OpenAI (retirados) |
