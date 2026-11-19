<script setup>
import { inject, onMounted, ref } from "vue";
import EmptyState from "@pm/components/EmptyState.vue";
import { toast, toastError } from "@pm/lib/toast.js";
import { archive, periodText, retentionText, stateClass, FILED, RESTRICTED, WAITING } from "./archive.js";

// Hồ sơ lưu trữ of a project: its files by category, what is still missing, "Cập nhật hồ sơ" for the manager, "Nộp lưu"
// for the company's archivist. A file opens on its own page (/pm/luu-tru/<file>).
const { name: project } = inject("project");
const data = ref(null);
const error = ref("");
const busy = ref(false);

async function load() {
  try {
    data.value = await archive.overview(project.value);
    error.value = "";
  } catch (e) {
    error.value = e.message;
  }
}

async function compileFiles() {
  busy.value = true;
  try {
    const result = await archive.compile(project.value);
    toast(result.added ? `Đã xếp thêm ${result.added} tài liệu vào hồ sơ` : "Không có tài liệu mới để xếp");
    await load();
  } catch (e) {
    toastError(e.message);
  } finally {
    busy.value = false;
  }
}

async function requestFiling() {
  busy.value = true;
  try {
    const result = await archive.requestFiling(project.value);
    toast(`${result.waiting} hồ sơ chờ người lưu trữ nộp lưu`);
    await load();
  } catch (e) {
    toastError(e.message);
  } finally {
    busy.value = false;
  }
}

async function fileAll() {
  const names = data.value.files.filter((f) => f.status === WAITING && f.item_count).map((f) => f.name);
  if (!names.length) return;
  busy.value = true;
  try {
    const result = await archive.fileRecords(names);
    toast(`Đang nộp lưu ${result.queued.length} hồ sơ (tính SHA-256 từng tài liệu)`);
    await load();
  } catch (e) {
    toastError(e.message);
  } finally {
    busy.value = false;
  }
}

onMounted(load);
</script>

<template>
  <p v-if="error" class="rounded-md bg-surface-muted px-3 py-2 text-sm text-ink-muted" role="status" data-archive-error>{{ error }}</p>
  <div v-else-if="data" class="space-y-4" data-archive-tab>
    <div class="flex flex-wrap items-center justify-between gap-3">
      <div class="flex flex-wrap gap-2 text-sm">
        <span v-for="(count, state) in data.counts" :key="state" :class="stateClass(state)">{{ state }}: {{ count }}</span>
      </div>
      <div class="flex flex-wrap gap-2">
        <button v-if="data.can.manage" class="btn" type="button" :disabled="busy" data-compile @click="compileFiles">Cập nhật hồ sơ</button>
        <button v-if="data.can.request" class="btn" type="button" :disabled="busy" data-request @click="requestFiling">Đề nghị nộp lưu</button>
        <button v-if="data.can.file && data.files.some((f) => f.status === WAITING)" class="btn btn-primary" type="button"
                :disabled="busy" data-file-all @click="fileAll">Nộp lưu các hồ sơ chờ</button>
      </div>
    </div>

    <div v-if="data.missing.length" class="rounded-md border border-warning bg-warning-soft px-3 py-2 text-sm" data-missing>
      <strong>Còn thiếu:</strong> {{ data.missing.map((m) => `${m.code} ${m.title}`).join(", ") }}
      <span class="block text-xs text-ink-muted">Danh mục bắt buộc chưa có tài liệu nào. Thêm tài liệu dự án, biểu mẫu, hoặc tải bản scan vào hồ sơ.</span>
    </div>

    <EmptyState v-if="!data.files.length" icon="archive" title="Chưa có hồ sơ"
                text="Bấm Cập nhật hồ sơ: tài liệu đã duyệt, biểu mẫu đã duyệt và ảnh hiện trường được xếp vào hồ sơ theo danh mục." />
    <div v-else class="card overflow-x-auto">
      <table class="w-full min-w-[720px] text-sm">
        <thead><tr class="border-b border-line text-left text-xs text-ink-muted">
          <th class="px-4 py-2">Số hồ sơ</th><th class="px-2">Tiêu đề</th><th class="px-2">Thời gian</th>
          <th class="px-2 text-right">Tài liệu</th><th class="px-2">Bảo quản</th><th class="px-4">Trạng thái</th></tr></thead>
        <tbody>
          <tr v-for="file in data.files" :key="file.name" class="border-b border-line last:border-0" data-archive-file>
            <td class="px-4 py-2 font-medium"><RouterLink :to="`/luu-tru/${encodeURIComponent(file.name)}`">{{ file.file_number }}</RouterLink></td>
            <td class="px-2">{{ file.title }}
              <span class="block text-xs text-ink-muted">{{ file.category_label }}<template v-if="file.access_mode === RESTRICTED"> · Hạn chế</template>
                <template v-if="file.is_addendum"> · bổ sung</template></span></td>
            <td class="px-2">{{ periodText(file.start_date, file.end_date) }}</td>
            <td class="px-2 text-right">{{ file.item_count }}</td>
            <td class="px-2">{{ retentionText(file.retention) }}</td>
            <td class="px-4"><span :class="stateClass(file.status)">{{ file.status }}</span>
              <span v-if="file.status !== FILED && file.lock_error" class="block text-xs text-danger">{{ file.lock_error }}</span>
              <span v-else-if="file.status !== FILED && file.lock_total" class="block text-xs text-ink-muted">đang kiểm {{ file.lock_done || 0 }}/{{ file.lock_total }}</span></td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>
