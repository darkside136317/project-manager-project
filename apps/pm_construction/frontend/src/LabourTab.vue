<script setup>
import { computed, inject, onBeforeUnmount, onMounted, ref, watch } from "vue";
import Icon from "@pm/components/Icon.vue";
import ReasonDialog from "@pm/components/ReasonDialog.vue";
import { formatDate } from "@pm/lib/format.js";
import { network, onSent, queueItem } from "@pm/lib/sync.js";
import { toast } from "@pm/lib/toast.js";
import { SHEET_TONE, attendanceLines, construction, moneyText, qtyText, site, today } from "./construction.js";

// Chấm công: a crew on a day — who worked on which work item, how many man-days. The crew lead writes and submits it
// (queued without a connection); the site commander confirms it or sends it back. Confirmed man-days are the labour cost.
const { name: project } = inject("project");
const data = ref(null);
const works = ref([]);
const team = ref("");
const day = ref(today());
const sheet = ref(null);
const lines = ref([]);
const error = ref("");
const busy = ref(false);
const sendingBack = ref(false);

const can = computed(() => sheet.value?.can || {});
const finance = computed(() => Boolean(data.value?.can?.finance));
const queued = computed(() => network.items.find((item) => item.kind === "attendance" && item.payload.project === project.value
  && item.payload.team === team.value && item.payload.day === day.value));
const total = computed(() => attendanceLines(lines.value).total);

async function load() {
  error.value = "";
  try {
    data.value = await site.labour(project.value);
    if (!team.value && data.value.crews.length) team.value = data.value.crews[0].name;
    if (!works.value.length) works.value = await construction.diaryWorks(project.value).catch(() => []);
  } catch (e) {
    error.value = e.message;
  }
}

async function loadSheet() {
  if (!team.value) return;
  try {
    sheet.value = await site.sheet(project.value, team.value, day.value);
    lines.value = sheet.value.lines.map((line) => ({ ...line, man_days: line.man_days ?? 1, overtime_hours: line.overtime_hours || "" }));
  } catch (e) {
    toast(e.message, "error");
  }
}

async function submit() {
  const { lines: rows, errors } = attendanceLines(lines.value);
  if (errors.length) return toast(errors.join("\n"), "error", 7000);
  if (!rows.length) return toast("Chưa chấm công cho ai", "error");
  const crew = data.value.crews.find((c) => c.name === team.value)?.team_name || team.value;
  const [y, m, d] = day.value.split("-");
  await queueItem("attendance", { project: project.value, team: team.value, day: day.value, lines: rows }, {
    label: `Chấm công ${crew} ngày ${d}/${m}/${y}`, reference: { doctype: "Project", name: project.value, link: `/du-an/${project.value}/cham-cong` } });
  if (!network.online) toast("Chưa có mạng: bảng chấm công được giữ lại, sẽ tự gửi khi có mạng", "warning", 7000);
}

async function confirmSheet() {
  busy.value = true;
  try {
    sheet.value = await site.attendanceConfirm(sheet.value.name);
    toast("Đã xác nhận chấm công");
    load();
  } catch (e) {
    toast(e.message, "error");
  } finally {
    busy.value = false;
  }
}

async function sendBack(reason) {
  busy.value = true;
  try {
    sheet.value = await site.attendanceSendBack(sheet.value.name, reason);
    sendingBack.value = false;
    toast("Đã trả lại bảng chấm công");
    await loadSheet();
    load();
  } catch (e) {
    toast(e.message, "error");
  } finally {
    busy.value = false;
  }
}

function open(row) {
  team.value = row.team;
  day.value = String(row.attendance_date);
}

const stopSent = onSent((item, answer) => {
  if (item.kind !== "attendance" || item.payload.project !== project.value) return;
  toast(`Đã nộp ${item.label.toLowerCase()}`);
  if (item.payload.team === team.value && item.payload.day === day.value) sheet.value = answer;
  load();
});
onBeforeUnmount(stopSent);
watch([team, day], loadSheet);
onMounted(async () => {
  await load();
  loadSheet();
});
</script>

<template>
  <p v-if="error" class="rounded-md bg-danger-soft px-3 py-2 text-sm text-danger" role="alert">{{ error }}</p>
  <div v-else-if="data" class="grid gap-4 lg:grid-cols-[1fr_300px]" data-labour>
    <section class="card min-w-0 p-4" aria-labelledby="sheet-title">
      <h2 id="sheet-title" class="sr-only">Bảng chấm công</h2>
      <p v-if="!data.crews.length" class="m-0 text-sm text-ink-muted">Chưa có tổ đội nào (Danh mục → Đội, tổ, loại "Tổ đội") hoặc tổ đội chưa có công nhân.</p>
      <div v-else class="flex flex-wrap items-center gap-2">
        <label class="sr-only" for="att-team">Tổ đội</label>
        <select id="att-team" v-model="team" class="input w-auto">
          <option v-for="crew in data.crews" :key="crew.name" :value="crew.name">{{ crew.team_name }} ({{ crew.workers.length }})</option>
        </select>
        <label class="sr-only" for="att-day">Ngày</label>
        <input id="att-day" v-model="day" class="input w-auto" type="date" :max="today()" />
        <span v-if="sheet?.name" class="badge" :class="SHEET_TONE[sheet.status]">{{ sheet.status }}</span>
        <span v-else-if="sheet" class="text-sm text-ink-muted">Chưa chấm công ngày này</span>
      </div>
      <p v-if="queued" class="m-0 mt-2 rounded-md border border-dashed border-warning bg-warning-soft p-2 text-sm">
        {{ queued.state === "failed" ? `Không gửi được: ${queued.error}` : network.online ? "Đang gửi chấm công…" : "Bảng chấm công đang chờ có mạng để gửi" }}</p>
      <p v-if="sheet?.return_note" class="m-0 mt-2 rounded-md bg-danger-soft p-2 text-sm text-danger">Bị trả lại: {{ sheet.return_note }}</p>

      <ul v-if="sheet" class="m-0 mt-3 list-none divide-y divide-line p-0">
        <li v-for="(line, index) in lines" :key="line.worker" class="py-2" data-attendance-line>
          <p class="m-0 text-sm font-medium">{{ line.worker_name }} <span class="text-xs font-normal text-ink-muted">{{ line.trade }}</span></p>
          <div v-if="can.write" class="mt-1 grid grid-cols-[1fr_80px_80px] gap-2">
            <select v-model="line.task" class="input" :aria-label="`Công tác của ${line.worker_name}`">
              <option :value="null">Không gắn công tác</option>
              <option v-for="work in works" :key="work.name" :value="work.name">{{ work.pm_wbs_code }} {{ work.subject }}</option>
            </select>
            <input v-model="line.man_days" class="input" inputmode="decimal" :aria-label="`Số công của ${line.worker_name}`" />
            <input v-model="line.overtime_hours" class="input" inputmode="decimal" placeholder="Giờ TC" :aria-label="`Giờ tăng ca của ${line.worker_name}`" />
          </div>
          <p v-else class="m-0 text-sm text-ink-muted">{{ qtyText(line.man_days) }} công · {{ line.task_label || "không gắn công tác" }}
            <template v-if="line.overtime_hours"> · {{ line.overtime_hours }} giờ tăng ca</template>
            <template v-if="finance && line.amount"> · {{ moneyText(line.amount) }}</template></p>
          <span v-if="index === 0" class="sr-only">Số công: 1 là cả ngày, 0,5 là nửa ngày, 0 là nghỉ</span>
        </li>
      </ul>
      <p v-if="sheet" class="m-0 mt-2 text-sm">Tổng: <strong>{{ qtyText(sheet.name && !can.write ? sheet.total_man_days : total) }} công</strong>
        <template v-if="finance && sheet.total_amount"> · {{ moneyText(sheet.total_amount) }}</template></p>
      <div v-if="sheet" class="mt-3 flex flex-wrap gap-2">
        <button v-if="can.submit" class="btn btn-primary" type="button" :disabled="busy" @click="submit"><Icon name="send" :size="16" /> Nộp chấm công</button>
        <button v-if="can.confirm" class="btn btn-primary" type="button" :disabled="busy" @click="confirmSheet"><Icon name="check" :size="16" /> Xác nhận</button>
        <button v-if="can.send_back" class="btn" type="button" :disabled="busy" @click="sendingBack = true"><Icon name="undo" :size="16" /> Trả lại</button>
      </div>
    </section>

    <aside class="card p-4" aria-labelledby="sheets-title">
      <h2 id="sheets-title" class="m-0 text-sm font-semibold">30 ngày gần đây</h2>
      <p v-if="!data.sheets.length" class="mt-2 text-sm text-ink-muted">Chưa có bảng chấm công.</p>
      <ul class="m-0 mt-2 list-none space-y-1 p-0 text-sm">
        <li v-for="row in data.sheets" :key="row.name">
          <button class="w-full text-left hover:underline" type="button" @click="open(row)">
            {{ formatDate(row.attendance_date) }} · {{ row.team_name }}: {{ qtyText(row.total_man_days) }} công
            <span class="badge ml-1" :class="SHEET_TONE[row.status]">{{ row.status }}</span>
          </button>
        </li>
      </ul>
    </aside>
  </div>

  <ReasonDialog :open="sendingBack" title="Trả lại bảng chấm công" label="Lý do" confirm-text="Trả lại" :busy="busy"
                @confirm="sendBack" @cancel="sendingBack = false" />
</template>
