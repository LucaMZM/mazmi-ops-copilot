# Aplicación segura de la migración 003

003 añade `document_chunks.search_vector` como columna generada STORED y un índice GIN. PostgreSQL calcula el texto de búsqueda para las filas existentes; no se regeneran embeddings ni se modifican IDs, contenido o relaciones. Requiere PostgreSQL con las migraciones 001/002 y extensión pgvector ya disponibles.

Antes de aplicarla sobre una base existente:

1. Verificar espacio libre para la columna, índice, WAL y backup. La operación puede reescribir la tabla; no aplicarla con almacenamiento casi lleno.
2. Hacer un backup consistente fuera del repositorio y comprobar que puede restaurarse en una base aislada. Probar allí la migración con un volumen representativo.
3. Programar una ventana de mantenimiento y detener ingestiones/escrituras. `ALTER TABLE` y el índice no concurrente pueden bloquear lectores/escritores; no se promete una migración sin interrupción.
4. Desde `backend`, usar la `DATABASE_URL` local de la base elegida, sin publicarla ni imprimirla, y ejecutar `python -m app.migrate`.
5. El runner usa una transacción, advisory lock, `lock_timeout=5s` y `statement_timeout=120s` por sentencia. Si falla por bloqueo, disco o tiempo, se revierte la transacción; investigar antes de reintentar. Para tablas grandes hay que planificar tiempos fuera de la ventana por defecto, no quitar límites sin medir.
6. Verificar que `schema_migrations` contiene `003_hybrid_retrieval.sql`, que la columna es generada y que `chunks_search_gin` está presente/válido. Comparar conteo de chunks y comprobar una búsqueda FTS conocida antes de reabrir escrituras. El ledger permite repetir el runner sin reaplicar una migración completada; no marcarla manualmente como aplicada.

Validado en esta sesión sobre PostgreSQL temporal: filas previas a 003 se conservan con los mismos IDs, textos y embeddings; FTS encuentra un código existente; dos ejecuciones dejan una sola entrada en el ledger. No se ha aplicado a ninguna base empresarial existente ni medido duración/espacio con grandes volúmenes. No requiere Docker.


## Migración 004: colecciones de embeddings

Aplicar las mismas precauciones anteriores: espacio suficiente, backup restaurable, ensayo en copia y ventana de mantenimiento. No aplicarla ahora a una base existente con el disco casi lleno. El arranque del backend aplica migraciones pendientes automáticamente: prepara la base antes de reiniciarlo con esta versión.

004 conserva los vectores existentes de 1536 dimensiones y les asigna colección OpenAI/modelo/1536/legacy. Cambia la columna a `vector` sin dimensión fija, elimina el antiguo índice HNSW e incorpora metadata e índice de colección. Retrieval sigue usando distancia exacta sobre un CTE MATERIALIZED filtrado por colección/workspace; no se promete escalabilidad ANN. Triggers verifican dimensiones, colección y workspace, incluida consistencia al commit de una reindexación.

Después de `python -m app.migrate`, verificar entrada `004_embedding_collections.sql` en `schema_migrations`, conteos/IDs/textos/vectores conservados, metadata rellenada y ambos triggers presentes. Probar retrieval con la colección original antes de reabrir escrituras; al seleccionar Ollama, reindexar documentos explícitamente desde Knowledge. El modelo activo no recupera colecciones incompatibles, ni siquiera por FTS.

Prueba realizada: esquema temporal con estructura antigua, migración repetida dos veces, preservación de filas/vectores, coexistencia 1536/768 y reindexación 768→256; rollback por vector inválido y rechazo entre workspaces. No se migró una base empresarial real.

## Gemini (19 de octubre de 2026)

No requiere migración 005: 004 ya permite colecciones y dimensiones independientes. Gemini Embedding 2 usa 768 dimensiones por defecto y un prefijo de colección distinto de Ollama/OpenAI, incluso con dimensiones iguales. Conservar backup/espacio/ventana de mantenimiento para aplicar 004 a bases antiguas. No editar el ledger ni borrar vectores anteriores para activar Gemini: cambiar configuración y reindexar explícitamente cada documento; un 429 revierte la reindexación completa. La reindexación desde datos OpenAI se comprobó con PostgreSQL real y Gemini simulado.

## Renovación de producto y demo (20 de octubre de 2026)

No se añade migración 005 ni se modifican 003/004. Las vistas de configuración, aprobaciones e inspector utilizan tablas existentes. La demo exige una base dedicada terminada en `_demo` y rechaza poblarla si contiene usuarios/documentos/tickets, antes de ejecutar migraciones. Las pruebas de integración siguieron usando esquemas aislados en una base temporal. No se aplicaron migraciones a bases del usuario.
