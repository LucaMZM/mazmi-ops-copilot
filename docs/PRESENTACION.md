# Guía de presentación (unos 8 minutos)

MAZMI funciona con **tus propios documentos y usuarios**: no hay datos precargados ni modo demo. Antes de enseñarlo, prepara una cuenta y 2-3 documentos reales (PDF, DOCX, TXT o MD) de la empresa o del equipo ante el que presentas.

## Preparación (una vez, 5 minutos)

1. Arranca PostgreSQL y Ollama, y lanza backend y frontend según el [README](../README.md).
2. Ejecuta `make check-local`: confirma que `qwen3:4b` y `embeddinggemma` están instalados y responden.
3. Abre http://127.0.0.1:3000, **crea tu cuenta** y tu workspace.
4. En *Configuración* pulsa **Verificar Ollama**. La primera vez puede tardar al cargar los modelos en memoria; verás el resultado real, no una etiqueta.
5. En *Conocimiento* sube los documentos y espera a que pasen a «Listo».

Haz una pregunta de calentamiento antes de la reunión: el primer turno carga el modelo en memoria y es el más lento.

## Recorrido

1. **Documentos (1 min).** En *Conocimiento* abre «Fragmentos» de un documento: cada fragmento conserva su sección. Explica que el texto original es lo que se cita.
2. **Respuesta con evidencia (2 min).** En *Copilot* (ASK) haz una pregunta cuya respuesta esté en un documento. La respuesta son frases literales con documento y sección; pulsa la cita para abrir el pasaje completo. Comenta que el servidor verificó que la cita existe en ese pasaje.
3. **Pregunta de varias partes (1 min).** Combina dos datos de uno o dos documentos en una sola pregunta.
4. **Abstención (1 min).** Pregunta algo relacionado pero que **no** esté escrito (un plazo, una marca, un importe que falte). El sistema se abstiene y lo dice; no inventa.
5. **Acción con confirmación (2 min).** Cambia a DO y escribe «Crea un ticket para …». Se crea una **propuesta**, no un ticket. Apruébala desde el chat o desde *Aprobaciones*; repetir la decisión no ejecuta dos veces.
6. **Auditoría (30 s).** En *Actividad* se ve cada consulta, propuesta y decisión.
7. **Aislamiento (30 s).** Crea un segundo workspace en *Configuración*: está vacío; los datos no cruzan.

## Qué decir con honestidad

- Todo se ejecuta en el equipo con Ollama (Qwen3 4B y EmbeddingGemma). No sale ningún documento a Internet.
- En un MacBook Air M2 de 8 GB una respuesta documental tarda unos segundos a decenas de segundos. Un modelo de 4B es conservador: prefiere abstenerse a inventar, y puede abstenerse con preguntas muy indirectas. Las cifras medidas están en [VALIDATION.md](../VALIDATION.md).
- Es un proyecto en evolución: sin RBAC, sin invitaciones por correo y con indexación síncrona. No es un despliegue de producción.
