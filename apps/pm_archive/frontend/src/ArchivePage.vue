<script setup>
import { onMounted, reactive, ref } from "vue";
import EmptyState from "@pm/components/EmptyState.vue";
import PageHeader from "@pm/components/PageHeader.vue";
import { toast, toastError } from "@pm/lib/toast.js";
import { archive, dayText, periodText, retentionText, stateClass, STATES } from "./archive.js";

// /pm/luu-tru — every archive file the user may read, across projects: filters (state, year, text), the files waiting for
// the archivist, the last integrity check; "Kiểm tra toàn vẹn" for the archivist.
const filters = reactive({ status: "", year: "", search: "" });
const rows = ref([]);
const next = ref(null);
const info = ref(null);
const loading = ref(false);
const error = ref("");

async function load(more = false) {
  loading.value = true;
  try {
    const result = await archive.listing({ ...filters }, more ? next.value : null);
    rows.value = more ? [...rows.value, ...result.rows] : result.rows;
    next.value = result.next;
    info.value = result;
    error.value = "";
  } catch (e) {
    error.value = e.message;
  } finally {
    loading.value = false;
  }
}

function waitingOnly() {
  filters.status = "Chờ nộp lưu";
  load();
}

async function check() {
  try {
    await archive.startCheck();
    toast("Đã xếp lần kiểm tra toàn vẹn: kết quả có ở đây khi xong");
  } catch (e) {
    toastError(e.message);
  }
}

onMounted(() => load());
</script>

<template>
  <PageHeader title="Lưu trữ hồ sơ" subtitle="Hồ sơ lưu trữ của các dự án: đang lập, chờ nộp lưu, đã nộp lưu.">
    <RouterLink class="btn" :to="{ path: '/bao-cao/muc-luc-ho-so' }">Mục lục hồ sơ</RouterLink>
    <button v-if="info?.can.file" class="btn" type="button" data-check @click="check">Kiểm tra toàn vẹn</button>
  </PageHeader>

  <div v-if="info" class="mb-4 flex flex-wrap gap-3 text-sm">
    <button v-if="info.waiting" class="card px-4 py-2 text-left" type="button" data-waiting @click="waitingOnly">
      <span class="block text-xs text-ink-muted">Chờ nộp lưu</span><span class="text-lg font-semibold text-warning">{{ info.waiting }}</span>
    </button>
    <div v-if="info.last_check" class="card px-4 py-2" data-last-check>
      <span class="block text-xs text-ink-muted">Kiểm tra toàn vẹn gần nhất ({{ dayText(info.last_check.run_on) }})</span>
      <span :class="stateClass(info.last_check.status)">{{ info.last_check.status }}</span>
      <span class="ml-2">{{ info.last_check.checked }} tài liệu<template v-if="info.last_check.changed || info.last_check.missing">,
        {{ info.last_check.changed }} bị đổi, {{ info.last_check.missing }} bị mất</template></span>
    </div>
  </div>

  <form class="mb-4 flex flex-wrap items-end gap-3" @submit.prevent="load()">
    <label class="text-sm">Trạng thái
      <select v-model="filters.status" class="input mt-1 block" data-filter-status>
        <option value="">Tất cả</option><option v-for="state in STATES" :key="state">{{ state }}</option>
      </select></label>
    <label class="text-sm">Năm kết thúc <input v-model="filters.year" class="input mt-1 block w-28" inputmode="numeric" /></label>
    <label class="min-w-0 flex-1 text-sm">Tìm (tiêu đề, số hồ sơ, trích yếu)
      <input v-model="filters.search" class="input mt-1 block w-full" type="search" data-filter-search /></label>
    <button class="btn btn-primary" type="submit" :disabled="loading">Lọc</button>
  </form>

  <p v-if="error" class="rounded-md bg-surface-muted px-3 py-2 text-sm text-ink-muted" role="status">{{ error }}</p>
  <EmptyState v-else-if="!loading && !rows.length" icon="archive" title="Không có hồ sơ"
              text="Hồ sơ lưu trữ hình thành từ các dự án, ở tab Hồ sơ lưu trữ của từng dự án." />
  <div v-else class="card overflow-x-auto">
    <table class="w-full min-w-[760px] text-sm">
      <thead><tr class="border-b border-line text-left text-xs text-ink-muted">
        <th class="px-4 py-2">Số hồ sơ</th><th class="px-2">Tiêu đề</th><th class="px-2">Dự án</th><th class="px-2">Thời gian</th>
        <th class="px-2 text-right">Tài liệu</th><th class="px-2">Bảo quản</th><th class="px-4">Trạng thái</th></tr></thead>
      <tbody>
        <tr v-for="file in rows" :key="file.name" class="border-b border-line last:border-0" data-register-row>
          <td class="px-4 py-2 font-medium"><RouterLink :to="`/luu-tru/${encodeURIComponent(file.name)}`">{{ file.file_number }}</RouterLink></td>
          <td class="px-2">{{ file.title }}</td>
          <td class="px-2"><RouterLink :to="`/du-an/${encodeURIComponent(file.project)}/ho-so-luu-tru`">{{ file.project_name }}</RouterLink></td>
          <td class="px-2">{{ periodText(file.start_date, file.end_date) }}</td>
          <td class="px-2 text-right">{{ file.item_count }}</td>
          <td class="px-2">{{ retentionText(file.retention) }}<span v-if="file.expires_on" class="block text-xs text-ink-muted">đến {{ dayText(file.expires_on) }}</span></td>
          <td class="px-4"><span :class="stateClass(file.status)">{{ file.status }}</span></td>
        </tr>
      </tbody>
    </table>
  </div>
  <div v-if="next" class="mt-3 text-center"><button class="btn" type="button" :disabled="loading" @click="load(true)">Xem thêm</button></div>
</template>
