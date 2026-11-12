<script setup>
import { computed, ref, watch } from "vue";
import Drawer from "../../components/Drawer.vue";
import Icon from "../../components/Icon.vue";
import { api } from "../../lib/api.js";
import { toast } from "../../lib/toast.js";
import { fileToBase64 } from "../../lib/work.js";

// Nhập WBS từ Excel hoặc kế hoạch từ MS Project (XML): pick a file, see every row with its problems (nothing is
// written), then import it in one go.
const props = defineProps({ open: { type: Boolean, default: false }, project: { type: String, required: true },
  kind: { type: String, default: "excel" } });
const KINDS = {
  excel: { title: "Nhập công việc từ Excel", accept: ".xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    pickText: "Chọn tệp .xlsx", preview: (project, content) => api.wbs.importPreview(project, content),
    run: (project, content) => api.wbs.importRun(project, content),
    done: (r) => `Đã nhập ${r.tasks} công việc, giao ${r.assigned} người phụ trách` },
  msproject: { title: "Nhập kế hoạch từ MS Project", accept: ".xml,application/xml,text/xml", pickText: "Chọn tệp .xml",
    preview: (project, content) => api.wbs.msprojectPreview(project, content),
    run: (project, content) => api.wbs.msprojectRun(project, content),
    done: (r) => `Đã nhập ${r.tasks} công việc, ${r.links} phụ thuộc, giao ${r.assigned} người phụ trách${r.skipped?.length ? `; bỏ ${r.skipped.length} phụ thuộc không hợp lệ` : ""}` },
};
const spec = computed(() => KINDS[props.kind] || KINDS.excel);
const emit = defineEmits(["close", "done"]);

const content = ref("");
const fileName = ref("");
const preview = ref(null);
const busy = ref(false);
const error = ref("");
const problems = computed(() => (preview.value?.rows || []).filter((row) => row.errors.length || row.warnings.length));

watch(() => props.open, (open) => {
  if (open) {
    content.value = "";
    fileName.value = "";
    preview.value = null;
    error.value = "";
  }
});

async function pick(event) {
  const file = event.target.files?.[0];
  if (!file) return;
  fileName.value = file.name;
  busy.value = true;
  error.value = "";
  preview.value = null;
  try {
    content.value = await fileToBase64(file);
    preview.value = await spec.value.preview(props.project, content.value);
  } catch (e) {
    error.value = e.message;
  } finally {
    busy.value = false;
  }
}

async function run() {
  busy.value = true;
  try {
    const result = await spec.value.run(props.project, content.value);
    toast(spec.value.done(result), "success", 7000);
    emit("done");
  } catch (e) {
    error.value = e.message;
  } finally {
    busy.value = false;
  }
}
</script>

<template>
  <Drawer :open="open" :title="spec.title" width="720px" @close="emit('close')">
    <div class="space-y-4 text-sm" :data-import="kind">
      <p v-if="kind === 'msproject'" class="m-0 text-ink-soft">
        Tệp XML lưu từ MS Project (File → Save As → XML). Hệ thống nhập cây công việc, ngày kế hoạch, mốc, phụ thuộc
        (FS, SS, FF, SF và độ trễ) và người phụ trách khi tài nguyên của việc là thành viên dự án (theo email hoặc họ tên).
        Tiến độ trong tệp không được nhập.
      </p>
      <p v-else class="m-0 text-ink-soft">
        Cột: Mã WBS, Tên công việc, Loại, Bắt đầu, Kết thúc, Trọng số, Người phụ trách, Ghi chú. Mã WBS (1, 1.1, 1.1.2)
        tạo thành cây; người phụ trách là email hoặc họ tên của một thành viên dự án.
        <a :href="api.wbs.importTemplateUrl()" class="font-medium underline">Tải tệp mẫu</a>
      </p>
      <label class="btn w-fit cursor-pointer">
        <Icon name="upload" :size="16" /> {{ fileName || spec.pickText }}
        <input class="sr-only" type="file" :accept="spec.accept" @change="pick" />
      </label>
      <p v-if="busy" class="flex items-center gap-2 text-ink-muted"><Icon name="loader" spin /> Đang kiểm tra...</p>
      <p v-if="error" class="whitespace-pre-line rounded-md bg-danger-soft px-3 py-2 text-danger" role="alert">{{ error }}</p>

      <template v-if="preview">
        <p class="m-0" data-import-summary>
          {{ preview.total }} dòng · {{ preview.groups }} nhóm<template v-if="preview.links !== undefined"> · {{ preview.links }} phụ thuộc</template> · {{ preview.assigned }} có người phụ trách ·
          <strong :class="preview.errors ? 'text-danger' : 'text-success'">{{ preview.errors ? `${preview.errors} dòng lỗi` : "không có lỗi" }}</strong>
        </p>
        <p v-for="text in preview.warnings || []" :key="text" class="m-0 text-warning">{{ text }}</p>
        <div v-if="problems.length" class="max-h-80 overflow-y-auto rounded-lg border border-line">
          <table class="w-full text-left text-sm">
            <thead class="sticky top-0 bg-surface-muted text-xs text-ink-muted"><tr><th class="px-2 py-1">Dòng</th><th class="px-2 py-1">Mã</th><th class="px-2 py-1">Vấn đề</th></tr></thead>
            <tbody>
              <tr v-for="row in problems" :key="row.line ?? row.uid" class="border-t border-line align-top">
                <td class="px-2 py-1">{{ row.line ?? row.uid }}</td>
                <td class="px-2 py-1">{{ row.code }} {{ row.subject }}</td>
                <td class="px-2 py-1">
                  <p v-for="text in row.errors" :key="text" class="m-0 text-danger">{{ text }}</p>
                  <p v-for="text in row.warnings" :key="text" class="m-0 text-warning">{{ text }}</p>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </template>
    </div>
    <template #footer>
      <button class="btn" type="button" @click="emit('close')">Đóng</button>
      <button class="btn btn-primary" type="button" :disabled="busy || !preview || preview.errors > 0 || !preview.total" @click="run">
        Nhập {{ preview?.total || "" }} công việc
      </button>
    </template>
  </Drawer>
</template>
