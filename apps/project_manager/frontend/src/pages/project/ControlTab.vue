<script setup>
import { computed, inject, onMounted, reactive, ref } from "vue";
import Drawer from "../../components/Drawer.vue";
import EmptyState from "../../components/EmptyState.vue";
import Icon from "../../components/Icon.vue";
import LinkSelect from "../../components/LinkSelect.vue";
import ReasonDialog from "../../components/ReasonDialog.vue";
import { api } from "../../lib/api.js";
import { ISSUE_STATES, PRIORITIES, RESPONSES, RISK_CATEGORIES, RISK_STATES, cellTone, levelBadge, matrix, priorityBadge, riskScore,
  stateBadge } from "../../lib/control.js";
import { formatDate } from "../../lib/format.js";
import { toast } from "../../lib/toast.js";

// Rủi ro, vấn đề: the 5 × 5 matrix of the open risks, the risk register (who handles each, how, by when), and the
// issues to solve. A risk that happened becomes an issue. Seen by those who see the whole project.
const { name: project, openTask } = inject("project");
const data = ref(null);
const members = ref([]);
const error = ref("");
const busy = ref(false);
const showClosed = ref(false);
const risk = reactive({ open: false, name: null, values: {} });
const issue = reactive({ open: false, name: null, values: {} });
const happening = ref(null);

const can = computed(() => data.value?.can || {});
const grid = computed(() => matrix(data.value?.risks));
const open = (row, states) => states.slice(0, 2).includes(row.status);
const risks = computed(() => (data.value?.risks || []).filter((r) => showClosed.value || open(r, RISK_STATES)));
const issues = computed(() => (data.value?.issues || []).filter((i) => showClosed.value || open(i, ISSUE_STATES)));
const preview = computed(() => riskScore(risk.values.probability, risk.values.impact));
const searchTasks = (txt) => api.schedule.searchTasks(project.value, txt);

async function load() {
  error.value = "";
  try {
    data.value = await api.control.register(project.value);
    if (!members.value.length) members.value = (await api.projects.members(project.value)).rows.filter((m) => m.current);
  } catch (e) {
    error.value = e.message;
  }
}

function editRisk(row = null) {
  Object.assign(risk, { open: true, name: row?.name || null, values: row ? { ...row } : { title: "", category: RISK_CATEGORIES[0], probability: 3,
    impact: 3, response: RESPONSES[0], status: "Mở", owner_user: "", task: "", plan: "", description: "", due_date: "" } });
}
function editIssue(row = null) {
  Object.assign(issue, { open: true, name: row?.name || null, values: row ? { ...row } : { title: "", priority: "Trung bình", status: "Mở",
    owner_user: "", task: "", description: "", due_date: "", resolution: "" } });
}

async function act(action, message) {
  busy.value = true;
  try {
    await action();
    toast(message);
    await load();
    return true;
  } catch (e) {
    toast(e.message, "error", 8000);
    return false;
  } finally {
    busy.value = false;
  }
}

const FIELDS_RISK = ["title", "category", "description", "task", "probability", "impact", "owner_user", "response", "plan", "due_date", "status", "close_note"];
const FIELDS_ISSUE = ["title", "description", "task", "priority", "owner_user", "due_date", "status", "resolution"];
const pick = (values, keys) => Object.fromEntries(keys.map((k) => [k, values[k] === "" ? null : values[k]]));

async function saveRisk() {
  if (await act(() => api.control.saveRisk(project.value, pick(risk.values, FIELDS_RISK), risk.name), risk.name ? "Đã lưu rủi ro" : "Đã ghi rủi ro")) risk.open = false;
}
async function saveIssue() {
  if (await act(() => api.control.saveIssue(project.value, pick(issue.values, FIELDS_ISSUE), issue.name), issue.name ? "Đã lưu vấn đề" : "Đã ghi vấn đề")) issue.open = false;
}
async function happened(note) {
  if (await act(() => api.control.riskHappened(happening.value.name, note), "Đã chuyển rủi ro thành vấn đề cần xử lý")) happening.value = null;
}

onMounted(load);
</script>

<template>
  <EmptyState v-if="error" icon="shield-alert" title="Không xem được rủi ro, vấn đề" :text="error" />
  <div v-else-if="data" class="space-y-5" data-control>
    <section class="grid grid-cols-2 gap-3 sm:grid-cols-4">
      <div class="card px-4 py-3"><span class="block text-xs text-ink-muted">Rủi ro đang mở</span><span class="text-2xl font-semibold">{{ data.summary.risks_open }}</span></div>
      <div class="card px-4 py-3"><span class="block text-xs text-ink-muted">Rủi ro mức cao</span><span class="text-2xl font-semibold" :class="data.summary.risks_high ? 'text-danger' : ''">{{ data.summary.risks_high }}</span></div>
      <div class="card px-4 py-3"><span class="block text-xs text-ink-muted">Vấn đề đang mở</span><span class="text-2xl font-semibold">{{ data.summary.issues_open }}</span></div>
      <div class="card px-4 py-3"><span class="block text-xs text-ink-muted">Vấn đề quá hạn</span><span class="text-2xl font-semibold" :class="data.summary.issues_overdue ? 'text-danger' : ''">{{ data.summary.issues_overdue }}</span></div>
    </section>

    <div class="grid gap-5 lg:grid-cols-[auto_1fr]">
      <section class="card p-4" aria-labelledby="risk-matrix">
        <h2 id="risk-matrix" class="m-0 mb-2 text-sm font-semibold">Ma trận rủi ro đang mở</h2>
        <table class="text-center text-xs" data-risk-matrix>
          <tbody>
            <tr v-for="row in grid" :key="row.impact">
              <th scope="row" class="pr-2 text-ink-muted">{{ row.impact }}</th>
              <td v-for="c in row.cells" :key="c.probability" class="h-10 w-10 border border-surface" :class="cellTone(c.level)"
                  :title="`Khả năng ${c.probability}, ảnh hưởng ${row.impact}: ${c.risks.map((r) => r.title).join(', ') || 'không có'}`">
                <strong v-if="c.risks.length">{{ c.risks.length }}</strong>
              </td>
            </tr>
            <tr><th></th><th v-for="p in 5" :key="p" class="pt-1 text-ink-muted">{{ p }}</th></tr>
          </tbody>
        </table>
        <p class="m-0 mt-1 text-xs text-ink-muted">Dọc: ảnh hưởng · Ngang: khả năng xảy ra</p>
      </section>

      <section class="card overflow-x-auto p-4" aria-labelledby="risk-list">
        <div class="mb-2 flex flex-wrap items-center gap-2">
          <h2 id="risk-list" class="m-0 flex-1 text-sm font-semibold">Sổ rủi ro</h2>
          <label class="flex items-center gap-2 text-sm"><input v-model="showClosed" type="checkbox" /> Hiện cả mục đã đóng</label>
          <button v-if="can.risk" class="btn btn-primary" type="button" @click="editRisk()"><Icon name="plus" :size="16" /> Ghi rủi ro</button>
        </div>
        <p v-if="!risks.length" class="m-0 text-sm text-ink-muted">Chưa có rủi ro nào.</p>
        <ul class="m-0 list-none divide-y divide-line p-0 text-sm">
          <li v-for="row in risks" :key="row.name" class="flex flex-wrap items-start gap-2 py-2" data-risk>
            <span :class="levelBadge(row.level)">{{ row.level }} · {{ row.score }}</span>
            <div class="min-w-0 flex-1">
              <strong>{{ row.title }}</strong> <span class="text-xs text-ink-muted">{{ row.name }} · {{ row.category }}</span>
              <span class="block text-xs text-ink-muted">{{ row.response }}<template v-if="row.owner_name"> · {{ row.owner_name }}</template>
                <template v-if="row.due_date"> · hạn <span :class="row.overdue ? 'font-semibold text-danger' : ''">{{ formatDate(row.due_date) }}</span></template>
                <template v-if="row.task_label"> · <button type="button" class="text-primary underline" @click="openTask(row.task)">{{ row.task_label }}</button></template></span>
              <span v-if="row.plan" class="block text-xs">{{ row.plan }}</span>
            </div>
            <span :class="stateBadge(row.status)">{{ row.status }}</span>
            <div v-if="can.risk" class="flex gap-1">
              <button class="btn btn-ghost btn-icon" type="button" :aria-label="`Sửa rủi ro ${row.title}`" @click="editRisk(row)"><Icon name="pencil" :size="14" /></button>
              <button v-if="open(row, RISK_STATES)" class="btn btn-ghost" type="button" @click="happening = row">Đã xảy ra</button>
            </div>
          </li>
        </ul>
      </section>
    </div>

    <section class="card overflow-x-auto p-4" aria-labelledby="issue-list">
      <div class="mb-2 flex flex-wrap items-center gap-2">
        <h2 id="issue-list" class="m-0 flex-1 text-sm font-semibold">Vấn đề cần xử lý</h2>
        <button v-if="can.risk" class="btn" type="button" @click="editIssue()"><Icon name="plus" :size="16" /> Ghi vấn đề</button>
      </div>
      <p v-if="!issues.length" class="m-0 text-sm text-ink-muted">Không có vấn đề nào đang mở.</p>
      <ul class="m-0 list-none divide-y divide-line p-0 text-sm">
        <li v-for="row in issues" :key="row.name" class="flex flex-wrap items-start gap-2 py-2" data-issue>
          <span :class="priorityBadge(row.priority)">{{ row.priority }}</span>
          <div class="min-w-0 flex-1">
            <strong>{{ row.title }}</strong> <span class="text-xs text-ink-muted">{{ row.name }}<template v-if="row.risk"> · từ {{ row.risk }}</template></span>
            <span class="block text-xs text-ink-muted"><template v-if="row.owner_name">{{ row.owner_name }}</template>
              <template v-if="row.due_date"> · hạn <span :class="row.overdue ? 'font-semibold text-danger' : ''" :data-overdue="row.overdue ? 1 : undefined">{{ formatDate(row.due_date) }}</span></template></span>
            <span v-if="row.resolution" class="block text-xs">Giải quyết: {{ row.resolution }}</span>
          </div>
          <span :class="stateBadge(row.status)">{{ row.status }}</span>
          <button v-if="can.risk" class="btn btn-ghost btn-icon" type="button" :aria-label="`Sửa vấn đề ${row.title}`" @click="editIssue(row)"><Icon name="pencil" :size="14" /></button>
        </li>
      </ul>
    </section>
  </div>

  <Drawer :open="risk.open" :title="risk.name ? `Rủi ro ${risk.name}` : 'Ghi rủi ro'" width="520px" @close="risk.open = false">
    <form id="risk-form" class="space-y-3" @submit.prevent="saveRisk">
      <div><label class="label" for="risk-title">Rủi ro</label><input id="risk-title" v-model="risk.values.title" class="input" required /></div>
      <div class="grid grid-cols-2 gap-2">
        <div><label class="label" for="risk-category">Nhóm</label><select id="risk-category" v-model="risk.values.category" class="input"><option v-for="c in RISK_CATEGORIES" :key="c">{{ c }}</option></select></div>
        <div><label class="label" for="risk-status">Trạng thái</label><select id="risk-status" v-model="risk.values.status" class="input"><option v-for="s in RISK_STATES" :key="s">{{ s }}</option></select></div>
        <div><label class="label" for="risk-p">Khả năng (1–5)</label><select id="risk-p" v-model.number="risk.values.probability" class="input"><option v-for="n in 5" :key="n" :value="n">{{ n }}</option></select></div>
        <div><label class="label" for="risk-i">Ảnh hưởng (1–5)</label><select id="risk-i" v-model.number="risk.values.impact" class="input"><option v-for="n in 5" :key="n" :value="n">{{ n }}</option></select></div>
      </div>
      <p class="m-0 text-sm">Điểm <strong>{{ preview.score }}</strong> <span :class="levelBadge(preview.level)">{{ preview.level }}</span></p>
      <div><label class="label" for="risk-description">Mô tả</label><textarea id="risk-description" v-model="risk.values.description" class="input" rows="2"></textarea></div>
      <div class="grid grid-cols-2 gap-2">
        <div><label class="label" for="risk-owner">Người phụ trách</label>
          <select id="risk-owner" v-model="risk.values.owner_user" class="input"><option value="">Chưa có</option><option v-for="m in members" :key="m.user" :value="m.user">{{ m.full_name || m.user }}</option></select></div>
        <div><label class="label" for="risk-response">Cách ứng phó</label><select id="risk-response" v-model="risk.values.response" class="input"><option v-for="r in RESPONSES" :key="r">{{ r }}</option></select></div>
      </div>
      <div><label class="label" for="risk-plan">Kế hoạch ứng phó</label><textarea id="risk-plan" v-model="risk.values.plan" class="input" rows="2"></textarea></div>
      <div class="grid grid-cols-2 gap-2">
        <div><label class="label" for="risk-due">Hạn xử lý</label><input id="risk-due" v-model="risk.values.due_date" class="input" type="date" /></div>
        <div><label class="label" for="risk-task">Công việc liên quan</label><LinkSelect v-model="risk.values.task" input-id="risk-task" doctype="Task" :searcher="searchTasks" :placeholder="risk.values.task_label || 'Không bắt buộc'" /></div>
      </div>
      <div v-if="risk.values.status === 'Đã đóng'"><label class="label" for="risk-close">Ghi chú khi đóng</label><input id="risk-close" v-model="risk.values.close_note" class="input" /></div>
    </form>
    <template #footer>
      <button class="btn" type="button" @click="risk.open = false">Hủy</button>
      <button class="btn btn-primary" type="submit" form="risk-form" :disabled="busy">Lưu</button>
    </template>
  </Drawer>

  <Drawer :open="issue.open" :title="issue.name ? `Vấn đề ${issue.name}` : 'Ghi vấn đề'" width="520px" @close="issue.open = false">
    <form id="issue-form" class="space-y-3" @submit.prevent="saveIssue">
      <div><label class="label" for="issue-title">Vấn đề</label><input id="issue-title" v-model="issue.values.title" class="input" required /></div>
      <div class="grid grid-cols-2 gap-2">
        <div><label class="label" for="issue-priority">Ưu tiên</label><select id="issue-priority" v-model="issue.values.priority" class="input"><option v-for="p in PRIORITIES" :key="p">{{ p }}</option></select></div>
        <div><label class="label" for="issue-status">Trạng thái</label><select id="issue-status" v-model="issue.values.status" class="input"><option v-for="s in ISSUE_STATES" :key="s">{{ s }}</option></select></div>
        <div><label class="label" for="issue-owner">Người xử lý</label>
          <select id="issue-owner" v-model="issue.values.owner_user" class="input"><option value="">Chưa có</option><option v-for="m in members" :key="m.user" :value="m.user">{{ m.full_name || m.user }}</option></select></div>
        <div><label class="label" for="issue-due">Hạn xử lý</label><input id="issue-due" v-model="issue.values.due_date" class="input" type="date" /></div>
      </div>
      <div><label class="label" for="issue-description">Mô tả</label><textarea id="issue-description" v-model="issue.values.description" class="input" rows="3"></textarea></div>
      <div><label class="label" for="issue-task">Công việc liên quan</label><LinkSelect v-model="issue.values.task" input-id="issue-task" doctype="Task" :searcher="searchTasks" :placeholder="issue.values.task_label || 'Không bắt buộc'" /></div>
      <div><label class="label" for="issue-resolution">Cách giải quyết</label><textarea id="issue-resolution" v-model="issue.values.resolution" class="input" rows="2" placeholder="Bắt buộc khi chuyển sang Đã giải quyết"></textarea></div>
    </form>
    <template #footer>
      <button class="btn" type="button" @click="issue.open = false">Hủy</button>
      <button class="btn btn-primary" type="submit" form="issue-form" :disabled="busy">Lưu</button>
    </template>
  </Drawer>

  <ReasonDialog :open="Boolean(happening)" title="Rủi ro đã xảy ra" :message="happening ? `“${happening.title}” sẽ đóng và mở một vấn đề cần xử lý.` : ''"
                label="Diễn biến (không bắt buộc)" confirm-text="Chuyển thành vấn đề" :required="false" :busy="busy"
                @confirm="happened" @cancel="happening = null" />
</template>
