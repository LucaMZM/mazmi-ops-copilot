// Serve the existing standalone build with its static assets, without next start.
import { access, cp } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import { join } from "node:path";
import { spawn } from "node:child_process";
const root = fileURLToPath(new URL("../", import.meta.url));
const standalone = join(root, ".next", "standalone");
try {
  await access(join(standalone, "server.js"));
  await cp(join(root, ".next", "static"), join(standalone, ".next", "static"), {
    recursive: true,
  });
  try {
    await access(join(root, "public"));
    await cp(join(root, "public"), join(standalone, "public"), {
      recursive: true,
    });
  } catch (error) {
    if (error.code !== "ENOENT") throw error;
  }
} catch {
  console.error(
    "No hay un build standalone completo. Ejecuta npm run build primero.",
  );
  process.exit(1);
}
const child = spawn(process.execPath, [join(standalone, "server.js")], {
  cwd: root,
  stdio: "inherit",
  env: { ...process.env, HOSTNAME: process.env.MAZMI_HOSTNAME ?? "127.0.0.1" },
});
for (const signal of ["SIGINT", "SIGTERM"])
  process.on(signal, () => child.kill(signal));
child.on("error", () => {
  console.error("No se pudo iniciar el servidor standalone.");
  process.exit(1);
});
child.on("exit", (code) => process.exit(code ?? 0));
