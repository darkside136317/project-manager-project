<script setup>
import { computed, inject, onMounted, reactive, ref } from "vue";
import Drawer from "../../components/Drawer.vue";
import EmptyState from "../../components/EmptyState.vue";
import Icon from "../../components/Icon.vue";
import LinkSelect from "../../components/LinkSelect.vue";
import ReasonDialog from "../../components/ReasonDialog.vue";
import { api } from "../../lib/api.js";
import { CHANGE_REASONS, money, stateBadge } from "../../lib/control.js";
import { formatDate, formatDateTime } from "../../lib/format.js";
import { toast } from "../../lib/toast.js";

// Phát sinh: change requests of the project, from the draft to the decision. Approved, the cost goes into the budget
// in use and the listed tasks move to their new end (with what depends on them). The author cannot decide.
const { name: project, reload } = inject("project");
const data = ref(null);
const error = ref("");
const busy = ref(false);
const form = reactive({ open: false, name: null, values: {}, tasks: [] });
const deciding = ref(null);  // {row, approve}
const dialogError = ref("");

const can = computed(() => data.value?.can || {});
const changes = computed(() => data.value?.changes || []);
const waiting = computed(() => changes.value.filter((c) => c.status === "Chờ duyệt").length);
const searchTasks = (txt) => api.schedule.searchTasks(project.value, txt);

async function load() {
  error.value = "";
  try {
    data.value = await api.control.register(project.value);
  } catch (e) {
    error.value = e.message;
  }
}

function edit(row = null) {
  Object.assign(form, { open: true, name: row?.name || null,
    values: row ? { title: row.title, reason: row.reason, description: row.description || "", cost_impact: row.cost_impact || "", days_impact: row.days_impact || "" }
      : { title: "", reason: CHANGE_REASONS[0], description: "", cost_impact: "", days_impact: "" },
    tasks: (row?.tasks || []).map((t) => ({ task: t.task, task_label: t.task_label, new_end: t.new_end || "", note: t.note || "" })) });
}

async function act(action, message) {
  busy.value = true;
  try {
    const result = await action();
    toast(message);
    await load();
    return result || true;
  } catch (e) {
    toast(e.message, "error", 8000);
    return false;
  } finally {
    busy.value = false;
  }
}

async function save(submit = false) {
  const values = { ...form.values, cost_impact: Number(form.values.cost_impact) || 0, days_impact: Number(form.values.days_impact) || 0 };
  const tasks = form.tasks.filter((t) => t.task).map((t) => ({ task: t.task, new_end: t.new_end || null, note: t.note }));
  const saved = await act(() => api.control.saveChange(project.value, values, tasks, form.name), "Đã lưu phát sinh");
  if (!saved) return;
  form.open = false;
  if (submit) await act(() => api.control.submitChange(saved.name), "Đã gửi duyệt phát sinh");
}

async function decide(note) {
  dialogError.value = "";
  const { row, approve } = deciding.value;
  busy.value = true;
  try {
    const result = await api.control.decideChange(row.name, approve, note);
    toast(approve ? `Đã duyệt${result.moved.length ? `, dời ${result.moved.length} công việc` : ""}${result.budget ? ", cộng vào ngân sách" : ""}` : "Đã từ chối phát sinh");
    deciding.value = null;
    await load();
    if (approve) reload();
  } catch (e) {
    dialogError.value = e.message;
  } finally {
    busy.value = false;
  }
}

onMounted(load);
</script>

<template>
  <EmptyState v-if="error" icon="git-pull-request" title="Không xem được phát sinh" :text="error" />
  <div v-else-if="data" class="space-y-4" data-changes>
    <div class="flex flex-wrap items-center gap-2">
      <p class="m-0 flex-1 text-sm text-ink-muted">{{ changes.length }} phát sinh<template v-if="waiting"> · <strong class="text-warning">{{ waiting }} chờ duyệt</strong></template>
        · đã duyệt {{ money(data.summary.changes_approved_cost) }}</p>
      <button v-if="can.request" class="btn btn-primary" type="button" @click="edit()"><Icon name="plus" :size="16" /> Lập phát sinh</button>
    </div>
    <EmptyState v-if="!changes.length" icon="git-pull-request" title="Chưa có phát sinh" text="Thay đổi phạm vi, chi phí, thời gian được lập ở đây rồi gửi duyệt." />
    <article v-for="row in changes" :key="row.name" class="card p-4" data-change>
      <div class="flex flex-wrap items-start gap-2">
        <div class="min-w-0 flex-1">
          <h3 class="m-0 text-sm font-semibold">{{ row.title }} <span class="text-xs font-normal text-ink-muted">{{ row.name }} · {{ row.reason }}</span></h3>
          <p v-if="row.description" class="m-0 mt-1 text-sm">{{ row.description }}</p>
        </div>
        <span :class="stateBadge(row.status)">{{ row.status }}</span>
      </div>
      <p class="m-0 mt-2 text-sm">Chi phí <strong class="tabular-nums">{{ money(row.cost_impact) }}</strong> · tiến độ <strong>{{ row.days_impact || 0 }}</strong> ngày
        <template v-if="row.budget"> · đã cộng vào <span class="badge badge-info">{{ row.budget }}</span></template></p>
      <ul v-if="row.tasks.length" class="m-0 mt-2 list-none space-y-1 p-0 text-xs text-ink-muted">
        <li v-for="t in row.tasks" :key="t.task">{{ t.task_label }}: kết thúc {{ formatDate(t.old_end) || "—" }} → <strong class="text-ink">{{ formatDate(t.new_end) || "giữ nguyên" }}</strong><template v-if="t.note"> · {{ t.note }}</template></li>
      </ul>
      <p class="m-0 mt-2 text-xs text-ink-muted">Đề nghị: {{ row.requested_name || row.requested_by }}<template v-if="row.submitted_on">, gửi {{ formatDateTime(row.submitted_on) }}</template>
        <template v-if="row.decided_by"> · {{ row.status === "Đã duyệt" ? "Duyệt" : "Quyết định" }}: {{ row.decided_name || row.decided_by }} {{ formatDateTime(row.decided_on) }}<template v-if="row.decision_note"> ({{ row.decision_note }})</template></template></p>
      <div v-if="row.can.edit || row.can.decide || row.can.cancel" class="mt-3 flex flex-wrap gap-2">
        <button v-if="row.can.edit" class="btn" type="button" @click="edit(row)"><Icon name="pencil" :size="16" /> Sửa</button>
        <button v-if="row.can.edit" class="btn" type="button" :disabled="busy" @click="act(() => api.control.submitChange(row.name), 'Đã gửi duyệt phát sinh')"><Icon name="send" :size="16" /> Gửi duyệt</button>
        <button v-if="row.can.decide" class="btn btn-primary" type="button" @click="deciding = { row, approve: true }"><Icon name="check" :size="16" /> Duyệt</button>
        <button v-if="row.can.decide" class="btn" type="button" @click="deciding = { row, approve: false }">Từ chối</button>
        <button v-if="row.can.cancel" class="btn btn-ghost" type="button" :disabled="busy" @click="act(() => api.control.cancelChange(row.name), 'Đã hủy phát sinh')">Hủy</button>
      </div>
    </article>
  </div>

  <Drawer :open="form.open" :title="form.name ? `Phát sinh ${form.name}` : 'Lập phát sinh'" width="560px" @close="form.open = false">
    <form id="change-form" class="space-y-3" @submit.prevent="save(false)">
      <div><label class="label" for="change-title">Nội dung phát sinh</label><input id="change-title" v-model="form.values.title" class="input" required /></div>
      <div><label class="label" for="change-reason">Nguyên nhân</label><select id="change-reason" v-model="form.values.reason" class="input"><option v-for="r in CHANGE_REASONS" :key="r">{{ r }}</option></select></div>
      <div><label class="label" for="change-description">Mô tả</label><textarea id="change-description" v-model="form.values.description" class="input" rows="3"></textarea></div>
      <div class="grid grid-cols-2 gap-2">
        <div><label class="label" for="change-cost">Chi phí phát sinh</label><input id="change-cost" v-model="form.values.cost_impact" class="input text-right" inputmode="numeric" /></div>
        <div><label class="label" for="change-days">Ảnh hưởng tiến độ (ngày)</label><input id="change-days" v-model="form.values.days_impact" class="input text-right" inputmode="numeric" /></div>
      </div>
      <fieldset class="space-y-2 rounded-md border border-line p-2">
        <legend class="px-1 text-xs font-semibold text-ink-muted">Công việc dời ngày khi được duyệt</legend>
        <div v-for="(row, index) in form.tasks" :key="index" class="grid gap-2 sm:grid-cols-[1fr_9rem_auto]" data-change-task>
          <LinkSelect v-model="row.task" doctype="Task" :searcher="searchTasks" :placeholder="row.task_label || 'Chọn công việc'" />
          <input v-model="row.new_end" class="input" type="date" :aria-label="`Kết thúc mới dòng ${index + 1}`" />
          <button class="btn btn-ghost btn-icon" type="button" :aria-label="`Bỏ dòng ${index + 1}`" @click="form.tasks.splice(index, 1)"><Icon name="trash-2" :size="16" /></button>
        </div>
        <button class="btn btn-ghost" type="button" @click="form.tasks.push({ task: '', task_label: '', new_end: '', note: '' })"><Icon name="plus" :size="16" /> Thêm công việc</button>
      </fieldset>
    </form>
    <template #footer>
      <button class="btn" type="button" @click="form.open = false">Hủy</button>
      <button class="btn" type="submit" form="change-form" :disabled="busy">Lưu nháp</button>
      <button class="btn btn-primary" type="button" :disabled="busy || !form.values.title" @click="save(true)">Lưu và gửi duyệt</button>
    </template>
  </Drawer>

  <ReasonDialog :open="Boolean(deciding)" :title="deciding?.approve ? 'Duyệt phát sinh' : 'Từ chối phát sinh'"
                :message="deciding ? `${deciding.row.title}: ${money(deciding.row.cost_impact)}${deciding.approve ? ' sẽ cộng vào ngân sách đang dùng' : ''}` : ''"
                :label="deciding?.approve ? 'Ý kiến (không bắt buộc)' : 'Lý do từ chối'" :required="!deciding?.approve"
                :confirm-text="deciding?.approve ? 'Duyệt' : 'Từ chối'" :danger="!deciding?.approve" :busy="busy" :error="dialogError"
                @confirm="decide" @cancel="deciding = null" />
</template>
