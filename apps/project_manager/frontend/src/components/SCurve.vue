<script setup>
import { computed, ref } from "vue";
import { formatDate } from "../lib/format.js";
import { dayNumber } from "../lib/gantt.js";

// Đường cong S: actual progress against plan over time, one axis 0-100 %. Two series: actual (solid, slot 1), which stops
// at the last daily snapshot, and plan (dashed, slot 2), which goes on to the end when there is a baseline. Legend and
// direct labels at each line's last point, a crosshair tooltip with both values, and a table for readers who cannot use
// the chart.
const props = defineProps({ points: { type: Array, default: () => [] } });

const W = 640;
const H = 220;
const PAD = { left: 36, right: 64, top: 12, bottom: 26 };
const hover = ref(-1);
const showTable = ref(false);

const rows = computed(() => props.points.map((point) => ({ ...point, number: dayNumber(point.snapshot_date) })));
const n = computed(() => rows.value.length);
const firstDay = computed(() => rows.value[0]?.number ?? 0);
const lastDay = computed(() => rows.value[n.value - 1]?.number ?? 0);
const x = (number) => PAD.left + (lastDay.value === firstDay.value ? 0 : ((number - firstDay.value) * (W - PAD.left - PAD.right)) / (lastDay.value - firstDay.value));
const y = (v) => PAD.top + (1 - Math.min(100, Math.max(0, Number(v) || 0)) / 100) * (H - PAD.top - PAD.bottom);
const hasValue = (value) => value !== null && value !== undefined;

function path(key) {
  return rows.value.filter((row) => hasValue(row[key]))
    .map((row, index) => `${index ? "L" : "M"}${x(row.number).toFixed(1)},${y(row[key]).toFixed(1)}`).join(" ");
}

const lastActual = computed(() => [...rows.value].reverse().find((row) => hasValue(row.progress)) || null);
const lastPlan = computed(() => rows.value[n.value - 1] || null);
const ticks = [0, 25, 50, 75, 100];
const dateTicks = computed(() => {
  if (!n.value) return [];
  const out = [];
  const steps = 5;
  for (let step = 0; step <= steps; step += 1) {
    const number = firstDay.value + Math.round(((lastDay.value - firstDay.value) * step) / steps);
    out.push({ number, label: formatDate(new Date(number * 86400000).toISOString().slice(0, 10)).slice(0, 5) });
    if (lastDay.value === firstDay.value) break;
  }
  return out;
});
const labelsClash = computed(() => lastActual.value && lastPlan.value && lastActual.value.number === lastPlan.value.number
  && Math.abs(y(lastActual.value.progress) - y(lastPlan.value.planned_progress)) < 12);

function onMove(event) {
  const box = event.currentTarget.getBoundingClientRect();
  const position = ((event.clientX - box.left) / box.width) * W;
  let best = -1;
  let distance = Infinity;
  rows.value.forEach((row, index) => {
    const gap = Math.abs(x(row.number) - position);
    if (gap < distance) {
      distance = gap;
      best = index;
    }
  });
  hover.value = best;
}
const tip = computed(() => (hover.value >= 0 ? rows.value[hover.value] : null));
const pct = (v) => (hasValue(v) ? `${Math.round(Number(v) || 0)}%` : "—");
const summary = computed(() => `Đường cong S: thực tế ${pct(lastActual.value?.progress)}, kế hoạch cuối kỳ ${pct(lastPlan.value?.planned_progress)}`);
</script>

<template>
  <figure class="s-curve m-0">
    <div class="mb-2 flex flex-wrap items-center gap-4 text-xs text-ink-soft">
      <span class="flex items-center gap-1.5"><svg width="18" height="6" aria-hidden="true"><line x1="0" y1="3" x2="18" y2="3" class="actual" /></svg> Thực tế</span>
      <span class="flex items-center gap-1.5"><svg width="18" height="6" aria-hidden="true"><line x1="0" y1="3" x2="18" y2="3" class="plan" /></svg> Kế hoạch</span>
      <button class="ml-auto text-xs text-ink-muted underline" type="button" @click="showTable = !showTable">{{ showTable ? "Xem biểu đồ" : "Xem bảng số liệu" }}</button>
    </div>
    <p v-if="!n" class="m-0 py-8 text-center text-sm text-ink-muted">Chưa có số liệu: tiến độ được ghi lại mỗi ngày từ hôm nay.</p>
    <div v-else-if="!showTable" class="relative">
      <svg :viewBox="`0 0 ${W} ${H}`" class="block h-auto w-full" role="img" :aria-label="summary" @pointermove="onMove" @pointerleave="hover = -1">
        <g class="s-gridlines">
          <line v-for="t in ticks" :key="t" :x1="PAD.left" :x2="W - PAD.right" :y1="y(t)" :y2="y(t)" />
        </g>
        <g class="axis">
          <text v-for="t in ticks" :key="`l${t}`" :x="PAD.left - 6" :y="y(t) + 4" text-anchor="end">{{ t }}%</text>
          <text v-for="tick in dateTicks" :key="`d${tick.number}`" :x="x(tick.number)" :y="H - 6" text-anchor="middle">{{ tick.label }}</text>
        </g>
        <path :d="path('planned_progress')" class="plan" fill="none" />
        <path :d="path('progress')" class="actual" fill="none" />
        <text v-if="lastActual" :x="x(lastActual.number) + 6" :y="y(lastActual.progress) + 4" class="label">{{ pct(lastActual.progress) }}</text>
        <text v-if="lastPlan" :x="x(lastPlan.number) + 6" :y="y(lastPlan.planned_progress) + (labelsClash ? 16 : 4)" class="label muted">{{ pct(lastPlan.planned_progress) }}</text>
        <g v-if="tip">
          <line :x1="x(tip.number)" :x2="x(tip.number)" :y1="PAD.top" :y2="H - PAD.bottom" class="cross" />
          <circle v-if="hasValue(tip.progress)" :cx="x(tip.number)" :cy="y(tip.progress)" r="4" class="dot-actual" />
          <circle v-if="hasValue(tip.planned_progress)" :cx="x(tip.number)" :cy="y(tip.planned_progress)" r="4" class="dot-plan" />
        </g>
      </svg>
      <div v-if="tip" class="pointer-events-none absolute top-1 rounded-md border border-line bg-surface px-2.5 py-1.5 text-xs shadow-pop" :style="{ left: `${Math.min(70, (x(tip.number) / W) * 100)}%` }">
        <p class="m-0 text-ink-muted">{{ formatDate(tip.snapshot_date) }}</p>
        <p class="m-0"><strong>{{ pct(tip.progress) }}</strong> <span class="text-ink-muted">thực tế</span></p>
        <p class="m-0"><strong>{{ pct(tip.planned_progress) }}</strong> <span class="text-ink-muted">kế hoạch</span></p>
      </div>
    </div>
    <div v-else class="max-h-64 overflow-y-auto">
      <table class="w-full text-sm">
        <thead><tr class="text-left text-xs text-ink-muted"><th class="py-1">Ngày</th><th>Thực tế</th><th>Kế hoạch</th></tr></thead>
        <tbody>
          <tr v-for="p in points" :key="p.snapshot_date" class="border-t border-line"><td class="py-1">{{ formatDate(p.snapshot_date) }}</td><td>{{ pct(p.progress) }}</td><td>{{ pct(p.planned_progress) }}</td></tr>
        </tbody>
      </table>
    </div>
  </figure>
</template>

<style scoped>
.s-curve { --series-actual: #2a78d6; --series-plan: #eb6834; }
:global(html[data-theme="dark"]) .s-curve { --series-actual: #3987e5; --series-plan: #d95926; }
.actual { stroke: var(--series-actual); stroke-width: 2; stroke-linejoin: round; stroke-linecap: round; }
.plan { stroke: var(--series-plan); stroke-width: 2; stroke-dasharray: 5 4; stroke-linecap: round; }
.s-gridlines line { stroke: var(--pm-border); stroke-width: 1; }
.axis text, .label { fill: var(--pm-muted); font-size: 11px; }
.label { fill: var(--pm-ink); font-weight: 600; }
.label.muted { fill: var(--pm-ink-soft); }
.cross { stroke: var(--pm-muted); stroke-width: 1; }
.dot-actual { fill: var(--series-actual); stroke: var(--pm-surface); stroke-width: 2; }
.dot-plan { fill: var(--series-plan); stroke: var(--pm-surface); stroke-width: 2; }
</style>
