/**
 * Locate, inside a stored passage, the literal quotes the answer shows for that source.
 *
 * The server writes every quote as «…» followed by its citation [n], and only after checking
 * that the text exists in passage n. Here we only find those same characters again to mark
 * them; nothing is inferred. A quote that cannot be found literally is simply not marked.
 */

export type Segment = { text: string; mark: boolean };

const QUOTE = /«([^»]+)»/g;
const CITATION = /\[(\d+)\]/g;
const MIN_FRAGMENT = 8;

/** Quotes shown in the answer for citation number `n` (1-based, as displayed). */
export function quotesFor(answer: string, n: number): string[] {
  const found: string[] = [];
  for (const line of answer.split("\n")) {
    const cited = Array.from(line.matchAll(CITATION), (m) => Number(m[1]));
    if (!cited.includes(n)) continue;
    for (const match of line.matchAll(QUOTE)) found.push(match[1]);
  }
  return found;
}

function escape(text: string) {
  return text.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

/** Ranges of `passage` that literally contain the quotes (whitespace-insensitive). */
export function quoteRanges(passage: string, quotes: string[]): [number, number][] {
  const ranges: [number, number][] = [];
  for (const quote of quotes) {
    // Focused quotes may join non-adjacent sentences with an ellipsis: find each part.
    for (const part of quote.split("…").map((p) => p.trim())) {
      if (part.length < MIN_FRAGMENT) continue;
      const pattern = new RegExp(part.split(/\s+/).map(escape).join("\\s+"), "g");
      for (const match of passage.matchAll(pattern)) {
        ranges.push([match.index, match.index + match[0].length]);
      }
    }
  }
  ranges.sort((a, b) => a[0] - b[0]);
  const merged: [number, number][] = [];
  for (const range of ranges) {
    const last = merged[merged.length - 1];
    if (last && range[0] <= last[1]) last[1] = Math.max(last[1], range[1]);
    else merged.push([...range]);
  }
  return merged;
}

export function segments(passage: string, ranges: [number, number][]): Segment[] {
  const out: Segment[] = [];
  let cursor = 0;
  for (const [start, end] of ranges) {
    if (start > cursor) out.push({ text: passage.slice(cursor, start), mark: false });
    out.push({ text: passage.slice(start, end), mark: true });
    cursor = end;
  }
  if (cursor < passage.length) out.push({ text: passage.slice(cursor), mark: false });
  return out;
}
