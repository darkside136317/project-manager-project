<script setup>
import { computed, inject, onMounted, reactive, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import Drawer from "../../components/Drawer.vue";
import EmptyState from "../../components/EmptyState.vue";
import Icon from "../../components/Icon.vue";
import { api } from "../../lib/api.js";
import { formatDate, formatDateTime } from "../../lib/format.js";
import { sizeText } from "../../lib/outbox.js";
import { toast } from "../../lib/toast.js";

// Tài liệu of a project: drawings, contracts, minutes... each with numbered versions. Whoever may change the
// project's data uploads; a project role with "Duyệt" approves a version, and the one approved before is replaced.
const { name: project, openTask } = inject("project");
const route = useRoute();
const router = useRouter();
const rows = ref([]);
const more = ref(false);
const categories = ref([]);
const can = ref({});
const loading = ref(false);
const filters = reactive({ category: "", search: "" });
const upload = reactive({ open: false, busy: false, title: "", category: "Bản vẽ", description: "", note: "", file: null, task: "", taskLabel: "", taskQuery: "", taskOptions: [] });
const open = ref(null);
const version = reactive({ busy: false, note: "", file: null, key: 0 });
const approving = ref(0);

const INLINE = /^(application\/pdf|image\/(jpeg|png|webp|gif))$/;
const canPreview = (type) => INLINE.test(type || "");

function stateOf(doc) {
  if (doc.status === "Đã duyệt") return { text: `Đã duyệt · bản ${doc.current_version}`, tone: "badge-success" };
  if (doc.approved_version) return { text: `Bản ${doc.current_version} chờ duyệt · đang dùng bản ${doc.approved_version}`, tone: "badge-warning" };
  return { text: `Nháp · bản ${doc.current_version}`, tone: "badge-muted" };
}
const versionTone = (status) => ({ "Đã duyệt": "badge-success", "Thay thế": "badge-muted", "Nháp": "badge-warning" })[status] || "badge-muted";

async function load(append = false) {
  loading.value = true;
  try {
    const result = await api.documents.list(project.value, { category: filters.category, search: filters.search, start: append ? rows.value.length : 0 });
    rows.value = append ? [...rows.value, ...result.documents] : result.documents;
    more.value = result.more;
    categories.value = result.categories;
    can.value = result.can;
  } catch (e) {
    toast(e.message, "error", 7000);
  } finally {
    loading.value = false;
  }
}

async function show(name) {
  try {
    open.value = await api.documents.detail(name);
    version.note = "";
    version.file = null;
    if (route.query["tai-lieu"] !== name) router.replace({ query: { ...route.query, "tai-lieu": name } });
  } catch (e) {
    toast(e.message, "error");
  }
}

function close() {
  open.value = null;
  const { "tai-lieu": _drop, ...rest } = route.query;
  router.replace({ query: rest });
}

let taskTimer = null;
function findTasks() {
  clearTimeout(taskTimer);
  taskTimer = setTimeout(async () => {
    try {
      upload.taskOptions = upload.taskQuery.trim() ? await api.schedule.searchTasks(project.value, upload.taskQuery) : [];
    } catch {
      upload.taskOptions = [];
    }
  }, 250);
}

function pickTask(option) {
  upload.task = option.value;
  upload.taskLabel = option.label;
  upload.taskOptions = [];
  upload.taskQuery = "";
}

function startUpload() {
  Object.assign(upload, { open: true, busy: false, title: "", category: categories.value.includes("Bản vẽ") ? "Bản vẽ" : categories.value[0] || "Khác",
    description: "", note: "", file: null, task: "", taskLabel: "", taskQuery: "", taskOptions: [] });
}

function onPick(event, target) {
  const file = event.target.files?.[0] || null;
  target.file = file;
  if (target === upload && file && !upload.title) upload.title = file.name.replace(/\.[^.]+$/, "");
}

async function create() {
  if (!upload.file) return toast("Chọn tệp cần tải lên", "warning");
  upload.busy = true;
  try {
    const form = new FormData();
    form.append("project", project.value);
    form.append("title", upload.title);
    form.append("category", upload.category);
    form.append("description", upload.description);
    form.append("note", upload.note);
    if (upload.task) form.append("task", upload.task);
    form.append("file", upload.file, upload.file.name);
    const doc = await api.documents.create(form);
    upload.open = false;
    toast("Đã tải lên tài liệu");
    await load();
    show(doc.name);
  } catch (e) {
    toast(e.message, "error", 8000);
  } finally {
    upload.busy = false;
  }
}

async function addVersion() {
  if (!version.file) return toast("Chọn tệp của bản mới", "warning");
  version.busy = true;
  try {
    const form = new FormData();
    form.append("name", open.value.name);
    form.append("note", version.note);
    form.append("file", version.file, version.file.name);
    open.value = await api.documents.addVersion(form);
    version.file = null;
    version.note = "";
    version.key += 1;  // a fresh file input: the old one would still show the uploaded file's name
    toast(`Đã tải lên bản ${open.value.current_version}`);
    load();
  } catch (e) {
    toast(e.message, "error", 8000);
  } finally {
    version.busy = false;
  }
}

async function approve(number) {
  approving.value = number;
  try {
    open.value = await api.documents.approve(open.value.name, number);
    toast(`Đã duyệt bản ${number}`);
    load();
  } catch (e) {
    toast(e.message, "error", 7000);
  } finally {
    approving.value = 0;
  }
}

const hasFilters = computed(() => Boolean(filters.category || filters.search));
let searchTimer = null;
watch(() => filters.search, () => { clearTimeout(searchTimer); searchTimer = setTimeout(() => load(), 300); });
watch(() => filters.category, () => load());
onMounted(async () => {
  await load();
  if (route.query["tai-lieu"]) show(route.query["tai-lieu"]);
});
</script>

<template>
  <div class="space-y-3">
    <div class="flex flex-wrap items-center gap-2">
      <label class="sr-only" for="doc-category">Loại tài liệu</label>
      <select id="doc-category" v-model="filters.category" class="input w-auto">
        <option value="">Mọi loại</option>
        <option v-for="item in categories" :key="item" :value="item">{{ item }}</option>
      </select>
      <label class="sr-only" for="doc-search">Tìm tài liệu</label>
      <input id="doc-search" v-model="filters.search" class="input min-w-0 flex-1 sm:max-w-xs" type="search" placeholder="Tìm theo tên tài liệu, tên tệp" />
      <button v-if="can.upload" type="button" class="btn btn-primary ml-auto" @click="startUpload"><Icon name="file-up" :size="16" /> Tải lên tài liệu</button>
    </div>

    <EmptyState v-if="!loading && !rows.length" icon="folder-open" :title="hasFilters ? 'Không có tài liệu khớp bộ lọc' : 'Chưa có tài liệu'"
      :text="hasFilters ? '' : 'Bản vẽ, hợp đồng, biên bản... của dự án, mỗi lần sửa là một bản mới.'" />

    <ul v-else class="m-0 list-none divide-y divide-line rounded-lg border border-line bg-surface p-0">
      <li v-for="doc in rows" :key="doc.name">
        <button type="button" class="flex w-full items-start gap-3 px-3 py-2.5 text-left hover:bg-surface-muted" @click="show(doc.name)">
          <Icon name="file-text" :size="20" class="mt-0.5 shrink-0 text-ink-muted" />
          <span class="min-w-0 flex-1">
            <span class="block truncate text-sm font-medium">{{ doc.title }}</span>
            <span class="mt-0.5 flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-ink-muted">
              <span class="badge badge-muted">{{ doc.category }}</span>
              <span class="badge" :class="stateOf(doc).tone">{{ stateOf(doc).text }}</span>
              <span class="truncate">{{ doc.file_name }} · {{ sizeText(doc.size_bytes) }}</span>
              <span>· {{ formatDate(doc.updated_on) }}</span>
              <span v-if="doc.task_label" class="truncate">· {{ doc.task_label }}</span>
            </span>
          </span>
        </button>
      </li>
    </ul>
    <div v-if="more" class="flex justify-center"><button type="button" class="btn" :disabled="loading" @click="load(true)">Xem thêm</button></div>

    <!-- upload -->
    <Drawer :open="upload.open" title="Tải lên tài liệu" @close="upload.open = false">
      <form class="space-y-3" @submit.prevent="create">
        <div>
          <label class="label" for="up-file">Tệp (tối đa 100 MB)</label>
          <input id="up-file" class="input" type="file" required @change="onPick($event, upload)" />
        </div>
        <div>
          <label class="label" for="up-title">Tên tài liệu</label>
          <input id="up-title" v-model="upload.title" class="input" required maxlength="140" />
        </div>
        <div>
          <label class="label" for="up-category">Loại</label>
          <select id="up-category" v-model="upload.category" class="input">
            <option v-for="item in categories" :key="item" :value="item">{{ item }}</option>
          </select>
        </div>
        <div class="relative">
          <label class="label" for="up-task">Gắn với công việc (không bắt buộc)</label>
          <p v-if="upload.task" class="m-0 flex items-center gap-2 text-sm">{{ upload.taskLabel }}
            <button type="button" class="text-xs underline" @click="upload.task = ''">Bỏ</button></p>
          <input v-else id="up-task" v-model="upload.taskQuery" class="input" placeholder="Gõ mã hoặc tên công việc" autocomplete="off" @input="findTasks" />
          <ul v-if="upload.taskOptions.length" class="absolute left-0 right-0 z-30 m-0 mt-1 max-h-56 list-none overflow-y-auto rounded-md border border-line bg-surface p-1 shadow-pop">
            <li v-for="option in upload.taskOptions" :key="option.value">
              <button type="button" class="block w-full rounded px-2 py-1.5 text-left text-sm hover:bg-surface-muted" @click="pickTask(option)">{{ option.label }}</button>
            </li>
          </ul>
          <p class="m-0 mt-1 text-xs text-ink-muted">Tài liệu gắn với công việc chỉ người xem được công việc đó mới thấy.</p>
        </div>
        <div>
          <label class="label" for="up-description">Mô tả</label>
          <textarea id="up-description" v-model="upload.description" class="input" rows="2" maxlength="2000"></textarea>
        </div>
        <div>
          <label class="label" for="up-note">Ghi chú bản 1</label>
          <input id="up-note" v-model="upload.note" class="input" maxlength="1000" />
        </div>
        <div class="flex justify-end gap-2">
          <button type="button" class="btn" @click="upload.open = false">Hủy</button>
          <button type="submit" class="btn btn-primary" :disabled="upload.busy"><Icon :name="upload.busy ? 'loader' : 'upload'" :size="16" :spin="upload.busy" /> {{ upload.busy ? "Đang tải lên…" : "Tải lên" }}</button>
        </div>
      </form>
    </Drawer>

    <!-- one document -->
    <Drawer :open="Boolean(open)" :title="open?.title || ''" width="640px" @close="close">
      <div v-if="open" class="space-y-4">
        <div class="flex flex-wrap items-center gap-2 text-sm">
          <span class="badge badge-muted">{{ open.category }}</span>
          <span class="badge" :class="stateOf(open).tone">{{ stateOf(open).text }}</span>
          <button v-if="open.task" type="button" class="text-primary underline" @click="openTask(open.task)">{{ open.task_label }}</button>
        </div>
        <p v-if="open.description" class="m-0 whitespace-pre-line text-sm text-ink-soft">{{ open.description }}</p>

        <section aria-labelledby="versions-title">
          <h3 id="versions-title" class="m-0 mb-2 text-sm font-semibold">Các bản</h3>
          <ol class="m-0 list-none space-y-2 p-0">
            <li v-for="row in open.versions" :key="row.version_no" class="rounded-lg border border-line p-2.5 text-sm">
              <div class="flex flex-wrap items-center gap-2">
                <strong>Bản {{ row.version_no }}</strong>
                <span class="badge" :class="versionTone(row.status)">{{ row.status }}</span>
                <span class="min-w-0 truncate text-ink-muted">{{ row.file_name }} · {{ sizeText(row.size_bytes) }}</span>
              </div>
              <p class="m-0 mt-1 text-xs text-ink-muted">Tải lên: {{ row.uploaded_by_name }} · {{ formatDateTime(row.uploaded_on) }}
                <span v-if="row.approved_by"> · Duyệt: {{ row.approved_by_name }} · {{ formatDateTime(row.approved_on) }}</span></p>
              <p v-if="row.note" class="m-0 mt-1 text-ink-soft">{{ row.note }}</p>
              <div class="mt-2 flex flex-wrap gap-2">
                <a v-if="canPreview(row.content_type)" class="btn btn-ghost px-2 text-xs" :href="api.documents.url(open.name, row.version_no, true)" target="_blank" rel="noopener"><Icon name="eye" :size="14" /> Xem</a>
                <a class="btn btn-ghost px-2 text-xs" :href="api.documents.url(open.name, row.version_no)"><Icon name="download" :size="14" /> Tải về</a>
                <button v-if="open.can.approve && row.status === 'Nháp' && row.version_no > (open.approved_version || 0)" type="button" class="btn btn-primary px-2 text-xs"
                  :disabled="Boolean(approving)" @click="approve(row.version_no)">
                  <Icon :name="approving === row.version_no ? 'loader' : 'badge-check'" :size="14" :spin="approving === row.version_no" /> Duyệt bản này
                </button>
              </div>
            </li>
          </ol>
        </section>

        <form v-if="open.can.upload" class="space-y-2 rounded-lg border border-dashed border-line p-3" @submit.prevent="addVersion">
          <h3 class="m-0 text-sm font-semibold">Tải lên bản {{ open.current_version + 1 }}</h3>
          <input :key="version.key" class="input" type="file" aria-label="Tệp của bản mới" @change="onPick($event, version)" />
          <input v-model="version.note" class="input" maxlength="1000" placeholder="Sửa gì so với bản trước" aria-label="Ghi chú bản mới" />
          <div class="flex justify-end">
            <button type="submit" class="btn btn-primary" :disabled="version.busy || !version.file"><Icon :name="version.busy ? 'loader' : 'upload'" :size="16" :spin="version.busy" /> Tải lên bản mới</button>
          </div>
        </form>
      </div>
    </Drawer>
  </div>
</template>
