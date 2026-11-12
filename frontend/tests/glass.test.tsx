import React from "react";
import { fireEvent, render, screen } from "@testing-library/react";
import { expect, test, vi } from "vitest";
import { Copilot } from "../src/components/copilot";
import { RobotMark } from "../src/components/brand/robot-mark";

const account = {
  email: "me@example.com",
  workspace_id: "w",
  workspaces: [{ id: "w", name: "Team" }],
};

function mount() {
  vi.spyOn(globalThis, "fetch").mockImplementation(async (input) =>
    String(input) === "/api/conversations"
      ? Response.json([{ id: "c1", title: "Consulta guardada" }])
      : Response.json([]),
  );
  return render(<Copilot account={account} onSignOut={async () => {}} onWorkspace={async () => {}} />);
}

test("the rail names every section and marks only the active one", async () => {
  mount();
  const nav = screen.getByRole("navigation", { name: "Secciones" });
  for (const name of ["Copilot", "Knowledge", "Workspace", "Aprobaciones", "Actividad", "Configuración"])
    expect(screen.getByRole("button", { name })).toBeInTheDocument();
  expect(nav.querySelectorAll('[aria-current="page"]')).toHaveLength(1);
  expect(screen.getByRole("button", { name: "Copilot" })).toHaveAttribute("aria-current", "page");
  fireEvent.click(screen.getByRole("button", { name: "Knowledge" }));
  expect(screen.getByRole("button", { name: "Knowledge" })).toHaveAttribute("aria-current", "page");
  expect(screen.getByRole("button", { name: "Copilot" })).not.toHaveAttribute("aria-current");
});

test("the panel opens on purpose, shows the history and closes with Escape", async () => {
  mount();
  const toggle = screen.getByRole("button", { name: "Mostrar nombres e historial" });
  const panel = document.getElementById("workspace-panel")!;
  // Closed: hidden from assistive technology and not focusable.
  expect(panel).toHaveAttribute("aria-hidden", "true");
  expect(screen.queryByRole("button", { name: "Consulta guardada" })).not.toBeInTheDocument();
  toggle.focus();
  fireEvent.click(toggle);
  expect(panel).toHaveAttribute("aria-hidden", "false");
  expect(toggle).toHaveAttribute("aria-expanded", "true");
  expect(await screen.findByRole("button", { name: "Consulta guardada" })).toBeInTheDocument();
  expect(document.activeElement).toHaveClass("panelClose");
  fireEvent.keyDown(document, { key: "Escape" });
  expect(panel).toHaveAttribute("aria-hidden", "true");
  expect(document.activeElement).toBe(toggle);
});

test("the empty conversation offers suggestions that only fill the composer", async () => {
  const fetch = vi.spyOn(globalThis, "fetch").mockImplementation(async () => Response.json([]));
  render(<Copilot account={account} onSignOut={async () => {}} onWorkspace={async () => {}} />);
  const calls = fetch.mock.calls.length;
  fireEvent.click(screen.getByRole("button", { name: /Lista los tickets del workspace/ }));
  expect(screen.getByLabelText("Mensaje al copiloto")).toHaveValue("Lista los tickets del workspace");
  // Nothing is sent until the person presses send.
  expect(fetch.mock.calls.length).toBe(calls);
});

test("the robot is decorative unless it is given a name", () => {
  const { container, rerender } = render(<RobotMark />);
  expect(container.querySelector("svg")).toHaveAttribute("aria-hidden", "true");
  rerender(<RobotMark title="MAZMI" />);
  expect(screen.getByRole("img", { name: "MAZMI" })).toBeInTheDocument();
});

test("the interface is dark unless another theme was chosen", async () => {
  const { applyTheme } = await import("../src/hooks/use-theme");
  window.localStorage.removeItem("mazmi-theme");
  applyTheme();
  expect(document.documentElement).toHaveAttribute("data-theme", "dark");
  window.localStorage.setItem("mazmi-theme", "system");
  applyTheme();
  expect(document.documentElement).not.toHaveAttribute("data-theme");
  window.localStorage.removeItem("mazmi-theme");
});
