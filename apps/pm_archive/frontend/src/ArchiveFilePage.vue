<script setup>
import { computed, onMounted, reactive, ref, watch } from "vue";
import { useRoute } from "vue-router";
import PageHeader from "@pm/components/PageHeader.vue";
import { pageTitle } from "@pm/lib/page.js";
import { downloadUrl } from "@pm/lib/reports.js";
import { toast, toastError } from "@pm/lib/toast.js";
import { archive, dayText, moved, periodText, placePath, retentionText, sizeText, stateClass, FILED } from "./archive.js";

// /pm/luu-tru/<file> — one archive file: its description, where the paper is, its items in order. Before filing the
// project's manager orders, describes, leaves out and moves items and adds scans; the archivist files it (Nộp lưu) and,
// once filed, builds its archive package (TT 05/2025/TT-BNV).
const route = useRoute();
const data = ref(null);
const error = ref("");
const busy = ref(false);
const storages = ref([]);
const paper = reactive({ storage: "", box: "", note: "" });
const editing = ref(null);
const values = reactive({ title: "", doc_number: "", doc_date: "", author: "", page_count: "", note: "" });
const scan = reactive({ file: null, title: "", doc_number: "", doc_date: "", author: "", page_count: "" });
const name = computed(() => route.params.name);
const file = computed(() => data.value?.file || {});
const catalogue = computed(() => ({ archive_file: name.value }));

async function load() {
  try {
    data.value = await archive.file(name.value);
    pageTitle.value = `${file.value.file_number} ${file.value.title}`;
    Object.assign(paper, { storage: file.value.storage || "", box: file.value.box || "", note: file.value.paper_note || "" });
    error.value = "";
  } catch (e) {
    error.value = e.message;
  }
}

async function run(action, message) {
  busy.value = true;
  try {
    await action();
    if (message) toast(message);
    await load();
  } catch (e) {
    toastError(e.message);
  } finally {
    busy.value = false;
  }
}

const step = (item, by) => run(() => archive.reorder(name.value, moved(data.value.items.map((i) => i.name), item.name, by)));
const toggle = (item) => run(() => archive.exclude(item.name, !item.excluded));
const moveTo = (item, target) => target && run(() => archive.move(item.name, target), "Đã chuyển tài liệu sang hồ sơ khác");
const savePaper = () => run(() => archive.setPaper(name.value, paper.storage || null, paper.box, paper.note), "Đã lưu chỗ để bản giấy");
const fileIt = () => run(() => archive.fileRecords([name.value]), "Đang nộp lưu: hệ thống kiểm SHA-256 từng tài liệu rồi khóa hồ sơ");
const buildPackage = () => run(() => archive.exportPackage(name.value), "Đang lập gói nộp lưu: có thông báo khi xong");

function edit(item) {
  editing.value = item.name;
  Object.assign(values, { title: item.title || "", doc_number: item.doc_number || "", doc_date: item.doc_date || "",
                          author: item.author || "", page_count: item.page_count || "", note: item.note || "" });
}

async function saveItem() {
  await run(() => archive.describe(editing.value, { ...values }), "Đã lưu");
  editing.value = null;
}

async function addScan() {
  if (!scan.file) return;
  const { file: upload, ...rest } = scan;
  await run(() => archive.upload(name.value, upload, rest), "Đã thêm tệp vào hồ sơ");
  Object.assign(scan, { file: null, title: "", doc_number: "", doc_date: "", author: "", page_count: "" });
}

onMounted(async () => {
  await load();
  try {
    storages.value = await archive.storages();
  } catch {
    storages.value = [];
  }
});
watch(name, load);
</script>

<template>
  <p v-if="error" class="rounded-md bg-surface-muted px-3 py-2 text-sm text-ink-muted" role="status" data-file-error>{{ error }}</p>
  <div v-else-if="data" data-archive-file-page>
    <PageHeader :title="`${file.file_number} · ${file.title}`" :subtitle="data.category ? `${data.category.code} ${data.category.title}` : ''">
      <span :class="stateClass(file.status)" data-file-status>{{ file.status }}</span>
      <a class="btn" :href="downloadUrl('muc-luc-van-ban', catalogue, 'xlsx')">Mục lục (Excel)</a>
      <RouterLink class="btn" :to="{ path: '/bao-cao/muc-luc-van-ban', query: catalogue }">Mục lục văn bản</RouterLink>
      <button v-if="data.can.file" class="btn btn-primary" type="button" :disabled="busy || !file.item_count" data-file-it @click="fileIt">Nộp lưu</button>
      <template v-if="data.can.export">
        <button class="btn" type="button" :disabled="busy" data-package @click="buildPackage">Lập gói nộp lưu</button>
        <a v-if="file.aip_on" class="btn" :href="archive.packageUrl(name)" data-package-download>Tải gói ({{ sizeText(file.aip_size) }})</a>
      </template>
    </PageHeader>

    <p v-if="file.lock_error && file.status !== FILED" class="mb-4 rounded-md bg-danger-soft px-3 py-2 text-sm text-danger">{{ file.lock_error }}</p>
    <p v-if="file.aip_error" class="mb-4 rounded-md bg-danger-soft px-3 py-2 text-sm text-danger">Lập gói không được: {{ file.aip_error }}</p>

    <div class="mb-4 grid gap-4 lg:grid-cols-3">
      <dl class="card grid grid-cols-2 gap-x-4 gap-y-2 p-4 text-sm lg:col-span-2">
        <dt class="text-ink-muted">Dự án</dt>
        <dd><RouterLink :to="`/du-an/${encodeURIComponent(file.project)}/ho-so-luu-tru`">{{ data.project.project_name }}</RouterLink></dd>
        <dt class="text-ink-muted">Thời gian</dt><dd>{{ periodText(file.start_date, file.end_date) || "—" }}</dd>
        <dt class="text-ink-muted">Số tài liệu, số tờ</dt><dd>{{ file.item_count }} tài liệu · {{ file.page_count || 0 }} tờ</dd>
        <dt class="text-ink-muted">Thời hạn bảo quản</dt>
        <dd>{{ retentionText(file.retention) }}<template v-if="file.expires_on"> (đến {{ dayText(file.expires_on) }})</template></dd>
        <dt class="text-ink-muted">Chế độ sử dụng</dt><dd>{{ file.access_mode }}</dd>
        <template v-if="file.status === FILED">
          <dt class="text-ink-muted">Nộp lưu</dt><dd>{{ dayText(file.locked_on) }} · {{ file.locked_by }}</dd>
          <dt class="text-ink-muted">SHA-256 của hồ sơ</dt><dd class="break-all font-mono text-xs" data-manifest>{{ file.manifest_sha256 }}</dd>
        </template>
      </dl>
      <form class="card space-y-2 p-4 text-sm" data-paper @submit.prevent="savePaper">
        <h2 class="m-0 text-sm font-semibold">Bản giấy</h2>
        <label class="block">Chỗ để
          <select v-model="paper.storage" class="input mt-1 block w-full" :disabled="!data.can.paper" data-paper-storage>
            <option value="">Chưa có</option>
            <option v-for="place in storages" :key="place.name" :value="place.name">{{ placePath(storages, place.name) }}</option>
          </select></label>
        <label class="block">Số hộp <input v-model="paper.box" class="input mt-1 block w-full" :disabled="!data.can.paper" data-paper-box /></label>
        <label class="block">Ghi chú <input v-model="paper.note" class="input mt-1 block w-full" :disabled="!data.can.paper" /></label>
        <button v-if="data.can.paper" class="btn" type="submit" :disabled="busy">Lưu chỗ để</button>
      </form>
    </div>

    <div class="card overflow-x-auto">
      <table class="w-full min-w-[760px] text-sm">
        <thead><tr class="border-b border-line text-left text-xs text-ink-muted">
          <th class="px-4 py-2">STT</th><th class="px-2">Trích yếu</th><th class="px-2">Số, ký hiệu · ngày · tác giả</th>
          <th class="px-2 text-right">Tờ</th><th class="px-2">Tệp</th><th v-if="data.can.edit" class="px-4 text-right">Sắp xếp</th></tr></thead>
        <tbody>
          <tr v-for="(item, index) in data.items" :key="item.name" class="border-b border-line last:border-0 align-top"
              :class="{ 'opacity-50': item.excluded }" data-item>
            <td class="px-4 py-2">{{ item.seq }}</td>
            <td class="px-2">{{ item.title }}<span class="block text-xs text-ink-muted">{{ item.kind }}<template v-if="item.note"> · {{ item.note }}</template>
              <template v-if="item.excluded"> · đã bỏ ra</template></span></td>
            <td class="px-2">{{ [item.doc_number, dayText(item.doc_date), item.author].filter(Boolean).join(" · ") }}</td>
            <td class="px-2 text-right">{{ item.page_count || "" }}</td>
            <td class="px-2"><a :href="archive.downloadUrl(item.name)" data-item-download>{{ item.file_name }}</a>
              <span class="block text-xs text-ink-muted">{{ sizeText(item.size_bytes) }}</span></td>
            <td v-if="data.can.edit" class="px-4 text-right whitespace-nowrap">
              <button class="btn btn-ghost px-2" type="button" :disabled="busy || index === 0" aria-label="Lên" @click="step(item, -1)">↑</button>
              <button class="btn btn-ghost px-2" type="button" :disabled="busy || index === data.items.length - 1" aria-label="Xuống" @click="step(item, 1)">↓</button>
              <button class="btn btn-ghost px-2" type="button" data-item-edit @click="edit(item)">Sửa</button>
              <button class="btn btn-ghost px-2" type="button" :disabled="busy" data-item-exclude @click="toggle(item)">{{ item.excluded ? "Đưa vào" : "Bỏ ra" }}</button>
              <select v-if="data.others.length" class="input mt-1 block text-xs" aria-label="Chuyển sang hồ sơ" @change="moveTo(item, $event.target.value)">
                <option value="">Chuyển sang…</option>
                <option v-for="other in data.others" :key="other.name" :value="other.name">{{ other.file_number }} {{ other.title }}</option>
              </select>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
    <p v-if="data.total > data.items.length" class="mt-2 text-xs text-ink-muted">Hiện {{ data.items.length }}/{{ data.total }} tài liệu đầu; mục lục văn bản có đủ.</p>

    <form v-if="editing" class="card mt-4 grid gap-3 p-4 text-sm sm:grid-cols-2" data-item-form @submit.prevent="saveItem">
      <label class="sm:col-span-2">Trích yếu <input v-model="values.title" class="input mt-1 block w-full" required /></label>
      <label>Số, ký hiệu <input v-model="values.doc_number" class="input mt-1 block w-full" /></label>
      <label>Ngày <input v-model="values.doc_date" class="input mt-1 block w-full" type="date" /></label>
      <label>Tác giả <input v-model="values.author" class="input mt-1 block w-full" /></label>
      <label>Số tờ <input v-model="values.page_count" class="input mt-1 block w-full" inputmode="numeric" /></label>
      <label class="sm:col-span-2">Ghi chú <input v-model="values.note" class="input mt-1 block w-full" /></label>
      <div class="flex gap-2 sm:col-span-2"><button class="btn btn-primary" type="submit" :disabled="busy">Lưu</button>
        <button class="btn" type="button" @click="editing = null">Thôi</button></div>
    </form>

    <form v-if="data.can.edit" class="card mt-4 grid gap-3 p-4 text-sm sm:grid-cols-2" data-scan @submit.prevent="addScan">
      <h2 class="m-0 text-sm font-semibold sm:col-span-2">Thêm tệp (bản scan, tài liệu ngoài hệ thống)</h2>
      <label class="sm:col-span-2">Tệp <input class="mt-1 block w-full" type="file" data-scan-file @change="scan.file = $event.target.files[0] || null" /></label>
      <label class="sm:col-span-2">Trích yếu <input v-model="scan.title" class="input mt-1 block w-full" placeholder="Để trống thì lấy tên tệp" /></label>
      <label>Số, ký hiệu <input v-model="scan.doc_number" class="input mt-1 block w-full" /></label>
      <label>Ngày <input v-model="scan.doc_date" class="input mt-1 block w-full" type="date" /></label>
      <label>Tác giả <input v-model="scan.author" class="input mt-1 block w-full" /></label>
      <label>Số tờ <input v-model="scan.page_count" class="input mt-1 block w-full" inputmode="numeric" /></label>
      <div class="sm:col-span-2"><button class="btn btn-primary" type="submit" :disabled="busy || !scan.file">Thêm vào hồ sơ</button></div>
    </form>
  </div>
</template>
