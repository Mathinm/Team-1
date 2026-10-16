// Export a report (as returned by GET /api/reports/{type}) to CSV or PDF.
// Done in the browser so the backend only has to return JSON.

import { toCsv, downloadText } from "./csv.js";

const ISO_DATETIME = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}/;

/** Display value for one cell: readable dates, numbers kept as numbers. */
export function formatCell(value) {
  if (value === null || value === undefined || value === "") return "-";
  if (typeof value === "string" && ISO_DATETIME.test(value)) {
    return new Date(value).toLocaleString("en-IN", {
      day: "2-digit", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit",
    });
  }
  return String(value);
}

export function reportFileName(report, ext) {
  return `pms-${report.type}-${report.from}_to_${report.to}.${ext}`;
}

export function reportToCsv(report) {
  const rows = report.rows.map((r) =>
    Object.fromEntries(report.columns.map((c) => [c.key, formatCell(r[c.key])])),
  );
  return toCsv(report.columns, rows);
}

export function exportReportCsv(report) {
  downloadText(reportFileName(report, "csv"), reportToCsv(report));
}

export async function exportReportPdf(report, storeName = "Perishables Management System") {
  // Loaded only when someone exports, to keep the main bundle small.
  const [{ jsPDF }, { default: autoTable }] = await Promise.all([
    import("jspdf"),
    import("jspdf-autotable"),
  ]);
  const doc = new jsPDF({ orientation: report.columns.length > 6 ? "landscape" : "portrait" });
  doc.setFontSize(15);
  doc.text(report.title, 14, 16);
  doc.setFontSize(9);
  doc.setTextColor(90);
  doc.text(`${storeName}  |  ${report.from} to ${report.to}  |  generated ${new Date().toLocaleString("en-IN")}`, 14, 22);
  let y = 26;
  for (const s of report.summary ?? []) {
    doc.text(`${s.label}: ${s.value}`, 14, (y += 5));
  }
  autoTable(doc, {
    startY: y + 4,
    head: [report.columns.map((c) => c.label)],
    body: report.rows.map((r) => report.columns.map((c) => formatCell(r[c.key]))),
    styles: { fontSize: 8, cellPadding: 1.8 },
    headStyles: { fillColor: [31, 111, 80] },
    columnStyles: Object.fromEntries(
      report.columns.map((c, i) => [i, c.numeric ? { halign: "right" } : {}]),
    ),
  });
  doc.save(reportFileName(report, "pdf"));
}
