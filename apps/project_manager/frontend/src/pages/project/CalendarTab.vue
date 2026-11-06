<script setup>
import { computed, inject, onMounted, ref, watch } from "vue";
import EmptyState from "../../components/EmptyState.vue";
import Icon from "../../components/Icon.vue";
import { api } from "../../lib/api.js";
import { formatDate } from "../../lib/format.js";
import { agenda, isOn, monthWeeks } from "../../lib/gantt.js";
import { toast } from "../../lib/toast.js";

// Lịch thi công: a month. A computer shows the month's grid with what runs on each day; a phone shows a list of what
// starts and what is due, day by day, which fits a small screen and answers "what is coming".
const { name: project, openTask, version } = inject("project");
const WEEKDAYS = ["T2", "T3", "T4", "T5", "T6", "T7", "CN"];
const PER_DAY = 3;
const now = new Date();
const year = ref(now.getFullYear());
const month = ref(now.getMonth());
const view = ref(null);
const loading = ref(false);

const weeks = computed(() => monthWeeks(year.value, month.value));
const first = computed(() => weeks.value[0][0]);
const last = computed(() => weeks.value.at(-1)[6]);
const prefix = computed(() => `${year.value}-${String(month.value + 1).padStart(2, "0")}`);
const tasks = computed(() => view.value?.tasks || []);
const off = computed(() => new Set(view.value?.days_off || []));
const today = computed(() => view.value?.today);
const days = computed(() => agenda(tasks.value, `${prefix.value}-01`, `${prefix.value}-31`));
const empty = computed(() => !loading.value && !tasks.value.length);

async function load() {
  loading.value = true;
  try {
    view.value = await api.schedule.calendar(project.value, first.value, last.value);
  } catch (e) {
    toast(e.message, "error", 7000);
  } finally {
    loading.value = false;
  }
}

function shift(step) {
  const date = new Date(year.value, month.value + step, 1);
  year.value = date.getFullYear();
  month.value = date.getMonth();
}

function goToday() {
  year.value = now.getFullYear();
  month.value = now.getMonth();
}

const onDay = (iso) => tasks.value.filter((task) => isOn(task, iso));
function chipTone(task) {
  if (task.status === "Completed") return "bg-success-soft text-success";
  if (task.pm_is_overdue) return "bg-danger-soft text-danger";
  return task.pm_is_critical ? "border border-danger text-danger" : "bg-primary-soft text-ink";
}

watch([year, month], load);
watch(version, load);
onMounted(load);
</script>

<template>
  <div class="mb-3 flex flex-wrap items-center gap-2">
    <button class="btn btn-ghost btn-icon" type="button" aria-label="Tháng trước" @click="shift(-1)"><Icon name="chevron-left" :size="16" /></button>
    <h2 class="m-0 min-w-28 text-center text-base font-semibold">Tháng {{ month + 1 }}/{{ year }}</h2>
    <button class="btn btn-ghost btn-icon" type="button" aria-label="Tháng sau" @click="shift(1)"><Icon name="chevron-right" :size="16" /></button>
    <button class="btn btn-ghost" type="button" @click="goToday">Hôm nay</button>
    <Icon v-if="loading" name="loader" spin class="text-ink-muted" />
  </div>

  <EmptyState v-if="empty" icon="calendar-clock" title="Tháng này không có việc nào" text="Việc có ngày kế hoạch sẽ hiện ở đây." />

  <!-- a computer: the month -->
  <div v-else class="card hidden overflow-hidden sm:block">
    <div class="grid grid-cols-7 border-b border-line text-center text-xs font-semibold text-ink-muted">
      <span v-for="name in WEEKDAYS" :key="name" class="py-1.5">{{ name }}</span>
    </div>
    <div v-for="week in weeks" :key="week[0]" class="grid grid-cols-7 border-b border-line last:border-b-0">
      <div v-for="iso in week" :key="iso" class="min-h-24 border-r border-line p-1 last:border-r-0" :class="{ 'bg-surface-muted': off.has(iso), 'opacity-50': !iso.startsWith(prefix) }">
        <p class="m-0 text-right text-xs" :class="iso === today ? 'font-bold text-danger' : 'text-ink-muted'">{{ Number(iso.slice(8)) }}</p>
        <button v-for="task in onDay(iso).slice(0, PER_DAY)" :key="task.name" class="mb-0.5 block w-full truncate rounded px-1 py-0.5 text-left text-xs" :class="chipTone(task)" type="button" :title="`${task.pm_wbs_code} ${task.subject}`" @click="openTask(task.name)">
          <Icon v-if="task.milestone" name="flag" :size="10" class="inline" /> {{ task.subject }}
        </button>
        <p v-if="onDay(iso).length > PER_DAY" class="m-0 text-xs text-ink-muted">+{{ onDay(iso).length - PER_DAY }} việc</p>
      </div>
    </div>
  </div>

  <!-- a phone: what starts and what is due -->
  <div v-if="!empty" class="space-y-3 sm:hidden">
    <p v-if="!days.length && !loading" class="m-0 text-sm text-ink-muted">Không có việc nào bắt đầu hay đến hạn trong tháng này.</p>
    <section v-for="entry in days" :key="entry.day" :aria-label="formatDate(entry.day)">
      <h3 class="m-0 mb-1 text-sm font-semibold" :class="{ 'text-danger': entry.day === today }">{{ formatDate(entry.day) }}<span v-if="entry.day === today"> · hôm nay</span></h3>
      <ul class="m-0 list-none space-y-1 p-0">
        <li v-for="item in entry.items" :key="`${item.task.name}-${item.kind}`">
          <button class="card flex w-full items-center gap-2 px-3 py-2 text-left text-sm" type="button" @click="openTask(item.task.name)">
            <span class="w-16 shrink-0 text-xs text-ink-muted">{{ item.kind }}</span>
            <span class="min-w-0 flex-1 truncate" :class="{ 'text-danger': item.task.pm_is_overdue }">{{ item.task.pm_wbs_code }} {{ item.task.subject }}</span>
            <span v-if="item.task.pm_is_critical" class="badge badge-danger shrink-0">Găng</span>
          </button>
        </li>
      </ul>
    </section>
  </div>
</template>
