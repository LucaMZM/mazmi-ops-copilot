import type { DocumentItem, SystemInfo } from "@/components/product-types";

export const eventNames: Record<string, string> = {
  "document.indexed": "Documento indexado",
  "document.reindexed": "Documento reindexado",
  "document.failed": "Indexación fallida",
  "document.deleted": "Documento eliminado",
  "chat.completed": "Consulta completada",
  "action.proposed": "Aprobación solicitada",
  "action.executed": "Acción ejecutada",
  "action.rejected": "Acción rechazada",
  "tool.completed": "Herramienta consultada",
  "conversation.updated": "Conversación actualizada",
};

const dateFormat = new Intl.DateTimeFormat("es-ES", {
  day: "2-digit",
  month: "short",
  hour: "2-digit",
  minute: "2-digit",
});

export const date = (value: string) => dateFormat.format(new Date(value));

/** Whether a document's vectors belong to the active collection (null: unknown). */
export function compatible(d: DocumentItem, system: SystemInfo | null): boolean | null {
  return system?.embeddings.collection
    ? d.embedding_collection === system.embeddings.collection
    : null;
}

export const plural = (n: number, one: string, many: string) => `${n} ${n === 1 ? one : many}`;

export const ABSTENTION_PREFIXES = [
  "No encuentro información suficiente",
  "Los documentos recuperados contienen información contradictoria",
  "No he podido completar la comprobación de la evidencia",
];

export const isAbstention = (text: string) =>
  ABSTENTION_PREFIXES.some((prefix) => text.startsWith(prefix));
