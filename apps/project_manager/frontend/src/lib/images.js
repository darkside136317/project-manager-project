// Photos from the field: read when and where a photo was taken (EXIF), then shrink it before it is queued, so a
// 6 MB camera picture travels as a few hundred KB over a weak site connection. Shrinking drops the EXIF block, which
// is why it is read first.

const pad = (n) => String(n).padStart(2, "0");

/** "YYYY-MM-DD HH:MM:SS" of a local date (what the server stores for the moment a photo was taken). */
export function localStamp(date) {
  if (!(date instanceof Date) || Number.isNaN(date.getTime())) return null;
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}:${pad(date.getSeconds())}`;
}

const TYPE_SIZE = { 1: 1, 2: 1, 3: 2, 4: 4, 5: 8, 7: 1, 9: 4, 10: 8 };

/** The TIFF block of a JPEG's EXIF segment as { view, start, little } or null. */
function tiffOf(buffer) {
  const view = new DataView(buffer);
  if (view.byteLength < 4 || view.getUint16(0) !== 0xffd8) return null;
  let offset = 2;
  while (offset + 4 <= view.byteLength) {
    const marker = view.getUint16(offset);
    if ((marker & 0xff00) !== 0xff00) return null;
    const length = view.getUint16(offset + 2);
    if (marker === 0xffe1 && offset + 10 <= view.byteLength
        && view.getUint32(offset + 4) === 0x45786966 && view.getUint16(offset + 8) === 0) {  // "Exif\0\0"
      const start = offset + 10;
      if (start + 8 > view.byteLength) return null;
      const order = view.getUint16(start);
      if (order !== 0x4949 && order !== 0x4d4d) return null;
      return { view, start, little: order === 0x4949 };
    }
    if (marker === 0xffda || length < 2) return null;  // image data starts: no EXIF before it
    offset += 2 + length;
  }
  return null;
}

/** Entries of one IFD: { tag: { type, count, at } } where `at` is where the value sits. */
function readIfd(tiff, ifdOffset) {
  const { view, start, little } = tiff;
  const out = {};
  const base = start + ifdOffset;
  if (base + 2 > view.byteLength) return out;
  const count = view.getUint16(base, little);
  for (let i = 0; i < count; i += 1) {
    const entry = base + 2 + i * 12;
    if (entry + 12 > view.byteLength) break;
    const tag = view.getUint16(entry, little);
    const type = view.getUint16(entry + 2, little);
    const items = view.getUint32(entry + 4, little);
    const bytes = (TYPE_SIZE[type] || 1) * items;
    const at = bytes <= 4 ? entry + 8 : start + view.getUint32(entry + 8, little);
    if (at + bytes <= view.byteLength) out[tag] = { type, count: items, at };
  }
  return out;
}

function ascii(tiff, field) {
  if (!field || field.type !== 2) return "";
  let text = "";
  for (let i = 0; i < field.count; i += 1) {
    const code = tiff.view.getUint8(field.at + i);
    if (!code) break;
    text += String.fromCharCode(code);
  }
  return text;
}

function rationals(tiff, field) {
  if (!field || field.type !== 5) return [];
  const out = [];
  for (let i = 0; i < field.count; i += 1) {
    const top = tiff.view.getUint32(field.at + i * 8, tiff.little);
    const bottom = tiff.view.getUint32(field.at + i * 8 + 4, tiff.little);
    out.push(bottom ? top / bottom : 0);
  }
  return out;
}

function pointer(tiff, field) {
  if (!field || (field.type !== 4 && field.type !== 3)) return null;
  return field.type === 4 ? tiff.view.getUint32(field.at, tiff.little) : tiff.view.getUint16(field.at, tiff.little);
}

function degrees(parts, ref) {
  if (parts.length < 3) return null;
  const value = parts[0] + parts[1] / 60 + parts[2] / 3600;
  if (!value) return null;
  return Math.round((ref === "S" || ref === "W" ? -value : value) * 1e7) / 1e7;
}

/** { takenAt: "YYYY-MM-DD HH:MM:SS" | null, lat, lng } from a JPEG's first bytes (an ArrayBuffer). */
export function readExif(buffer) {
  const none = { takenAt: null, lat: null, lng: null };
  try {
    const tiff = tiffOf(buffer);
    if (!tiff) return none;
    const first = tiff.view.getUint32(tiff.start + 4, tiff.little);
    const root = readIfd(tiff, first);
    const out = { ...none };
    const exifAt = pointer(tiff, root[0x8769]);
    if (exifAt !== null) {
      const exif = readIfd(tiff, exifAt);
      const raw = ascii(tiff, exif[0x9003]) || ascii(tiff, exif[0x9004]);
      const match = /^(\d{4}):(\d{2}):(\d{2}) (\d{2}):(\d{2}):(\d{2})/.exec(raw);
      if (match && match[1] !== "0000") out.takenAt = `${match[1]}-${match[2]}-${match[3]} ${match[4]}:${match[5]}:${match[6]}`;
    }
    const gpsAt = pointer(tiff, root[0x8825]);
    if (gpsAt !== null) {
      const gps = readIfd(tiff, gpsAt);
      out.lat = degrees(rationals(tiff, gps[2]), ascii(tiff, gps[1]));
      out.lng = degrees(rationals(tiff, gps[4]), ascii(tiff, gps[3]));
      if (out.lat === null || out.lng === null) out.lat = out.lng = null;
    }
    return out;
  } catch {
    return none;
  }
}

/** When and where a picked photo was taken: EXIF first, else the file's own date. */
export async function describePhoto(file) {
  let found = { takenAt: null, lat: null, lng: null };
  if (/jpe?g$/i.test(file.type || file.name || "")) {
    try {
      found = readExif(await file.slice(0, 256 * 1024).arrayBuffer());
    } catch {
      // unreadable: keep the defaults
    }
  }
  if (!found.takenAt && file.lastModified) found.takenAt = localStamp(new Date(file.lastModified));
  return found;
}

/** Width and height that fit within `maxSide`, never larger than the original. */
export function fitWithin(width, height, maxSide = 1600) {
  const scale = Math.min(1, maxSide / Math.max(width, height || 1));
  return { width: Math.max(1, Math.round(width * scale)), height: Math.max(1, Math.round(height * scale)) };
}

/** A JPEG of at most `maxSide` pixels (a small JPEG is kept as it is). */
export async function shrink(file, { maxSide = 1600, quality = 0.82 } = {}) {
  if (typeof createImageBitmap !== "function") return file;
  let bitmap;
  try {
    bitmap = await createImageBitmap(file, { imageOrientation: "from-image" });
  } catch {
    return file;  // a format the browser cannot draw: the server decides
  }
  const size = fitWithin(bitmap.width, bitmap.height, maxSide);
  if (size.width === bitmap.width && file.type === "image/jpeg" && file.size < 1_500_000) {
    bitmap.close?.();
    return file;
  }
  let blob;
  if (typeof OffscreenCanvas !== "undefined") {
    const canvas = new OffscreenCanvas(size.width, size.height);
    canvas.getContext("2d").drawImage(bitmap, 0, 0, size.width, size.height);
    blob = await canvas.convertToBlob({ type: "image/jpeg", quality });
  } else {
    const canvas = document.createElement("canvas");
    canvas.width = size.width;
    canvas.height = size.height;
    canvas.getContext("2d").drawImage(bitmap, 0, 0, size.width, size.height);
    blob = await new Promise((resolve) => canvas.toBlob(resolve, "image/jpeg", quality));
  }
  bitmap.close?.();
  return blob || file;
}

/** The phone's position, when the user asked for it (null when refused or too slow). */
export function currentPosition(timeout = 6000) {
  if (typeof navigator === "undefined" || !navigator.geolocation) return Promise.resolve(null);
  return new Promise((resolve) => {
    navigator.geolocation.getCurrentPosition(
      (position) => resolve({ lat: Math.round(position.coords.latitude * 1e7) / 1e7, lng: Math.round(position.coords.longitude * 1e7) / 1e7 }),
      () => resolve(null),
      { enableHighAccuracy: true, timeout, maximumAge: 60000 },
    );
  });
}
