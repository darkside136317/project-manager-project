<script setup>
import { computed, ref, watch } from "vue";
import { useRouter } from "vue-router";
import { api } from "../../lib/api.js";
import { formStateBadge, SUB } from "../../lib/forms.js";
import { toast } from "../../lib/toast.js";
import Icon from "../Icon.vue";

// The forms of one task, in its panel: what it requires before it can close, what was filled in, a new one.
const props = defineProps({ task: { type: String, required: true }, project: { type: String, default: "" } });
const emit = defineEmits(["changed"]);
const router = useRouter();

const view = ref(null);
const chosen = ref("");
const required = ref("");
const busy = ref(false);
const templates = computed(() => view.value?.templates || []);
const requirable = computed(() => templates.value.filter((t) => !view.value.gates.some((g) => g.form_code === t.code)));

async function load() {
  try {
    view.value = await api.forms.forTask(props.task);
  } catch (e) {
    toast(e.message, "error", 7000);
  }
}

async function run(action, after) {
  busy.value = true;
  try {
    const result = await action();
    if (after) await after(result);
  } catch (e) {
    toast(e.message, "error", 7000);
  } finally {
    busy.value = false;
  }
}

const open = (name) => router.push(`/bieu-mau/${name}`);
const start = (code) => run(() => api.forms.start(code, props.project, props.task), (result) => open(result.name));
const addGate = () => run(() => api.forms.gateAdd(props.task, required.value), async () => {
  required.value = "";
  await load();
  emit("changed");
});
const removeGate = (gate) => run(() => api.forms.gateRemove(gate.name), async () => {
  await load();
  emit("changed");
});

function gateText(gate) {
  if (gate.met) return "Đã duyệt";
  return gate.state ? `Chưa duyệt (${gate.state})` : "Chưa điền";
}

watch(() => props.task, load, { immediate: true });
</script>

<template>
  <section v-if="view" aria-labelledby="task-forms">
    <h3 id="task-forms" class="m-0 text-sm font-semibold">Biểu mẫu</h3>

    <ul v-if="view.gates.length" class="m-0 mt-2 list-none space-y-2 p-0" aria-label="Biểu mẫu bắt buộc để đóng việc">
      <li v-for="gate in view.gates" :key="gate.name" class="flex flex-wrap items-center gap-2 rounded-lg border px-3 py-2 text-sm" :class="gate.met ? 'border-line' : 'border-warning bg-warning-soft'">
        <Icon :name="gate.met ? 'circle-check' : 'alert-triangle'" :size="16" :class="gate.met ? 'text-success' : 'text-warning'" />
        <span class="font-medium">Bắt buộc: {{ gate.form_title }}</span>
        <span class="text-ink-muted">{{ gateText(gate) }}</span>
        <span class="ml-auto flex gap-1">
          <button v-if="gate.submission" class="btn btn-ghost !min-h-0 !py-1 text-xs" type="button" @click="open(gate.submission)">Mở</button>
          <button v-else-if="view.can_fill" class="btn btn-ghost !min-h-0 !py-1 text-xs" type="button" :disabled="busy" @click="start(gate.form_code)">Điền</button>
          <button v-if="view.can_gate" class="btn btn-ghost btn-icon !min-h-0 !p-1" type="button" aria-label="Bỏ điều kiện" title="Bỏ điều kiện" :disabled="busy" @click="removeGate(gate)"><Icon name="x" :size="14" /></button>
        </span>
      </li>
    </ul>

    <ul v-if="view.forms.length" class="m-0 mt-2 list-none space-y-1 p-0">
      <li v-for="form in view.forms" :key="form.name">
        <button class="flex w-full flex-wrap items-center gap-2 rounded-md px-2 py-1 text-left text-sm hover:bg-surface-muted" type="button" @click="open(form.name)">
          <span :class="formStateBadge(form.state)">{{ form.state }}</span>
          <span class="font-medium">{{ form.title }}</span>
          <span class="text-xs text-ink-muted">số {{ form.name }} · {{ form.who }}</span>
        </button>
      </li>
    </ul>
    <p v-if="!view.gates.length && !view.forms.length" class="m-0 mt-1 text-sm text-ink-muted">Chưa có biểu mẫu nào.</p>

    <div v-if="view.can_fill" class="mt-2 flex flex-wrap gap-2">
      <select v-model="chosen" class="input min-w-0 flex-1" aria-label="Chọn biểu mẫu để điền">
        <option value="">Chọn biểu mẫu để điền...</option>
        <option v-for="item in templates" :key="item.code" :value="item.code">{{ item.title }}</option>
      </select>
      <button class="btn" type="button" :disabled="!chosen || busy" @click="start(chosen)"><Icon name="pencil" :size="16" /> Điền</button>
    </div>
    <div v-if="view.can_gate && requirable.length" class="mt-2 flex flex-wrap gap-2">
      <select v-model="required" class="input min-w-0 flex-1" aria-label="Chọn biểu mẫu bắt buộc">
        <option value="">Bắt buộc biểu mẫu đã duyệt mới đóng được việc...</option>
        <option v-for="item in requirable" :key="item.code" :value="item.code">{{ item.title }}</option>
      </select>
      <button class="btn" type="button" :disabled="!required || busy" @click="addGate"><Icon name="plus" :size="16" /> Thêm điều kiện</button>
    </div>
    <p v-if="view.gates.some((g) => g.state === SUB.RETURNED)" class="m-0 mt-2 text-xs text-danger">Có biểu mẫu bị trả lại: mở để xem cần sửa gì.</p>
  </section>
</template>
