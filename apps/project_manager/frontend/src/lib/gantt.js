// The Gantt and the calendar without any drawing: dates as day numbers, which rows show, where things go. No Vue, no canvas.

export const ROW = 30;
export const HEADER = 44;
export const ZOOMS = {
  day: { label: "Ngày", px: 30 },
  week: { label: "Tuần", px: 10 },
  month: { label: "Tháng", px: 3 },
};
export const LINK_KINDS = [
  { value: "FS", label: "Xong việc trước mới bắt đầu (FS)" },
  { value: "SS", label: "Bắt đầu cùng lúc với việc trước (SS)" },
  { value: "FF", label: "Xong cùng lúc với việc trước (FF)" },
  { value: "SF", label: "Việc trước bắt đầu thì việc này mới xong (SF)" },
];
const MONTHS = ["1", "2", "3", "4", "5", "6", "7", "8", "9", "10", "11", "12"];
const DAY_MS = 86400000;

/** "2026-11-06" (or a datetime) as a whole number of days: no time zone can shift it. */
export function dayNumber(value) {
  if (!value) return null;
  const match = /^(\d{4})-(\d{2})-(\d{2})/.exec(String(value));
  return match ? Math.round(Date.UTC(+match[1], +match[2] - 1, +match[3]) / DAY_MS) : null;
}

export function isoOf(number) {
  return new Date(number * DAY_MS).toISOString().slice(0, 10);
}

/** The server's compact rows as objects, with their days as numbers. */
export function tasksFrom(payload) {
  const { columns, rows } = payload;
  const parents = new Set();
  const tasks = rows.map((row) => {
    const task = Object.fromEntries(columns.map((column, index) => [column, row[index]]));
    task.startDay = dayNumber(task.start);
    task.endDay = dayNumber(task.end);
    task.forecastDay = dayNumber(task.forecast);
    task.baseStartDay = dayNumber(task.base_start);
    task.baseEndDay = dayNumber(task.base_end);
    if (task.parent) parents.add(task.parent);
    return task;
  });
  for (const task of tasks) task.hasChildren = parents.has(task.name);
  return tasks;
}

export const linksFrom = (payload) => payload.links.map(([name, from, to, kind, lag]) => ({ name, from, to, kind, lag }));

/** The rows that show: a row under a collapsed group does not. Tasks come in tree order. */
export function visibleRows(tasks, collapsed) {
  const shown = new Set();
  const out = [];
  for (const task of tasks) {
    const parentShown = !task.parent || (shown.has(task.parent) && !collapsed.has(task.parent));
    if (parentShown) {
      shown.add(task.name);
      out.push(task);
    }
  }
  return out;
}

/** Only the critical tasks and the groups that lead to them. */
export function criticalOnly(tasks) {
  const byName = new Map(tasks.map((task) => [task.name, task]));
  const keep = new Set();
  for (const task of tasks) {
    if (task.group || !task.critical) continue;
    let current = task;
    while (current && !keep.has(current.name)) {
      keep.add(current.name);
      current = current.parent ? byName.get(current.parent) : null;
    }
  }
  return tasks.filter((task) => keep.has(task.name));
}

/** Groups to close so that only `depth` levels show. */
export function collapsedBeyond(tasks, depth) {
  return new Set(tasks.filter((task) => task.hasChildren && task.level >= depth).map((task) => task.name));
}

/** The days the chart covers, with some room on both sides. */
export function dayRange(tasks, today) {
  let first = dayNumber(today);
  let last = first;
  for (const task of tasks) {
    for (const day of [task.startDay, task.endDay, task.forecastDay, task.baseStartDay, task.baseEndDay]) {
      if (day === null || day === undefined) continue;
      if (day < first) first = day;
      if (day > last) last = day;
    }
  }
  return { first: first - 14, last: last + 30 };
}

function dateOf(number) {
  const date = new Date(number * DAY_MS);
  return { year: date.getUTCFullYear(), month: date.getUTCMonth(), day: date.getUTCDate(), weekday: (date.getUTCDay() + 6) % 7 };
}

/** The scale above the chart between two days: `major` on top, `minor` under it. */
export function axisTicks(from, to, zoom) {
  const major = [];
  const minor = [];
  for (let number = from; number <= to; number += 1) {
    const { year, month, day, weekday } = dateOf(number);
    if (zoom === "month") {
      if (day === 1) {
        minor.push({ day: number, label: MONTHS[month] });
        if (month === 0) major.push({ day: number, label: String(year) });
      }
    } else {
      if (day === 1) major.push({ day: number, label: `${MONTHS[month]}/${year}` });
      if (zoom === "day") minor.push({ day: number, label: String(day) });
      else if (weekday === 0) minor.push({ day: number, label: `${day}/${MONTHS[month]}` });
    }
  }
  return { major, minor };
}

/** Which part of a bar a point is on. */
export function hitZone(x, left, right, milestone = false, canResize = true, handle = 6) {
  if (x < left - handle || x > right + handle) return null;
  if (milestone || !canResize || right - left < handle * 3) return x >= left - handle && x <= right + handle ? "move" : null;
  if (x <= left + handle) return "start";
  if (x >= right - handle) return "end";
  return "move";
}

/** New dates after dragging by a number of days, or null when nothing changes. */
export function movedDates(task, zone, days) {
  if (!days) return null;
  let start = task.startDay;
  let end = task.endDay;
  if (zone === "move") {
    start += days;
    end += days;
  } else if (zone === "start") {
    start = Math.min(start + days, end);
  } else if (zone === "end") {
    end = Math.max(end + days, start);
  }
  if (start === task.startDay && end === task.endDay) return null;
  return { start: isoOf(start), end: isoOf(end), startDay: start, endDay: end };
}

/** Where a dependency arrow runs: out of one bar, into the other, going round when the target lies behind. */
export function linkPath(from, to, fromEnd, toStart, gap = 8) {
  const out = fromEnd ? from.x + gap : from.x - gap;
  const into = toStart ? to.x - gap : to.x + gap;
  const clear = toStart ? out <= into : out >= into;
  if (clear) return [[from.x, from.y], [out, from.y], [out, to.y], [to.x, to.y]];
  const middle = from.y + (to.y >= from.y ? ROW / 2 : -ROW / 2);
  return [[from.x, from.y], [out, from.y], [out, middle], [into, middle], [into, to.y], [to.x, to.y]];
}

export const fromSideIsEnd = (kind) => kind === "FS" || kind === "FF";
export const toSideIsStart = (kind) => kind === "FS" || kind === "SS";

export function slipText(days) {
  if (days === null || days === undefined) return "";
  if (days === 0) return "đúng kế hoạch";
  return days > 0 ? `trễ ${days} ngày` : `sớm ${-days} ngày`;
}
export const slipTone = (days) => (days > 0 ? "text-danger" : days < 0 ? "text-success" : "text-ink-muted");

// --- the calendar --------------------------------------------------------------------------------------------------------

/** The weeks of a month, Monday first, each a list of 7 ISO days (including the ends of the months around it). */
export function monthWeeks(year, month) {
  const first = Math.round(Date.UTC(year, month, 1) / DAY_MS);
  const last = Math.round(Date.UTC(year, month + 1, 0) / DAY_MS);
  const begin = first - dateOf(first).weekday;
  const weeks = [];
  for (let day = begin; day <= last; day += 7) {
    weeks.push(Array.from({ length: 7 }, (_unused, offset) => isoOf(day + offset)));
  }
  return weeks;
}

export const isOn = (task, iso) => (task.start || task.end) <= iso && iso <= (task.end || task.start);

/** Per day, what starts and what is due: what a phone shows of a month. */
export function agenda(tasks, first, last) {
  const days = new Map();
  const add = (iso, task, kind) => {
    if (!iso || iso < first || iso > last) return;
    if (!days.has(iso)) days.set(iso, []);
    days.get(iso).push({ task, kind });
  };
  for (const task of tasks) {
    if (task.milestone || task.start === task.end) {
      add(task.end || task.start, task, task.milestone ? "Mốc" : "Trong ngày");
    } else {
      add(task.start, task, "Bắt đầu");
      add(task.end, task, "Hạn");
    }
  }
  return [...days.entries()].sort(([a], [b]) => a.localeCompare(b)).map(([day, items]) => ({ day, items }));
}
