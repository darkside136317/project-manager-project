<script setup>
import { computed, inject, onMounted, reactive, ref } from "vue";
import EmptyState from "../../components/EmptyState.vue";
import Icon from "../../components/Icon.vue";
import LinkSelect from "../../components/LinkSelect.vue";
import { api } from "../../lib/api.js";
import { BUDGET_CATEGORIES, budgetLines, indexTone, money, moneyShort, ratio, stateBadge, total, usage, varianceTone } from "../../lib/control.js";
import { formatDateTime } from "../../lib/format.js";
import { toast } from "../../lib/toast.js";

// Ngân sách: the budget in use (BAC) and its earned value today, budget against actual by cost category and by
// section of the WBS, and the draft being prepared (approving it replaces the one in use). Needs finance.view.
const { name: project } = inject("project");
const data = ref(null);
const error = ref("");
const busy = ref(false);
const form = reactive({ open: false, name: null, title: "", note: "", lines: [] });

const figures = computed(() => data.value?.evm || {});
const can = computed(() => data.value?.can || {});
const draftTotal = computed(() => total(form.lines));
const tiles = computed(() => [
  { key: "bac", label: "Ngân sách (BAC)", value: moneyShort(figures.value.bac) },
  { key: "pv", label: "Giá trị kế hoạch (PV)", value: moneyShort(figures.value.pv), hint: `${figures.value.planned_pct ?? 0}% kế hoạch` },
  { key: "ev", label: "Giá trị thu được (EV)", value: moneyShort(figures.value.ev), hint: `${figures.value.progress_pct ?? 0}% tiến độ` },
  { key: "ac", label: "Chi phí thực tế (AC)", value: moneyShort(figures.value.ac) },
  { key: "cpi", label: "CPI (EV / AC)", value: ratio(figures.value.cpi), tone: indexTone(figures.value.cpi) },
  { key: "spi", label: "SPI (EV / PV)", value: ratio(figures.value.spi), tone: indexTone(figures.value.spi) },
  { key: "eac", label: "Dự báo khi xong (EAC)", value: figures.value.eac === null ? "—" : moneyShort(figures.value.eac) },
  { key: "vac", label: "Chênh lệch khi xong (VAC)", value: figures.value.vac === null ? "—" : moneyShort(figures.value.vac), tone: varianceTone(figures.value.vac) },
]);

async function load() {
  error.value = "";
  try {
    data.value = await api.control.budget(project.value);
  } catch (e) {
    error.value = e.message;
  }
}

function edit(source) {
  Object.assign(form, { open: true, name: source?.name || null, title: source?.title || "Ngân sách dự án", note: source?.note || "",
    lines: (source?.lines || []).map((l) => ({ category: l.category, task: l.task || "", task_label: l.task_label || "",
      description: l.description || "", amount: l.amount ? String(Math.round(l.amount)) : "" })) });
  if (!form.lines.length) addLine();
}
const addLine = () => form.lines.push({ category: BUDGET_CATEGORIES[0], task: "", task_label: "", description: "", amount: "" });
const searchTasks = (txt) => api.schedule.searchTasks(project.value, txt);

async function run(action, message) {
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

async function save() {
  if (await run(() => api.control.saveBudget(project.value, form.title, budgetLines(form.lines), form.note, form.name), "Đã lưu ngân sách nháp")) {
    form.open = false;
  }
}
const revise = () => run(() => api.control.reviseBudget(project.value), "Đã tạo bản điều chỉnh từ ngân sách đang dùng");
const approve = (name) => run(() => api.control.approveBudget(name), "Đã duyệt: ngân sách này được dùng từ nay");
const discard = (name) => run(() => api.control.discardBudget(name), "Đã bỏ bản nháp");

onMounted(load);
</script>

<template>
  <EmptyState v-if="error" icon="wallet" title="Không xem được ngân sách" :text="error" />
  <div v-else-if="data" class="space-y-5" data-budget>
    <section class="grid grid-cols-2 gap-3 lg:grid-cols-4" aria-label="Giá trị thu được hôm nay">
      <div v-for="tile in tiles" :key="tile.key" class="card px-4 py-3" :data-evm="tile.key">
        <span class="block text-xs text-ink-muted">{{ tile.label }}</span>
        <span class="text-xl font-semibold" :class="tile.tone">{{ tile.value }}</span>
        <span v-if="tile.hint" class="block text-xs text-ink-muted">{{ tile.hint }}</span>
      </div>
    </section>
    <p v-if="!data.in_use" class="m-0 rounded-md bg-warning-soft px-3 py-2 text-sm text-warning">Chưa có ngân sách được duyệt: các chỉ số giá trị thu được chưa có ý nghĩa.</p>

    <div class="grid gap-5 lg:grid-cols-2">
      <section class="card overflow-x-auto" aria-labelledby="budget-categories">
        <h2 id="budget-categories" class="m-0 px-4 pt-3 text-sm font-semibold">Theo khoản mục</h2>
        <table class="w-full min-w-[420px] text-sm">
          <thead><tr class="border-b border-line text-left text-xs text-ink-muted">
            <th class="px-4 py-2">Khoản mục</th><th class="px-2 py-2 text-right">Ngân sách</th><th class="px-2 py-2 text-right">Thực tế</th><th class="px-4 py-2">Đã dùng</th></tr></thead>
          <tbody>
            <tr v-for="row in data.by_category" :key="row.category" class="border-b border-line last:border-0" data-category-row>
              <td class="px-4 py-2">{{ row.category }}</td>
              <td class="px-2 py-2 text-right tabular-nums">{{ money(row.budget) }}</td>
              <td class="px-2 py-2 text-right tabular-nums" :class="usage(row.budget, row.actual).over ? 'font-semibold text-danger' : ''">{{ money(row.actual) }}</td>
              <td class="px-4 py-2">
                <div class="h-2 w-24 rounded bg-surface-muted"><div class="h-2 rounded" :class="usage(row.budget, row.actual).over ? 'bg-danger' : 'bg-primary'" :style="{ width: `${usage(row.budget, row.actual).width}%` }"></div></div>
                <span class="text-xs text-ink-muted">{{ usage(row.budget, row.actual).pct === null ? "ngoài ngân sách" : `${usage(row.budget, row.actual).pct}%` }}</span>
              </td>
            </tr>
            <tr v-if="!data.by_category.length"><td colspan="4" class="px-4 py-3 text-ink-muted">Chưa có số liệu.</td></tr>
          </tbody>
        </table>
      </section>
      <section class="card overflow-x-auto" aria-labelledby="budget-sections">
        <h2 id="budget-sections" class="m-0 px-4 pt-3 text-sm font-semibold">Theo hạng mục</h2>
        <table class="w-full min-w-[380px] text-sm">
          <thead><tr class="border-b border-line text-left text-xs text-ink-muted">
            <th class="px-4 py-2">Hạng mục</th><th class="px-2 py-2 text-right">Ngân sách</th><th class="px-4 py-2 text-right">Thực tế</th></tr></thead>
          <tbody>
            <tr v-for="row in data.by_section" :key="row.task || 'chung'" class="border-b border-line last:border-0">
              <td class="px-4 py-2">{{ row.label }}</td>
              <td class="px-2 py-2 text-right tabular-nums">{{ money(row.budget) }}</td>
              <td class="px-4 py-2 text-right tabular-nums" :class="row.budget && row.actual > row.budget ? 'font-semibold text-danger' : ''">{{ money(row.actual) }}</td>
            </tr>
            <tr v-if="!data.by_section.length"><td colspan="3" class="px-4 py-3 text-ink-muted">Chưa có số liệu.</td></tr>
          </tbody>
        </table>
      </section>
    </div>

    <section class="card p-4" aria-labelledby="budget-versions">
      <div class="flex flex-wrap items-center gap-2">
        <h2 id="budget-versions" class="m-0 flex-1 text-sm font-semibold">Các bản ngân sách</h2>
        <button v-if="can.manage && !data.draft && data.in_use" class="btn" type="button" :disabled="busy" @click="revise"><Icon name="copy" :size="16" /> Điều chỉnh</button>
        <button v-if="can.manage && !data.draft && !data.in_use" class="btn btn-primary" type="button" @click="edit(null)"><Icon name="plus" :size="16" /> Lập ngân sách</button>
      </div>
      <ul class="m-0 mt-2 list-none divide-y divide-line p-0 text-sm">
        <li v-for="row in data.budgets" :key="row.name" class="flex flex-wrap items-center gap-2 py-2" data-budget-row>
          <span :class="stateBadge(row.status)">{{ row.status }}</span>
          <strong>{{ row.title }}</strong><span class="text-ink-muted">lần {{ row.version }}</span>
          <span class="ml-auto tabular-nums">{{ money(row.total) }}</span>
          <span v-if="row.approved_on" class="w-full text-xs text-ink-muted sm:w-auto">duyệt {{ formatDateTime(row.approved_on) }}</span>
        </li>
      </ul>
      <div v-if="data.draft" class="mt-3 rounded-lg border border-dashed border-line p-3" data-budget-draft>
        <p class="m-0 text-sm">Bản nháp <strong>{{ data.draft.title }}</strong>: {{ money(data.draft.total) }} ({{ data.draft.lines.length }} dòng)</p>
        <div v-if="can.manage" class="mt-2 flex flex-wrap gap-2">
          <button class="btn" type="button" @click="edit(data.draft)"><Icon name="pencil" :size="16" /> Sửa</button>
          <button class="btn btn-primary" type="button" :disabled="busy" @click="approve(data.draft.name)"><Icon name="check" :size="16" /> Duyệt và dùng</button>
          <button class="btn btn-ghost" type="button" :disabled="busy" @click="discard(data.draft.name)">Bỏ bản nháp</button>
        </div>
      </div>
      <div v-if="data.in_use" class="mt-3 overflow-x-auto">
        <table class="w-full min-w-[520px] text-sm">
          <caption class="mb-1 text-left text-xs text-ink-muted">Đang dùng: {{ data.in_use.title }}</caption>
          <thead><tr class="border-b border-line text-left text-xs text-ink-muted">
            <th class="py-2 pr-2">Khoản mục</th><th class="px-2 py-2">Hạng mục, công việc</th><th class="px-2 py-2">Diễn giải</th><th class="py-2 pl-2 text-right">Số tiền</th></tr></thead>
          <tbody>
            <tr v-for="line in data.in_use.lines" :key="line.name" class="border-b border-line last:border-0">
              <td class="py-1.5 pr-2">{{ line.category }}</td><td class="px-2 py-1.5">{{ line.task_label || "—" }}</td>
              <td class="px-2 py-1.5">{{ line.description || "" }}<span v-if="line.change_request" class="badge badge-info ml-1">{{ line.change_request }}</span></td>
              <td class="py-1.5 pl-2 text-right tabular-nums">{{ money(line.amount) }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>

    <section v-if="form.open" class="card p-4" aria-labelledby="budget-form-title" data-budget-form>
      <h2 id="budget-form-title" class="m-0 mb-3 text-sm font-semibold">{{ form.name ? "Sửa ngân sách nháp" : "Lập ngân sách" }}</h2>
      <form class="space-y-3" @submit.prevent="save">
        <div class="grid gap-3 sm:grid-cols-2">
          <div><label class="label" for="budget-title">Tên</label><input id="budget-title" v-model="form.title" class="input" required /></div>
          <div><label class="label" for="budget-note">Ghi chú</label><input id="budget-note" v-model="form.note" class="input" /></div>
        </div>
        <div class="space-y-2">
          <div v-for="(line, index) in form.lines" :key="index" class="grid gap-2 rounded-md border border-line p-2 sm:grid-cols-[10rem_1fr_1fr_9rem_auto]" data-budget-line>
            <select v-model="line.category" class="input" :aria-label="`Khoản mục dòng ${index + 1}`"><option v-for="c in BUDGET_CATEGORIES" :key="c">{{ c }}</option></select>
            <LinkSelect v-model="line.task" doctype="Task" :searcher="searchTasks" :placeholder="line.task_label || 'Hạng mục (không bắt buộc)'" />
            <input v-model="line.description" class="input" placeholder="Diễn giải" :aria-label="`Diễn giải dòng ${index + 1}`" />
            <input v-model="line.amount" class="input text-right" inputmode="numeric" placeholder="Số tiền" :aria-label="`Số tiền dòng ${index + 1}`" />
            <button class="btn btn-ghost btn-icon" type="button" :aria-label="`Xóa dòng ${index + 1}`" @click="form.lines.splice(index, 1)"><Icon name="trash-2" :size="16" /></button>
          </div>
        </div>
        <div class="flex flex-wrap items-center gap-2">
          <button class="btn" type="button" @click="addLine"><Icon name="plus" :size="16" /> Thêm dòng</button>
          <span class="ml-auto text-sm">Tổng: <strong class="tabular-nums" data-budget-total>{{ money(draftTotal) }}</strong></span>
        </div>
        <div class="flex justify-end gap-2">
          <button class="btn" type="button" @click="form.open = false">Hủy</button>
          <button class="btn btn-primary" type="submit" :disabled="busy">Lưu bản nháp</button>
        </div>
      </form>
    </section>
  </div>
</template>
