<script setup>
import { computed, ref } from "vue";
import { formatDate } from "../lib/format.js";

// Đường cong S: actual progress against plan over time (daily snapshots), one axis 0-100 %.
// Two series: actual (solid, slot 1) and plan (dashed, slot 2); legend + direct labels at the last point,
// a crosshair tooltip that lists both values, and a table for readers who cannot use the chart.
const props = defineProps({ points: { type: Array, default: () => [] } });

const W = 640;
const H = 220;
const PAD = { left: 36, right: 64, top: 12, bottom: 26 };
const hover = ref(-1);
const showTable = ref(false);

const n = computed(() => props.points.length);
const x = (i) => PAD.left + (n.value <= 1 ? 0 : (i * (W - PAD.left - PAD.right)) / (n.value - 1));
const y = (v) => PAD.top + (1 - Math.min(100, Math.max(0, Number(v) || 0)) / 100) * (H - PAD.top - PAD.bottom);
const path = (key) => props.points.map((p, i) => `${i ? "L" : "M"}${x(i).toFixed(1)},${y(p[key]).toFixed(1)}`).join(" ");
const last = computed(() => props.points[n.value - 1] || null);
const ticks = [0, 25, 50, 75, 100];
const dateTicks = computed(() => {
  if (!n.value) return [];
  const step = Math.max(1, Math.ceil(n.value / 5));
  const out = [];
  for (let i = 0; i < n.value; i += step) out.push(i);
  if (out[out.length - 1] !== n.value - 1) out.push(n.value - 1);
  return out;
});

function onMove(event) {
  const box = event.currentTarget.getBoundingClientRect();
  const px = ((event.clientX - box.left) / box.width) * W;
  const span = (W - PAD.left - PAD.right) / Math.max(1, n.value - 1);
  hover.value = Math.min(n.value - 1, Math.max(0, Math.round((px - PAD.left) / span)));
}
const tip = computed(() => (hover.value >= 0 ? props.points[hover.value] : null));
const pct = (v) => `${Math.round(Number(v) || 0)}%`;
</script>

<template>
  <figure class="m-0 s-curve">
    <div class="mb-2 flex flex-wrap items-center gap-4 text-xs text-ink-soft">
      <span class="flex items-center gap-1.5"><svg width="18" height="6" aria-hidden="true"><line x1="0" y1="3" x2="18" y2="3" class="actual" /></svg> Thực tế</span>
      <span class="flex items-center gap-1.5"><svg width="18" height="6" aria-hidden="true"><line x1="0" y1="3" x2="18" y2="3" class="plan" /></svg> Kế hoạch</span>
      <button class="ml-auto text-xs text-ink-muted underline" type="button" @click="showTable = !showTable">{{ showTable ? "Xem biểu đồ" : "Xem bảng số liệu" }}</button>
    </div>
    <p v-if="!n" class="m-0 py-8 text-center text-sm text-ink-muted">Chưa có số liệu: tiến độ được ghi lại mỗi ngày từ hôm nay.</p>
    <div v-else-if="!showTable" class="relative">
      <svg :viewBox="`0 0 ${W} ${H}`" class="block h-auto w-full" role="img" :aria-label="`Đường cong S: thực tế ${pct(last.progress)}, kế hoạch ${pct(last.planned_progress)}`"
        @pointermove="onMove" @pointerleave="hover = -1">
        <g class="grid">
          <line v-for="t in ticks" :key="t" :x1="PAD.left" :x2="W - PAD.right" :y1="y(t)" :y2="y(t)" />
        </g>
        <g class="axis">
          <text v-for="t in ticks" :key="`l${t}`" :x="PAD.left - 6" :y="y(t) + 4" text-anchor="end">{{ t }}%</text>
          <text v-for="i in dateTicks" :key="`d${i}`" :x="x(i)" :y="H - 6" text-anchor="middle">{{ formatDate(points[i].snapshot_date).slice(0, 5) }}</text>
        </g>
        <path :d="path('planned_progress')" class="plan" fill="none" />
        <path :d="path('progress')" class="actual" fill="none" />
        <text :x="x(n - 1) + 6" :y="y(last.progress) + 4" class="label">{{ pct(last.progress) }}</text>
        <text :x="x(n - 1) + 6" :y="y(last.planned_progress) + (Math.abs(y(last.progress) - y(last.planned_progress)) < 12 ? 16 : 4)" class="label muted">{{ pct(last.planned_progress) }}</text>
        <g v-if="tip">
          <line :x1="x(hover)" :x2="x(hover)" :y1="PAD.top" :y2="H - PAD.bottom" class="cross" />
          <circle :cx="x(hover)" :cy="y(tip.progress)" r="4" class="dot-actual" />
          <circle :cx="x(hover)" :cy="y(tip.planned_progress)" r="4" class="dot-plan" />
        </g>
      </svg>
      <div v-if="tip" class="pointer-events-none absolute top-1 rounded-md border border-line bg-surface px-2.5 py-1.5 text-xs shadow-pop"
        :style="{ left: `${Math.min(70, (x(hover) / W) * 100)}%` }">
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
.grid line { stroke: var(--pm-border); stroke-width: 1; }
.axis text, .label { fill: var(--pm-muted); font-size: 11px; }
.label { fill: var(--pm-ink); font-weight: 600; }
.label.muted { fill: var(--pm-ink-soft); }
.cross { stroke: var(--pm-muted); stroke-width: 1; }
.dot-actual { fill: var(--series-actual); stroke: var(--pm-surface); stroke-width: 2; }
.dot-plan { fill: var(--series-plan); stroke: var(--pm-surface); stroke-width: 2; }
</style>
