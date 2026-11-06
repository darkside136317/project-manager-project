<script setup>
import { computed, inject, onBeforeUnmount, onMounted, reactive, ref, watch } from "vue";
import EmptyState from "../../components/EmptyState.vue";
import GanttChart from "../../components/gantt/GanttChart.vue";
import MovePreview from "../../components/gantt/MovePreview.vue";
import Icon from "../../components/Icon.vue";
import { api } from "../../lib/api.js";
import { formatDate } from "../../lib/format.js";
import { ZOOMS, collapsedBeyond, criticalOnly, dayRange, linksFrom, slipText, slipTone, tasksFrom, visibleRows } from "../../lib/gantt.js";
import { toast } from "../../lib/toast.js";

// Gantt of a project: on a computer the bars can be dragged, and a preview from the server shows what else that moves;
// on a phone it is for reading, showing three levels at first. The tree of the Công việc tab holds the same data as text.
const { name: project, openTask, version, reload } = inject("project");
const PHONE = 768;
const data = ref(null);
const tasks = ref([]);
const links = ref([]);
const loading = ref(false);
const error = ref("");
const zoom = ref("week");
const baseline = ref("");
const onlyCritical = ref(false);
const collapsed = ref(new Set());
const phone = ref(window.innerWidth < PHONE);
const preview = reactive({ plan: null, title: "", apply: null, busy: false, error: "" });
const chart = ref(null);
let first = true;

const shownTasks = computed(() => (onlyCritical.value ? criticalOnly(tasks.value) : tasks.value));
const rows = computed(() => visibleRows(shownTasks.value, collapsed.value));
const span = computed(() => dayRange(tasks.value, data.value?.today));
const summary = computed(() => data.value?.summary || {});
const editable = computed(() => Boolean(data.value?.can?.dates) && !phone.value && !data.value?.flat);
const canLink = computed(() => Boolean(data.value?.can?.plan) && !phone.value && !data.value?.flat);
const chartLabel = computed(() => `Biểu đồ Gantt: ${rows.value.length} việc đang hiện, ${summary.value.critical || 0} việc trên đường găng. Cùng dữ liệu ở dạng chữ nằm trong mục Công việc.`);

async function load() {
  loading.value = true;
  error.value = "";
  try {
    const payload = await api.schedule.gantt(project.value, baseline.value || null);
    data.value = payload;
    tasks.value = tasksFrom(payload);
    links.value = linksFrom(payload);
    baseline.value = payload.baseline || "";
    if (first) {
      first = false;
      if (phone.value) collapsed.value = collapsedBeyond(tasks.value, 3);
      else if (tasks.value.length > 400) collapsed.value = collapsedBeyond(tasks.value, 2);
    }
  } catch (e) {
    error.value = e.message;
  } finally {
    loading.value = false;
  }
}

function toggle(name) {
  const next = new Set(collapsed.value);
  if (next.has(name)) next.delete(name);
  else next.add(name);
  collapsed.value = next;
}

const expandAll = () => { collapsed.value = new Set(); };
const collapseAll = () => { collapsed.value = collapsedBeyond(tasks.value, 1); };

function closePreview() {
  Object.assign(preview, { plan: null, apply: null, busy: false, error: "" });
  chart.value?.redraw();
}

async function onChange({ task, start, end, zone }) {
  // moving a whole bar keeps its working days, whatever days off it now crosses: only the new start is sent
  const last = zone === "move" ? null : end;
  try {
    const plan = await api.schedule.previewMove(task.name, start, last);
    Object.assign(preview, { plan, title: `Dời lịch: ${task.subject}`, error: "", busy: false,
      apply: (reason) => api.schedule.applyMove(task.name, start, last, reason) });
  } catch (e) {
    toast(e.message, "error", 8000);
    chart.value?.redraw();
  }
}

async function fixConflicts() {
  try {
    const plan = await api.schedule.previewConflicts(project.value);
    Object.assign(preview, { plan, title: "Sửa các xung đột với phụ thuộc", error: "", busy: false,
      apply: (reason) => api.schedule.applyConflicts(project.value, reason) });
  } catch (e) {
    toast(e.message, "error", 8000);
  }
}

async function confirmPreview(reason) {
  preview.busy = true;
  preview.error = "";
  try {
    const result = await preview.apply(reason);
    toast(`Đã dời ${result.total} việc`);
    closePreview();
    reload();  // the page asks its tab to load again
  } catch (e) {
    preview.error = e.message;
    preview.busy = false;
  }
}

async function onLink({ from, to }) {
  try {
    await api.schedule.addDependency(from, to);
    toast("Đã thêm phụ thuộc");
    reload();
  } catch (e) {
    toast(e.message, "error", 8000);
    chart.value?.redraw();
  }
}

function onResize() {
  phone.value = window.innerWidth < PHONE;
}

watch(baseline, (value, old) => {
  if (old !== "" && value !== (data.value?.baseline || "")) load();
});
watch(version, load);
onMounted(() => {
  load();
  window.addEventListener("resize", onResize);
});
onBeforeUnmount(() => window.removeEventListener("resize", onResize));
</script>

<template>
  <p v-if="error" class="rounded-md bg-danger-soft px-3 py-2 text-sm text-danger" role="alert">{{ error }}</p>
  <template v-else-if="data">
    <dl class="m-0 mb-3 grid grid-cols-2 gap-3 text-sm sm:grid-cols-4">
      <div class="card px-3 py-2"><dt class="text-xs text-ink-muted">Kế hoạch xong</dt><dd class="m-0 font-semibold">{{ formatDate(summary.plan_end) || "—" }}</dd></div>
      <div class="card px-3 py-2"><dt class="text-xs text-ink-muted">Dự báo xong</dt><dd class="m-0 font-semibold">{{ formatDate(summary.forecast_end) || "—" }} <span class="text-xs font-normal" :class="slipTone(summary.forecast_slip)">{{ slipText(summary.forecast_slip) }}</span></dd></div>
      <div class="card px-3 py-2"><dt class="text-xs text-ink-muted">{{ summary.baseline_title ? `Baseline: ${summary.baseline_title}` : "Hạn của dự án" }}</dt><dd class="m-0 font-semibold">{{ formatDate(summary.baseline_end || summary.contract_end) || "—" }}</dd></div>
      <div class="card px-3 py-2"><dt class="text-xs text-ink-muted">Đường găng</dt><dd class="m-0 font-semibold text-danger">{{ summary.critical }} việc</dd></div>
    </dl>

    <div class="mb-3 flex flex-wrap items-center gap-2 text-sm">
      <div class="flex rounded-lg border border-line p-0.5" role="group" aria-label="Thu phóng">
        <button v-for="(item, key) in ZOOMS" :key="key" class="btn btn-ghost !min-h-0 !py-1" :class="{ 'bg-surface-muted': zoom === key }" type="button" :aria-pressed="zoom === key" @click="zoom = key">{{ item.label }}</button>
      </div>
      <select v-if="data.baselines.length" v-model="baseline" class="input w-auto" aria-label="So với baseline">
        <option v-for="item in data.baselines" :key="item.name" :value="item.name">So với: {{ item.title }}</option>
      </select>
      <label class="flex items-center gap-1"><input v-model="onlyCritical" type="checkbox" /> Chỉ đường găng</label>
      <button class="btn btn-ghost !min-h-0 !py-1" type="button" @click="expandAll">Mở hết</button>
      <button class="btn btn-ghost !min-h-0 !py-1" type="button" @click="collapseAll">Thu gọn</button>
      <button class="btn btn-ghost !min-h-0 !py-1" type="button" @click="chart?.goToToday()">Hôm nay</button>
      <button v-if="summary.conflicts && data.can.dates" class="btn !min-h-0 !py-1" type="button" @click="fixConflicts"><Icon name="alert-triangle" :size="14" class="text-warning" /> Sửa {{ summary.conflicts }} xung đột</button>
      <Icon v-if="loading" name="loader" spin class="text-ink-muted" />
    </div>

    <p v-if="data.flat" class="mb-2 text-sm text-ink-muted">Bạn chỉ thấy các việc được giao cho mình hoặc đội của mình.</p>
    <p v-else-if="phone" class="mb-2 text-xs text-ink-muted">Trên điện thoại Gantt chỉ để xem; mở trên máy tính để kéo đổi ngày.</p>
    <p v-else-if="!summary.links && data.can.plan" class="mb-2 text-xs text-ink-muted">Chưa có phụ thuộc nào nên chưa có đường găng thật. Kéo từ chấm tròn sau một thanh sang thanh khác để nối hai việc.</p>
    <p v-if="data.more" class="mb-2 text-sm text-warning">Dự án quá lớn: chỉ hiện 20.000 việc đầu tiên.</p>

    <EmptyState v-if="!tasks.length" icon="chart-bar" title="Chưa có công việc nào" text="Thêm công việc trong mục Công việc." />
    <div v-else class="gantt-frame">
      <GanttChart ref="chart" :rows="rows" :links="links" :span="span" :days-off="data.days_off" :today="data.today" :zoom="zoom" :editable="editable" :can-link="canLink"
        :collapsed="collapsed" :grid-width="phone ? 130 : 300" :label="chartLabel" @open="openTask" @toggle="toggle" @change="onChange" @link="onLink" />
    </div>

    <ul class="m-0 mt-2 flex list-none flex-wrap gap-x-4 gap-y-1 p-0 text-xs text-ink-muted" aria-label="Chú giải">
      <li class="flex items-center gap-1.5"><span class="legend-bar" style="background: var(--pm-primary)"></span> Tiến độ</li>
      <li class="flex items-center gap-1.5"><span class="legend-bar" style="background: var(--pm-danger)"></span> Đường găng</li>
      <li class="flex items-center gap-1.5"><span class="legend-bar" style="background: var(--pm-success)"></span> Xong</li>
      <li class="flex items-center gap-1.5"><span class="legend-thin" style="background: var(--pm-muted)"></span> Baseline</li>
      <li class="flex items-center gap-1.5"><span class="legend-dash"></span> Dự báo trễ</li>
      <li class="flex items-center gap-1.5"><span class="legend-today"></span> Hôm nay</li>
    </ul>

    <MovePreview :plan="preview.plan" :title="preview.title" :busy="preview.busy" :error="preview.error" @confirm="confirmPreview" @cancel="closePreview" />
  </template>
  <p v-else class="flex items-center gap-2 text-sm text-ink-muted"><Icon name="loader" spin /> Đang tải...</p>
</template>

<style scoped>
.gantt-frame { height: calc(100vh - 340px); min-height: 420px; }
.legend-bar { display: inline-block; width: 18px; height: 8px; border-radius: 2px; }
.legend-thin { display: inline-block; width: 18px; height: 3px; opacity: 0.65; }
.legend-dash { display: inline-block; width: 18px; border-top: 2px dashed var(--pm-warning); }
.legend-today { display: inline-block; width: 2px; height: 12px; background: var(--pm-warning); }
</style>
