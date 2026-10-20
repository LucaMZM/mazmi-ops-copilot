import React from "react";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { expect, test, vi } from "vitest";
import { AccountGate } from "../src/components/account";

test("session check resolves to a useful sign in screen without a key", async () => {
  vi.spyOn(globalThis, "fetch").mockResolvedValue(
    Response.json({ detail: "Inicia sesión" }, { status: 401 }),
  );
  render(<AccountGate />);
  await screen.findByRole("button", { name: "Entrar" });
  expect(screen.getByLabelText("Email")).toBeInTheDocument();
  expect(screen.queryByLabelText(/API/)).not.toBeInTheDocument();
});
test("unavailable backend is visible on the account screen", async () => {
  vi.spyOn(globalThis, "fetch").mockResolvedValue(
    Response.json({ detail: "Database unavailable" }, { status: 503 }),
  );
  render(<AccountGate />);
  await waitFor(() =>
    expect(screen.getByRole("alert")).toHaveTextContent(
      "El servidor no está disponible",
    ),
  );
  expect(screen.getByRole("button", { name: "Entrar" })).toBeEnabled();
});
test("invalid sign in remains on the form and never opens workspace data", async () => {
  const fetcher = vi
    .spyOn(globalThis, "fetch")
    .mockImplementation(async (_url, init) =>
      Response.json(
        {
          detail:
            init?.method === "POST"
              ? "Credenciales incorrectas"
              : "Inicia sesión",
        },
        { status: 401 },
      ),
    );
  render(<AccountGate />);
  await screen.findByRole("button", { name: "Entrar" });
  fireEvent.change(screen.getByLabelText("Email"), {
    target: { value: "person@test.local" },
  });
  fireEvent.change(screen.getByLabelText("Contraseña"), {
    target: { value: "fictitious-password" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Entrar" }));
  await waitFor(() =>
    expect(screen.getByRole("alert")).toHaveTextContent(
      "Credenciales incorrectas",
    ),
  );
  expect(fetcher.mock.calls.some(([url]) => url === "/api/documents")).toBe(
    false,
  );
});
