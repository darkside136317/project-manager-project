<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from "vue";

// Our own Gantt: one scroll area, a DOM list of the visible rows on the left and a canvas of the same rows on the right.
// Only what is on screen is drawn, so the cost does not grow with the number of tasks.
const props = defineProps({ plan: { type: Object, required: true } });
const ROW = 28;
const DAY_W = 8;
const GRID_W = 280;
const DAY = 86400000;

const scroller = ref(null);
const canvas = ref(null);
const top = ref(0);
const left = ref(0);
const height = ref(600);
const width = ref(800);

const rows = props.plan.tasks;
const rowOf = new Map(rows.map((t, i) => [t.id, i]));
const min = Math.min(...rows.map((t) => t.start));
const max = Math.max(...rows.map((t) => t.end));
const totalWidth = Math.ceil((max - min) / DAY + 30) * DAY_W;
const incoming = new Map();
for (const link of props.plan.links) {
  if (!incoming.has(link.target)) incoming.set(link.target, []);
  incoming.get(link.target).push(link);
}
const levels = new Map();
for (const t of rows) levels.set(t.id, t.parent ? (levels.get(t.parent) || 0) + 1 : 0);

const first = computed(() => Math.max(0, Math.floor(top.value / ROW) - 2));
const last = computed(() => Math.min(rows.length, Math.ceil((top.value + height.value) / ROW) + 2));
const visible = computed(() => rows.slice(first.value, last.value).map((t, i) => ({ ...t, index: first.value + i })));

const x = (ms) => ((ms - min) / DAY) * DAY_W - left.value;

function draw() {
  const ctx = canvas.value?.getContext("2d");
  if (!ctx) return;
  const ratio = window.devicePixelRatio || 1;
  const w = width.value - GRID_W;
  canvas.value.width = w * ratio;
  canvas.value.height = height.value * ratio;
  canvas.value.style.width = `${w}px`;
  canvas.value.style.height = `${height.value}px`;
  ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
  ctx.clearRect(0, 0, w, height.value);
  const offset = top.value;
  ctx.strokeStyle = "#e2e8f0";
  for (let day = Math.floor(left.value / DAY_W / 7) * 7; day * DAY_W - left.value < w; day += 7) {
    const gx = day * DAY_W - left.value;
    ctx.beginPath(); ctx.moveTo(gx, 0); ctx.lineTo(gx, height.value); ctx.stroke();
  }
  for (const t of visible.value) {
    const y = t.index * ROW - offset;
    const bx = x(t.start);
    const bw = Math.max(4, x(t.end) - bx);
    if (t.group) {
      ctx.fillStyle = "#0a1f35";
      ctx.fillRect(bx, y + 10, bw, 8);
    } else {
      ctx.fillStyle = "#cbd5e1";
      ctx.fillRect(bx, y + 6, bw, 16);
      ctx.fillStyle = "#f59f0a";
      ctx.fillRect(bx, y + 6, (bw * t.progress) / 100, 16);
    }
    for (const link of incoming.get(t.id) || []) {
      const source = rows[rowOf.get(link.source)];
      if (!source) continue;
      const sy = rowOf.get(link.source) * ROW - offset + ROW / 2;
      const sx = link.type === "SS" ? x(source.start) : x(source.end);
      const tx = link.type === "FF" ? x(t.end) : bx;
      ctx.strokeStyle = "#64748b";
      ctx.beginPath();
      ctx.moveTo(sx, sy);
      ctx.lineTo(sx + 6, sy);
      ctx.lineTo(sx + 6, y + ROW / 2);
      ctx.lineTo(tx, y + ROW / 2);
      ctx.stroke();
    }
  }
}

let frame = 0;
function onScroll() {
  top.value = scroller.value.scrollTop;
  left.value = scroller.value.scrollLeft;
  cancelAnimationFrame(frame);
  frame = requestAnimationFrame(draw);
}
function measure() {
  height.value = scroller.value.clientHeight;
  width.value = scroller.value.clientWidth;
  draw();
}
let observer;
onMounted(async () => {
  await nextTick();
  observer = new ResizeObserver(measure);
  observer.observe(scroller.value);
  measure();
});
onBeforeUnmount(() => observer?.disconnect());
</script>

<template>
  <div ref="scroller" class="scroller" @scroll="onScroll">
    <div :style="{ height: `${rows.length * ROW}px`, width: `${GRID_W + totalWidth}px` }"></div>
    <div class="viewport">
      <ol class="grid" :style="{ width: `${GRID_W}px` }">
        <li v-for="t in visible" :key="t.id" :style="{ transform: `translateY(${t.index * ROW - top}px)`, paddingLeft: `${8 + levels.get(t.id) * 14}px`, fontWeight: t.group ? 600 : 400 }">
          {{ t.wbs }} {{ t.text }}
        </li>
      </ol>
      <canvas ref="canvas" class="chart"></canvas>
    </div>
  </div>
</template>

<style scoped>
.scroller { position: relative; height: 100%; overflow: auto; }
.viewport { position: sticky; top: 0; left: 0; height: 100%; margin-top: -100%; display: flex; pointer-events: none; }
.grid { position: sticky; left: 0; margin: 0; padding: 0; list-style: none; background: #fff; border-right: 1px solid #e2e8f0; height: 100%; overflow: hidden; }
.grid li { position: absolute; left: 0; right: 0; height: 28px; line-height: 28px; font-size: 13px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; border-bottom: 1px solid #f1f5f9; }
.chart { display: block; }
</style>
