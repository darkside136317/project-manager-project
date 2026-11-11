<script setup>
import { computed, onMounted, reactive, ref, watch } from "vue";
import Drawer from "../components/Drawer.vue";
import EmptyState from "../components/EmptyState.vue";
import Icon from "../components/Icon.vue";
import LinkSelect from "../components/LinkSelect.vue";
import PageHeader from "../components/PageHeader.vue";
import { api } from "../lib/api.js";
import { formatDate } from "../lib/format.js";
import { PERIODS, percent, weekLabel } from "../lib/people.js";
import { statusLabel } from "../lib/work.js";

// Hiệu suất: finished on time, late, open and late, progress reports, per person, per project, and the productivity of
// the crews (from the industry layer). Each sees their own; a team leader their team; perf.view_project everyone in
// that project; perf.view_all everyone.
const filters = reactive({ period: "4w", project: "", team: "" });
const data = ref({ people: [], projects: [], crews: [], total: {}, scope: {} });
const teams = ref([]);
const loading = ref(false);
const error = ref("");
const person = ref(null);
const personLoading = ref(false);

const scopeText = computed(() => {
  const scope = data.value.scope || {};
  if (scope.all) return "Bạn xem được hiệu suất của mọi người.";
  const parts = ["của chính bạn"];
  if (scope.teams?.length) parts.push("tổ đội bạn phụ trách");
  if (scope.projects?.length) parts.push(`mọi người trong ${scope.projects.length} dự án bạn có quyền xem hiệu suất`);
  return `Bạn xem được hiệu suất ${parts.join(", ")}.`;
});
const rateTone = (rate) => (rate === null || rate === undefined ? "" : rate < 0.7 ? "text-danger" : rate < 0.9 ? "text-warning" : "text-success");
const maxDone = computed(() => Math.max(1, ...(person.value?.trend || []).map((w) => w.done + w.open_late)));

async function load() {
  loading.value = true;
  error.value = "";
  try {
    data.value = await api.people.performance({ period: filters.period, project: filters.project || null, team: filters.team || null });
  } catch (e) {
    error.value = e.message;
  } finally {
    loading.value = false;
  }
}

async function openPerson(row) {
  person.value = { user: row.user, full_name: row.full_name, total: row, projects: [], tasks: [], trend: [] };
  personLoading.value = true;
  try {
    person.value = await api.people.person(row.user, { period: filters.period });
  } catch (e) {
    error.value = e.message;
    person.value = null;
  } finally {
    personLoading.value = false;
  }
}

watch(() => [filters.period, filters.project, filters.team], load);
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
  <PageHeader title="Hiệu suất" :subtitle="scopeText">
    <button class="btn btn-ghost" type="button" :disabled="loading" @click="load"><Icon name="refresh-cw" :size="16" /> Tải lại</button>
  </PageHeader>

  <div class="card mb-4 flex flex-wrap items-end gap-3 p-3">
    <div role="group" aria-label="Khoảng thời gian" class="flex gap-1">
      <button v-for="p in PERIODS" :key="p.key" type="button" class="btn" :class="filters.period === p.key ? 'btn-primary' : 'btn-ghost'"
              :aria-pressed="filters.period === p.key" @click="filters.period = p.key">{{ p.label }}</button>
    </div>
    <div>
      <label class="label" for="pf-team">Tổ đội, phòng</label>
      <select id="pf-team" v-model="filters.team" class="input w-auto">
        <option value="">Tất cả</option>
        <option v-for="team in teams" :key="team.name" :value="team.name">{{ team.team_name }}</option>
      </select>
    </div>
    <div class="min-w-[220px]">
      <label class="label" for="pf-project">Dự án</label>
      <LinkSelect v-model="filters.project" doctype="Project" input-id="pf-project" placeholder="Mọi dự án" />
    </div>
    <span class="text-sm text-ink-muted">{{ formatDate(data.first) }} – {{ formatDate(data.last) }}</span>
  </div>

  <div class="mb-4 grid grid-cols-2 gap-3 sm:grid-cols-4">
    <div class="card px-4 py-3"><span class="block text-xs text-ink-muted">Việc xong</span><span class="text-2xl font-semibold" data-total-done>{{ data.total.done || 0 }}</span></div>
    <div class="card px-4 py-3"><span class="block text-xs text-ink-muted">Đúng hạn</span><span class="text-2xl font-semibold" :class="rateTone(data.total.on_time_rate)">{{ percent(data.total.on_time_rate) }}</span></div>
    <div class="card px-4 py-3"><span class="block text-xs text-ink-muted">Đang trễ</span><span class="text-2xl font-semibold" :class="data.total.open_late ? 'text-danger' : ''">{{ data.total.open_late || 0 }}</span></div>
    <div class="card px-4 py-3"><span class="block text-xs text-ink-muted">Trễ trung bình</span><span class="text-2xl font-semibold">{{ data.total.avg_delay ?? "—" }}</span><span class="text-xs text-ink-muted"> ngày</span></div>
  </div>

  <p v-if="error" class="rounded-md bg-danger-soft px-3 py-2 text-sm text-danger" role="alert">{{ error }}</p>
  <EmptyState v-else-if="!loading && !data.people.length && !data.crews.length" icon="trending-up" title="Chưa có số liệu"
              text="Việc được giao (chịu trách nhiệm, thực hiện) xong hoặc trễ trong khoảng này sẽ hiện ở đây." />

  <template v-else>
    <section class="card mb-4 overflow-x-auto" aria-labelledby="pf-people">
      <h2 id="pf-people" class="m-0 px-4 pt-3 text-base font-semibold">Theo người</h2>
      <table class="w-full min-w-[720px] text-sm">
        <thead>
          <tr class="border-b border-line text-left text-xs text-ink-muted">
            <th class="px-4 py-2">Người</th><th class="px-2 py-2 text-right">Xong</th><th class="px-2 py-2 text-right">Đúng hạn</th>
            <th class="px-2 py-2 text-right">Xong trễ</th><th class="px-2 py-2 text-right">Trễ TB (ngày)</th>
            <th class="px-2 py-2 text-right">Đang trễ</th><th class="px-4 py-2 text-right">Lần báo tiến độ</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in data.people" :key="row.user" class="border-b border-line last:border-0" data-performance-row>
            <td class="px-4 py-2"><button type="button" class="text-left font-medium text-primary underline" @click="openPerson(row)">{{ row.full_name }}</button></td>
            <td class="px-2 py-2 text-right">{{ row.done }}</td>
            <td class="px-2 py-2 text-right font-semibold" :class="rateTone(row.on_time_rate)">{{ percent(row.on_time_rate) }}</td>
            <td class="px-2 py-2 text-right">{{ row.late_done }}</td>
            <td class="px-2 py-2 text-right">{{ row.avg_delay ?? "—" }}</td>
            <td class="px-2 py-2 text-right" :class="row.open_late ? 'font-semibold text-danger' : ''">{{ row.open_late }}</td>
            <td class="px-4 py-2 text-right">{{ row.reports }}</td>
          </tr>
        </tbody>
      </table>
    </section>

    <section v-if="data.projects.length" class="card mb-4 overflow-x-auto" aria-labelledby="pf-projects">
      <h2 id="pf-projects" class="m-0 px-4 pt-3 text-base font-semibold">Theo dự án</h2>
      <table class="w-full min-w-[560px] text-sm">
        <thead>
          <tr class="border-b border-line text-left text-xs text-ink-muted">
            <th class="px-4 py-2">Dự án</th><th class="px-2 py-2 text-right">Xong</th><th class="px-2 py-2 text-right">Đúng hạn</th>
            <th class="px-2 py-2 text-right">Đang trễ</th><th class="px-4 py-2 text-right">Trễ TB (ngày)</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in data.projects" :key="row.project" class="border-b border-line last:border-0">
            <td class="px-4 py-2"><RouterLink :to="`/du-an/${encodeURIComponent(row.project)}/tong-quan`">{{ row.project_name }}</RouterLink></td>
            <td class="px-2 py-2 text-right">{{ row.done }}</td>
            <td class="px-2 py-2 text-right font-semibold" :class="rateTone(row.on_time_rate)">{{ percent(row.on_time_rate) }}</td>
            <td class="px-2 py-2 text-right" :class="row.open_late ? 'text-danger' : ''">{{ row.open_late }}</td>
            <td class="px-4 py-2 text-right">{{ row.avg_delay ?? "—" }}</td>
          </tr>
        </tbody>
      </table>
    </section>

    <section v-if="data.crews.length" class="card mb-4 overflow-x-auto" aria-labelledby="pf-crews">
      <h2 id="pf-crews" class="m-0 px-4 pt-3 text-base font-semibold">Năng suất tổ đội</h2>
      <p class="m-0 px-4 text-xs text-ink-muted">Khối lượng nhật ký đã nộp chia cho số công đã xác nhận trên cùng công tác.</p>
      <table class="w-full min-w-[560px] text-sm">
        <thead>
          <tr class="border-b border-line text-left text-xs text-ink-muted">
            <th class="px-4 py-2">Tổ đội</th><th class="px-2 py-2">Đơn vị</th><th class="px-2 py-2 text-right">Khối lượng</th>
            <th class="px-2 py-2 text-right">Công</th><th class="px-2 py-2 text-right">Năng suất / công</th><th class="px-4 py-2 text-right">Công tác</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in data.crews" :key="`${row.team}-${row.uom}`" class="border-b border-line last:border-0" data-crew-row>
            <td class="px-4 py-2">{{ row.team_name }}</td><td class="px-2 py-2">{{ row.uom || "—" }}</td>
            <td class="px-2 py-2 text-right">{{ row.qty }}</td><td class="px-2 py-2 text-right">{{ row.man_days }}</td>
            <td class="px-2 py-2 text-right font-semibold">{{ row.per_man_day ?? "—" }}</td><td class="px-4 py-2 text-right">{{ row.works }}</td>
          </tr>
        </tbody>
      </table>
    </section>
  </template>

  <Drawer :open="!!person" :title="person?.full_name || ''" @close="person = null">
    <div v-if="person" class="space-y-5" data-person-drawer>
      <p v-if="personLoading" class="text-sm text-ink-muted">Đang tải…</p>
      <template v-else>
        <p class="m-0 text-sm">Xong <strong>{{ person.total?.done || 0 }}</strong>, đúng hạn <strong :class="rateTone(person.total?.on_time_rate)">{{ percent(person.total?.on_time_rate) }}</strong>, đang trễ <strong>{{ person.total?.open_late || 0 }}</strong></p>
        <section v-if="person.projects.length">
          <h3 class="mb-2 text-sm font-semibold">Theo dự án</h3>
          <ul class="m-0 list-none space-y-1 p-0 text-sm">
            <li v-for="row in person.projects" :key="row.project">{{ row.project_name }}: xong {{ row.done }}, đúng hạn {{ percent(row.on_time_rate) }}, đang trễ {{ row.open_late }}</li>
          </ul>
        </section>
        <section v-if="person.trend.length">
          <h3 class="mb-2 text-sm font-semibold">Các tuần trước</h3>
          <div class="flex items-end gap-1" role="img" :aria-label="`Việc xong và đang trễ của ${person.full_name} theo tuần`">
            <div v-for="week in person.trend" :key="week.week" class="flex flex-1 flex-col items-center gap-0.5">
              <span class="w-full rounded-t bg-danger" :style="{ height: `${(week.open_late / maxDone) * 60}px` }"></span>
              <span class="w-full rounded-b bg-success" :style="{ height: `${(week.done / maxDone) * 60}px` }"></span>
              <span class="text-[10px] text-ink-muted">{{ weekLabel(week.week) }}</span>
            </div>
          </div>
          <p class="mt-1 text-xs text-ink-muted"><span class="text-success">■</span> xong · <span class="text-danger">■</span> trễ cuối tuần</p>
        </section>
        <section>
          <h3 class="mb-2 text-sm font-semibold">Việc xong và việc trễ</h3>
          <p v-if="!person.tasks.length" class="text-sm text-ink-muted">Không có việc nào trong khoảng này.</p>
          <ul class="m-0 list-none space-y-2 p-0">
            <li v-for="task in person.tasks" :key="task.name" class="rounded-md border border-line px-3 py-2 text-sm">
              <RouterLink :to="`/cong-viec/${encodeURIComponent(task.name)}`" class="font-medium">{{ task.pm_wbs_code }} {{ task.subject }}</RouterLink>
              <span v-if="task.late" class="badge badge-danger ml-1">Trễ</span>
              <span class="block text-xs text-ink-muted">{{ task.project_name }} · {{ statusLabel(task.status) }} · hạn {{ formatDate(task.exp_end_date) }}<template v-if="task.act_end_date"> · xong {{ formatDate(task.act_end_date) }}</template></span>
            </li>
          </ul>
        </section>
      </template>
    </div>
  </Drawer>
</template>
