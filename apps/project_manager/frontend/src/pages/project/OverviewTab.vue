<script setup>
import { computed, inject, ref, watch } from "vue";
import HealthBadge from "../../components/HealthBadge.vue";
import Icon from "../../components/Icon.vue";
import ProgressBar from "../../components/ProgressBar.vue";
import ReasonDialog from "../../components/ReasonDialog.vue";
import SCurve from "../../components/SCurve.vue";
import { api } from "../../lib/api.js";
import { formatDate, formatDateTime } from "../../lib/format.js";
import { slipText, slipTone } from "../../lib/gantt.js";
import { ALERT_OPEN, GATE_MODES, GATE_PASSED, GATE_WAITING, alertBadge, canPassPhase, gateSummary, levelText, spaPath } from "../../lib/health.js";
import { toast } from "../../lib/toast.js";
import { statusBadge, statusLabel, variance } from "../../lib/work.js";

// Tổng quan: health and the current phase, actual against plan, the state of the work, where it is late and why,
// the open alerts, what happened lately.
const { overview, openTask, name, reload } = inject("project");
const data = computed(() => overview.value);
const gap = computed(() => variance(data.value.project.percent_complete, data.value.planned_progress));
const base = computed(() => `/du-an/${encodeURIComponent(name.value)}`);
const schedule = computed(() => data.value.schedule || {});
const gate = computed(() => data.value.gate);
const current = computed(() => gate.value?.current || null);
const alerts = ref([]);
const passing = ref(false);
const busy = ref(false);
const passError = ref("");
const mayAcknowledge = computed(() => Boolean(data.value.can?.["plan.edit"] || data.value.can?.["task.approve"]));

async function loadAlerts() {
  try {
    alerts.value = data.value.alerts_open ? await api.alerts.ofProject(name.value) : [];
  } catch {
    alerts.value = [];  // the rest of the overview matters more
  }
}

async function passPhase(note) {
  busy.value = true;
  passError.value = "";
  try {
    await api.alerts.passPhase(current.value.name, note);
    passing.value = false;
    toast("Đã chuyển giai đoạn");
    reload();
  } catch (e) {
    passError.value = e.message;
  } finally {
    busy.value = false;
  }
}

async function setMode(phase, mode) {
  try {
    await api.wbs.setGateMode(phase.name, mode);
    toast(`${phase.subject}: chuyển giai đoạn ${mode.toLowerCase()}`);
    reload();
  } catch (e) {
    toast(e.message, "error", 7000);
  }
}

async function acknowledge(alert) {
  try {
    const updated = await api.alerts.acknowledge(alert.name);
    alerts.value = alerts.value.map((row) => (row.name === updated.name ? { ...row, ...updated } : row));
    toast("Đã xác nhận cảnh báo");
  } catch (e) {
    toast(e.message, "error", 7000);
  }
}

watch(() => [name.value, data.value?.alerts_open], loadAlerts, { immediate: true });
</script>

<template>
  <div class="grid gap-4 lg:grid-cols-3">
    <section class="card p-4 lg:col-span-3" aria-labelledby="ov-health" data-health-card>
      <div class="grid gap-4 sm:grid-cols-[minmax(160px,auto)_minmax(0,1fr)_auto] sm:gap-x-8">
        <div>
          <h2 id="ov-health" class="m-0 text-sm font-semibold">Sức khỏe dự án</h2>
          <div class="mt-2"><HealthBadge :level="data.health?.level" :reason="data.health?.reason" detailed /></div>
        </div>
        <div v-if="gate" class="min-w-0" data-gate>
          <h2 class="m-0 text-sm font-semibold">
            <template v-if="current">Giai đoạn {{ gate.done + 1 }}/{{ gate.phases }}: {{ current.label }}</template>
            <template v-else>Đã qua cả {{ gate.phases }} giai đoạn</template>
          </h2>
          <p v-if="current" class="m-0 mt-1 text-xs text-ink-muted">Chuyển giai đoạn: {{ current.mode }}<template v-if="current.next"> · tiếp theo: {{ current.next }}</template></p>
          <p class="m-0 mt-1 text-sm" :class="{ 'font-medium': !current?.missing?.length }">{{ gateSummary(current) }}</p>
          <button v-if="canPassPhase(current)" class="btn btn-primary mt-2" type="button" @click="passing = true">
            <Icon name="arrow-left-right" :size="16" /> {{ current.state === GATE_WAITING ? "Duyệt chuyển giai đoạn" : "Chuyển sang giai đoạn sau" }}
          </button>
        </div>
        <div>
          <h2 class="m-0 text-sm font-semibold">Cảnh báo</h2>
          <p class="m-0 mt-2 text-sm"><strong :class="{ 'text-danger': data.alerts_open }">{{ data.alerts_open }}</strong> đang mở</p>
        </div>
      </div>
      <ul v-if="alerts.length" class="m-0 mt-3 list-none divide-y divide-line border-t border-line p-0" aria-label="Cảnh báo đang mở của dự án">
        <li v-for="alert in alerts.slice(0, 8)" :key="alert.name" class="flex flex-wrap items-center gap-2 py-2 text-sm sm:flex-nowrap" data-project-alert>
          <span class="flex shrink-0 gap-1">
            <span :class="alertBadge(alert.state)">{{ alert.state }}</span>
            <span v-if="levelText(alert.level)" class="badge badge-warning">{{ levelText(alert.level) }}</span>
          </span>
          <RouterLink :to="spaPath(alert.link)" class="min-w-0 basis-full text-ink sm:basis-auto sm:flex-1">{{ alert.message }}</RouterLink>
          <button v-if="alert.state === ALERT_OPEN && mayAcknowledge" class="btn btn-ghost ml-auto shrink-0" type="button" @click="acknowledge(alert)">Đã biết</button>
        </li>
      </ul>
    </section>

    <section class="card p-4 lg:col-span-2" aria-labelledby="ov-progress">
      <div class="flex flex-wrap items-baseline justify-between gap-2">
        <h2 id="ov-progress" class="m-0 text-sm font-semibold">Tiến độ dự án</h2>
        <p class="m-0 text-xs text-ink-muted">{{ formatDate(data.project.expected_start_date) || "—" }} → {{ formatDate(data.project.expected_end_date) || "—" }} · {{ data.project.pm_rollup_method }}</p>
      </div>
      <div class="mt-2 flex items-end gap-6">
        <p class="m-0"><span class="text-3xl font-semibold">{{ Math.round(data.project.percent_complete || 0) }}%</span> <span class="text-sm text-ink-muted">thực tế</span></p>
        <p class="m-0 text-sm text-ink-muted">Kế hoạch {{ Math.round(data.planned_progress) }}%
          <strong :class="gap < -5 ? 'text-danger' : 'text-success'">({{ gap >= 0 ? "+" : "" }}{{ gap }} điểm)</strong></p>
      </div>
      <ProgressBar class="mt-3" :value="data.project.percent_complete" :planned="data.planned_progress" />
      <dl class="m-0 mt-3 grid grid-cols-2 gap-2 text-sm sm:grid-cols-4">
        <div><dt class="text-xs text-ink-muted">Dự báo xong</dt><dd class="m-0 font-medium">{{ formatDate(schedule.forecast_end) || "—" }} <span class="block text-xs font-normal" :class="slipTone(schedule.forecast_slip)">{{ slipText(schedule.forecast_slip) }}</span></dd></div>
        <div><dt class="text-xs text-ink-muted">Kế hoạch xong</dt><dd class="m-0 font-medium">{{ formatDate(schedule.plan_end) || "—" }}</dd></div>
        <div><dt class="text-xs text-ink-muted">{{ schedule.baseline_title ? `Baseline: ${schedule.baseline_title}` : "Chưa có baseline" }}</dt><dd class="m-0 font-medium">{{ formatDate(schedule.baseline_end) || "—" }}</dd></div>
        <div><dt class="text-xs text-ink-muted" title="Tiến độ đạt được chia cho tiến độ kế hoạch; dưới 1 là chậm">SPI</dt><dd class="m-0 font-medium" :class="schedule.spi && schedule.spi < 0.95 ? 'text-danger' : ''">{{ schedule.spi ? schedule.spi.toFixed(2) : "—" }}</dd></div>
      </dl>
      <div class="mt-4"><SCurve :points="data.curve" /></div>
    </section>

    <section class="card p-4" aria-labelledby="ov-work">
      <h2 id="ov-work" class="m-0 text-sm font-semibold">Công việc</h2>
      <dl class="mt-3 grid grid-cols-2 gap-3 text-sm">
        <div><dt class="text-ink-muted">Tổng số</dt><dd class="m-0 text-lg font-semibold">{{ data.tasks.total }}</dd></div>
        <div><dt class="text-ink-muted">Đã xong</dt><dd class="m-0 text-lg font-semibold">{{ data.tasks.done }}</dd></div>
        <div><dt class="text-ink-muted">Đang làm</dt><dd class="m-0 text-lg font-semibold">{{ data.tasks.working }}</dd></div>
        <div><dt class="text-ink-muted">Chờ duyệt</dt><dd class="m-0 text-lg font-semibold">{{ data.tasks.review }}</dd></div>
        <div><dt class="flex items-center gap-1 text-ink-muted"><Icon name="alert-triangle" :size="14" class="text-danger" /> Quá hạn</dt><dd class="m-0 text-lg font-semibold text-danger">{{ data.tasks.late }}</dd></div>
        <div><dt class="flex items-center gap-1 text-ink-muted"><Icon name="hourglass" :size="14" /> Hạn trong 7 ngày</dt><dd class="m-0 text-lg font-semibold">{{ data.tasks.soon }}</dd></div>
      </dl>
      <p v-if="data.pending_acceptance" class="mt-3 rounded-md bg-warning-soft px-3 py-2 text-sm">
        {{ data.pending_acceptance }} phân công chưa được nhận.
        <RouterLink :to="`${base}/ai-lam-gi`" class="font-medium underline">Xem ai làm gì</RouterLink>
      </p>
      <p v-if="schedule.conflicts" class="mt-3 rounded-md bg-warning-soft px-3 py-2 text-sm">
        {{ schedule.conflicts }} việc bắt đầu sớm hơn phụ thuộc cho phép.
        <RouterLink :to="`${base}/gantt`" class="font-medium underline">Xem Gantt</RouterLink>
      </p>
      <p v-if="data.forms_waiting" class="mt-3 rounded-md bg-warning-soft px-3 py-2 text-sm">
        {{ data.forms_waiting }} biểu mẫu chờ duyệt.
        <RouterLink :to="`${base}/bieu-mau`" class="font-medium underline">Xem biểu mẫu</RouterLink>
      </p>
      <p v-if="!data.sees_all_tasks" class="mt-3 text-xs text-ink-muted">Bạn chỉ thấy các việc được giao cho mình hoặc đội của mình.</p>
    </section>

    <section v-if="data.phases.length" class="card p-4 lg:col-span-2" aria-labelledby="ov-phases">
      <h2 id="ov-phases" class="m-0 text-sm font-semibold">Giai đoạn</h2>
      <ul class="m-0 mt-3 list-none space-y-3 p-0">
        <li v-for="phase in data.phases" :key="phase.name">
          <button class="w-full text-left" type="button" @click="openTask(phase.name)">
            <div class="flex flex-wrap items-center gap-2 text-sm">
              <span class="text-ink-muted">{{ phase.pm_wbs_code }}</span>
              <span class="font-medium">{{ phase.subject }}</span>
              <span :class="statusBadge(phase.status)">{{ statusLabel(phase.status) }}</span>
              <span v-if="phase.pm_is_overdue" class="badge badge-danger">Quá hạn</span>
              <span v-if="phase.pm_gate_state === GATE_PASSED" class="badge badge-success">Đã chuyển giai đoạn</span>
              <span v-else-if="phase.pm_gate_state === GATE_WAITING" class="badge badge-warning">Chờ duyệt chuyển</span>
              <HealthBadge v-if="phase.pm_health && phase.pm_health !== 'Xanh'" :level="phase.pm_health" short />
              <span class="ml-auto text-xs text-ink-muted">{{ formatDate(phase.exp_start_date) }} → {{ formatDate(phase.exp_end_date) }}</span>
            </div>
            <div class="mt-1 flex items-center gap-3">
              <ProgressBar class="flex-1" :value="phase.progress" :planned="phase.planned_progress" :label="`Tiến độ ${phase.subject}`" />
              <span class="w-24 text-right text-xs">{{ Math.round(phase.progress || 0) }}% / {{ Math.round(phase.planned_progress) }}%</span>
            </div>
          </button>
          <label v-if="data.can['plan.edit'] && phase.is_group && phase.pm_gate_state !== GATE_PASSED" class="mt-1 flex items-center justify-end gap-2 text-xs text-ink-muted">
            Chuyển giai đoạn
            <select class="input w-auto py-1 text-xs" :value="phase.pm_gate_mode || GATE_MODES[0]" :aria-label="`Chuyển giai đoạn ${phase.subject}`"
                    @change="setMode(phase, $event.target.value)">
              <option v-for="mode in GATE_MODES" :key="mode" :value="mode">{{ mode }}</option>
            </select>
          </label>
        </li>
      </ul>
    </section>

    <section class="card p-4" aria-labelledby="ov-delays">
      <h2 id="ov-delays" class="m-0 text-sm font-semibold">Chậm ở đâu</h2>
      <p v-if="!data.delays.length" class="mt-3 text-sm text-ink-muted">Không có việc nào quá hạn.</p>
      <table v-else class="mt-3 w-full text-sm">
        <thead><tr class="text-left text-xs text-ink-muted"><th class="pb-1">Khâu / lý do</th><th class="pb-1 text-right">Việc</th><th class="pb-1 text-right">Ngày trễ</th></tr></thead>
        <tbody>
          <tr v-for="row in data.delays" :key="`${row.source}-${row.reason}`" class="border-t border-line">
            <td class="py-1.5">{{ row.source || "Chưa rõ khâu" }}<span class="block text-xs text-ink-muted">{{ row.reason || "Chưa ghi lý do" }}</span></td>
            <td class="text-right">{{ row.tasks }}</td><td class="text-right">{{ row.days }}</td>
          </tr>
        </tbody>
      </table>
    </section>

    <section class="card p-4 lg:col-span-3" aria-labelledby="ov-recent">
      <h2 id="ov-recent" class="m-0 text-sm font-semibold">Hoạt động gần đây</h2>
      <p v-if="!data.recent.length" class="mt-3 text-sm text-ink-muted">Chưa có hoạt động nào.</p>
      <ul class="m-0 mt-3 list-none space-y-2 p-0">
        <li v-for="entry in data.recent" :key="entry.name" class="text-sm">
          <button v-if="entry.task" class="text-left hover:underline" type="button" @click="openTask(entry.task)">
            <strong>{{ entry.actor_name }}</strong> · <span class="font-medium">{{ entry.task_label }}</span>: {{ entry.content }}
          </button>
          <span v-else><strong>{{ entry.actor_name }}</strong> · {{ entry.content }}</span>
          <span class="ml-1 text-xs text-ink-muted">{{ entry.activity_type }} · {{ formatDateTime(entry.creation) }}</span>
        </li>
      </ul>
    </section>
  </div>

  <ReasonDialog :open="passing" :title="current?.state === GATE_WAITING ? 'Duyệt chuyển giai đoạn' : 'Chuyển giai đoạn'"
                :message="current ? `Chuyển từ ${current.label} sang ${current.next || 'hoàn thành dự án'}.` : ''"
                label="Ghi chú (không bắt buộc)" confirm-text="Chuyển giai đoạn" :required="false" :busy="busy" :error="passError"
                @confirm="passPhase" @cancel="passing = false" />
</template>
