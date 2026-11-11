<script setup>
import { computed, inject, onBeforeUnmount, onMounted, reactive, ref } from "vue";
import Drawer from "@pm/components/Drawer.vue";
import Icon from "@pm/components/Icon.vue";
import { api } from "@pm/lib/api.js";
import { formatDate } from "@pm/lib/format.js";
import { network, onSent, queueItem } from "@pm/lib/sync.js";
import { toast } from "@pm/lib/toast.js";
import { REQUEST_STATUS, STOCK_ACTIONS, byWork, construction, materialRows, moneyText, qtyText, site, today } from "./construction.js";

// Vật tư: the site store, what the engineers ask for (queued, so it works without a connection), what the store keeper
// receives, issues to work items, takes back, writes off or moves; per work item what was used against the norm of the
// work done.
const { name: project, reload } = inject("project");
const data = ref(null);
const works = ref([]);
const projects = ref([]);
const error = ref("");
const busy = ref(false);
const form = reactive({ open: false, mode: "request", lines: [], note: "", date: today(), neededBy: today(), target: "" });

const can = computed(() => data.value?.can || {});
const groups = computed(() => byWork(data.value?.rows || []));
const openRequests = computed(() => (data.value?.requests || []).filter((r) => r.open));
const queued = computed(() => network.items.filter((item) => item.kind === "material-request" && item.payload.project === project.value));
const action = computed(() => (form.mode === "request" ? { label: "Đề xuất vật tư", task: true } : STOCK_ACTIONS[form.mode]));
const itemsById = computed(() => new Map((data.value?.items || []).map((item) => [item.name, item])));

async function load() {
  error.value = "";
  try {
    data.value = await site.materials(project.value);
    if (!works.value.length) works.value = await construction.diaryWorks(project.value).catch(() => []);
  } catch (e) {
    error.value = e.message;
  }
}

function blank(values = {}) {
  return { item: "", item_name: "", task: "", qty: "", rate: "", uom: "", ...values };
}

function open(mode, lines = null) {
  Object.assign(form, { open: true, mode, note: "", date: today(), neededBy: today(), target: "", lines: lines || [blank()] });
  if (mode === "transfer" && !projects.value.length) {
    api.projects.list({ limit: 200 }).then((r) => { projects.value = r.rows.filter((p) => p.name !== project.value); }).catch(() => {});
  }
}

function issueRequest(request) {
  open("issue", request.lines.filter((line) => line.left > 0).map((line) => blank({
    item: line.item_code, item_name: line.item_name, task: line.pmc_task, qty: line.left, uom: line.uom,
    material_request_item: line.name })));
}

function pickItem(line) {
  const item = itemsById.value.get(line.item);
  line.item_name = item?.item_name || "";
  line.uom = item?.stock_uom || "";
}

async function createStore() {
  busy.value = true;
  try {
    await site.createStore(project.value);
    toast("Đã lập kho công trường");
    await load();
  } catch (e) {
    toast(e.message, "error", 7000);
  } finally {
    busy.value = false;
  }
}

async function recompute() {
  try {
    const result = await site.recomputePlan(project.value);
    toast(`Đã tính lại kế hoạch vật tư: ${result.rows} dòng`);
    await load();
  } catch (e) {
    toast(e.message, "error", 7000);
  }
}

async function save() {
  const { rows, errors } = materialRows(form.lines, { task: action.value.task, rate: action.value.rate });
  if (errors.length) return toast(errors.join("\n"), "error", 7000);
  if (!rows.length) return toast("Chưa có dòng vật tư nào", "error");
  if (action.value.note && !form.note.trim()) return toast("Ghi lý do hao hụt", "error");
  if (action.value.target && !form.target) return toast("Chọn dự án nhận", "error");
  busy.value = true;
  try {
    if (form.mode === "request") {
      await queueItem("material-request", { project: project.value, rows, note: form.note, needed_by: form.neededBy }, {
        label: "Đề xuất vật tư", reference: { doctype: "Project", name: project.value, link: `/du-an/${project.value}/vat-tu` } });
      if (!network.online) toast("Chưa có mạng: đề xuất được giữ lại, sẽ tự gửi khi có mạng", "warning", 7000);
    } else {
      const values = { posting_date: form.date, note: form.note, client_uuid: crypto.randomUUID() };
      if (form.mode === "transfer") values.to_project = form.target;
      const result = await site.stock(form.mode, project.value, rows, values);
      toast(`${action.value.label}: ${result.name}`);
      await load();
      reload();
    }
    form.open = false;
  } catch (e) {
    toast(e.message, "error", 9000);
  } finally {
    busy.value = false;
  }
}

async function stop(request) {
  try {
    await site.stopRequest(request.name);
    toast(`Đã dừng ${request.name}`);
    await load();
  } catch (e) {
    toast(e.message, "error");
  }
}

const stopSent = onSent((item) => {
  if (item.kind !== "material-request" || item.payload.project !== project.value) return;
  toast("Đã gửi đề xuất vật tư");
  load();
});
onBeforeUnmount(stopSent);
onMounted(load);
</script>

<template>
  <p v-if="error" class="rounded-md bg-danger-soft px-3 py-2 text-sm text-danger" role="alert">{{ error }}</p>
  <div v-else-if="data" class="space-y-4" data-materials>
    <section class="card p-4" aria-labelledby="store-title">
      <div class="flex flex-wrap items-center gap-2">
        <h2 id="store-title" class="m-0 flex-1 text-sm font-semibold">
          <Icon name="warehouse" :size="16" class="mr-1 inline" />
          {{ data.store ? `Kho công trường: ${data.store}` : "Dự án chưa có kho công trường" }}
        </h2>
        <span v-if="data.over_norm" class="badge badge-danger">{{ data.over_norm }} dòng vượt định mức</span>
      </div>
      <div class="mt-3 flex flex-wrap gap-2">
        <button v-if="!data.store && (can.manage || can.plan)" class="btn btn-primary" type="button" :disabled="busy" @click="createStore">
          <Icon name="plus" :size="16" /> Lập kho công trường
        </button>
        <button v-if="data.store && can.request" class="btn btn-primary" type="button" @click="open('request')">
          <Icon name="package" :size="16" /> Đề xuất vật tư
        </button>
        <template v-if="data.store && can.manage">
          <button v-for="(item, key) in STOCK_ACTIONS" :key="key" class="btn" type="button" @click="open(key)">
            <Icon :name="item.icon" :size="16" /> {{ item.label }}
          </button>
        </template>
        <button v-if="can.plan || can.manage" class="btn btn-ghost" type="button" @click="recompute"><Icon name="refresh-cw" :size="16" /> Tính lại kế hoạch</button>
      </div>
      <p v-for="item in queued" :key="item.id" class="m-0 mt-2 flex items-center gap-2 rounded-md border border-dashed border-warning bg-warning-soft p-2 text-sm">
        <Icon :name="item.state === 'sending' ? 'loader' : 'cloud-upload'" :size="16" :spin="item.state === 'sending'" />
        {{ item.state === "failed" ? `Không gửi được đề xuất: ${item.error}` : network.online ? "Đang gửi đề xuất…" : "Đề xuất đang chờ có mạng để gửi" }}
      </p>
    </section>

    <section v-if="openRequests.length" class="card p-4" aria-labelledby="requests-title">
      <h2 id="requests-title" class="m-0 text-sm font-semibold">Đề xuất chờ cấp phát</h2>
      <ul class="m-0 mt-2 list-none space-y-3 p-0">
        <li v-for="request in openRequests" :key="request.name" class="rounded-lg border border-line p-3" data-request>
          <div class="flex flex-wrap items-center gap-2 text-sm">
            <strong>{{ request.name }}</strong>
            <span class="badge badge-warning">{{ REQUEST_STATUS[request.status] || request.status }}</span>
            <span class="text-xs text-ink-muted">{{ request.requester }} · cần ngày {{ formatDate(request.schedule_date) }}</span>
          </div>
          <ul class="m-0 mt-1 list-none p-0 text-sm">
            <li v-for="line in request.lines" :key="line.name">{{ line.item_name }}: <strong>{{ qtyText(line.left, line.uom) }}</strong>
              <span class="text-xs text-ink-muted"> · {{ line.task_label }}</span></li>
          </ul>
          <div v-if="can.manage" class="mt-2 flex gap-2">
            <button class="btn btn-primary" type="button" @click="issueRequest(request)"><Icon name="send" :size="16" /> Cấp phát</button>
            <button class="btn btn-ghost" type="button" @click="stop(request)">Dừng</button>
          </div>
        </li>
      </ul>
    </section>

    <section class="card p-4" aria-labelledby="usage-title">
      <h2 id="usage-title" class="m-0 text-sm font-semibold">Vật tư theo công tác: định mức so với thực tế</h2>
      <p v-if="!groups.length" class="mt-2 text-sm text-ink-muted">Chưa có kế hoạch vật tư: công tác cần mã hiệu định mức có trong danh mục định mức.</p>
      <div v-for="group in groups" :key="group.task" class="mt-3" data-work>
        <h3 class="m-0 flex flex-wrap items-center gap-2 text-sm font-medium">{{ group.label }}
          <span v-if="group.over" class="badge badge-danger">Vượt định mức</span>
          <span v-else-if="group.ahead" class="badge badge-warning" title="Đã cấp nhiều hơn khối lượng đã làm cần: vật tư chờ ở mặt bằng, công tác chưa xong">Cấp trước khối lượng</span></h3>
        <div class="mt-1 overflow-x-auto">
          <table class="w-full min-w-[640px] text-sm">
            <thead><tr class="text-left text-xs text-ink-muted">
              <th class="py-1 pr-2">Vật tư</th><th class="px-2 text-right">Kế hoạch</th><th class="px-2 text-right">Đề xuất</th>
              <th class="px-2 text-right">Đã cấp</th><th class="px-2 text-right">Trả lại</th><th class="px-2 text-right">Đã dùng</th>
              <th class="px-2 text-right" title="Định mức nhân với khối lượng đã làm">Định mức KL đã làm</th><th class="px-2 text-right">Chênh lệch</th>
              <th v-if="can.finance" class="pl-2 text-right">Giá trị</th></tr></thead>
            <tbody>
              <tr v-for="row in group.rows" :key="row.item" class="border-t border-line" :class="{ 'bg-danger-soft': row.over_norm, 'bg-warning-soft': row.ahead }">
                <td class="py-1.5 pr-2">{{ row.item_name }}<span class="block text-xs text-ink-muted">{{ row.uom }}</span></td>
                <td class="px-2 text-right">{{ qtyText(row.planned) }}</td>
                <td class="px-2 text-right">{{ qtyText(row.requested) }}</td>
                <td class="px-2 text-right">{{ qtyText(row.issued) }}</td>
                <td class="px-2 text-right">{{ qtyText(row.returned) }}</td>
                <td class="px-2 text-right font-medium">{{ qtyText(row.used) }}</td>
                <td class="px-2 text-right">{{ row.norm_done === null ? "—" : qtyText(row.norm_done) }}</td>
                <td class="px-2 text-right" :class="row.over_norm ? 'font-semibold text-danger' : row.ahead ? 'text-warning' : ''">{{ row.gap === null ? "—" : qtyText(row.gap) }}</td>
                <td v-if="can.finance" class="pl-2 text-right">{{ moneyText(row.value, { short: true }) }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </section>

    <section v-if="data.store" class="card p-4" aria-labelledby="stock-title">
      <h2 id="stock-title" class="m-0 text-sm font-semibold">Tồn kho công trường</h2>
      <p v-if="!data.stock.length" class="mt-2 text-sm text-ink-muted">Kho chưa có vật tư.</p>
      <table v-else class="mt-2 w-full text-sm">
        <tbody>
          <tr v-for="row in data.stock" :key="row.item" class="border-t border-line first:border-0">
            <td class="py-1.5">{{ row.item_name }}</td>
            <td class="text-right font-medium">{{ qtyText(row.qty, row.uom) }}</td>
            <td v-if="can.finance" class="pl-2 text-right text-xs text-ink-muted">{{ moneyText(row.value, { short: true }) }}</td>
          </tr>
        </tbody>
      </table>
    </section>

    <section v-if="data.entries.length" class="card p-4" aria-labelledby="entries-title">
      <h2 id="entries-title" class="m-0 text-sm font-semibold">Phiếu kho gần đây</h2>
      <ul class="m-0 mt-2 list-none space-y-1 p-0 text-sm">
        <li v-for="entry in data.entries.slice(0, 15)" :key="entry.name">
          <span class="badge badge-muted">{{ entry.pmc_kind }}</span> {{ formatDate(entry.posting_date) }} · {{ entry.name }}:
          {{ entry.lines.map((l) => `${l.item_name} ${qtyText(l.transfer_qty, l.stock_uom)}`).join(", ") }}
        </li>
      </ul>
    </section>
  </div>

  <Drawer :open="form.open" :title="action.label" width="560px" @close="form.open = false">
    <form id="stock-form" class="space-y-3" @submit.prevent="save">
      <div v-for="(line, index) in form.lines" :key="index" class="space-y-2 rounded-lg border border-line p-3" data-line>
        <div>
          <label class="label" :for="`line-item-${index}`">Vật tư</label>
          <select :id="`line-item-${index}`" v-model="line.item" class="input" @change="pickItem(line)">
            <option value="">Chọn vật tư</option>
            <option v-for="item in data?.items || []" :key="item.name" :value="item.name">{{ item.item_name }} ({{ item.stock_uom }})</option>
          </select>
        </div>
        <div v-if="action.task || form.mode === 'write_off'">
          <label class="label" :for="`line-task-${index}`">Công tác{{ action.task ? "" : " (nếu có)" }}</label>
          <select :id="`line-task-${index}`" v-model="line.task" class="input">
            <option value="">{{ action.task ? "Chọn công tác" : "Không gắn công tác" }}</option>
            <option v-for="work in works" :key="work.name" :value="work.name">{{ work.pm_wbs_code }} {{ work.subject }}</option>
          </select>
        </div>
        <div class="grid grid-cols-2 gap-2">
          <div><label class="label" :for="`line-qty-${index}`">Số lượng{{ line.uom ? ` (${line.uom})` : "" }}</label>
            <input :id="`line-qty-${index}`" v-model="line.qty" class="input" inputmode="decimal" /></div>
          <div v-if="action.rate"><label class="label" :for="`line-rate-${index}`">Đơn giá (đ)</label>
            <input :id="`line-rate-${index}`" v-model="line.rate" class="input" inputmode="decimal" /></div>
        </div>
        <button v-if="form.lines.length > 1" class="btn btn-ghost text-danger" type="button" @click="form.lines.splice(index, 1)">Bỏ dòng</button>
      </div>
      <button class="btn" type="button" @click="form.lines.push(blank())"><Icon name="plus" :size="16" /> Thêm dòng</button>
      <div v-if="action.target">
        <label class="label" for="stock-target">Dự án nhận</label>
        <select id="stock-target" v-model="form.target" class="input">
          <option value="">Chọn dự án</option>
          <option v-for="item in projects" :key="item.name" :value="item.name">{{ item.project_name }}</option>
        </select>
      </div>
      <div v-if="form.mode === 'request'"><label class="label" for="stock-needed">Cần ngày</label>
        <input id="stock-needed" v-model="form.neededBy" class="input" type="date" :min="today()" /></div>
      <div v-else><label class="label" for="stock-date">Ngày phiếu</label>
        <input id="stock-date" v-model="form.date" class="input" type="date" :max="today()" /></div>
      <div><label class="label" for="stock-note">{{ action.note ? "Lý do" : "Ghi chú" }}</label>
        <textarea id="stock-note" v-model="form.note" class="input" rows="2"></textarea></div>
    </form>
    <template #footer>
      <button class="btn" type="button" @click="form.open = false">Hủy</button>
      <button class="btn btn-primary" type="submit" form="stock-form" :disabled="busy"><Icon v-if="busy" name="loader" :size="16" spin /> {{ form.mode === "request" ? "Gửi đề xuất" : action.label }}</button>
    </template>
  </Drawer>
</template>
