/** Client-side downloads: CSV text, PNG bytes, and one uncompressed zip of both. */

export type CsvCell = string | number | null | undefined;

const CRC_TABLE = (() => {
  const table = new Uint32Array(256);
  for (let n = 0; n < 256; n++) {
    let c = n;
    for (let k = 0; k < 8; k++) c = (c & 1) ? (0xedb88320 ^ (c >>> 1)) : (c >>> 1);
    table[n] = c >>> 0;
  }
  return table;
})();

function crc32(data: Uint8Array): number {
  let c = 0xffffffff;
  for (let i = 0; i < data.length; i++) c = CRC_TABLE[(c ^ data[i]) & 0xff] ^ (c >>> 8);
  return (c ^ 0xffffffff) >>> 0;
}

function csvCell(value: CsvCell): string {
  if (value == null) return "";
  const text = String(value);
  return /[",\r\n]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text;
}

/** UTF-8 CSV with a byte-order mark so Excel keeps Chinese headers. */
export function toCsv(rows: CsvCell[][]): string {
  return `\uFEFF${rows.map((row) => row.map(csvCell).join(",")).join("\r\n")}\r\n`;
}

export function textBytes(text: string): Uint8Array {
  return new TextEncoder().encode(text);
}

export function dataUrlToBytes(dataUrl: string): Uint8Array {
  const bin = atob(dataUrl.slice(dataUrl.indexOf(",") + 1));
  const out = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) out[i] = bin.charCodeAt(i);
  return out;
}

export function fileStem(name: string): string {
  const cleaned = name.replace(/[\\/:*?"<>|\u0000-\u001f]+/g, " ").replace(/\s+/g, " ").trim();
  return (cleaned || "chart").slice(0, 80);
}

type ZipFile = { path: string; bytes: Uint8Array };

/** A zip of stored (uncompressed) files. PNG is already compressed; the text files are small. */
export function zipStore(files: ZipFile[]): Uint8Array {
  const encoded = files.map((file) => ({
    name: new TextEncoder().encode(file.path),
    bytes: file.bytes,
    crc: crc32(file.bytes),
  }));
  const localSize = encoded.reduce((n, file) => n + 30 + file.name.length + file.bytes.length, 0);
  const centralSize = encoded.reduce((n, file) => n + 46 + file.name.length, 0);
  const out = new Uint8Array(localSize + centralSize + 22);
  const view = new DataView(out.buffer);
  const offsets: number[] = [];
  let o = 0;
  for (const file of encoded) {
    offsets.push(o);
    view.setUint32(o, 0x04034b50, true); o += 4;
    view.setUint16(o, 20, true); o += 2;
    view.setUint16(o, 0x0800, true); o += 2;
    view.setUint16(o, 0, true); o += 2;
    view.setUint16(o, 0, true); o += 2;
    view.setUint16(o, 0, true); o += 2;
    view.setUint32(o, file.crc, true); o += 4;
    view.setUint32(o, file.bytes.length, true); o += 4;
    view.setUint32(o, file.bytes.length, true); o += 4;
    view.setUint16(o, file.name.length, true); o += 2;
    view.setUint16(o, 0, true); o += 2;
    out.set(file.name, o); o += file.name.length;
    out.set(file.bytes, o); o += file.bytes.length;
  }
  const centralStart = o;
  encoded.forEach((file, index) => {
    view.setUint32(o, 0x02014b50, true); o += 4;
    view.setUint16(o, 20, true); o += 2;
    view.setUint16(o, 20, true); o += 2;
    view.setUint16(o, 0x0800, true); o += 2;
    view.setUint16(o, 0, true); o += 2;
    view.setUint16(o, 0, true); o += 2;
    view.setUint16(o, 0, true); o += 2;
    view.setUint32(o, file.crc, true); o += 4;
    view.setUint32(o, file.bytes.length, true); o += 4;
    view.setUint32(o, file.bytes.length, true); o += 4;
    view.setUint16(o, file.name.length, true); o += 2;
    view.setUint16(o, 0, true); o += 2;
    view.setUint16(o, 0, true); o += 2;
    view.setUint16(o, 0, true); o += 2;
    view.setUint16(o, 0, true); o += 2;
    view.setUint32(o, 0, true); o += 4;
    view.setUint32(o, offsets[index], true); o += 4;
    out.set(file.name, o); o += file.name.length;
  });
  const centralBytes = o - centralStart;
  view.setUint32(o, 0x06054b50, true); o += 4;
  view.setUint16(o, 0, true); o += 2;
  view.setUint16(o, 0, true); o += 2;
  view.setUint16(o, encoded.length, true); o += 2;
  view.setUint16(o, encoded.length, true); o += 2;
  view.setUint32(o, centralBytes, true); o += 4;
  view.setUint32(o, centralStart, true); o += 4;
  view.setUint16(o, 0, true);
  return out;
}

export function downloadBytes(filename: string, bytes: Uint8Array, mime: string) {
  const blob = new Blob([bytes.slice()], { type: mime });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1500);
}

export function downloadDataUrl(filename: string, dataUrl: string) {
  const link = document.createElement("a");
  link.href = dataUrl;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
}

type ChartSlot = { name: string; png: () => string | null };
const slots: ChartSlot[] = [];

export function registerChart(slot: ChartSlot): () => void {
  slots.push(slot);
  return () => {
    const index = slots.indexOf(slot);
    if (index >= 0) slots.splice(index, 1);
  };
}

export function chartCount(): number {
  return slots.length;
}

/** PNG of every chart currently on the page, in the order they were drawn. */
export function captureChartPngs(): { name: string; bytes: Uint8Array }[] {
  const seen = new Map<string, number>();
  const out: { name: string; bytes: Uint8Array }[] = [];
  for (const slot of slots) {
    let url: string | null = null;
    try {
      url = slot.png();
    } catch {
      url = null;
    }
    if (!url) continue;
    let stem = fileStem(slot.name);
    const count = (seen.get(stem) ?? 0) + 1;
    seen.set(stem, count);
    if (count > 1) stem = `${stem} ${count}`;
    out.push({ name: `${stem}.png`, bytes: dataUrlToBytes(url) });
  }
  return out;
}
