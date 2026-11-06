<script setup>
import { computed, inject, onMounted, reactive, ref, watch } from "vue";
import ConfirmDialog from "../../components/ConfirmDialog.vue";
import EmptyState from "../../components/EmptyState.vue";
import Icon from "../../components/Icon.vue";
import { api } from "../../lib/api.js";
import { formatDate, formatDateTime } from "../../lib/format.js";
import { slipText, slipTone } from "../../lib/gantt.js";
import { toast } from "../../lib/toast.js";
import { statusBadge, statusLabel } from "../../lib/work.js";

// Baseline: copies of the plan to measure against. The table shows, task by task, how far the plan and the forecast have
// moved from the chosen copy, worst first.
const { name: project, openTask, version, reload } = inject("project");
const list = ref(null);
const chosen = ref("");
const compare = ref(null);
const lateOnly = ref(false);
const busy = ref(false);
const removing = ref(null);
const form = reactive({ open: false, title: "", note: "" });
const summary = computed(() => compare.value?.summary || {});
const current = computed(() => list.value?.rows.find((row) => row.name === chosen.value));

async function loadCompare() {
  if (!chosen.value) {
    compare.value = null;
    return;
  }
  try {
    compare.value = await api.schedule.compareBaseline(chosen.value, lateOnly.value ? 1 : 0);
  } catch (e) {
    toast(e.message, "error", 7000);
  }
}

async function load() {
  try {
    list.value = await api.schedule.listBaselines(project.value);
    const known = list.value.rows.some((row) => row.name === chosen.value);
    if (!known) chosen.value = list.value.rows.find((row) => row.is_primary)?.name || list.value.rows[0]?.name || "";
    await loadCompare();
  } catch (e) {
    toast(e.message, "error", 7000);
  }
}

async function run(action, message) {
  busy.value = true;
  try {
    const result = await action();
    toast(message);
    await load();
    reload();
    return result;
  } catch (e) {
    toast(e.message, "error", 8000);
    return null;
  } finally {
    busy.value = false;
  }
}

async function capture() {
  const result = await run(() => api.schedule.captureBaseline(project.value, form.title, form.note), "Đã chụp baseline");
  if (result) {
    Object.assign(form, { open: false, title: "", note: "" });
    chosen.value = result.name;
    await loadCompare();
  }
}

const setPrimary = (row) => run(() => api.schedule.setPrimaryBaseline(row.name), `Đã dùng ${row.title} làm baseline chính`);

async function remove() {
  const row = removing.value;
  removing.value = null;
  await run(() => api.schedule.removeBaseline(row.name), "Đã xóa baseline");
}

watch([chosen, lateOnly], loadCompare);
watch(version, load);
onMounted(load);
</script>

<template>
  <template v-if="list">
    <div class="mb-3 flex flex-wrap items-center gap-2">
      <button v-if="list.can_edit && !form.open" class="btn btn-primary" type="button" @click="form.open = true"><Icon name="save" :size="16" /> Chụp baseline</button>
      <select v-if="list.rows.length" v-model="chosen" class="input w-auto" aria-label="Baseline đang xem">
        <option v-for="row in list.rows" :key="row.name" :value="row.name">{{ row.title }}{{ row.is_primary ? " (chính)" : "" }}</option>
      </select>
      <label v-if="list.rows.length" class="flex items-center gap-1 text-sm"><input v-model="lateOnly" type="checkbox" /> Chỉ việc trễ</label>
      <template v-if="current && list.can_edit">
        <button v-if="!current.is_primary" class="btn btn-ghost" type="button" :disabled="busy" @click="setPrimary(current)">Dùng làm baseline chính</button>
        <button v-if="!current.is_primary" class="btn btn-ghost" type="button" :disabled="busy" @click="removing = current"><Icon name="trash-2" :size="16" /> Xóa</button>
      </template>
    </div>

    <form v-if="form.open" class="card mb-3 grid gap-3 p-3 sm:grid-cols-2" @submit.prevent="capture">
      <div><label class="label" for="bl-title">Tên</label><input id="bl-title" v-model="form.title" class="input" placeholder="Kế hoạch được duyệt tháng 11" /></div>
      <div><label class="label" for="bl-note">Ghi chú</label><input id="bl-note" v-model="form.note" class="input" /></div>
      <p class="m-0 text-xs text-ink-muted sm:col-span-2">Baseline là bản sao của kế hoạch hiện tại, không đổi về sau. Baseline đầu tiên là baseline chính: đường kế hoạch của đường cong S và SPI tính theo nó.</p>
      <div class="flex justify-end gap-2 sm:col-span-2">
        <button class="btn" type="button" @click="form.open = false">Hủy</button>
        <button class="btn btn-primary" type="submit" :disabled="busy">Chụp</button>
      </div>
    </form>

    <EmptyState v-if="!list.rows.length" icon="history" title="Chưa có baseline nào" text="Chụp baseline khi kế hoạch đã được thống nhất, để sau này so sánh với thực tế." />

    <template v-else-if="compare">
      <p class="m-0 mb-2 text-xs text-ink-muted">{{ compare.title }}, chụp lúc {{ formatDateTime(compare.taken_on) }}<template v-if="current?.taken_by_name"> bởi {{ current.taken_by_name }}</template><template v-if="current?.note">: {{ current.note }}</template></p>
      <dl class="m-0 mb-3 grid grid-cols-2 gap-3 text-sm sm:grid-cols-4">
        <div class="card px-3 py-2"><dt class="text-xs text-ink-muted">Baseline kết thúc</dt><dd class="m-0 font-semibold">{{ formatDate(compare.end_date) }}</dd></div>
        <div class="card px-3 py-2"><dt class="text-xs text-ink-muted">Kế hoạch hiện tại</dt><dd class="m-0 font-semibold">{{ formatDate(summary.plan_end) || "—" }}</dd></div>
        <div class="card px-3 py-2"><dt class="text-xs text-ink-muted">Dự báo xong</dt><dd class="m-0 font-semibold">{{ formatDate(summary.forecast_end) || "—" }}</dd></div>
        <div class="card px-3 py-2"><dt class="text-xs text-ink-muted">So với baseline</dt><dd class="m-0">{{ compare.later }} việc lùi · {{ compare.earlier }} việc sớm · {{ compare.added }} việc mới</dd></div>
      </dl>
      <div class="card table-wrap">
        <table class="w-full min-w-[640px] text-left text-sm">
          <thead class="text-xs text-ink-muted">
            <tr class="border-b border-line"><th class="px-3 py-2 font-medium">Công việc</th><th class="px-3 py-2 font-medium">Baseline</th><th class="px-3 py-2 font-medium">Kế hoạch</th><th class="px-3 py-2 font-medium">Chênh kế hoạch</th><th class="px-3 py-2 font-medium">Dự báo</th><th class="px-3 py-2 font-medium">Trạng thái</th></tr>
          </thead>
          <tbody>
            <tr v-for="row in compare.rows" :key="row.task" class="border-b border-line last:border-0">
              <td class="px-3 py-2"><button class="text-left hover:underline" :class="{ 'text-danger': row.critical }" type="button" @click="openTask(row.task)">{{ row.label }}</button></td>
              <td class="whitespace-nowrap px-3 py-2 text-xs text-ink-muted">{{ formatDate(row.base_end) }}</td>
              <td class="whitespace-nowrap px-3 py-2 text-xs">{{ formatDate(row.end) }}</td>
              <td class="whitespace-nowrap px-3 py-2 text-xs" :class="slipTone(row.plan_slip)">{{ slipText(row.plan_slip) }}</td>
              <td class="whitespace-nowrap px-3 py-2 text-xs" :class="slipTone(row.forecast_slip)">{{ formatDate(row.forecast) }} <span v-if="row.forecast_slip">({{ slipText(row.forecast_slip) }})</span></td>
              <td class="px-3 py-2"><span :class="statusBadge(row.status)">{{ statusLabel(row.status) }}</span></td>
            </tr>
            <tr v-if="!compare.rows.length"><td colspan="6" class="px-3 py-6 text-center text-ink-muted">Không có việc nào trễ so với baseline này.</td></tr>
          </tbody>
        </table>
      </div>
      <p v-if="compare.total > compare.rows.length" class="m-0 mt-2 text-xs text-ink-muted">Đang hiện {{ compare.rows.length }}/{{ compare.total }} việc, trễ nhiều nhất trước.</p>
    </template>
  </template>
  <ConfirmDialog :open="Boolean(removing)" title="Xóa baseline" danger confirm-text="Xóa" :message="removing ? `Xóa ${removing.title}? Bản sao kế hoạch này sẽ mất.` : ''" @confirm="remove" @cancel="removing = null" />
</template>
