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

El primer comando migra únicamente la base demo vacía y carga datos ficticios: dos workspaces, tres documentos indexados, un documento fallido, consultas con cita/abstención y una propuesta pendiente. Si encuentra usuarios, documentos o tickets previos, se detiene **antes de migrar** y conserva los datos. No se debe repetir el seed para reiniciar datos; continúa con el servidor sobre la base ya preparada.

Desde `frontend`, usando sus dependencias instaladas:

```bash
npm run dev
# También puedes probar el build:
# npm run build
# npm start
```

Abre http://127.0.0.1:3000. Cuenta ficticia: **demo@mazmi.local**. El seed genera una contraseña aleatoria y la muestra una sola vez en tu terminal local. Guárdala en privado; no la copies a Git, capturas ni logs compartidos. No hay contraseña universal publicada. Elige `MAZMI · Operaciones` para ver el corpus; Laboratorio está vacío y permite comprobar separación de datos.

## Recorrido de presentación

1. Workspace: revisa documentos y la propuesta pendiente.
2. Knowledge: busca un documento, filtra fallidos y abre sus fragmentos. Sube un TXT pequeño para probar el flujo completo; no hay porcentaje de progreso inventado.
3. Copilot: pregunta «¿Cuántos días de vacaciones hay?» y abre [1]. Pregunta por salario durante vacaciones para observar abstención. El proveedor demo solo entiende un conjunto pequeño de temas: vacaciones, acceso y gastos.
4. DO: «Crea un ticket para revisar acceso». La propuesta aún no crea un ticket. Confirma o rechaza y revisa Aprobaciones / Actividad. Los tickets creados son registros reales dentro de esta base demo aislada.
5. Configuración: identifica que se están usando fixtures, no una conexión Gemini real. Crea un workspace vacío si quieres comprobar la navegación entre espacios.

El banner y las respuestas identifican la demo. El servidor rechaza `DEMO_MODE=true` si `APP_ENV` no es development o si el nombre de la base no termina en `_demo`. No hay endpoint para saltarse login ni aprobación. Las colecciones tienen prefijo `demo:` y no se mezclan con Gemini/Ollama/OpenAI.

## Volver a Gemini

Detén el backend y configura `DEMO_MODE=false`, `APP_ENV=production`, los proveedores Gemini y la `GEMINI_API_KEY` exclusivamente local según [GEMINI.md](GEMINI.md). Usa tu base normal migrada, o reindexa explícitamente los documentos que decidas conservar: los vectores demo son incompatibles con embeddings reales. Reinicia backend. Configurado no equivale a verificado: ejecuta `python -m app.check_gemini` cuando dispongas de clave y cuota.

La voz no se simula como disponible. Requiere la configuración opcional documentada en [LOCAL_AI.md](LOCAL_AI.md); su ausencia no bloquea el texto.

## Arranque de producción del frontend

`npm start` sirve la salida standalone, copia sus recursos estáticos y escucha en 127.0.0.1 por defecto. `PORT` permite cambiar puerto; `MAZMI_HOSTNAME` permite elegir host deliberadamente. Cambiar `BACKEND_URL` requiere reconstruir el frontend. No expongas la demo a Internet.
