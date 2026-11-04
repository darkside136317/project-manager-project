<script setup>
import { onMounted, reactive, ref } from "vue";
import { useRouter } from "vue-router";
import Drawer from "../components/Drawer.vue";
import EmptyState from "../components/EmptyState.vue";
import Icon from "../components/Icon.vue";
import PageHeader from "../components/PageHeader.vue";
import { api } from "../lib/api.js";
import { templateStateBadge } from "../lib/forms.js";
import { toast } from "../lib/toast.js";

// /pm/bieu-mau-mau — the forms people can fill in, each with its versions; a new form starts as a draft.
const router = useRouter();
const rows = ref([]);
const loading = ref(false);
const error = ref("");
const creating = ref(false);
const saving = ref(false);
const form = reactive({ code: "", title: "", category: "" });

async function load() {
  loading.value = true;
  try {
    rows.value = (await api.forms.templates()).rows;
  } catch (e) {
    error.value = e.message;
  } finally {
    loading.value = false;
  }
}

async function create() {
  saving.value = true;
  try {
    const doc = await api.forms.templateCreate(form.code, { title: form.title, category: form.category });
    router.push(`/bieu-mau-mau/${encodeURIComponent(doc.name)}`);
  } catch (e) {
    toast(e.message, "error", 7000);
  } finally {
    saving.value = false;
  }
}

const main = (row) => row.draft || row.active || row.versions[0].name;

onMounted(load);
</script>

<template>
  <PageHeader title="Mẫu biểu mẫu" subtitle="Thiết kế biểu mẫu để điền theo dự án, công việc. Sửa mẫu đang dùng là tạo phiên bản mới; bản đã nộp không bị ảnh hưởng.">
    <button class="btn btn-primary" type="button" @click="creating = true"><Icon name="plus" :size="16" /> Tạo mẫu</button>
  </PageHeader>

  <p v-if="error" class="rounded-md bg-danger-soft px-3 py-2 text-sm text-danger" role="alert">{{ error }}</p>
  <EmptyState v-else-if="!loading && !rows.length" icon="clipboard-list" title="Chưa có mẫu nào" />
  <ul class="m-0 list-none space-y-2 p-0">
    <li v-for="row in rows" :key="row.code" class="card px-4 py-3">
      <div class="flex flex-wrap items-center gap-2">
        <RouterLink :to="`/bieu-mau-mau/${encodeURIComponent(main(row))}`" class="font-semibold text-ink no-underline hover:underline">{{ row.title }}</RouterLink>
        <span class="text-xs text-ink-muted">{{ row.code }}<template v-if="row.category"> · {{ row.category }}</template></span>
      </div>
      <ul class="m-0 mt-2 flex list-none flex-wrap gap-2 p-0">
        <li v-for="version in row.versions" :key="version.name">
          <RouterLink :to="`/bieu-mau-mau/${encodeURIComponent(version.name)}`" class="flex items-center gap-1.5 rounded-lg border border-line px-2 py-1 text-xs text-ink no-underline hover:bg-surface-muted">
            v{{ version.version }} <span :class="templateStateBadge(version.status)">{{ version.status }}</span>
            <span v-if="version.submissions" class="text-ink-muted">{{ version.submissions }} bản nộp</span>
          </RouterLink>
        </li>
      </ul>
    </li>
  </ul>

  <Drawer :open="creating" title="Tạo mẫu biểu mẫu" @close="creating = false">
    <form id="new-template" class="space-y-4" @submit.prevent="create">
      <div><label class="label" for="t-title">Tên biểu mẫu *</label><input id="t-title" v-model="form.title" class="input" required /></div>
      <div>
        <label class="label" for="t-code">Mã mẫu *</label>
        <input id="t-code" v-model="form.code" class="input" required placeholder="NT-CV" />
        <p class="mt-1 text-xs text-ink-muted">Chữ không dấu, số và gạch nối. Mã không đổi qua các phiên bản.</p>
      </div>
      <div><label class="label" for="t-category">Nhóm</label><input id="t-category" v-model="form.category" class="input" placeholder="Nghiệm thu, An toàn, Kiểm tra..." /></div>
    </form>
    <template #footer>
      <button class="btn" type="button" @click="creating = false">Hủy</button>
      <button class="btn btn-primary" type="submit" form="new-template" :disabled="saving">Tạo</button>
    </template>
  </Drawer>
</template>
