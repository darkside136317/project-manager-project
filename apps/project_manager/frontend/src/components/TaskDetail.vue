<script setup>
import { computed, reactive, ref, watch } from "vue";
import { api } from "../lib/api.js";
import { formatDate, formatDateTime } from "../lib/format.js";
import { toast } from "../lib/toast.js";
import {
  PERSON_ONLY,
  RACI,
  clampProgress,
  clientUuid,
  deadlineText,
  deadlineTone,
  needsDelayReason,
  stateBadge,
  statusBadge,
  statusLabel,
} from "../lib/work.js";
import Icon from "./Icon.vue";
import LinkSelect from "./LinkSelect.vue";
import ReasonDialog from "./ReasonDialog.vue";

// One task in full: where it sits, who holds it (and their answers), the progress form, dates, the timeline.
// Used in a drawer (lists, board, tree) and as the page /pm/cong-viec/:id (links of notifications).
const props = defineProps({ name: { type: String, required: true } });
const emit = defineEmits(["changed"]);

const detail = ref(null);
const loading = ref(false);
const error = ref("");
const busy = ref(false);
const members = ref([]);
const form = reactive({ progress: 0, note: "", delay_reason: "", delay_source: "", delay_note: "", man_days: "" });
const assignForm = reactive({ open: false, raci: RACI.RESPONSIBLE, kind: "user", user: "", team: "", note: "" });
const dates = reactive({ open: false, start: "", end: "", reason: "" });
const dialog = reactive({ open: false, kind: "", target: null, title: "", label: "Lý do", error: "" });

const task = computed(() => detail.value?.task || {});
const can = computed(() => detail.value?.can || {});
const deadline = computed(() => deadlineText(task.value));
const askDelay = computed(() => needsDelayReason(task.value, form.progress));
const pendingMine = computed(() => (detail.value?.assignments || []).filter((row) => row.can_respond));
const liveAssignments = computed(() => (detail.value?.assignments || []).filter((row) => row.is_active && ["Chờ nhận", "Đã nhận"].includes(row.state)));
const pastAssignments = computed(() => (detail.value?.assignments || []).filter((row) => !liveAssignments.value.includes(row)));

async function load() {
  loading.value = true;
  error.value = "";
  try {
    detail.value = await api.tasks.detail(props.name);
    form.progress = clampProgress(task.value.progress);
    form.note = "";
    form.delay_reason = task.value.pm_delay_reason || "";
    form.delay_source = task.value.pm_delay_source || "";
    form.delay_note = "";
    form.man_days = "";
    dates.start = String(task.value.exp_start_date || "").slice(0, 10);  // Task dates are datetimes in ERPNext v16
    dates.end = String(task.value.exp_end_date || "").slice(0, 10);
  } catch (e) {
    error.value = e.message;
  } finally {
    loading.value = false;
  }
}

async function loadMembers() {
  if (members.value.length || !task.value.project) return;
  const result = await api.projects.members(task.value.project);
  const seen = new Set();
  members.value = result.rows.filter((row) => row.current && !seen.has(row.user) && seen.add(row.user));
}

async function run(action, message) {
  busy.value = true;
  try {
    await action();
    if (message) toast(message);
    await load();
    emit("changed", props.name);
    return true;
  } catch (e) {
    toast(e.message, "error", 7000);
    return false;
  } finally {
    busy.value = false;
  }
}

function report() {
  return run(() => api.tasks.report(props.name, {
    progress_value: clampProgress(form.progress),
    note: form.note,
    delay_reason: form.delay_reason,
    delay_source: form.delay_source,
    delay_note: form.delay_note,
    man_days: form.man_days,
    client_uuid: clientUuid(),
  }), "Đã cập nhật tiến độ");
}

const approve = () => run(() => api.tasks.review(props.name, true), "Đã duyệt công việc");
const accept = (row) => run(() => api.tasks.respond(row.name, true), "Đã nhận việc");

function ask(kind, target, title, label = "Lý do") {
  Object.assign(dialog, { open: true, kind, target, title, label, error: "" });
}

async function confirmDialog(reason) {
  const { kind, target } = dialog;
  const actions = {
    decline: () => api.tasks.respond(target.name, false, reason),
    revoke: () => api.tasks.revoke(target.name, reason),
    reject: () => api.tasks.review(props.name, false, reason),
  };
  const done = await run(actions[kind], kind === "reject" ? "Đã trả lại công việc" : "Đã cập nhật phân công");
  if (done) dialog.open = false;
}

async function openAssign() {
  assignForm.open = true;
  await loadMembers();
}

async function assign() {
  const values = { raci: assignForm.raci, note: assignForm.note };
  if (assignForm.kind === "team" && !PERSON_ONLY.has(assignForm.raci)) values.team = assignForm.team;
  else values.user = assignForm.user;
  const done = await run(() => api.tasks.assign(props.name, values), "Đã giao việc");
  if (done) Object.assign(assignForm, { open: false, user: "", team: "", note: "" });
}

async function saveDates() {
  const done = await run(() => api.wbs.update(props.name, { exp_start_date: dates.start, exp_end_date: dates.end }, dates.reason),
    "Đã đổi ngày");
  if (done) Object.assign(dates, { open: false, reason: "" });
}

watch(() => props.name, load, { immediate: true });
</script>

<template>
  <div>
    <p v-if="loading && !detail" class="flex items-center gap-2 text-sm text-ink-muted"><Icon name="loader" spin /> Đang tải...</p>
    <p v-else-if="error" class="rounded-md bg-danger-soft px-3 py-2 text-sm text-danger" role="alert">{{ error }}</p>

    <article v-if="detail" class="space-y-5">
      <header>
        <nav class="mb-1 flex flex-wrap items-center gap-1 text-xs text-ink-muted" aria-label="Vị trí trong dự án">
          <RouterLink v-if="task.project" :to="`/du-an/${encodeURIComponent(task.project)}/cong-viec`" class="hover:underline">{{ task.project_name || task.project }}</RouterLink>
          <template v-for="item in detail.ancestors" :key="item.name">
            <Icon name="chevron-right" :size="12" /><span>{{ item.pm_wbs_code }} {{ item.subject }}</span>
          </template>
        </nav>
        <h2 class="m-0 text-lg font-semibold">
          <span class="mr-1 text-ink-muted">{{ task.pm_wbs_code }}</span>{{ task.subject }}
        </h2>
        <div class="mt-2 flex flex-wrap items-center gap-2 text-sm">
          <span :class="statusBadge(task.status)">{{ statusLabel(task.status) }}</span>
          <span v-if="deadline" :class="deadlineTone(deadline)" class="font-medium">{{ deadline }}</span>
          <span v-if="task.pm_delay_reason" class="badge badge-danger">{{ task.pm_delay_source }} · {{ task.pm_delay_reason }}</span>
          <span v-if="detail.mine" class="badge badge-info">Việc của tôi</span>
        </div>
        <p v-if="task.pm_delay_note" class="m-0 mt-1 text-sm text-ink-soft">Giải thích chậm: {{ task.pm_delay_note }}</p>
      </header>

      <!-- answers the caller owes -->
      <section v-for="row in pendingMine" :key="row.name" class="rounded-lg border border-warning bg-warning-soft p-3 text-sm">
        <p class="m-0">Bạn được giao vai trò <strong>{{ row.raci }}</strong><span v-if="row.note">: {{ row.note }}</span></p>
        <div class="mt-2 flex gap-2">
          <button class="btn btn-primary" type="button" :disabled="busy" @click="accept(row)"><Icon name="thumbs-up" :size="16" /> Nhận việc</button>
          <button class="btn" type="button" :disabled="busy" @click="ask('decline', row, 'Từ chối việc', 'Lý do từ chối')"><Icon name="thumbs-down" :size="16" /> Từ chối</button>
        </div>
      </section>

      <!-- progress -->
      <section aria-labelledby="progress-title">
        <div class="flex items-center justify-between">
          <h3 id="progress-title" class="m-0 text-sm font-semibold">Tiến độ</h3>
          <span class="text-sm font-semibold">{{ Math.round(task.progress || 0) }}%</span>
        </div>
        <div class="mt-2 h-2 overflow-hidden rounded-full bg-surface-muted" role="progressbar" :aria-valuenow="Math.round(task.progress || 0)" aria-valuemin="0" aria-valuemax="100">
          <div class="h-full rounded-full bg-primary" :style="{ width: `${Math.min(100, task.progress || 0)}%` }"></div>
        </div>
        <dl class="mt-3 grid grid-cols-2 gap-x-4 gap-y-1 text-sm">
          <dt class="text-ink-muted">Kế hoạch</dt><dd class="m-0">{{ formatDate(task.exp_start_date) || "—" }} → {{ formatDate(task.exp_end_date) || "—" }}</dd>
          <dt class="text-ink-muted">Thực tế</dt><dd class="m-0">{{ formatDate(task.act_start_date) || "—" }} → {{ formatDate(task.act_end_date) || "—" }}</dd>
          <dt class="text-ink-muted">Chịu trách nhiệm</dt><dd class="m-0">{{ task.accountable_name || "Chưa giao" }}</dd>
          <dt v-if="task.reviewer_name" class="text-ink-muted">Người duyệt</dt><dd v-if="task.reviewer_name" class="m-0">{{ task.reviewer_name }}</dd>
        </dl>

        <div v-if="can.review" class="mt-3 flex flex-wrap gap-2 rounded-lg bg-surface-muted p-3">
          <p class="m-0 w-full text-sm">Công việc đã báo xong, chờ bạn duyệt.</p>
          <button class="btn btn-primary" type="button" :disabled="busy" @click="approve"><Icon name="check" :size="16" /> Duyệt</button>
          <button class="btn" type="button" :disabled="busy" @click="ask('reject', null, 'Trả lại công việc', 'Cần làm thêm gì')"><Icon name="undo" :size="16" /> Trả lại</button>
        </div>

        <form v-if="can.update && !['Completed', 'Cancelled', 'Pending Review'].includes(task.status)" class="mt-3 space-y-3 rounded-lg border border-line p-3" @submit.prevent="report">
          <div>
            <label class="label" for="task-progress">Cập nhật tiến độ: {{ form.progress }}%</label>
            <div class="flex items-center gap-3">
              <input id="task-progress" v-model.number="form.progress" class="flex-1" type="range" min="0" max="100" step="5" />
              <input v-model.number="form.progress" class="input w-20" type="number" min="0" max="100" aria-label="Phần trăm" />
            </div>
          </div>
          <div v-if="askDelay" class="grid gap-3 rounded-md bg-danger-soft p-3 sm:grid-cols-2">
            <p class="m-0 text-sm text-danger sm:col-span-2">Công việc đã quá hạn: chọn lý do chậm và khâu gây chậm.</p>
            <div>
              <label class="label" for="delay-reason">Lý do chậm</label>
              <select id="delay-reason" v-model="form.delay_reason" class="input" required>
                <option value="" disabled>Chọn...</option>
                <option v-for="item in detail.delay_reasons" :key="item" :value="item">{{ item }}</option>
              </select>
            </div>
            <div>
              <label class="label" for="delay-source">Khâu gây chậm</label>
              <select id="delay-source" v-model="form.delay_source" class="input" required>
                <option value="" disabled>Chọn...</option>
                <option v-for="item in detail.delay_sources" :key="item" :value="item">{{ item }}</option>
              </select>
            </div>
            <input v-model="form.delay_note" class="input sm:col-span-2" placeholder="Giải thích thêm (không bắt buộc)" aria-label="Giải thích lý do chậm" />
          </div>
          <div class="grid gap-3 sm:grid-cols-[1fr_120px]">
            <input v-model="form.note" class="input" placeholder="Ghi chú: đã làm được gì, vướng gì" aria-label="Ghi chú" />
            <input v-model="form.man_days" class="input" type="number" min="0" step="0.5" placeholder="Công" aria-label="Số công" />
          </div>
          <div class="flex justify-end">
            <button class="btn btn-primary" type="submit" :disabled="busy"><Icon :name="busy ? 'loader' : 'send'" :size="16" :spin="busy" /> Gửi cập nhật</button>
          </div>
        </form>

        <div v-if="can.dates && !task.is_group" class="mt-3">
          <button v-if="!dates.open" class="btn btn-ghost" type="button" @click="dates.open = true"><Icon name="calendar-clock" :size="16" /> Đổi ngày kế hoạch</button>
          <form v-else class="grid gap-3 rounded-lg border border-line p-3 sm:grid-cols-2" @submit.prevent="saveDates">
            <div><label class="label" for="date-start">Bắt đầu</label><input id="date-start" v-model="dates.start" class="input" type="date" /></div>
            <div><label class="label" for="date-end">Kết thúc</label><input id="date-end" v-model="dates.end" class="input" type="date" /></div>
            <div class="sm:col-span-2">
              <label class="label" for="date-reason">Lý do đổi ngày</label>
              <input id="date-reason" v-model="dates.reason" class="input" placeholder="Bắt buộc khi việc đã giao cho người thực hiện" />
            </div>
            <div class="flex justify-end gap-2 sm:col-span-2">
              <button class="btn" type="button" @click="dates.open = false">Hủy</button>
              <button class="btn btn-primary" type="submit" :disabled="busy">Lưu</button>
            </div>
          </form>
        </div>
      </section>

      <!-- who -->
      <section aria-labelledby="who-title">
        <div class="flex items-center justify-between">
          <h3 id="who-title" class="m-0 text-sm font-semibold">Phân công</h3>
          <button v-if="can.assign && !assignForm.open" class="btn btn-ghost" type="button" @click="openAssign"><Icon name="user-plus" :size="16" /> Giao việc</button>
        </div>
        <form v-if="assignForm.open" class="mt-2 grid gap-3 rounded-lg border border-line p-3 sm:grid-cols-2" @submit.prevent="assign">
          <div>
            <label class="label" for="assign-raci">Vai trò</label>
            <select id="assign-raci" v-model="assignForm.raci" class="input">
              <option v-for="role in detail.raci_roles" :key="role" :value="role">{{ role }}</option>
            </select>
          </div>
          <div>
            <label class="label" for="assign-kind">Giao cho</label>
            <select id="assign-kind" v-model="assignForm.kind" class="input" :disabled="PERSON_ONLY.has(assignForm.raci)">
              <option value="user">Một người</option>
              <option value="team">Một đội / tổ</option>
            </select>
          </div>
          <div class="sm:col-span-2">
            <template v-if="assignForm.kind === 'team' && !PERSON_ONLY.has(assignForm.raci)">
              <label class="label" for="assign-team">Đội</label>
              <LinkSelect v-model="assignForm.team" input-id="assign-team" doctype="PM Team" :filters="{ is_active: 1 }" />
            </template>
            <template v-else>
              <label class="label" for="assign-user">Người</label>
              <select id="assign-user" v-model="assignForm.user" class="input" required>
                <option value="" disabled>Chọn thành viên dự án...</option>
                <option v-for="row in members" :key="row.user" :value="row.user">{{ row.full_name || row.user }} · {{ row.project_role }}</option>
              </select>
            </template>
          </div>
          <input v-model="assignForm.note" class="input sm:col-span-2" placeholder="Lời nhắn (không bắt buộc)" aria-label="Lời nhắn" />
          <div class="flex justify-end gap-2 sm:col-span-2">
            <button class="btn" type="button" @click="assignForm.open = false">Hủy</button>
            <button class="btn btn-primary" type="submit" :disabled="busy">Giao</button>
          </div>
        </form>
        <ul class="m-0 mt-2 list-none space-y-2 p-0">
          <li v-for="row in liveAssignments" :key="row.name" class="flex flex-wrap items-center gap-2 rounded-lg border border-line px-3 py-2 text-sm">
            <span class="font-medium">{{ row.who }}</span>
            <span class="text-ink-muted">{{ row.raci }}</span>
            <span :class="stateBadge(row.state)">{{ row.state }}</span>
            <button v-if="row.can_revoke" class="btn btn-ghost ml-auto !min-h-0 !py-1 text-xs" type="button" @click="ask('revoke', row, 'Thu hồi phân công')">Thu hồi</button>
          </li>
          <li v-if="!liveAssignments.length" class="text-sm text-ink-muted">Chưa giao cho ai.</li>
        </ul>
        <details v-if="pastAssignments.length" class="mt-2 text-sm">
          <summary class="cursor-pointer text-ink-muted">Lịch sử phân công ({{ pastAssignments.length }})</summary>
          <ul class="m-0 mt-2 list-none space-y-1 p-0">
            <li v-for="row in pastAssignments" :key="row.name" class="text-ink-muted">
              {{ row.who }} · {{ row.raci }} · <span :class="stateBadge(row.state)">{{ row.state }}</span>
              <span v-if="row.decline_reason || row.end_reason">: {{ row.decline_reason || row.end_reason }}</span>
            </li>
          </ul>
        </details>
      </section>

      <!-- timeline -->
      <section aria-labelledby="timeline-title">
        <h3 id="timeline-title" class="m-0 text-sm font-semibold">Lịch sử</h3>
        <ol class="m-0 mt-2 list-none space-y-3 border-l border-line p-0 pl-4">
          <li v-for="entry in detail.timeline" :key="entry.name" class="text-sm">
            <p class="m-0"><strong>{{ entry.actor_name }}</strong> <span class="text-ink-muted">· {{ entry.activity_type }} · {{ formatDateTime(entry.creation) }}</span></p>
            <p class="m-0 whitespace-pre-line text-ink-soft">{{ entry.content }}</p>
          </li>
          <li v-if="!detail.timeline.length" class="text-sm text-ink-muted">Chưa có hoạt động nào.</li>
        </ol>
      </section>
    </article>

    <ReasonDialog :open="dialog.open" :title="dialog.title" :label="dialog.label" :busy="busy" :error="dialog.error"
      @confirm="confirmDialog" @cancel="dialog.open = false" />
  </div>
</template>
