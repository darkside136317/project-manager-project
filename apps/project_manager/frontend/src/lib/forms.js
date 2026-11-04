// Helpers of the form screens: states, what is still missing, pictures. No Vue, no network.

export const SUB = { DRAFT: "Nháp", SUBMITTED: "Đã nộp", APPROVED: "Đã duyệt", RETURNED: "Trả lại" };
export const TEMPLATE = { DRAFT: "Nháp", ACTIVE: "Đang dùng", RETIRED: "Ngừng dùng" };
export const F = {
  TEXT: "Văn bản", LONG: "Văn bản dài", NUMBER: "Số", DATE: "Ngày", SELECT: "Chọn", CHECK: "Hộp kiểm",
  TABLE: "Bảng", IMAGE: "Ảnh", SIGNATURE: "Chữ ký", SECTION: "Tiêu đề mục",
};

const STATE_TONES = { "Nháp": "muted", "Đã nộp": "warning", "Đã duyệt": "success", "Trả lại": "danger" };
const TEMPLATE_TONES = { "Nháp": "warning", "Đang dùng": "success", "Ngừng dùng": "muted" };

export const formStateBadge = (state) => `badge badge-${STATE_TONES[state] || "muted"}`;
export const templateStateBadge = (state) => `badge badge-${TEMPLATE_TONES[state] || "muted"}`;

const empty = (value) => value === undefined || value === null || value === "" || (Array.isArray(value) && !value.length);

function rowIsFilled(field, row) {
  const columns = field.preset_rows?.length ? field.columns.slice(1) : field.columns;
  return columns.some((column) => !empty(row?.[column.key]));
}

/** The rows a table shows: a checklist's fixed rows (first column from the template), or what was typed so far. */
export function tableRows(field, value) {
  const rows = Array.isArray(value) ? value : [];
  if (!field.preset_rows?.length) return rows;
  return field.preset_rows.map((label, index) => ({ ...(rows[index] || {}), [field.columns[0].key]: label }));
}

/** Fieldnames of required answers still missing (the server checks again when submitting). */
export function missingFields(spec, data) {
  const missing = [];
  for (const field of spec?.fields || []) {
    if (!field.reqd || field.fieldtype === F.SECTION) continue;
    const value = data?.[field.fieldname];
    let absent;
    if (field.fieldtype === F.TABLE) {
      const rows = tableRows(field, value);
      absent = field.preset_rows?.length ? rows.some((row) => !rowIsFilled(field, row)) : !rows.some((row) => rowIsFilled(field, row));
    } else if (field.fieldtype === F.CHECK) {
      absent = !value;
    } else {
      absent = empty(value);
    }
    if (absent) missing.push(field.fieldname);
  }
  return missing;
}

export function blobToBase64(blob) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result).split(",", 2)[1] || "");
    reader.onerror = () => reject(new Error("Không đọc được tệp"));
    reader.readAsDataURL(blob);
  });
}

/** The size a picture is reduced to so that its longer side is at most `limit`. */
export function fitSize(width, height, limit = 1600) {
  const scale = Math.min(1, limit / Math.max(width, height));
  return { width: Math.round(width * scale), height: Math.round(height * scale) };
}

/** A photo from a phone, reduced to a sensible size (JPEG) before it is sent. */
export async function compressImage(file, limit = 1600, quality = 0.82) {
  let bitmap;
  try {
    bitmap = await createImageBitmap(file);
  } catch {
    throw new Error("Không đọc được ảnh này. Hãy chọn ảnh JPEG hoặc PNG.");
  }
  const size = fitSize(bitmap.width, bitmap.height, limit);
  const canvas = document.createElement("canvas");
  canvas.width = size.width;
  canvas.height = size.height;
  canvas.getContext("2d").drawImage(bitmap, 0, 0, size.width, size.height);
  bitmap.close?.();
  const blob = await new Promise((resolve) => canvas.toBlob(resolve, "image/jpeg", quality));
  if (!blob) throw new Error("Không xử lý được ảnh này.");
  return blobToBase64(blob);
}

/** The options a designer may need for a field of this type. */
export function fieldNeeds(fieldtype) {
  return {
    options: fieldtype === F.SELECT || fieldtype === F.TABLE,
    preset: fieldtype === F.TABLE,
    number: fieldtype === F.NUMBER,
    required: fieldtype !== F.SECTION,
  };
}
