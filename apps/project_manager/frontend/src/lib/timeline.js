// The parts of a discussion that are not drawing: mention tokens, search marks, the @ being typed, day headings.

// @[Full name](user@example.com): what the composer inserts (services/timeline.py reads the same form).
const MENTION = /@\[([^\]\n]{1,140})\]\(([^)\s]{3,140})\)/g;
export const MARK_START = "";
export const MARK_END = "";

export const KINDS = [
  { value: "", label: "Tất cả" },
  { value: "comment", label: "Trao đổi" },
  { value: "progress", label: "Tiến độ" },
  { value: "change", label: "Thay đổi" },
];

const ICONS = {
  "Bình luận": "message-square", "Tiến độ": "trending-up", "Giao việc": "user-check", "Đổi hạn": "calendar-clock",
  "Trạng thái": "flag", "Tệp": "file-text", "Biểu mẫu": "clipboard-list", "Thay đổi": "pencil", "Hệ thống": "info",
};
export const entryIcon = (type) => ICONS[type] || "info";

/** The text cut into plain parts and mentions: { type: "text", text } | { type: "mention", name, user }. */
export function segments(content) {
  const text = String(content ?? "");
  const out = [];
  let last = 0;
  for (const match of text.matchAll(MENTION)) {
    if (match.index > last) out.push({ type: "text", text: text.slice(last, match.index) });
    out.push({ type: "mention", name: match[1], user: match[2] });
    last = match.index + match[0].length;
  }
  if (last < text.length) out.push({ type: "text", text: text.slice(last) });
  return out;
}

/** Mentions shown as names: for previews and the queue screen. */
export const plainText = (content) => String(content ?? "").replace(MENTION, (_all, name) => `@${name}`);

/** A search result's text cut into marked and unmarked parts (no HTML involved). */
export function marked(text) {
  const out = [];
  const source = String(text ?? "");
  let position = 0;
  while (position < source.length) {
    const start = source.indexOf(MARK_START, position);
    if (start < 0) {
      out.push({ text: source.slice(position), marked: false });
      break;
    }
    if (start > position) out.push({ text: source.slice(position, start), marked: false });
    const end = source.indexOf(MARK_END, start + 1);
    const stop = end < 0 ? source.length : end;
    out.push({ text: source.slice(start + 1, stop), marked: true });
    position = stop + 1;
  }
  return out.filter((part) => part.text);
}

/** The "@word" right before the caret, if the user is typing a mention: { query, start } or null. */
export function mentionAt(text, caret) {
  const before = String(text ?? "").slice(0, caret);
  const match = /(^|[\s(])@([^\s@[\]()]{0,30})$/.exec(before);
  if (!match) return null;
  return { query: match[2], start: before.length - match[2].length - 1 };
}

/** Replace the "@word" being typed with the mention token of `person`. Returns { text, caret }. */
export function insertMention(text, start, caret, person) {
  const token = `@[${person.full_name || person.user}](${person.user}) `;
  const value = String(text ?? "");
  return { text: value.slice(0, start) + token + value.slice(caret), caret: start + token.length };
}

const pad = (n) => String(n).padStart(2, "0");
const isoDay = (date) => `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`;

/** "Hôm nay", "Hôm qua" or the date, for the day an entry was written. */
export function dayLabel(value, today = new Date()) {
  const day = String(value ?? "").slice(0, 10);
  if (!day) return "";
  const yesterday = new Date(today);
  yesterday.setDate(today.getDate() - 1);
  if (day === isoDay(today)) return "Hôm nay";
  if (day === isoDay(yesterday)) return "Hôm qua";
  const [y, m, d] = day.split("-");
  return `${d}/${m}/${y}`;
}

/** Entries (newest first) grouped by day: [{ day, label, entries }]. */
export function byDay(entries, today = new Date()) {
  const groups = [];
  for (const entry of entries) {
    const day = String(entry.creation ?? "").slice(0, 10);
    const last = groups[groups.length - 1];
    if (last && last.day === day) last.entries.push(entry);
    else groups.push({ day, label: dayLabel(day, today), entries: [entry] });
  }
  return groups;
}

/** A map link for a photo taken at (lat, lng). */
export function mapLink(lat, lng) {
  if (lat === null || lat === undefined || lng === null || lng === undefined) return "";
  return `https://www.openstreetmap.org/?mlat=${lat}&mlon=${lng}#map=18/${lat}/${lng}`;
}

/** Readable state of a queued item. */
export function queuedState(item, online) {
  if (item.state === "failed") return { text: `Không gửi được: ${item.error}`, tone: "danger" };
  if (item.state === "sending") return { text: "Đang gửi…", tone: "info" };
  if (!online) return { text: "Chờ có mạng", tone: "warning" };
  return { text: item.error ? `Sẽ thử lại: ${item.error}` : "Đang chờ gửi", tone: "warning" };
}
