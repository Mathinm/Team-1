// Minimal CSV helpers (no quoted newlines needed for our files).

function splitLine(line) {
  const out = [];
  let cur = "";
  let quoted = false;
  for (let i = 0; i < line.length; i++) {
    const ch = line[i];
    if (quoted) {
      if (ch === '"' && line[i + 1] === '"') {
        cur += '"';
        i++;
      } else if (ch === '"') {
        quoted = false;
      } else {
        cur += ch;
      }
    } else if (ch === '"') {
      quoted = true;
    } else if (ch === ",") {
      out.push(cur);
      cur = "";
    } else {
      cur += ch;
    }
  }
  out.push(cur);
  return out.map((s) => s.trim());
}

/**
 * Parse CSV text with a header row.
 * Returns [{line, values: {header: value}}]; `line` is the 1-based file line.
 */
export function parseCsv(text) {
  const lines = text.replace(/\r\n?/g, "\n").split("\n");
  const headerIdx = lines.findIndex((l) => l.trim() !== "");
  if (headerIdx === -1) return { headers: [], rows: [] };
  const headers = splitLine(lines[headerIdx]).map((h) => h.toLowerCase());
  const rows = [];
  for (let i = headerIdx + 1; i < lines.length; i++) {
    if (lines[i].trim() === "") continue;
    const cells = splitLine(lines[i]);
    const values = {};
    headers.forEach((h, j) => {
      values[h] = cells[j] ?? "";
    });
    rows.push({ line: i + 1, values });
  }
  return { headers, rows };
}

function escapeCell(v) {
  const s = v === null || v === undefined ? "" : String(v);
  return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
}

/** columns: [{key, label}] */
export function toCsv(columns, rows) {
  const head = columns.map((c) => escapeCell(c.label)).join(",");
  const body = rows.map((r) => columns.map((c) => escapeCell(r[c.key])).join(","));
  return [head, ...body].join("\n") + "\n";
}

export function downloadText(filename, text, type = "text/csv") {
  downloadBlob(filename, new Blob([text], { type }));
}

export function downloadBlob(filename, blob) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
