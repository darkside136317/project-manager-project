<script setup>
import { computed, inject, onMounted, reactive, ref } from "vue";
import ConfirmDialog from "@pm/components/ConfirmDialog.vue";
import Drawer from "@pm/components/Drawer.vue";
import EmptyState from "@pm/components/EmptyState.vue";
import Icon from "@pm/components/Icon.vue";
import { formatDateTime } from "@pm/lib/format.js";
import { toast } from "@pm/lib/toast.js";
import { BOQ_TONE, boqRows, construction, moneyText, percentText, qtyText, share } from "./construction.js";

// BOQ of a project: its imported versions, the one in force with what has been done and accepted on each line, and
// importing a new version from Excel (shown first, then kept as a draft until approved: approving updates the WBS).
const { name: project, openTask, reload } = inject("project");
const data = ref(null);
const detail = ref(null);
const selected = ref("");
const loading = ref(false);
const approving = ref(false);
const asking = ref(false);
const upload = reactive({ open: false, busy: false, content: "", filename: "", preview: null, title: "", note: "", error: "" });

const rows = computed(() => boqRows(detail.value?.items || []));
const inForce = computed(() => detail.value?.status === "Đã duyệt");
const summary = computed(() => data.value?.summary || {});

async function load(keep = false) {
  loading.value = true;
  try {
    data.value = await construction.boqVersions(project.value);
    const versions = data.value.versions;
    if (!keep || !versions.some((v) => v.name === selected.value)) {
      selected.value = (versions.find((v) => v.status === "Đã duyệt") || versions[0])?.name || "";
    }
    detail.value = selected.value ? await construction.boqDetail(selected.value) : null;
  } catch (e) {
    toast(e.message, "error", 7000);
  } finally {
    loading.value = false;
  }
}

async function choose(name) {
  selected.value = name;
  detail.value = await construction.boqDetail(name).catch((e) => toast(e.message, "error"));
}

function start() {
  Object.assign(upload, { open: true, busy: false, content: "", filename: "", preview: null, title: "", note: "", error: "" });
}

function onFile(event) {
  const file = event.target.files?.[0];
  if (!file) return;
  upload.filename = file.name;
  upload.preview = null;
  upload.error = "";
  const reader = new FileReader();
  reader.onload = async () => {
    upload.content = String(reader.result);
    upload.busy = true;
    try {
      upload.preview = await construction.boqPreview(project.value, upload.content);
      upload.title = upload.title || `BOQ bản ${upload.preview.next_version}`;
    } catch (e) {
      upload.error = e.message;
    } finally {
      upload.busy = false;
    }
  };
  reader.readAsDataURL(file);
}

async function save() {
  upload.busy = true;
  try {
    const version = await construction.boqUpload(project.value, upload.content, { filename: upload.filename, title: upload.title, note: upload.note });
    upload.open = false;
    toast(`Đã nhập ${version.title}: chờ duyệt`);
    selected.value = version.name;
    await load(true);
  } catch (e) {
    upload.error = e.message;
  } finally {
    upload.busy = false;
  }
}

async function approve() {
  asking.value = false;
  approving.value = true;
  try {
    const result = await construction.boqApprove(detail.value.name);
    const { created, updated, missing } = result.sync;
    toast(`Đã duyệt: thêm ${created} hạng mục, công tác; cập nhật ${updated}${missing.length ? `; ${missing.length} dòng không còn trong BOQ` : ""}`, "success", 8000);
    await load(true);
    reload();
  } catch (e) {
    toast(e.message, "error", 8000);
  } finally {
    approving.value = false;
  }
}

onMounted(load);
</script>

<template>
  <div class="space-y-4">
    <section class="grid gap-3 sm:grid-cols-3" aria-label="Giá trị theo BOQ">
      <div class="card p-3">
        <p class="m-0 text-xs text-ink-muted">Giá trị dự toán</p>
        <p class="m-0 mt-1 text-lg font-semibold">{{ moneyText(summary.planned_value, { short: true }) }}</p>
        <p class="m-0 text-xs text-ink-muted">{{ summary.works || 0 }} công tác</p>
      </div>
      <div class="card p-3">
        <p class="m-0 text-xs text-ink-muted">Đã thi công</p>
        <p class="m-0 mt-1 text-lg font-semibold">{{ percentText(summary.done_percent) }}</p>
        <p class="m-0 text-xs text-ink-muted">{{ moneyText(summary.done_value, { short: true }) }}</p>
      </div>
      <div class="card p-3">
        <p class="m-0 text-xs text-ink-muted">Đã nghiệm thu</p>
        <p class="m-0 mt-1 text-lg font-semibold">{{ percentText(summary.accepted_percent) }}</p>
        <p class="m-0 text-xs text-ink-muted">{{ moneyText(summary.accepted_value, { short: true }) }}</p>
      </div>
    </section>

    <div class="flex flex-wrap items-center gap-2">
      <div v-if="data?.versions.length" class="flex flex-wrap gap-1" role="group" aria-label="Phiên bản BOQ">
        <button v-for="version in data.versions" :key="version.name" type="button" class="rounded-full border px-3 py-1 text-xs"
          :class="selected === version.name ? 'border-primary bg-primary text-white' : 'border-line text-ink-soft'" :aria-pressed="selected === version.name"
          @click="choose(version.name)">Bản {{ version.version_no }} · {{ version.status }}</button>
      </div>
      <a class="btn btn-ghost ml-auto px-2 text-sm" :href="construction.boqTemplateUrl()"><Icon name="download" :size="16" /> Tải mẫu BOQ</a>
      <button v-if="data?.can.plan" type="button" class="btn btn-primary" @click="start"><Icon name="file-up" :size="16" /> Nhập BOQ từ Excel</button>
    </div>

    <EmptyState v-if="data && !data.versions.length" icon="sheet" title="Chưa có BOQ"
      text="Nhập bảng khối lượng dự toán từ Excel. Khi duyệt, hệ thống tạo hạng mục và công tác có khối lượng, đơn giá; tiến độ dự án tính theo giá trị dự toán." />

    <section v-if="detail" class="space-y-3" :aria-label="detail.title">
      <div class="flex flex-wrap items-center gap-2">
        <h3 class="m-0 text-base font-semibold">{{ detail.title }}</h3>
        <span class="badge" :class="BOQ_TONE[detail.status]">{{ detail.status }}</span>
        <span class="text-xs text-ink-muted">{{ detail.item_count }} công tác · {{ moneyText(detail.total_value) }} · nhập {{ formatDateTime(detail.imported_on) }}{{ detail.source_file ? ` từ ${detail.source_file}` : "" }}</span>
      </div>
      <div v-if="detail.can.approve" class="flex flex-wrap items-center gap-3 rounded-lg border border-warning bg-warning-soft p-3 text-sm">
        <p class="m-0 flex-1">Bản nháp: chưa ảnh hưởng tới công việc. Duyệt thì danh sách hạng mục, công tác và khối lượng của dự án đi theo bản này.</p>
        <button type="button" class="btn btn-primary" :disabled="approving" @click="asking = true">
          <Icon :name="approving ? 'loader' : 'badge-check'" :size="16" :spin="approving" /> Duyệt bản này
        </button>
      </div>
      <div class="overflow-x-auto rounded-lg border border-line">
        <table class="w-full min-w-[760px] text-sm">
          <thead class="bg-surface-muted text-left text-xs text-ink-muted">
            <tr><th class="px-2 py-2">STT</th><th class="px-2">Mã hiệu</th><th class="px-2">Nội dung công việc</th><th class="px-2">ĐV</th>
              <th class="px-2 text-right">Khối lượng</th><th class="px-2 text-right">Đơn giá</th><th class="px-2 text-right">Thành tiền</th>
              <th v-if="inForce" class="px-2">Đã làm</th></tr>
          </thead>
          <tbody>
            <tr v-for="row in rows" :key="row.line_no" class="border-t border-line" :class="row.is_group ? 'bg-surface-muted font-semibold' : ''">
              <td class="px-2 py-1.5 align-top">{{ row.code }}</td>
              <td class="px-2 align-top text-xs text-ink-muted">{{ row.norm_code }}</td>
              <td class="px-2 align-top" :style="{ paddingLeft: `${Math.max(0, row.level - 1) * 14 + 8}px` }">
                <button v-if="!row.is_group && row.task" type="button" class="text-left hover:underline" @click="openTask(row.task)">{{ row.description }}</button>
                <span v-else>{{ row.description }}</span>
              </td>
              <td class="px-2 align-top">{{ row.uom }}</td>
              <td class="px-2 text-right align-top">{{ row.is_group ? "" : qtyText(row.qty) }}</td>
              <td class="px-2 text-right align-top">{{ row.is_group ? "" : moneyText(row.unit_price) }}</td>
              <td class="px-2 text-right align-top">{{ moneyText(row.is_group ? row.total : row.amount) }}</td>
              <td v-if="inForce" class="px-2 align-top">
                <template v-if="!row.is_group">
                  <div class="h-1.5 w-24 overflow-hidden rounded-full bg-surface-muted"><div class="h-full bg-primary" :style="{ width: `${share(row.done_qty, row.qty)}%` }"></div></div>
                  <span class="text-xs text-ink-muted">{{ qtyText(row.done_qty) }}<span v-if="row.accepted_qty"> · NT {{ qtyText(row.accepted_qty) }}</span></span>
                </template>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>

    <Drawer :open="upload.open" title="Nhập BOQ từ Excel" width="720px" @close="upload.open = false">
      <div class="space-y-3">
        <p class="m-0 text-sm text-ink-soft">Tệp .xlsx có các cột STT, Mã hiệu, Nội dung công việc, Đơn vị, Khối lượng, Đơn giá, Thành tiền (tên cột viết khác vẫn nhận). Dòng không có khối lượng và đơn vị là hạng mục.</p>
        <div>
          <label class="label" for="boq-file">Tệp BOQ</label>
          <input id="boq-file" class="input" type="file" accept=".xlsx" @change="onFile" />
        </div>
        <p v-if="upload.busy && !upload.preview" class="m-0 text-sm text-ink-muted"><Icon name="loader" :size="14" spin /> Đang đọc tệp…</p>
        <p v-if="upload.error" class="m-0 whitespace-pre-line rounded-md bg-danger-soft p-2 text-sm text-danger" role="alert">{{ upload.error }}</p>
        <template v-if="upload.preview">
          <p class="m-0 text-sm"><strong>{{ upload.preview.sections }}</strong> hạng mục, <strong>{{ upload.preview.works }}</strong> công tác, tổng <strong>{{ moneyText(upload.preview.total) }}</strong></p>
          <ul v-if="upload.preview.issues.length" class="m-0 max-h-40 list-none space-y-1 overflow-y-auto rounded-md bg-warning-soft p-2 text-xs" aria-label="Cần xem lại">
            <li v-for="issue in upload.preview.issues" :key="issue.message">{{ issue.message }}</li>
          </ul>
          <div class="max-h-64 overflow-auto rounded-md border border-line">
            <table class="w-full min-w-[560px] text-xs">
              <tbody>
                <tr v-for="item in upload.preview.items.slice(0, 40)" :key="item.line_no" class="border-t border-line" :class="item.is_group ? 'font-semibold' : ''">
                  <td class="px-2 py-1">{{ item.code }}</td>
                  <td class="px-2" :style="{ paddingLeft: `${Math.max(0, item.level - 1) * 12 + 8}px` }">{{ item.description }}</td>
                  <td class="px-2">{{ item.uom }}</td>
                  <td class="px-2 text-right">{{ item.is_group ? "" : qtyText(item.qty) }}</td>
                  <td class="px-2 text-right">{{ item.is_group ? "" : moneyText(item.amount) }}</td>
                </tr>
              </tbody>
            </table>
          </div>
          <div>
            <label class="label" for="boq-title">Tên phiên bản</label>
            <input id="boq-title" v-model="upload.title" class="input" maxlength="140" />
          </div>
          <div>
            <label class="label" for="boq-note">Ghi chú</label>
            <input id="boq-note" v-model="upload.note" class="input" maxlength="1000" placeholder="Ví dụ: theo hồ sơ dự toán được duyệt ngày..." />
          </div>
          <div class="flex justify-end gap-2">
            <button type="button" class="btn" @click="upload.open = false">Hủy</button>
            <button type="button" class="btn btn-primary" :disabled="upload.busy" @click="save">
              <Icon :name="upload.busy ? 'loader' : 'save'" :size="16" :spin="upload.busy" /> Nhập bản {{ upload.preview.next_version }}
            </button>
          </div>
        </template>
      </div>
    </Drawer>

    <ConfirmDialog :open="asking" title="Duyệt BOQ?" confirm-text="Duyệt"
      message="Hạng mục và công tác của dự án sẽ đi theo bản này: dòng mới thành công việc mới, dòng đổi khối lượng hay đơn giá được cập nhật, dòng bị bỏ được báo lại (công việc cũ vẫn giữ). Tiến độ dự án tính theo giá trị dự toán."
      @confirm="approve" @cancel="asking = false" />
  </div>
</template>
