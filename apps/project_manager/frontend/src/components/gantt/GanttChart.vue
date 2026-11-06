<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { formatDate } from "../../lib/format.js";
import {
  HEADER,
  ROW,
  ZOOMS,
  axisTicks,
  dayNumber,
  fromSideIsEnd,
  hitZone,
  linkPath,
  movedDates,
  toSideIsStart,
} from "../../lib/gantt.js";
import { statusLabel } from "../../lib/work.js";
import Icon from "../Icon.vue";

// Our own Gantt: a DOM list of the visible rows on the left and a canvas on the right, drawn only for what is on screen,
// so its cost does not grow with the size of the project. Dates are moved by dragging; what that does to other tasks
// is the server's business (the parent asks for a preview before anything changes).
const props = defineProps({
  rows: { type: Array, required: true },
  links: { type: Array, default: () => [] },
  span: { type: Object, required: true },
  daysOff: { type: Array, default: () => [] },
  today: { type: String, required: true },
  zoom: { type: String, default: "week" },
  editable: { type: Boolean, default: false },
  canLink: { type: Boolean, default: false },
  collapsed: { type: Object, required: true },
  gridWidth: { type: Number, default: 300 },
  label: { type: String, default: "" },
});
const emit = defineEmits(["open", "toggle", "change", "link"]);

const scroller = ref(null);
const canvas = ref(null);
const top = ref(0);
const left = ref(0);
const viewWidth = ref(800);
const viewHeight = ref(500);
const tip = ref(null);
const drawn = ref(false);

const px = computed(() => ZOOMS[props.zoom].px);
const totalWidth = computed(() => (props.span.last - props.span.first + 1) * px.value);
const rowOf = computed(() => new Map(props.rows.map((row, index) => [row.name, index])));
const off = computed(() => new Set(props.daysOff.map(dayNumber)));
const firstRow = computed(() => Math.max(0, Math.floor(top.value / ROW) - 2));
const lastRow = computed(() => Math.min(props.rows.length, Math.ceil((top.value + viewHeight.value) / ROW) + 2));
const gridRows = computed(() => props.rows.slice(firstRow.value, lastRow.value).map((row, offset) => ({ row, index: firstRow.value + offset })));

let drag = null;  // { task, zone, x, days } or { link: task, x, y }
let justDragged = false;
let hovered = null;
let frame = 0;

const dayX = (day) => (day - props.span.first) * px.value - left.value;
const rowY = (index) => HEADER + index * ROW - top.value;

let palette = null;
let paletteTheme = null;

/** The theme's colours, read again only when the theme changes: reading styles on every frame makes scrolling heavy. */
function colors() {
  const theme = document.documentElement.dataset.theme || "";
  if (palette && paletteTheme === theme) return palette;
  const style = getComputedStyle(document.documentElement);
  const read = (name, fallback) => style.getPropertyValue(name).trim() || fallback;
  paletteTheme = theme;
  palette = {
    line: read("--pm-border", "#e2e8f0"), surface: read("--pm-surface", "#fff"), muted: read("--pm-surface-muted", "#f8fafc"),
    ink: read("--pm-ink", "#1e293b"), soft: read("--pm-muted", "#64748b"), primary: read("--pm-primary", "#0a1f35"),
    danger: read("--pm-danger", "#dc2626"), warning: read("--pm-warning", "#d97706"), success: read("--pm-success", "#16a34a"),
  };
  return palette;
}

/** The bar's days, as being dragged if it is. */
function daysOf(task) {
  if (drag?.task === task && drag.moved) return { startDay: drag.moved.startDay, endDay: drag.moved.endDay };
  return task;
}

function barOf(task) {
  const days = daysOf(task);
  if (days.startDay === null || days.startDay === undefined) return null;
  if (task.milestone) {
    const middle = dayX(days.endDay) + px.value / 2;
    return { left: middle - 7, right: middle + 7, middle };
  }
  return { left: dayX(days.startDay), right: dayX(days.endDay + 1) };
}

function drawHeader(ctx, c, width) {
  const from = props.span.first + Math.floor(left.value / px.value) - 1;
  const to = from + Math.ceil(width / px.value) + 2;
  const { major, minor } = axisTicks(from, to, props.zoom);
  ctx.fillStyle = c.surface;
  ctx.fillRect(0, 0, width, HEADER);
  ctx.textBaseline = "middle";
  ctx.textAlign = "left";
  ctx.font = "600 12px system-ui, sans-serif";
  ctx.fillStyle = c.ink;
  for (const tick of major) ctx.fillText(tick.label, dayX(tick.day) + 4, 12);
  ctx.font = "11px system-ui, sans-serif";
  ctx.fillStyle = c.soft;
  for (const tick of minor) ctx.fillText(tick.label, dayX(tick.day) + (props.zoom === "day" ? 8 : 3), 33);
  ctx.strokeStyle = c.line;
  ctx.beginPath();
  ctx.moveTo(0, HEADER - 0.5);
  ctx.lineTo(width, HEADER - 0.5);
  ctx.moveTo(0, 22.5);
  ctx.lineTo(width, 22.5);
  ctx.stroke();
}

function drawBackground(ctx, c, width, height) {
  const from = props.span.first + Math.floor(left.value / px.value) - 1;
  const to = from + Math.ceil(width / px.value) + 2;
  if (props.zoom !== "month") {
    ctx.fillStyle = c.muted;
    for (let day = from; day <= to; day += 1) {
      if (off.value.has(day)) ctx.fillRect(dayX(day), HEADER, px.value, height - HEADER);
    }
  }
  ctx.strokeStyle = c.line;
  ctx.lineWidth = 1;
  ctx.beginPath();
  for (const tick of axisTicks(from, to, props.zoom).minor) {
    const x = Math.round(dayX(tick.day)) + 0.5;
    ctx.moveTo(x, HEADER);
    ctx.lineTo(x, height);
  }
  for (let index = firstRow.value; index <= lastRow.value; index += 1) {
    const y = Math.round(rowY(index)) + 0.5;
    ctx.moveTo(0, y);
    ctx.lineTo(width, y);
  }
  ctx.stroke();
}

function roundBar(ctx, x, y, width, height, radius = 3) {
  ctx.beginPath();
  if (ctx.roundRect) ctx.roundRect(x, y, Math.max(width, 2), height, radius);
  else ctx.rect(x, y, Math.max(width, 2), height);
}

function drawTask(ctx, c, task, index) {
  const y = rowY(index);
  const bar = barOf(task);
  if (!bar) return;
  if (hovered === task.name && props.canLink && !drag) {
    ctx.strokeStyle = c.primary;
    ctx.fillStyle = c.surface;
    ctx.lineWidth = 2;
    ctx.beginPath();
    ctx.arc(bar.right + 11, y + ROW / 2 - 1, 4, 0, Math.PI * 2);
    ctx.fill();
    ctx.stroke();
    ctx.lineWidth = 1;
  }
  const tone = task.critical ? c.danger : c.primary;
  if (task.baseStartDay !== null && task.baseEndDay !== null && !task.group) {
    ctx.fillStyle = c.soft;
    ctx.globalAlpha = 0.65;
    ctx.fillRect(dayX(task.baseStartDay), y + 23, Math.max(2, dayX(task.baseEndDay + 1) - dayX(task.baseStartDay)), 3);
    ctx.globalAlpha = 1;
  }
  if (task.milestone) {
    ctx.fillStyle = tone;
    ctx.beginPath();
    ctx.moveTo(bar.middle, y + 7);
    ctx.lineTo(bar.middle + 7, y + 14);
    ctx.lineTo(bar.middle, y + 21);
    ctx.lineTo(bar.middle - 7, y + 14);
    ctx.closePath();
    ctx.fill();
    return;
  }
  const width = bar.right - bar.left;
  if (task.group) {
    ctx.fillStyle = task.critical ? c.danger : c.ink;
    ctx.fillRect(bar.left, y + 9, width, 5);
    ctx.fillRect(bar.left, y + 9, 3, 11);
    ctx.fillRect(bar.right - 3, y + 9, 3, 11);
    return;
  }
  const done = task.status === "Completed";
  const fill = done ? c.success : tone;
  ctx.fillStyle = fill;
  ctx.globalAlpha = done ? 1 : 0.22;
  roundBar(ctx, bar.left + 0.5, y + 6, width - 1, 15);
  ctx.fill();
  ctx.globalAlpha = 1;
  if (!done && task.progress > 0) {
    roundBar(ctx, bar.left + 0.5, y + 6, (width - 1) * Math.min(100, task.progress) / 100, 15);
    ctx.fill();
  }
  if (task.critical && !done) {
    ctx.strokeStyle = c.danger;
    ctx.lineWidth = 1.5;
    roundBar(ctx, bar.left + 0.5, y + 6, width - 1, 15);
    ctx.stroke();
    ctx.lineWidth = 1;
  }
  if (!done && task.forecastDay !== null && task.forecastDay > task.endDay && !drag?.moved) {
    const end = dayX(task.forecastDay + 1);
    ctx.strokeStyle = c.warning;
    ctx.setLineDash([3, 3]);
    ctx.lineWidth = 2;
    ctx.beginPath();
    ctx.moveTo(bar.right, y + 13.5);
    ctx.lineTo(end, y + 13.5);
    ctx.stroke();
    ctx.setLineDash([]);
    ctx.lineWidth = 1;
    ctx.fillStyle = c.warning;
    ctx.fillRect(end - 2, y + 9, 2, 9);
  }
  if (task.conflict > 0) {
    ctx.fillStyle = c.warning;
    ctx.beginPath();
    ctx.moveTo(bar.left - 9, y + 19);
    ctx.lineTo(bar.left - 4, y + 9);
    ctx.lineTo(bar.left + 1, y + 19);
    ctx.closePath();
    ctx.fill();
  }
}

function endpoint(task, atEnd, index) {
  const bar = barOf(task);
  if (!bar) return null;
  return { x: atEnd ? bar.right : bar.left, y: rowY(index) + ROW / 2 - 1 };
}

function drawLinks(ctx, c) {
  const low = firstRow.value;
  const high = lastRow.value;
  for (const link of props.links) {
    const a = rowOf.value.get(link.from);
    const b = rowOf.value.get(link.to);
    if (a === undefined || b === undefined || Math.max(a, b) < low || Math.min(a, b) > high) continue;
    const from = endpoint(props.rows[a], fromSideIsEnd(link.kind), a);
    const to = endpoint(props.rows[b], toSideIsStart(link.kind), b);
    if (!from || !to) continue;
    const critical = props.rows[a].critical && props.rows[b].critical;
    const color = critical ? c.danger : c.soft;
    ctx.strokeStyle = color;
    ctx.fillStyle = color;
    ctx.beginPath();
    linkPath(from, to, fromSideIsEnd(link.kind), toSideIsStart(link.kind)).forEach(([x, y], position) => {
      if (position) ctx.lineTo(x, y);
      else ctx.moveTo(x, y);
    });
    ctx.stroke();
    const direction = toSideIsStart(link.kind) ? 1 : -1;
    ctx.beginPath();
    ctx.moveTo(to.x, to.y);
    ctx.lineTo(to.x - 5 * direction, to.y - 3);
    ctx.lineTo(to.x - 5 * direction, to.y + 3);
    ctx.closePath();
    ctx.fill();
  }
}

function draw() {
  const element = canvas.value;
  const ctx = element?.getContext?.("2d");
  if (!ctx) return;
  const ratio = window.devicePixelRatio || 1;
  const width = Math.max(0, viewWidth.value - props.gridWidth);
  const height = viewHeight.value;
  if (element.width !== Math.round(width * ratio) || element.height !== Math.round(height * ratio)) {
    element.width = Math.round(width * ratio);
    element.height = Math.round(height * ratio);
    element.style.width = `${width}px`;
    element.style.height = `${height}px`;
  }
  ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
  ctx.clearRect(0, 0, width, height);
  const c = colors();
  drawBackground(ctx, c, width, height);
  drawLinks(ctx, c);
  for (let index = firstRow.value; index < lastRow.value; index += 1) drawTask(ctx, c, props.rows[index], index);
  const todayX = Math.round(dayX(dayNumber(props.today)) + px.value / 2) + 0.5;
  ctx.strokeStyle = c.warning;
  ctx.lineWidth = 2;
  ctx.beginPath();
  ctx.moveTo(todayX, HEADER);
  ctx.lineTo(todayX, height);
  ctx.stroke();
  ctx.lineWidth = 1;
  if (drag?.link) {
    ctx.strokeStyle = c.primary;
    ctx.setLineDash([4, 3]);
    ctx.beginPath();
    ctx.moveTo(drag.fromX, drag.fromY);
    ctx.lineTo(drag.x, drag.y);
    ctx.stroke();
    ctx.setLineDash([]);
  }
  drawHeader(ctx, c, width);
  if (!drawn.value && props.rows.length) {
    drawn.value = true;
    performance.mark?.("pm-gantt-drawn");
  }
}

function redraw() {
  cancelAnimationFrame(frame);
  frame = requestAnimationFrame(draw);
}

function onScroll() {
  top.value = scroller.value.scrollTop;
  left.value = scroller.value.scrollLeft;
  tip.value = null;
  redraw();
}

function measure() {
  if (!scroller.value) return;
  viewWidth.value = scroller.value.clientWidth;
  viewHeight.value = scroller.value.clientHeight;
  draw();
}

function pointAt(event) {
  const box = canvas.value.getBoundingClientRect();
  return { x: event.clientX - box.left, y: event.clientY - box.top };
}

function taskAt(point) {
  if (point.y < HEADER) return null;
  const index = Math.floor((point.y - HEADER + top.value) / ROW);
  const task = props.rows[index];
  return task ? { task, index } : null;
}

const canDrag = (task) => props.editable && task.status !== "Completed" && task.startDay !== null;

function zoneAt(point, found) {
  const bar = found && barOf(found.task);
  if (!bar) return null;
  return hitZone(point.x, bar.left, bar.right, Boolean(found.task.milestone), !found.task.group && canDrag(found.task));
}

/** The small dot after a bar, from which a dependency is dragged. */
function onLinkHandle(point, found) {
  if (!props.canLink || !found) return false;
  const bar = barOf(found.task);
  if (!bar) return false;
  const y = rowY(found.index) + ROW / 2 - 1;
  return Math.hypot(point.x - (bar.right + 11), point.y - y) <= 7;
}

function onPointerDown(event) {
  if (!props.editable && !props.canLink) return;
  const point = pointAt(event);
  const found = taskAt(point);
  if (!found) return;
  if (onLinkHandle(point, found)) {
    const bar = barOf(found.task);
    drag = { link: found.task, x: point.x, y: point.y, fromX: bar.right, fromY: rowY(found.index) + ROW / 2 - 1 };
  } else {
    const zone = zoneAt(point, found);
    if (!zone || !canDrag(found.task)) return;
    drag = { task: found.task, zone, x: point.x, moved: null };
  }
  canvas.value.setPointerCapture?.(event.pointerId);
  event.preventDefault();
}

function describe(task) {
  const lines = [`${formatDate(task.start) || "chưa có ngày"} → ${formatDate(task.end) || "—"}`, `${Math.round(task.progress)}% · ${statusLabel(task.status)}`];
  if (task.who) lines.push(task.who);
  if (task.critical) lines.push("Trên đường găng");
  else if (!task.group && task.float > 0) lines.push(`Dự trữ ${task.float} ngày làm việc`);
  if (task.conflict > 0) lines.push(`Bắt đầu sớm hơn phụ thuộc cho phép ${task.conflict} ngày`);
  if (task.forecast && task.forecast !== task.end) lines.push(`Dự báo xong ${formatDate(task.forecast)}`);
  if (task.base_end) lines.push(`Baseline ${formatDate(task.base_start)} → ${formatDate(task.base_end)}`);
  return lines;
}

function onPointerMove(event) {
  const point = pointAt(event);
  if (drag?.link) {
    drag.x = point.x;
    drag.y = point.y;
    redraw();
    return;
  }
  if (drag) {
    drag.moved = movedDates(drag.task, drag.zone, Math.round((point.x - drag.x) / px.value));
    redraw();
    return;
  }
  const found = taskAt(point);
  const zone = zoneAt(point, found);
  const onHandle = onLinkHandle(point, found);
  const under = found && (zone || onHandle) ? found.task.name : null;
  if (under !== hovered) {
    hovered = under;
    redraw();
  }
  canvas.value.style.cursor = onHandle ? "crosshair"
    : !zone ? "default"
      : zone === "move" ? (found && canDrag(found.task) ? "grab" : "pointer") : "ew-resize";
  if (found && (zone || onHandle)) {
    tip.value = { title: `${found.task.code} ${found.task.subject}`.trim(), lines: describe(found.task),
      x: Math.min(point.x + props.gridWidth + 14, viewWidth.value - 250), y: Math.min(point.y + 14, viewHeight.value - 130) };
  } else {
    tip.value = null;
  }
}

function onPointerUp(event) {
  if (!drag) return;
  const finished = drag;
  drag = null;
  canvas.value.releasePointerCapture?.(event.pointerId);
  if (finished.link) {
    const found = taskAt(pointAt(event));
    if (found && found.task !== finished.link && barOf(found.task)) emit("link", { from: finished.link.name, to: found.task.name });
    justDragged = true;
  } else if (finished.moved) {
    justDragged = true;
    const { start, end } = finished.moved;
    emit("change", { task: finished.task, start, end, zone: finished.zone });
    return;  // the bar stays where it was until the move is confirmed
  }
  redraw();
}

function onClick(event) {
  if (justDragged) {
    justDragged = false;
    redraw();
    return;
  }
  const point = pointAt(event);
  const found = taskAt(point);
  if (found && zoneAt(point, found)) emit("open", found.task.name);
}

function goToToday() {
  if (!scroller.value) return;
  scroller.value.scrollLeft = Math.max(0, (dayNumber(props.today) - props.span.first) * px.value - (viewWidth.value - props.gridWidth) / 3);
}

let observer;
onMounted(async () => {
  await nextTick();
  measure();
  goToToday();
  observer = window.ResizeObserver ? new ResizeObserver(measure) : null;
  observer?.observe(scroller.value);
});
onBeforeUnmount(() => {
  observer?.disconnect();
  cancelAnimationFrame(frame);
});
watch(() => [props.rows, props.links, props.daysOff], redraw);
watch(() => props.zoom, async () => {
  await nextTick();
  goToToday();
  redraw();
});
defineExpose({ goToToday, redraw });
</script>

<template>
  <div ref="scroller" class="gantt-scroller" :data-ready="drawn ? '1' : undefined" @scroll.passive="onScroll">
    <div :style="{ width: `${gridWidth + totalWidth}px`, height: `${HEADER + rows.length * ROW + 8}px` }">
      <div class="gantt-view" :style="{ width: `${viewWidth}px`, height: `${viewHeight}px` }">
        <div class="gantt-grid" :style="{ width: `${gridWidth}px` }">
          <div class="gantt-grid-head" :style="{ height: `${HEADER}px` }">Công việc</div>
          <div class="gantt-rows" :style="{ transform: `translateY(${HEADER - top}px)` }">
            <div v-for="{ row, index } in gridRows" :key="row.name" class="gantt-row" :style="{ top: `${index * ROW}px`, height: `${ROW}px`, paddingLeft: `${Math.max(0, row.level - 1) * 12 + 4}px` }">
              <button v-if="row.hasChildren" class="gantt-toggle" type="button" :aria-label="collapsed.has(row.name) ? 'Mở rộng' : 'Thu gọn'" :aria-expanded="!collapsed.has(row.name)" @click="emit('toggle', row.name)">
                <Icon :name="collapsed.has(row.name) ? 'chevron-right' : 'chevron-down'" :size="14" />
              </button>
              <span v-else class="inline-block w-5 shrink-0"></span>
              <button class="gantt-name" :class="{ 'font-semibold': row.group, 'text-danger': row.critical && !row.group }" type="button" :title="`${row.code} ${row.subject}`" @click="emit('open', row.name)">
                <span class="text-ink-muted">{{ row.code }}</span> {{ row.subject }}
              </button>
            </div>
          </div>
        </div>
        <canvas ref="canvas" class="gantt-canvas" :style="{ left: `${gridWidth}px`, touchAction: editable || canLink ? 'pan-y pan-x' : 'auto' }" role="img" :aria-label="label"
          @pointerdown="onPointerDown" @pointermove="onPointerMove" @pointerup="onPointerUp" @pointercancel="onPointerUp" @pointerleave="tip = null" @click="onClick"></canvas>
        <div v-if="tip" class="gantt-tip" :style="{ left: `${tip.x}px`, top: `${tip.y}px` }" role="status">
          <p class="m-0 font-semibold">{{ tip.title }}</p>
          <p v-for="line in tip.lines" :key="line" class="m-0">{{ line }}</p>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.gantt-scroller { position: relative; height: 100%; overflow: auto; border: 1px solid var(--pm-border); border-radius: 0.75rem; background: var(--pm-surface); }
.gantt-view { position: sticky; top: 0; left: 0; overflow: hidden; }
.gantt-grid { position: absolute; top: 0; left: 0; bottom: 0; z-index: 2; overflow: hidden; background: var(--pm-surface); border-right: 1px solid var(--pm-border); }
.gantt-grid-head { position: absolute; top: 0; left: 0; right: 0; z-index: 3; display: flex; align-items: center; padding-left: 12px; font-size: 12px; font-weight: 600; color: var(--pm-muted); background: var(--pm-surface); border-bottom: 1px solid var(--pm-border); }
.gantt-rows { position: absolute; top: 0; left: 0; right: 0; will-change: transform; }
.gantt-row { position: absolute; left: 0; right: 0; display: flex; align-items: center; gap: 2px; border-bottom: 1px solid var(--pm-border); font-size: 13px; }
.gantt-toggle { display: grid; place-items: center; width: 20px; height: 22px; flex-shrink: 0; color: var(--pm-muted); border-radius: 4px; }
.gantt-toggle:hover, .gantt-name:hover { background: var(--pm-surface-muted); }
.gantt-name { min-width: 0; flex: 1; overflow: hidden; white-space: nowrap; text-overflow: ellipsis; text-align: left; padding: 2px 4px; border-radius: 4px; }
.gantt-canvas { position: absolute; top: 0; display: block; }
.gantt-tip { position: absolute; z-index: 5; width: 236px; pointer-events: none; padding: 6px 10px; font-size: 12px; border: 1px solid var(--pm-border); border-radius: 8px; background: var(--pm-surface); box-shadow: 0 8px 24px rgb(0 0 0 / 0.16); }
</style>
