<script setup>
import { computed, reactive, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import Drawer from "../components/Drawer.vue";
import EmptyState from "../components/EmptyState.vue";
import FilterForm from "../components/FilterForm.vue";
import Icon from "../components/Icon.vue";
import PageHeader from "../components/PageHeader.vue";
import PaginationBar from "../components/PaginationBar.vue";
import { api } from "../lib/api.js";
import { boot } from "../lib/boot.js";
import { formatDateTime, formatNumber } from "../lib/format.js";
import { pageTitle } from "../lib/page.js";
import { FREQUENCIES, WEEKDAYS, cleanFilters, downloadUrl, formatCell, initialFilters, printUrl, routeOf, scheduleText } from "../lib/reports.js";
import { toast } from "../lib/toast.js";

// One report: its filters (kept in the address, so a view can be shared), the result with its totals, the ways out
// of it (Excel, CSV, a printable page, a PDF) and its scheduled sending (each recipient gets it as they may see it).
// Copied from document_manager (pages/ReportPage.vue, see docs/NGUON_GOC.md) and adapted.
const props = defineProps({ slug: { type: String, required: true } });
const route = useRoute();
const router = useRouter();

const definition = ref(null);
const filters = ref({});
const result = ref(null);
const loading = ref(false);
const error = ref("");
const showFilters = ref(true);
const PAGE_SIZE = 50;
const schedule = reactive({ open: false, rows: [], editing: null, values: {}, recipients: [], search: "", found: [], busy: false });

const page = computed(() => Math.max(1, Number(route.query.page) || 1));
const applied = computed(() => cleanFilters(filters.value));
const columns = computed(() => result.value?.columns || definition.value?.columns || []);
const missing = computed(() => (definition.value?.filters || []).filter((f) => f.reqd && !applied.value[f.fieldname]));

async function load() {
  if (!definition.value) return;
  if (missing.value.length) {
    result.value = null;
    return;
  }
  loading.value = true;
  error.value = "";
  try {
    result.value = await api.reports.run(props.slug, applied.value, page.value, PAGE_SIZE);
  } catch (e) {
    error.value = e.message;
    result.value = null;
  } finally {
    loading.value = false;
  }
}

async function open() {
  definition.value = null;
  result.value = null;
  error.value = "";
  try {
    definition.value = await api.reports.get(props.slug);
  } catch (e) {
    error.value = e.message;
    return;
  }
  pageTitle.value = definition.value.title;
  filters.value = initialFilters(definition.value.filters, route.query);
  await load();
}
watch(() => props.slug, open, { immediate: true });
watch(() => route.query, (now, before) => { if (definition.value && JSON.stringify(now) !== JSON.stringify(before)) load(); });

function search() {
  router.replace({ query: { ...applied.value } });
  if (JSON.stringify(route.query) === JSON.stringify(applied.value)) load();
}
function reset() {
  filters.value = initialFilters(definition.value.filters);
  search();
}
function goto(next) {
  router.replace({ query: { ...applied.value, ...(next > 1 ? { page: next } : {}) } });
}

// --- scheduled sending ---------------------------------------------------------------------------------------------
async function openSchedule() {
  schedule.open = true;
  schedule.editing = null;
  try {
    schedule.rows = await api.reports.subscriptions(props.slug);
  } catch (e) {
    toast(e.message, "error");
  }
  if (!schedule.rows.length) newSchedule();
}
function newSchedule(row = null) {
  schedule.editing = row?.name || "new";
  schedule.values = row ? { title: row.title, file_format: row.file_format, frequency: row.frequency, weekday: row.weekday,
    day_of_month: row.day_of_month, hour: row.hour, is_active: row.is_active }
    : { title: definition.value.title, file_format: "PDF", frequency: "Hằng tuần", weekday: WEEKDAYS[0], day_of_month: 1, hour: 7, is_active: 1 };
  schedule.recipients = row ? row.recipients.map((user) => ({ name: user, full_name: user })) : [{ name: boot.user.name, full_name: boot.user.full_name || boot.user.name }];
  schedule.search = "";
  schedule.found = [];
}
async function findPeople() {
  try {
    schedule.found = (await api.reports.recipients(schedule.search)).filter((p) => !schedule.recipients.some((r) => r.name === p.name));
  } catch (e) {
    toast(e.message, "error");
  }
}
async function saveSchedule() {
  schedule.busy = true;
  try {
    const name = schedule.editing === "new" ? null : schedule.editing;
    const rowFilters = name ? schedule.rows.find((r) => r.name === name)?.filters : applied.value;
    await api.reports.saveSubscription(props.slug, schedule.values, schedule.recipients.map((r) => r.name), rowFilters, name);
    toast("Đã lưu lịch gửi");
    schedule.editing = null;
    schedule.rows = await api.reports.subscriptions(props.slug);
  } catch (e) {
    toast(e.message, "error", 8000);
  } finally {
    schedule.busy = false;
  }
}
async function removeSchedule(row) {
  try {
    await api.reports.deleteSubscription(row.name);
    schedule.rows = schedule.rows.filter((r) => r.name !== row.name);
    toast("Đã xóa lịch gửi");
  } catch (e) {
    toast(e.message, "error");
  }
}
async function sendNow(row) {
  try {
    const done = await api.reports.sendNow(row.name);
    toast(`Đã gửi cho ${done.sent.length} người${done.emailed.length ? ` (${done.emailed.length} qua email)` : ""}`);
  } catch (e) {
    toast(e.message, "error", 8000);
  }
}
</script>

<template>
  <EmptyState v-if="error && !definition" icon="alert-triangle" title="Không mở được báo cáo" :text="error">
    <RouterLink class="btn" to="/bao-cao">Về danh sách báo cáo</RouterLink>
  </EmptyState>

  <template v-else-if="definition">
    <nav class="mb-2 text-sm text-ink-muted" aria-label="Đường dẫn"><RouterLink to="/bao-cao">Báo cáo</RouterLink> › {{ definition.group }}</nav>
    <PageHeader :title="definition.title" :subtitle="definition.description">
      <template v-if="!missing.length">
        <a class="btn" :href="downloadUrl(slug, applied, 'xlsx')" data-export="xlsx"><Icon name="file-spreadsheet" :size="16" /> Excel</a>
        <a class="btn" :href="downloadUrl(slug, applied, 'csv')"><Icon name="download" :size="16" /> CSV</a>
        <a class="btn" :href="printUrl(slug, applied)" target="_blank" rel="noopener"><Icon name="printer" :size="16" /> In</a>
        <a class="btn" :href="printUrl(slug, applied, 'pdf')" data-export="pdf"><Icon name="file-down" :size="16" /> PDF</a>
      </template>
      <button class="btn" type="button" @click="openSchedule"><Icon name="mail" :size="16" /> Gửi theo lịch</button>
    </PageHeader>

    <section v-if="definition.filters.length" class="card mb-5">
      <button class="flex w-full items-center justify-between px-5 py-3 text-left text-sm font-semibold" type="button" :aria-expanded="showFilters" @click="showFilters = !showFilters">
        <span class="flex items-center gap-2"><Icon name="sliders" :size="16" /> Bộ lọc<span v-if="Object.keys(applied).length" class="badge badge-info">{{ Object.keys(applied).length }}</span></span>
        <Icon :name="showFilters ? 'chevron-down' : 'chevron-right'" :size="16" />
      </button>
      <div v-show="showFilters" class="border-t border-line px-5 py-4">
        <FilterForm v-model="filters" :filters="definition.filters" :busy="loading" submit-label="Xem báo cáo" @submit="search" @reset="reset" />
      </div>
    </section>

    <p v-if="missing.length" class="mb-4 rounded-md bg-info-soft px-3 py-2 text-sm text-info">Chọn {{ missing.map((f) => f.label.toLowerCase()).join(", ") }} rồi bấm "Xem báo cáo".</p>
    <p v-if="error" class="mb-4 whitespace-pre-line rounded-md bg-danger-soft px-3 py-2 text-sm text-danger" role="alert">{{ error }}</p>

    <section v-if="result?.info?.length" class="card mb-5 grid gap-x-8 gap-y-1 px-5 py-4 text-sm sm:grid-cols-2">
      <p v-for="[label, value] in result.info" :key="label" class="m-0"><span class="text-ink-muted">{{ label }}:</span> <strong>{{ value }}</strong></p>
    </section>

    <section v-if="result || loading" class="card">
      <div v-if="loading && !result" class="space-y-2 p-5"><div v-for="n in 6" :key="n" class="h-8 animate-pulse rounded bg-surface-muted"></div></div>
      <EmptyState v-else-if="result && !result.rows.length" icon="search" title="Không có dữ liệu" text="Không có dòng nào khớp với bộ lọc, hoặc trong phạm vi bạn được xem." />
      <div v-else-if="result" class="table-wrap" :class="{ 'opacity-60': loading }">
        <table class="data-table" data-report-table>
          <caption class="sr-only">{{ definition.title }}</caption>
          <thead>
            <tr>
              <th v-if="result.paged" scope="col" class="w-12 text-right">STT</th>
              <th v-for="column in columns" :key="column.fieldname" scope="col" :class="{ 'text-right': column.align === 'right' }">{{ column.label }}</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(row, index) in result.rows" :key="row.name || index" data-report-row>
              <td v-if="result.paged" class="text-right text-ink-subtle tabular-nums">{{ (result.page - 1) * result.page_size + index + 1 }}</td>
              <td v-for="column in columns" :key="column.fieldname" :class="column.align === 'right' ? 'text-right tabular-nums' : ''">
                <RouterLink v-if="routeOf(column, row)" :to="routeOf(column, row)">{{ formatCell(column, row[column.fieldname]) }}</RouterLink>
                <template v-else>{{ formatCell(column, row[column.fieldname]) }}</template>
              </td>
            </tr>
          </tbody>
          <tfoot v-if="result.summary">
            <tr class="font-semibold">
              <td v-if="result.paged"></td>
              <td v-for="column in columns" :key="column.fieldname" :class="column.align === 'right' ? 'text-right tabular-nums' : ''">{{ formatCell(column, result.summary[column.fieldname]) }}</td>
            </tr>
          </tfoot>
        </table>
      </div>
      <PaginationBar v-if="result?.paged" :page="result.page" :page-size="result.page_size" :total="result.total" @change="goto" />
      <p v-else-if="result" class="m-0 border-t border-line px-4 py-3 text-sm text-ink-muted">{{ formatNumber(result.total) }} dòng</p>
    </section>
  </template>

  <Drawer :open="schedule.open" title="Gửi báo cáo theo lịch" width="520px" @close="schedule.open = false">
    <div class="space-y-4" data-schedule>
      <p class="m-0 text-sm text-ink-muted">Mỗi người nhận nhận báo cáo theo quyền xem của chính họ, kèm tệp PDF hoặc Excel (qua email khi hệ thống gửi được email) và một thông báo trong ứng dụng.</p>
      <ul v-if="schedule.rows.length" class="m-0 list-none divide-y divide-line p-0 text-sm">
        <li v-for="row in schedule.rows" :key="row.name" class="py-2" data-schedule-row>
          <div class="flex flex-wrap items-center gap-2">
            <strong class="flex-1">{{ row.title }}</strong>
            <button class="btn btn-ghost" type="button" @click="sendNow(row)">Gửi thử ngay</button>
            <button class="btn btn-ghost btn-icon" type="button" :aria-label="`Sửa lịch ${row.title}`" @click="newSchedule(row)"><Icon name="pencil" :size="14" /></button>
            <button class="btn btn-ghost btn-icon" type="button" :aria-label="`Xóa lịch ${row.title}`" @click="removeSchedule(row)"><Icon name="trash-2" :size="14" /></button>
          </div>
          <span class="text-xs text-ink-muted">{{ scheduleText(row) }} · {{ row.file_format }} · {{ row.recipients.join(", ") }}<template v-if="row.last_sent_on"> · gửi lần cuối {{ formatDateTime(row.last_sent_on) }}</template></span>
          <span v-if="row.last_error" class="block text-xs text-warning">{{ row.last_error }}</span>
        </li>
      </ul>
      <button v-if="!schedule.editing" class="btn" type="button" @click="newSchedule()"><Icon name="plus" :size="16" /> Thêm lịch gửi</button>
      <form v-if="schedule.editing" class="space-y-3 rounded-lg border border-line p-3" data-schedule-form @submit.prevent="saveSchedule">
        <p v-if="schedule.editing === 'new'" class="m-0 text-xs text-ink-muted">Dùng bộ lọc đang chọn trên trang ({{ Object.keys(applied).length || "không có" }} điều kiện).</p>
        <div><label class="label" for="sub-title">Tiêu đề</label><input id="sub-title" v-model="schedule.values.title" class="input" /></div>
        <div class="grid grid-cols-2 gap-2">
          <div><label class="label" for="sub-format">Định dạng</label><select id="sub-format" v-model="schedule.values.file_format" class="input"><option>PDF</option><option>Excel</option></select></div>
          <div><label class="label" for="sub-frequency">Tần suất</label><select id="sub-frequency" v-model="schedule.values.frequency" class="input"><option v-for="f in FREQUENCIES" :key="f">{{ f }}</option></select></div>
          <div v-if="schedule.values.frequency === 'Hằng tuần'"><label class="label" for="sub-weekday">Thứ</label><select id="sub-weekday" v-model="schedule.values.weekday" class="input"><option v-for="d in WEEKDAYS" :key="d">{{ d }}</option></select></div>
          <div v-if="schedule.values.frequency === 'Hằng tháng'"><label class="label" for="sub-day">Ngày (1–28)</label><input id="sub-day" v-model.number="schedule.values.day_of_month" class="input" type="number" min="1" max="28" /></div>
          <div><label class="label" for="sub-hour">Giờ gửi</label><input id="sub-hour" v-model.number="schedule.values.hour" class="input" type="number" min="0" max="23" /></div>
        </div>
        <div>
          <span class="label">Người nhận</span>
          <div class="flex flex-wrap gap-1">
            <span v-for="(person, index) in schedule.recipients" :key="person.name" class="badge badge-info">{{ person.full_name || person.name }}
              <button type="button" :aria-label="`Bỏ ${person.full_name || person.name}`" @click="schedule.recipients.splice(index, 1)"><Icon name="x" :size="12" /></button></span>
          </div>
          <div class="mt-2 flex gap-2"><input v-model="schedule.search" class="input" placeholder="Tìm người cùng dự án" aria-label="Tìm người nhận" @keydown.enter.prevent="findPeople" />
            <button class="btn" type="button" @click="findPeople"><Icon name="search" :size="16" /></button></div>
          <ul v-if="schedule.found.length" class="m-0 mt-1 list-none p-0 text-sm">
            <li v-for="person in schedule.found" :key="person.name"><button type="button" class="text-primary underline" @click="schedule.recipients.push(person); schedule.found = schedule.found.filter((p) => p.name !== person.name)">+ {{ person.full_name || person.name }}</button></li>
          </ul>
        </div>
        <label class="flex items-center gap-2 text-sm"><input v-model="schedule.values.is_active" type="checkbox" :true-value="1" :false-value="0" /> Đang dùng</label>
        <div class="flex justify-end gap-2">
          <button class="btn" type="button" @click="schedule.editing = null">Hủy</button>
          <button class="btn btn-primary" type="submit" :disabled="schedule.busy || !schedule.recipients.length">Lưu lịch gửi</button>
        </div>
      </form>
    </div>
  </Drawer>
</template>
