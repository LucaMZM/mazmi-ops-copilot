# Demo de desarrollo sin API key

La demo utiliza el mismo FastAPI, PostgreSQL/pgvector, sesiones, aislamiento, búsqueda híbrida, rutas de documentos y confirmaciones que la aplicación normal. Solo sustituye los proveedores por fixtures deterministas. No es una simulación de la calidad de Gemini.

## Preparación

Necesitas PostgreSQL con pgvector y las dependencias existentes de Python/Node. No requiere Docker, Ollama ni modelos locales. Usa una base **nueva y dedicada** con nombre terminado en `_demo` (por ejemplo `mazmi_product_demo`). No apuntes a una base empresarial ni a la base de tests.

En `.env` local de la raíz, configura tu conexión PostgreSQL y estos valores:

```dotenv
APP_ENV=development
DEMO_MODE=true
# DATABASE_URL debe apuntar a tu base dedicada, por ejemplo mazmi_product_demo.
GEMINI_API_KEY=
OPENAI_API_KEY=
```

Desde `backend`, con el virtualenv activado:

```bash
python -m app.demo
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

El primer comando migra únicamente la base demo vacía y carga datos ficticios: dos workspaces, cinco documentos estructurados (manual del empleado, gastos, seguridad, inventario y teletrabajo), un documento fallido, consultas con cita, multi-documento y abstención, y una propuesta pendiente. Si encuentra usuarios, documentos o tickets previos, se detiene **antes de migrar** y conserva los datos. No se debe repetir el seed para reiniciar datos; continúa con el servidor sobre la base ya preparada.

Desde `frontend`, usando sus dependencias instaladas:

```bash
npm run dev
# También puedes probar el build:
# npm run build
# npm start
```

Abre http://127.0.0.1:3000. Cuenta ficticia: **demo@mazmi.local**. El seed genera una contraseña aleatoria y la muestra una sola vez en tu terminal local. Guárdala en privado; no la copies a Git, capturas ni logs compartidos. No hay contraseña universal publicada. Elige `MAZMI · Operaciones` para ver el corpus; Laboratorio está vacío y permite comprobar separación de datos.

## Recorrido de presentación (unos 5 minutos)

La demo usa un evaluador determinista por palabras clave (vacaciones, inventario, acceso, gastos, teletrabajo, contraseñas). Todo lo demás es real: sesiones, PostgreSQL/pgvector, chunking estructurado, búsqueda híbrida, guardas de evidencia, propuestas, aprobación y auditoría. La cinta superior lo indica en todo momento.

1. **Acceso y workspace (30 s).** Inicia sesión con `demo@mazmi.local` y la contraseña que imprimió el seed. El Workspace muestra cifras reales: 5 documentos listos, propuestas por decidir y conversaciones. Señala el documento fallido (aviso de revisión) y cambia a «MAZMI · Laboratorio» para enseñar que está vacío: los datos no cruzan workspaces.
2. **Biblioteca (45 s).** En Knowledge abre «Fragmentos» de `manual-del-empleado.md`: cada fragmento conserva su sección («2. Vacaciones y permisos › 2.2 Solicitud de vacaciones»). Filtra «Fallidos» para ver un error explicado. Opcional: sube un TXT corto.
3. **Respuesta con evidencia (45 s).** En Copilot (ASK) pregunta «¿Cuántos días de vacaciones hay?». La respuesta cita frases literales con documento y sección; pulsa la cita para abrir el pasaje almacenado completo.
4. **Pregunta multi-documento (45 s).** «¿Qué restricciones hay durante la campaña de inventario de diciembre?» combina `inventario-almacenes.md` y `manual-del-empleado.md`, con dos citas verificables.
5. **Abstención (30 s).** «¿Cuál es el salario durante las vacaciones?»: el sistema se abstiene porque ningún pasaje relaciona salario y vacaciones, aunque recupera fragmentos del tema.
6. **Acción operativa (45 s).** Cambia el conmutador a DO (el composer pasa a ámbar) y escribe «Crea un ticket para revisar el acceso de una nueva incorporación». Se crea una **propuesta**, no un ticket, con sus consecuencias visibles.
7. **Aprobación humana (30 s).** Confirma desde el chat o desde Aprobaciones. Aparece «Ticket #N» y el contador baja. Repetir la decisión devuelve el estado real (ya resuelta), nunca una segunda ejecución.
8. **Auditoría (20 s).** En Actividad: aprobación solicitada, acción ejecutada con «Confirmación humana verificada», consultas y documentos.
9. **Configuración (20 s).** Proveedores en modo demo («Probado con fixtures; sin conexión real»), colección y dimensiones de embeddings, y tema claro/oscuro.

Para enseñar ingeniería: [VALIDATION.md](VALIDATION.md) recoge los defectos reproducidos, las mediciones reales (incluidos los fallos del modelo local) y qué no está verificado.

## Volver a Gemini

Detén el backend y configura `DEMO_MODE=false`, `APP_ENV=production`, los proveedores Gemini y la `GEMINI_API_KEY` exclusivamente local según [GEMINI.md](GEMINI.md). Usa tu base normal migrada, o reindexa explícitamente los documentos que decidas conservar: los vectores demo son incompatibles con embeddings reales. Reinicia backend. Configurado no equivale a verificado: ejecuta `python -m app.check_gemini` cuando dispongas de clave y cuota.

La voz no se simula como disponible. Requiere la configuración opcional documentada en [LOCAL_AI.md](LOCAL_AI.md); su ausencia no bloquea el texto.

## Arranque de producción del frontend

`npm start` sirve la salida standalone, copia sus recursos estáticos y escucha en 127.0.0.1 por defecto. `PORT` permite cambiar puerto; `MAZMI_HOSTNAME` permite elegir host deliberadamente. Cambiar `BACKEND_URL` requiere reconstruir el frontend. No expongas la demo a Internet.
