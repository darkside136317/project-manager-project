<script setup>
import { computed, onBeforeUnmount, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import ConfirmDialog from "../components/ConfirmDialog.vue";
import DynamicForm from "../components/forms/DynamicForm.vue";
import Icon from "../components/Icon.vue";
import ReasonDialog from "../components/ReasonDialog.vue";
import { api } from "../lib/api.js";
import { formatDateTime } from "../lib/format.js";
import { SUB, formStateBadge, missingFields } from "../lib/forms.js";
import { pageTitle } from "../lib/page.js";
import { toast } from "../lib/toast.js";

// /pm/bieu-mau/:id — one form: fill it in (kept automatically while typing), submit, approve or send back, print.
const route = useRoute();
const router = useRouter();
const name = computed(() => String(route.params.id || ""));
const form = ref(null);
const data = ref({});
const error = ref("");
const busy = ref(false);
const missing = ref([]);
const problems = ref("");
const savedAt = ref("");
const saveState = ref("");
const returning = ref(false);
const discarding = ref(false);
let timer = null;
let dirty = false;

const can = computed(() => form.value?.can || {});
const editable = computed(() => Boolean(can.value.edit));
const backLink = computed(() => (form.value?.task ? `/cong-viec/${encodeURIComponent(form.value.task)}`
  : `/du-an/${encodeURIComponent(form.value?.project || "")}/bieu-mau`));
const pdfUrl = computed(() => api.forms.pdfUrl(name.value));

async function load() {
  error.value = "";
  try {
    form.value = await api.forms.detail(name.value);
    data.value = form.value.data || {};
    pageTitle.value = form.value.title;
    dirty = false;
  } catch (e) {
    error.value = e.message;
  }
}

async function keep() {
  clearTimeout(timer);
  timer = null;
  if (!dirty || !editable.value) return;
  dirty = false;
  saveState.value = "Đang lưu...";
  try {
    await api.forms.save(name.value, data.value);
    savedAt.value = new Date().toLocaleTimeString("vi-VN", { hour: "2-digit", minute: "2-digit" });
    saveState.value = "";
    problems.value = "";
  } catch (e) {
    saveState.value = "Chưa lưu được";
    problems.value = e.message;
  }
}

function onInput(value) {
  data.value = value;
  dirty = true;
  if (missing.value.length) missing.value = missingFields(form.value.spec, value).filter((key) => missing.value.includes(key));
  clearTimeout(timer);
  timer = setTimeout(keep, 1500);
}

const uploader = (content, filename) => api.forms.attach(name.value, content, filename);

async function act(action, message) {
  busy.value = true;
  try {
    form.value = await action();
    data.value = form.value.data || {};
    dirty = false;
    problems.value = "";
    if (message) toast(message);
    return true;
  } catch (e) {
    problems.value = e.message;
    window.scrollTo?.({ top: 0, behavior: "smooth" });
    return false;
  } finally {
    busy.value = false;
  }
}

async function submit() {
  missing.value = missingFields(form.value.spec, data.value);
  if (missing.value.length) {
    problems.value = `Còn ${missing.value.length} mục bắt buộc chưa điền.`;
    document.getElementById(`f-${missing.value[0]}`)?.scrollIntoView?.({ behavior: "smooth", block: "center" });
    return;
  }
  clearTimeout(timer);
  await act(() => api.forms.submit(name.value, data.value), "Đã nộp biểu mẫu");
}

const approve = () => act(() => api.forms.approve(name.value), "Đã duyệt biểu mẫu");

async function sendBack(note) {
  if (await act(() => api.forms.sendBack(name.value, note), "Đã trả lại biểu mẫu")) returning.value = false;
}

async function discard() {
  busy.value = true;
  const back = backLink.value;
  try {
    clearTimeout(timer);
    dirty = false;
    await api.forms.discard(name.value);
    toast("Đã bỏ bản nháp");
    router.push(back);
  } catch (e) {
    problems.value = e.message;
    discarding.value = false;
  } finally {
    busy.value = false;
  }
}

watch(name, load, { immediate: true });
onBeforeUnmount(() => {
  if (dirty) keep();
});
</script>

<template>
  <p v-if="error" class="rounded-md bg-danger-soft px-3 py-2 text-sm text-danger" role="alert">{{ error }}</p>
  <p v-else-if="!form" class="flex items-center gap-2 text-sm text-ink-muted"><Icon name="loader" spin /> Đang tải...</p>
  <article v-else class="mx-auto max-w-3xl pb-20">
    <RouterLink :to="backLink" class="inline-flex items-center gap-1 text-xs text-ink-muted hover:underline"><Icon name="chevron-left" :size="14" /> {{ form.task_label || form.project_name }}</RouterLink>
    <header class="mb-4 mt-1">
      <h1 class="m-0 text-xl font-semibold tracking-tight">{{ form.title }}</h1>
      <p class="m-0 text-sm text-ink-muted">Số {{ form.name }} · {{ form.template_code }}, phiên bản {{ form.version }} · {{ form.project_name }}</p>
      <div class="mt-2 flex flex-wrap items-center gap-2 text-sm">
        <span :class="formStateBadge(form.state)">{{ form.state }}</span>
        <span v-if="form.submitted_by" class="text-ink-muted">Nộp: {{ form.submitted_by_name }}, {{ formatDateTime(form.submitted_on) }}</span>
        <span v-if="form.reviewed_by && form.state === SUB.APPROVED" class="text-ink-muted">Duyệt: {{ form.reviewed_by_name }}, {{ formatDateTime(form.reviewed_on) }}</span>
        <a :href="pdfUrl" class="btn btn-ghost ml-auto !min-h-0 !py-1" target="_blank" rel="noopener"><Icon name="printer" :size="16" /> {{ form.state === SUB.APPROVED ? "Tải PDF" : "Xem bản in" }}</a>
      </div>
    </header>

    <p v-if="form.state === SUB.RETURNED" class="mb-4 rounded-lg border border-danger bg-danger-soft px-3 py-2 text-sm"><strong>Bị trả lại</strong> bởi {{ form.reviewed_by_name }}: {{ form.review_note }}</p>
    <p v-if="form.state === SUB.APPROVED && form.review_note" class="mb-4 rounded-lg bg-surface-muted px-3 py-2 text-sm">Ghi chú khi duyệt: {{ form.review_note }}</p>
    <p v-if="problems" class="mb-4 whitespace-pre-line rounded-md bg-danger-soft px-3 py-2 text-sm text-danger" role="alert">{{ problems }}</p>

    <section class="card p-4">
      <DynamicForm :spec="form.spec" :model-value="data" :readonly="!editable" :missing="missing" :uploader="uploader" @update:model-value="onInput" />
    </section>

    <section v-if="form.history.length" class="mt-4" aria-labelledby="form-history">
      <h2 id="form-history" class="m-0 text-sm font-semibold">Lịch sử</h2>
      <ol class="m-0 mt-2 list-none space-y-1 p-0 text-sm">
        <li v-for="entry in form.history" :key="entry.name"><strong>{{ entry.actor_name }}</strong> <span class="text-ink-muted">· {{ formatDateTime(entry.creation) }}</span> · {{ entry.content }}</li>
      </ol>
    </section>

    <footer v-if="editable || can.send_back" class="fixed inset-x-0 bottom-0 z-20 border-t border-line bg-surface px-4 py-3 lg:sticky lg:mt-4 lg:rounded-xl lg:border">
      <div class="mx-auto flex max-w-3xl flex-wrap items-center gap-2">
        <span v-if="editable" class="mr-auto text-xs text-ink-muted" role="status">{{ saveState || (savedAt ? `Đã lưu lúc ${savedAt}` : "Tự lưu khi bạn điền") }}</span>
        <button v-if="can.discard" class="btn btn-ghost" type="button" :disabled="busy" @click="discarding = true">Bỏ nháp</button>
        <button v-if="editable" class="btn btn-primary" type="button" :disabled="busy" @click="submit"><Icon :name="busy ? 'loader' : 'send'" :size="16" :spin="busy" /> Nộp</button>
        <template v-if="can.send_back">
          <span v-if="can.self_submitted && !can.approve" class="mr-auto text-xs text-ink-muted">Bạn là người nộp: cần người khác duyệt.</span>
          <button class="btn" type="button" :disabled="busy" @click="returning = true"><Icon name="undo" :size="16" /> Trả lại</button>
          <button v-if="can.approve" class="btn btn-primary" type="button" :disabled="busy" @click="approve"><Icon :name="busy ? 'loader' : 'check'" :size="16" :spin="busy" /> Duyệt</button>
        </template>
      </div>
    </footer>

    <ReasonDialog :open="returning" title="Trả lại biểu mẫu" label="Cần sửa gì" confirm-text="Trả lại" :busy="busy" @confirm="sendBack" @cancel="returning = false" />
    <ConfirmDialog :open="discarding" title="Bỏ bản nháp" danger confirm-text="Bỏ" :busy="busy" message="Mọi nội dung đã điền và ảnh của bản nháp này sẽ bị xóa." @confirm="discard" @cancel="discarding = false" />
  </article>
</template>
