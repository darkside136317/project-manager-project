<script setup>
import { reactive, ref, watch } from "vue";
import { api } from "../../lib/api.js";
import { LINK_KINDS } from "../../lib/gantt.js";
import { formatDate } from "../../lib/format.js";
import { toast } from "../../lib/toast.js";
import Icon from "../Icon.vue";
import LinkSelect from "../LinkSelect.vue";

// In the task panel: what this task waits for, what waits for it, and where it stands on the critical path.
const props = defineProps({ task: { type: String, required: true }, project: { type: String, default: "" } });
const emit = defineEmits(["changed"]);
const view = ref(null);
const busy = ref(false);
const form = reactive({ open: false, side: "before", other: "", kind: "FS", lag: 0 });

async function load() {
  try {
    view.value = await api.schedule.dependencies(props.task);
  } catch (e) {
    toast(e.message, "error", 7000);
  }
}

const search = async (txt) => api.schedule.searchTasks(props.project, txt, props.task);

async function run(action, message) {
  busy.value = true;
  try {
    await action();
    if (message) toast(message);
    await load();
    emit("changed");
    return true;
  } catch (e) {
    toast(e.message, "error", 8000);
    return false;
  } finally {
    busy.value = false;
  }
}

async function add() {
  const [before, after] = form.side === "before" ? [form.other, props.task] : [props.task, form.other];
  const done = await run(() => api.schedule.addDependency(before, after, form.kind, form.lag || 0), "Đã thêm phụ thuộc");
  if (done) Object.assign(form, { open: false, other: "", kind: "FS", lag: 0 });
}

const remove = (link) => run(() => api.schedule.removeDependency(link.name), "Đã bỏ phụ thuộc");
const lagText = (lag) => (lag ? ` ${lag > 0 ? "+" : ""}${lag} ngày` : "");

watch(() => props.task, load, { immediate: true });
</script>

<template>
  <section v-if="view" aria-labelledby="task-links">
    <div class="flex items-center justify-between">
      <h3 id="task-links" class="m-0 text-sm font-semibold">Lịch trình</h3>
      <button v-if="view.can_edit && !form.open" class="btn btn-ghost" type="button" @click="form.open = true"><Icon name="plus" :size="16" /> Thêm phụ thuộc</button>
    </div>
    <p class="m-0 mt-1 flex flex-wrap items-center gap-2 text-sm">
      <span v-if="view.critical" class="badge badge-danger">Trên đường găng</span>
      <span v-else class="text-ink-muted">Dự trữ {{ view.total_float }} ngày làm việc</span>
      <span v-if="view.forecast_end" class="text-ink-muted">Dự báo xong {{ formatDate(view.forecast_end) }}</span>
    </p>
    <p v-if="view.conflict_days" class="m-0 mt-1 rounded-md bg-warning-soft px-3 py-1.5 text-sm">Bắt đầu sớm hơn phụ thuộc cho phép {{ view.conflict_days }} ngày làm việc: dời ngày hoặc sửa phụ thuộc.</p>

    <form v-if="form.open" class="mt-2 grid gap-3 rounded-lg border border-line p-3 sm:grid-cols-2" @submit.prevent="add">
      <div>
        <label class="label" for="link-side">Việc được chọn là</label>
        <select id="link-side" v-model="form.side" class="input">
          <option value="before">Việc trước (việc này chờ nó)</option>
          <option value="after">Việc sau (nó chờ việc này)</option>
        </select>
      </div>
      <div>
        <label class="label" for="link-other">Công việc</label>
        <LinkSelect v-model="form.other" input-id="link-other" doctype="Task" :searcher="search" placeholder="Gõ tên hoặc mã WBS..." />
      </div>
      <div>
        <label class="label" for="link-kind">Kiểu</label>
        <select id="link-kind" v-model="form.kind" class="input">
          <option v-for="kind in LINK_KINDS" :key="kind.value" :value="kind.value">{{ kind.label }}</option>
        </select>
      </div>
      <div>
        <label class="label" for="link-lag">Độ trễ (ngày làm việc)</label>
        <input id="link-lag" v-model.number="form.lag" class="input" type="number" step="1" />
      </div>
      <div class="flex justify-end gap-2 sm:col-span-2">
        <button class="btn" type="button" @click="form.open = false">Hủy</button>
        <button class="btn btn-primary" type="submit" :disabled="busy || !form.other">Thêm</button>
      </div>
    </form>

    <template v-for="group in [{ title: 'Chờ các việc', rows: view.predecessors }, { title: 'Các việc đang chờ việc này', rows: view.successors }]" :key="group.title">
      <div v-if="group.rows.length" class="mt-2">
        <p class="m-0 text-xs text-ink-muted">{{ group.title }}</p>
        <ul class="m-0 mt-1 list-none space-y-1 p-0">
          <li v-for="link in group.rows" :key="link.name" class="flex flex-wrap items-center gap-2 rounded-lg border border-line px-3 py-1.5 text-sm">
            <span class="min-w-0 flex-1">{{ link.label }}</span>
            <span class="text-xs text-ink-muted">{{ link.dep_type }}{{ lagText(link.lag_days) }}</span>
            <button v-if="view.can_edit" class="btn btn-ghost btn-icon !min-h-0 !p-1" type="button" aria-label="Bỏ phụ thuộc" title="Bỏ phụ thuộc" :disabled="busy" @click="remove(link)"><Icon name="x" :size="14" /></button>
          </li>
        </ul>
      </div>
    </template>
  </section>
</template>
