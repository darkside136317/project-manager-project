<script setup>
import { defineAsyncComponent, nextTick, onMounted, ref, shallowRef } from "vue";
import { makePlan } from "./data.js";

// /?lib=svar|dhtmlx|frappe|canvas&n=5000 — renders the plan with one candidate, then measures:
//   render   time from the start of the mount to two painted frames after it
//   scroll   average frame time while the chart is scrolled down 120 steps (lower = smoother; 16.7 ms = 60 fps)
const params = new URLSearchParams(location.search);
const lib = params.get("lib") || "canvas";
const count = Number(params.get("n") || 5000);
const views = {
  svar: () => import("./SvarView.vue"),
  dhtmlx: () => import("./DhtmlxView.vue"),
  frappe: () => import("./FrappeView.vue"),
  canvas: () => import("./CanvasView.vue"),
};
const view = shallowRef(null);
const plan = makePlan(count);
const result = ref(null);
const host = ref(null);

const frames = () => new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve)));

function scrollTarget() {
  const candidates = [...host.value.querySelectorAll("*")].filter((el) => el.scrollHeight > el.clientHeight + 50
    && ["auto", "scroll"].includes(getComputedStyle(el).overflowY));
  return candidates.sort((a, b) => b.scrollHeight - a.scrollHeight)[0] || null;
}

async function scrollTest() {
  const target = scrollTarget();
  if (!target) return null;
  const times = [];
  let last = performance.now();
  for (let i = 0; i < 120; i++) {
    target.scrollTop += 60;
    target.dispatchEvent(new Event("scroll"));
    await new Promise((resolve) => requestAnimationFrame(resolve));
    const now = performance.now();
    times.push(now - last);
    last = now;
  }
  times.sort((a, b) => a - b);
  return { average: times.reduce((s, t) => s + t, 0) / times.length, p95: times[Math.floor(times.length * 0.95)] };
}

onMounted(async () => {
  const component = (await views[lib]()).default;
  const started = performance.now();
  view.value = component;
  await nextTick();
  await frames();
  const render = performance.now() - started;
  const domNodes = host.value.querySelectorAll("*").length;
  await new Promise((resolve) => setTimeout(resolve, 300));
  const scroll = await scrollTest();
  result.value = { lib, count: plan.tasks.length, links: plan.links.length, render: Math.round(render), domNodes,
    scrollAvg: scroll ? Number(scroll.average.toFixed(1)) : null, scrollP95: scroll ? Number(scroll.p95.toFixed(1)) : null,
    heapMb: performance.memory ? Math.round(performance.memory.usedJSHeapSize / 1048576) : null };
  window.__spike = result.value;
});
</script>

<template>
  <div class="page">
    <header>
      <strong>Spike Gantt</strong> — {{ lib }} · {{ count }} công việc
      <span v-if="result"> · vẽ {{ result.render }} ms · cuộn TB {{ result.scrollAvg }} ms/khung (p95 {{ result.scrollP95 }}) · {{ result.domNodes }} nút DOM</span>
      <span v-else> · đang đo…</span>
    </header>
    <div ref="host" class="chart"><component :is="view" v-if="view" :plan="plan" /></div>
  </div>
</template>

<style>
html, body, #app { height: 100%; margin: 0; font-family: system-ui, sans-serif; }
.page { display: flex; flex-direction: column; height: 100%; }
header { padding: 8px 12px; font-size: 13px; border-bottom: 1px solid #ddd; }
.chart { flex: 1; min-height: 0; position: relative; }
</style>
