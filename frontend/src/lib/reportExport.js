// Export a report (as returned by GET /api/reports/{type}) to CSV or PDF.
// Done in the browser so the backend only has to return JSON.

import { toCsv, downloadText } from "./csv.js";

const ISO_DATETIME = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}/;

/** Display value for one cell: readable dates, numbers kept as numbers. */
export function formatCell(value, column) {
  if (value === null || value === undefined || value === "") return "-";
  // N20: money columns always show rupees with two decimals.
  if (column?.money && typeof value === "number") {
    return `₹${value.toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
  }
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
    Object.fromEntries(report.columns.map((c) => [c.key, formatCell(r[c.key], c)])),
  );
  return toCsv(report.columns, rows);
}

/** "1 Nov 2026 to 7 Nov 2026", or "As of 13 Nov 2026, 10:30 am" for a snapshot report (N15). */
export function reportPeriod(report) {
  if (report.asOf) return `As of ${formatCell(report.asOf)}`;
  return `${report.from} to ${report.to}`;
}

// jsPDF's built-in fonts have no ₹ glyph, so the PDF spells it "Rs.".
const pdfText = (s) => String(s).replace(/₹(?=[\d-])/g, "Rs. ").replaceAll("₹", "Rs.");

export function exportReportCsv(report) {
  // The byte-order mark makes Excel read the file as UTF-8, so ₹ shows correctly.
  downloadText(reportFileName(report, "csv"), "\ufeff" + reportToCsv(report), "text/csv;charset=utf-8");
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
  doc.text(`${storeName}  |  ${reportPeriod(report)}  |  generated ${new Date().toLocaleString("en-IN")}`, 14, 22);
  let y = 26;
  for (const s of report.summary ?? []) {
    doc.text(pdfText(`${s.label}: ${s.value}`), 14, (y += 5));
  }
  autoTable(doc, {
    startY: y + 4,
    head: [report.columns.map((c) => pdfText(c.label))],
    body: report.rows.map((r) => report.columns.map((c) => pdfText(formatCell(r[c.key], c)))),
    styles: { fontSize: 8, cellPadding: 1.8 },
    headStyles: { fillColor: [31, 111, 80] },
    columnStyles: Object.fromEntries(
      report.columns.map((c, i) => [i, c.numeric ? { halign: "right" } : {}]),
    ),
  });
  doc.save(reportFileName(report, "pdf"));
}
