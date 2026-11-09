<script setup>
import { computed, inject, onMounted, ref } from "vue";
import { useRouter } from "vue-router";
import EmptyState from "@pm/components/EmptyState.vue";
import Icon from "@pm/components/Icon.vue";
import { api } from "@pm/lib/api.js";
import { formatDate } from "@pm/lib/format.js";
import { formStateBadge } from "@pm/lib/forms.js";
import { toast } from "@pm/lib/toast.js";
import { construction, moneyText, percentText, qtyText, share } from "./construction.js";

// Nghiệm thu: each work item's planned, done and accepted quantities, what is done but not yet accepted, and the
// acceptance records (forms of the core). A record is started here and filled, signed and approved on the form's page.
const { name: project, openTask } = inject("project");
const router = useRouter();
const data = ref(null);
const starting = ref("");
const onlyWaiting = ref(false);

const works = computed(() => (data.value?.works || []).filter((w) => !onlyWaiting.value || w.waiting_qty > 0));
const workTemplate = computed(() => data.value?.templates.find((t) => t.code === "NT-CONGVIEC"));
const others = computed(() => (data.value?.templates || []).filter((t) => t.code !== "NT-CONGVIEC"));

async function load() {
  try {
    data.value = await construction.acceptance(project.value);
  } catch (e) {
    toast(e.message, "error", 7000);
  }
}

async function start(code, task = null) {
  starting.value = `${code}:${task || ""}`;
  try {
    const form = await api.forms.start(code, project.value, task);
    router.push(`/bieu-mau/${form.name}`);
  } catch (e) {
    toast(e.message, "error", 7000);
  } finally {
    starting.value = "";
  }
}

onMounted(load);
</script>

<template>
  <div v-if="data" class="space-y-4">
    <section class="flex flex-wrap items-center gap-3">
      <div class="card min-w-[200px] flex-1 p-3">
        <p class="m-0 text-xs text-ink-muted">Đã nghiệm thu</p>
        <p class="m-0 mt-1 text-lg font-semibold">{{ percentText(data.summary.accepted_percent) }} <span class="text-sm font-normal text-ink-muted">giá trị dự toán</span></p>
        <p class="m-0 text-xs text-ink-muted">{{ moneyText(data.summary.accepted_value, { short: true }) }} / {{ moneyText(data.summary.planned_value, { short: true }) }} · đã thi công {{ percentText(data.summary.done_percent) }}</p>
      </div>
      <div v-if="data.can.fill && others.length" class="flex flex-wrap gap-2">
        <button v-for="template in others" :key="template.code" type="button" class="btn" :disabled="Boolean(starting)" @click="start(template.code)">
          <Icon name="clipboard-check" :size="16" /> {{ template.title }}
        </button>
      </div>
    </section>

    <section aria-labelledby="works-title">
      <div class="mb-2 flex flex-wrap items-center gap-2">
        <h3 id="works-title" class="m-0 text-sm font-semibold">Khối lượng theo công tác</h3>
        <label class="ml-auto flex items-center gap-1.5 text-sm"><input v-model="onlyWaiting" type="checkbox" /> Chỉ việc đã làm, chưa nghiệm thu</label>
      </div>
      <EmptyState v-if="!data.works.length" icon="sheet" title="Chưa có công tác có khối lượng" text="Nhập và duyệt BOQ ở tab BOQ trước." />
      <div v-else class="overflow-x-auto rounded-lg border border-line">
        <table class="w-full min-w-[720px] text-sm">
          <thead class="bg-surface-muted text-left text-xs text-ink-muted">
            <tr><th class="px-2 py-2">Công tác</th><th class="px-2 text-right">Thiết kế</th><th class="px-2 text-right">Đã làm</th><th class="px-2 text-right">Đã nghiệm thu</th><th class="px-2 text-right">Chờ nghiệm thu</th><th class="px-2"></th></tr>
          </thead>
          <tbody>
            <tr v-for="work in works" :key="work.name" class="border-t border-line">
              <td class="px-2 py-1.5"><button type="button" class="text-left hover:underline" @click="openTask(work.name)"><span class="text-ink-muted">{{ work.pm_wbs_code }}</span> {{ work.subject }}</button></td>
              <td class="px-2 text-right">{{ qtyText(work.pmc_planned_qty, work.pmc_uom) }}</td>
              <td class="px-2 text-right">{{ qtyText(work.pmc_done_qty) }}</td>
              <td class="px-2 text-right">
                {{ qtyText(work.pmc_accepted_qty) }}
                <div class="ml-auto mt-0.5 h-1 w-16 overflow-hidden rounded-full bg-surface-muted"><div class="h-full bg-success" :style="{ width: `${share(work.pmc_accepted_qty, work.pmc_planned_qty)}%` }"></div></div>
              </td>
              <td class="px-2 text-right" :class="work.waiting_qty > 0 ? 'font-semibold text-warning' : 'text-ink-muted'">{{ qtyText(work.waiting_qty) }}</td>
              <td class="px-2 text-right">
                <button v-if="data.can.fill && workTemplate && work.waiting_qty > 0" type="button" class="btn btn-ghost px-2 text-xs" :disabled="Boolean(starting)" @click="start('NT-CONGVIEC', work.name)">
                  <Icon :name="starting === `NT-CONGVIEC:${work.name}` ? 'loader' : 'clipboard-check'" :size="14" :spin="starting === `NT-CONGVIEC:${work.name}`" /> Lập biên bản
                </button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>

    <section aria-labelledby="records-title">
      <h3 id="records-title" class="m-0 mb-2 text-sm font-semibold">Biên bản</h3>
      <p v-if="!data.records.length" class="m-0 text-sm text-ink-muted">Chưa có biên bản nào.</p>
      <ul class="m-0 list-none divide-y divide-line rounded-lg border border-line p-0" :class="{ hidden: !data.records.length }">
        <li v-for="record in data.records" :key="record.name">
          <RouterLink :to="`/bieu-mau/${record.name}`" class="flex flex-wrap items-center gap-2 px-3 py-2 text-sm no-underline hover:bg-surface-muted">
            <span class="min-w-0 flex-1"><span class="font-medium text-ink">{{ record.title }}</span>
              <span v-if="record.task_label" class="block truncate text-xs text-ink-muted">{{ record.task_label }}<span v-if="record.qty !== null"> · {{ qtyText(record.qty) }}</span></span></span>
            <span :class="formStateBadge(record.state)">{{ record.state }}</span>
            <span class="text-xs text-ink-muted">{{ formatDate(record.reviewed_on || record.submitted_on) }}</span>
          </RouterLink>
        </li>
      </ul>
    </section>
  </div>
</template>
