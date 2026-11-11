<script setup>
import { computed, onMounted, reactive, ref, watch } from "vue";
import { useRoute } from "vue-router";
import Drawer from "../components/Drawer.vue";
import EmptyState from "../components/EmptyState.vue";
import Icon from "../components/Icon.vue";
import LinkSelect from "../components/LinkSelect.vue";
import PageHeader from "../components/PageHeader.vue";
import { api } from "../lib/api.js";
import { formatDate } from "../lib/format.js";
import { CAPACITY_REASONS, LEVELS, cellClass, days, levelBadge, mondayOf, percent, shares, shiftWeeks, weekLabel } from "../lib/people.js";
import { toast } from "../lib/toast.js";

// Khối lượng công việc: each person, week by week, the work of every running project against what they can give
// (working days less leave, part time). Over 120 %: overloaded; overloaded by several projects: a conflict. The load
// of projects I may not see shows as "Dự án khác".
const route = useRoute();
const filters = reactive({ start: mondayOf(), weeks: 6, team: String(route.query.team || ""), project: String(route.query.project || "") });
const data = ref({ weeks: [], rows: [], projects: {}, conflicts: [], can: {} });
const teams = ref([]);
const loading = ref(false);
const error = ref("");
const onlyBusy = ref(false);
const CONFLICTS_SHOWN = 10;
const allConflicts = ref(false);
const cell = ref(null);  // {user, week, ...detail}
const cellLoading = ref(false);
const form = reactive({ from_date: "", to_date: "", capacity_pct: 0, reason: CAPACITY_REASONS[0], note: "" });
const saving = ref(false);
const formError = ref("");

const rows = computed(() => (onlyBusy.value ? data.value.rows.filter((r) => r.peak > data.value.thresholds?.busy) : data.value.rows));
const overloaded = computed(() => data.value.rows.filter((r) => r.weeks.some((w) => w.level === "Quá tải")).length);
const thisWeek = computed(() => filters.start === mondayOf());
const conflicts = computed(() => (allConflicts.value ? data.value.conflicts : data.value.conflicts.slice(0, CONFLICTS_SHOWN)));

async function load() {
  loading.value = true;
  error.value = "";
  try {
    data.value = await api.people.workload({ start: filters.start, weeks: filters.weeks, team: filters.team || null, project: filters.project || null });
  } catch (e) {
    error.value = e.message;
  } finally {
    loading.value = false;
  }
}

async function openCell(row, week) {
  cell.value = { user: row.user, full_name: row.full_name, week: week.week, summary: week, tasks: [], periods: [] };
  cellLoading.value = true;
  Object.assign(form, { from_date: week.week, to_date: week.week, capacity_pct: 0, reason: CAPACITY_REASONS[0], note: "" });
  formError.value = "";
  try {
    cell.value = { ...cell.value, ...(await api.people.cell(row.user, week.week)) };
  } catch (e) {
    toast(e.message, "error");
    cell.value = null;
  } finally {
    cellLoading.value = false;
  }
}

async function saveCapacity() {
  saving.value = true;
  formError.value = "";
  try {
    await api.people.saveCapacity({ user: cell.value.user, ...form });
    toast("Đã ghi kỳ năng lực");
    const { user, full_name: fullName, week } = cell.value;
    await load();
    await openCell({ user, full_name: fullName }, data.value.rows.find((r) => r.user === user)?.weeks.find((w) => w.week === week) || { week });
  } catch (e) {
    formError.value = e.message;
  } finally {
    saving.value = false;
  }
}

async function removePeriod(period) {
  try {
    await api.people.deleteCapacity(period.name);
    cell.value.periods = cell.value.periods.filter((p) => p.name !== period.name);
    toast("Đã xóa kỳ năng lực");
    load();
  } catch (e) {
    toast(e.message, "error");
  }
}

const move = (weeks) => { filters.start = weeks === 0 ? mondayOf() : shiftWeeks(filters.start, weeks); };
watch(() => [filters.start, filters.weeks, filters.team, filters.project], load);
onMounted(async () => {
  load();
  try {
    teams.value = await api.people.teams();
  } catch {
    teams.value = [];
  }
});
</script>

<template>
  <PageHeader title="Khối lượng công việc" subtitle="Việc của mỗi người theo tuần, trên mọi dự án đang chạy, so với ngày công có thể làm.">
    <button class="btn btn-ghost" type="button" :disabled="loading" @click="load"><Icon name="refresh-cw" :size="16" /> Tải lại</button>
  </PageHeader>

  <div class="card mb-4 flex flex-wrap items-end gap-3 p-3">
    <div class="flex items-center gap-1" role="group" aria-label="Chọn tuần">
      <button class="btn btn-ghost btn-icon" type="button" aria-label="Tuần trước" @click="move(-1)"><Icon name="chevron-left" /></button>
      <button class="btn btn-ghost" type="button" :disabled="thisWeek" @click="move(0)">Tuần này</button>
      <button class="btn btn-ghost btn-icon" type="button" aria-label="Tuần sau" @click="move(1)"><Icon name="chevron-right" /></button>
      <span class="text-sm text-ink-muted">Từ {{ formatDate(filters.start) }}</span>
    </div>
    <div>
      <label class="label" for="wl-weeks">Số tuần</label>
      <select id="wl-weeks" v-model.number="filters.weeks" class="input w-auto">
        <option v-for="n in [4, 6, 8, 12]" :key="n" :value="n">{{ n }} tuần</option>
      </select>
    </div>
    <div>
      <label class="label" for="wl-team">Tổ đội, phòng</label>
      <select id="wl-team" v-model="filters.team" class="input w-auto">
        <option value="">Tất cả</option>
        <option v-for="team in teams" :key="team.name" :value="team.name">{{ team.team_name }}</option>
      </select>
    </div>
    <div class="min-w-[220px]">
      <label class="label" for="wl-project">Dự án</label>
      <LinkSelect v-model="filters.project" doctype="Project" input-id="wl-project" placeholder="Mọi dự án" />
    </div>
    <label class="flex items-center gap-2 text-sm"><input v-model="onlyBusy" type="checkbox" /> Chỉ người bận, quá tải</label>
  </div>

  <div class="mb-4 flex flex-wrap items-center gap-2 text-xs text-ink-muted" aria-label="Chú thích">
    <span v-for="level in LEVELS" :key="level" :class="levelBadge(level)">{{ level }}</span>
    <span>Bận trên {{ percent(data.thresholds?.busy) }}, quá tải trên {{ percent(data.thresholds?.overload) }} số ngày công có thể làm.</span>
    <span v-if="overloaded" class="font-semibold text-danger" data-overloaded-count>{{ overloaded }} người quá tải</span>
  </div>

  <section v-if="data.conflicts.length" class="card mb-4 p-4" aria-labelledby="wl-conflicts">
    <h2 id="wl-conflicts" class="m-0 mb-2 flex items-center gap-2 text-base font-semibold"><Icon name="alert-triangle" :size="18" class="text-danger" /> Xung đột giữa các dự án</h2>
    <ul class="m-0 list-none space-y-2 p-0">
      <li v-for="(item, i) in conflicts" :key="i" class="flex flex-wrap items-baseline gap-x-2 text-sm" data-conflict>
        <span class="badge badge-danger">{{ item.kind }}</span>
        <strong>{{ item.subject }}</strong>
        <span class="text-ink-muted">tuần {{ weekLabel(item.week) }}</span>
        <span v-if="item.utilization">· cần {{ percent(item.utilization) }} sức</span>
        <span v-if="item.message" class="text-ink-muted">· {{ item.message }}</span>
        <span class="w-full text-xs text-ink-muted sm:w-auto">
          <template v-for="(part, j) in shares(item.projects, data.projects)" :key="part.key">{{ j ? " · " : "" }}{{ part.label }}: {{ days(part.days) }} {{ item.kind === "Máy" ? "ngày" : "ngày công" }}</template>
        </span>
      </li>
    </ul>
    <button v-if="data.conflicts.length > CONFLICTS_SHOWN" class="btn btn-ghost mt-2" type="button" @click="allConflicts = !allConflicts">
      {{ allConflicts ? "Thu gọn" : `Xem tất cả ${data.conflicts.length} xung đột` }}</button>
  </section>

  <p v-if="error" class="rounded-md bg-danger-soft px-3 py-2 text-sm text-danger" role="alert">{{ error }}</p>
  <EmptyState v-else-if="!loading && !rows.length" icon="calendar-clock" title="Không có ai trong phạm vi xem"
              :text="onlyBusy ? 'Không ai bận hay quá tải trong các tuần này.' : 'Bạn xem được khối lượng của chính mình, tổ đội mình phụ trách, hoặc mọi người trong dự án bạn có quyền xem hiệu suất.'" />

  <div v-else class="card overflow-x-auto">
    <table class="w-full text-sm" :style="{ minWidth: `${200 + data.weeks.length * 96}px` }">
      <thead>
        <tr class="border-b border-line text-left text-xs text-ink-muted">
          <th class="sticky left-0 z-10 bg-surface px-4 py-2">Người</th>
          <th v-for="week in data.weeks" :key="week" class="px-2 py-2 text-center">Tuần {{ weekLabel(week) }}</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in rows" :key="row.user" class="border-b border-line last:border-0" data-workload-row>
          <th scope="row" class="sticky left-0 z-10 bg-surface px-4 py-2 text-left font-medium">{{ row.full_name }}</th>
          <td v-for="week in row.weeks" :key="week.week" class="p-1">
            <button type="button" class="w-full rounded-md px-2 py-1.5 text-center" :class="cellClass(week.level)"
                    :aria-label="`${row.full_name}, tuần ${weekLabel(week.week)}: ${week.level}, cần ${days(week.demand)} trên ${days(week.capacity)} ngày công`"
                    data-workload-cell @click="openCell(row, week)">
              <span class="block font-semibold">{{ week.capacity || week.demand ? percent(week.utilization) : "—" }}</span>
              <span class="block text-[11px] opacity-80">{{ days(week.demand) }}/{{ days(week.capacity) }}</span>
            </button>
          </td>
        </tr>
      </tbody>
    </table>
  </div>

  <Drawer :open="!!cell" :title="cell ? `${cell.full_name} · tuần ${weekLabel(cell.week)}` : ''" @close="cell = null">
    <div v-if="cell" class="space-y-5" data-workload-drawer>
      <p class="m-0 text-sm">
        Cần <strong>{{ days(cell.summary?.demand) }}</strong> ngày công, có thể làm <strong>{{ days(cell.capacity ?? cell.summary?.capacity) }}</strong>
        <span v-if="cell.summary?.level" class="ml-1" :class="levelBadge(cell.summary.level)">{{ cell.summary.level }} · {{ percent(cell.summary.utilization) }}</span>
      </p>
      <p v-if="cellLoading" class="text-sm text-ink-muted">Đang tải…</p>
      <section v-else>
        <h3 class="mb-2 text-sm font-semibold">Công việc trong tuần</h3>
        <p v-if="!cell.tasks.length && !cell.other" class="text-sm text-ink-muted">Không có việc nào.</p>
        <ul class="m-0 list-none space-y-2 p-0">
          <li v-for="task in cell.tasks" :key="task.task" class="rounded-md border border-line px-3 py-2 text-sm">
            <RouterLink :to="`/cong-viec/${encodeURIComponent(task.task)}`" class="font-medium">{{ task.label }}</RouterLink>
            <span class="block text-xs text-ink-muted">{{ task.project_name || task.project }} · {{ task.raci }} · {{ formatDate(task.start) }} – {{ formatDate(task.end) }} · {{ Math.round(task.progress || 0) }}%</span>
            <span class="text-xs">{{ days(task.days) }} ngày công trong tuần</span>
          </li>
          <li v-if="cell.other" class="rounded-md border border-dashed border-line px-3 py-2 text-sm text-ink-muted">Dự án khác: {{ days(cell.other) }} ngày công (bạn không xem được chi tiết)</li>
        </ul>
      </section>
      <section>
        <h3 class="mb-2 text-sm font-semibold">Nghỉ, bán thời gian</h3>
        <p v-if="!cell.periods?.length" class="text-sm text-ink-muted">Không có kỳ nào trong tuần.</p>
        <ul class="m-0 list-none space-y-1 p-0">
          <li v-for="period in cell.periods" :key="period.name" class="flex items-center justify-between gap-2 text-sm">
            <span>{{ period.reason }}: {{ formatDate(period.from_date) }} – {{ formatDate(period.to_date) }}, còn {{ Math.round(period.capacity_pct) }}%<span v-if="period.note" class="text-ink-muted"> · {{ period.note }}</span></span>
            <button v-if="data.can.capacity" class="btn btn-ghost btn-icon" type="button" :aria-label="`Xóa kỳ ${period.reason}`" @click="removePeriod(period)"><Icon name="trash-2" :size="16" /></button>
          </li>
        </ul>
        <form v-if="data.can.capacity" class="mt-3 grid grid-cols-2 gap-3" data-capacity-form @submit.prevent="saveCapacity">
          <div><label class="label" for="cap-from">Từ ngày</label><input id="cap-from" v-model="form.from_date" class="input" type="date" required /></div>
          <div><label class="label" for="cap-to">Đến ngày</label><input id="cap-to" v-model="form.to_date" class="input" type="date" required /></div>
          <div><label class="label" for="cap-reason">Lý do</label>
            <select id="cap-reason" v-model="form.reason" class="input"><option v-for="r in CAPACITY_REASONS" :key="r">{{ r }}</option></select></div>
          <div><label class="label" for="cap-pct">Còn làm được (%)</label><input id="cap-pct" v-model.number="form.capacity_pct" class="input" type="number" min="0" max="100" required /></div>
          <div class="col-span-2"><label class="label" for="cap-note">Ghi chú</label><input id="cap-note" v-model="form.note" class="input" /></div>
          <p v-if="formError" class="col-span-2 m-0 text-sm text-danger" role="alert">{{ formError }}</p>
          <div class="col-span-2"><button class="btn btn-primary" type="submit" :disabled="saving">Ghi kỳ năng lực</button></div>
        </form>
      </section>
    </div>
  </Drawer>
</template>
