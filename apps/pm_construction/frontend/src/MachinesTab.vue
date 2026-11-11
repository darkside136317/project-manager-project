<script setup>
import { computed, inject, onBeforeUnmount, onMounted, reactive, ref } from "vue";
import Drawer from "@pm/components/Drawer.vue";
import Icon from "@pm/components/Icon.vue";
import { formatDate } from "@pm/lib/format.js";
import { network, onSent, queueItem } from "@pm/lib/sync.js";
import { toast } from "@pm/lib/toast.js";
import { clashText, construction, moneyText, qtyText, site, today } from "./construction.js";

// Máy: the machines at the project, their shifts on work items (written on site, queued without a connection), fuel
// against the norm; the planner brings machines in and sends them back, and books machines ahead (đặt máy): another
// project's booking of the same days is a conflict, shown here and on the workload page.
const { name: project } = inject("project");
const data = ref(null);
const works = ref([]);
const error = ref("");
const busy = ref(false);
const shift = reactive({ open: false, machine: "", task: "", shift_date: today(), shifts: "1", hours: "", fuel: "", operator: "", note: "" });
const move = reactive({ open: false, machine: "", note: "" });
const booking = reactive({ open: false, machine: "", task: "", from_date: today(), to_date: today(), note: "" });

const can = computed(() => data.value?.can || {});
const queued = computed(() => network.items.filter((item) => item.kind === "machine-shift" && item.payload.project === project.value));

async function load() {
  error.value = "";
  try {
    data.value = await site.machines(project.value);
    if (!works.value.length) works.value = await construction.diaryWorks(project.value).catch(() => []);
  } catch (e) {
    error.value = e.message;
  }
}

function openShift(machine = "") {
  Object.assign(shift, { open: true, machine: machine || data.value?.machines[0]?.name || "", task: "", shift_date: today(),
    shifts: "1", hours: "", fuel: "", operator: "", note: "" });
}

async function saveShift() {
  const shifts = Number(String(shift.shifts).replace(",", "."));
  if (!shift.machine) return toast("Chọn máy", "error");
  if (!(shifts > 0 && shifts <= 3)) return toast("Số ca từ 0 đến 3", "error");
  const payload = { project: project.value, machine: shift.machine, task: shift.task || null, shift_date: shift.shift_date, shifts,
    hours: Number(String(shift.hours).replace(",", ".")) || null, fuel: Number(String(shift.fuel).replace(",", ".")) || null,
    operator: shift.operator, note: shift.note };
  const name = data.value.machines.find((m) => m.name === shift.machine)?.machine_name || shift.machine;
  await queueItem("machine-shift", payload, { label: `Ca máy ${name}`, reference: { doctype: "Project", name: project.value, link: `/du-an/${project.value}/may` } });
  if (!network.online) toast("Chưa có mạng: ca máy được giữ lại, sẽ tự gửi khi có mạng", "warning", 7000);
  shift.open = false;
}

async function bring() {
  if (!move.machine) return toast("Chọn máy", "error");
  busy.value = true;
  try {
    await site.moveMachine(move.machine, project.value, today(), move.note);
    toast("Đã đưa máy vào dự án");
    move.open = false;
    await load();
  } catch (e) {
    toast(e.message, "error", 8000);
  } finally {
    busy.value = false;
  }
}

async function release(machine) {
  try {
    await site.moveMachine(machine.name, null, today(), "Trả về công ty");
    toast(`Đã trả ${machine.machine_name} về công ty`);
    await load();
  } catch (e) {
    toast(e.message, "error", 8000);
  }
}

async function book() {
  if (!booking.machine) return toast("Chọn máy", "error");
  if (booking.to_date < booking.from_date) return toast("Ngày kết thúc phải sau ngày bắt đầu", "error");
  busy.value = true;
  try {
    const result = await site.book({ project: project.value, machine: booking.machine, task: booking.task || null,
      from_date: booking.from_date, to_date: booking.to_date, note: booking.note });
    if (result.clashes.length) toast(`Đã đặt máy, nhưng trùng lịch với ${clashText(result.clashes)}`, "warning", 9000);
    else toast("Đã đặt máy");
    booking.open = false;
    await load();
  } catch (e) {
    toast(e.message, "error", 8000);
  } finally {
    busy.value = false;
  }
}

async function cancelBooking(row) {
  try {
    await site.cancelBooking(row.name);
    toast("Đã hủy lượt đặt máy");
    await load();
  } catch (e) {
    toast(e.message, "error");
  }
}

async function removeShift(row) {
  try {
    await site.deleteShift(row.name);
    toast("Đã xóa ca máy");
    await load();
  } catch (e) {
    toast(e.message, "error");
  }
}

const stopSent = onSent((item) => {
  if (item.kind !== "machine-shift" || item.payload.project !== project.value) return;
  toast(`Đã ghi ${item.label.toLowerCase()}`);
  load();
});
onBeforeUnmount(stopSent);
onMounted(load);
</script>

<template>
  <p v-if="error" class="rounded-md bg-danger-soft px-3 py-2 text-sm text-danger" role="alert">{{ error }}</p>
  <div v-else-if="data" class="space-y-4" data-machines>
    <section class="card p-4" aria-labelledby="machines-title">
      <div class="flex flex-wrap items-center gap-2">
        <h2 id="machines-title" class="m-0 flex-1 text-sm font-semibold">Máy đang ở dự án</h2>
        <button v-if="can.record && data.machines.length" class="btn btn-primary" type="button" @click="openShift()"><Icon name="clock" :size="16" /> Ghi ca máy</button>
        <button v-if="can.move" class="btn" type="button" @click="Object.assign(move, { open: true, machine: '', note: '' })"><Icon name="truck" :size="16" /> Đưa máy vào</button>
      </div>
      <p v-for="item in queued" :key="item.id" class="m-0 mt-2 rounded-md border border-dashed border-warning bg-warning-soft p-2 text-sm">
        {{ item.state === "failed" ? `Không gửi được: ${item.error}` : network.online ? "Đang gửi ca máy…" : "Ca máy đang chờ có mạng để gửi" }}
      </p>
      <p v-if="!data.machines.length" class="mt-2 text-sm text-ink-muted">Chưa có máy nào ở dự án.</p>
      <ul class="m-0 mt-2 grid list-none gap-2 p-0 sm:grid-cols-2">
        <li v-for="machine in data.machines" :key="machine.name" class="rounded-lg border border-line p-3 text-sm" data-machine>
          <div class="flex items-start justify-between gap-2">
            <div><strong>{{ machine.machine_name }}</strong>
              <span class="block text-xs text-ink-muted">{{ machine.machine_type || machine.name }} · {{ machine.ownership }} · từ {{ formatDate(machine.since) }}</span></div>
            <span class="badge badge-info">{{ machine.status }}</span>
          </div>
          <p class="m-0 mt-2">{{ qtyText(machine.shifts_total) }} ca · nhiên liệu {{ qtyText(machine.fuel_total, "lít") }}
            <span v-if="machine.fuel_norm" :class="machine.fuel_total > machine.fuel_expected * 1.05 ? 'font-semibold text-danger' : 'text-ink-muted'">
              (định mức {{ qtyText(machine.fuel_expected, "lít") }})</span></p>
          <p v-if="can.finance" class="m-0 text-xs text-ink-muted">Chi phí {{ moneyText(machine.amount_total) }} · {{ moneyText(machine.shift_rate) }}/ca</p>
          <p v-if="machine.next_maintenance" class="m-0 text-xs" :class="machine.next_maintenance <= today() ? 'text-danger' : 'text-ink-muted'">Bảo dưỡng tiếp theo {{ formatDate(machine.next_maintenance) }}</p>
          <div class="mt-2 flex gap-2">
            <button v-if="can.record" class="btn" type="button" @click="openShift(machine.name)">Ghi ca</button>
            <button v-if="can.move" class="btn btn-ghost" type="button" @click="release(machine)">Trả về công ty</button>
          </div>
        </li>
      </ul>
    </section>

    <section v-if="can.book || data.bookings?.length" class="card p-4" aria-labelledby="bookings-title" data-bookings>
      <div class="flex flex-wrap items-center gap-2">
        <h2 id="bookings-title" class="m-0 flex-1 text-sm font-semibold">Lịch đặt máy</h2>
        <button v-if="can.book" class="btn" type="button" @click="Object.assign(booking, { open: true, machine: '', task: '', from_date: today(), to_date: today(), note: '' })"><Icon name="calendar-clock" :size="16" /> Đặt máy</button>
      </div>
      <p v-if="!data.bookings?.length" class="mt-2 text-sm text-ink-muted">Chưa đặt máy nào.</p>
      <ul class="m-0 mt-2 list-none divide-y divide-line p-0 text-sm">
        <li v-for="row in data.bookings" :key="row.name" class="flex flex-wrap items-center gap-2 py-2" data-booking>
          <span class="w-28 text-xs text-ink-muted">{{ formatDate(row.from_date) }} – {{ formatDate(row.to_date) }}</span>
          <span class="min-w-0 flex-1"><strong>{{ row.machine_name }}</strong><template v-if="row.note"> · {{ row.note }}</template>
            <span v-if="row.clashes.length" class="block text-xs font-semibold text-danger" data-booking-clash>Trùng lịch: {{ clashText(row.clashes) }}</span></span>
          <button v-if="can.book" class="btn btn-ghost" type="button" :aria-label="`Hủy đặt ${row.machine_name}`" @click="cancelBooking(row)"><Icon name="x" :size="14" /></button>
        </li>
      </ul>
    </section>

    <section class="card p-4" aria-labelledby="shifts-title">
      <h2 id="shifts-title" class="m-0 text-sm font-semibold">Ca máy gần đây</h2>
      <p v-if="!data.shifts.length" class="mt-2 text-sm text-ink-muted">Chưa ghi ca máy nào.</p>
      <ul class="m-0 mt-2 list-none divide-y divide-line p-0 text-sm">
        <li v-for="row in data.shifts" :key="row.name" class="flex flex-wrap items-center gap-2 py-2" data-shift>
          <span class="w-16 text-xs text-ink-muted">{{ formatDate(row.shift_date) }}</span>
          <span class="min-w-0 flex-1"><strong>{{ row.machine_name }}</strong> · {{ qtyText(row.shifts) }} ca<template v-if="row.fuel"> · {{ qtyText(row.fuel, "lít") }}</template>
            <span class="block text-xs text-ink-muted">{{ row.task_label || "Không gắn công tác" }}<template v-if="row.operator"> · {{ row.operator }}</template></span></span>
          <span v-if="can.finance" class="text-xs">{{ moneyText(row.amount, { short: true }) }}</span>
          <button v-if="can.record" class="btn btn-ghost" type="button" :aria-label="`Xóa ca máy ${row.machine_name} ngày ${formatDate(row.shift_date)}`" @click="removeShift(row)"><Icon name="trash-2" :size="14" /></button>
        </li>
      </ul>
    </section>
  </div>

  <Drawer :open="shift.open" title="Ghi ca máy" width="480px" @close="shift.open = false">
    <form id="shift-form" class="space-y-3" @submit.prevent="saveShift">
      <div><label class="label" for="shift-machine">Máy</label>
        <select id="shift-machine" v-model="shift.machine" class="input">
          <option v-for="machine in data?.machines || []" :key="machine.name" :value="machine.name">{{ machine.machine_name }}</option>
        </select></div>
      <div><label class="label" for="shift-task">Công tác</label>
        <select id="shift-task" v-model="shift.task" class="input">
          <option value="">Không gắn công tác</option>
          <option v-for="work in works" :key="work.name" :value="work.name">{{ work.pm_wbs_code }} {{ work.subject }}</option>
        </select></div>
      <div class="grid grid-cols-2 gap-2">
        <div><label class="label" for="shift-date">Ngày</label><input id="shift-date" v-model="shift.shift_date" class="input" type="date" :max="today()" /></div>
        <div><label class="label" for="shift-shifts">Số ca</label><input id="shift-shifts" v-model="shift.shifts" class="input" inputmode="decimal" /></div>
        <div><label class="label" for="shift-hours">Số giờ</label><input id="shift-hours" v-model="shift.hours" class="input" inputmode="decimal" /></div>
        <div><label class="label" for="shift-fuel">Nhiên liệu (lít)</label><input id="shift-fuel" v-model="shift.fuel" class="input" inputmode="decimal" /></div>
      </div>
      <div><label class="label" for="shift-operator">Người vận hành</label><input id="shift-operator" v-model="shift.operator" class="input" /></div>
      <div><label class="label" for="shift-note">Ghi chú</label><textarea id="shift-note" v-model="shift.note" class="input" rows="2"></textarea></div>
    </form>
    <template #footer>
      <button class="btn" type="button" @click="shift.open = false">Hủy</button>
      <button class="btn btn-primary" type="submit" form="shift-form">Ghi ca máy</button>
    </template>
  </Drawer>

  <Drawer :open="move.open" title="Đưa máy vào dự án" width="440px" @close="move.open = false">
    <form id="move-form" class="space-y-3" @submit.prevent="bring">
      <div><label class="label" for="move-machine">Máy đang rảnh</label>
        <select id="move-machine" v-model="move.machine" class="input">
          <option value="">Chọn máy</option>
          <option v-for="machine in data?.free || []" :key="machine.name" :value="machine.name">{{ machine.machine_name }} ({{ machine.ownership }})</option>
        </select>
        <p v-if="!(data?.free || []).length" class="mt-1 text-xs text-ink-muted">Không có máy rảnh: máy đang ở dự án khác phải trả về công ty trước.</p></div>
      <div><label class="label" for="move-note">Ghi chú</label><textarea id="move-note" v-model="move.note" class="input" rows="2"></textarea></div>
    </form>
    <template #footer>
      <button class="btn" type="button" @click="move.open = false">Hủy</button>
      <button class="btn btn-primary" type="submit" form="move-form" :disabled="busy">Đưa vào</button>
    </template>
  </Drawer>

  <Drawer :open="booking.open" title="Đặt máy cho dự án" width="440px" @close="booking.open = false">
    <form id="booking-form" class="space-y-3" @submit.prevent="book">
      <div><label class="label" for="booking-machine">Máy</label>
        <select id="booking-machine" v-model="booking.machine" class="input">
          <option value="">Chọn máy</option>
          <option v-for="machine in data?.bookable || []" :key="machine.name" :value="machine.name">{{ machine.machine_name }}{{ machine.machine_type ? ` (${machine.machine_type})` : "" }}</option>
        </select></div>
      <div><label class="label" for="booking-task">Công tác</label>
        <select id="booking-task" v-model="booking.task" class="input">
          <option value="">Không gắn công tác</option>
          <option v-for="work in works" :key="work.name" :value="work.name">{{ work.pm_wbs_code }} {{ work.subject }}</option>
        </select></div>
      <div class="grid grid-cols-2 gap-2">
        <div><label class="label" for="booking-from">Từ ngày</label><input id="booking-from" v-model="booking.from_date" class="input" type="date" required /></div>
        <div><label class="label" for="booking-to">Đến ngày</label><input id="booking-to" v-model="booking.to_date" class="input" type="date" :min="booking.from_date" required /></div>
      </div>
      <div><label class="label" for="booking-note">Ghi chú</label><textarea id="booking-note" v-model="booking.note" class="input" rows="2"></textarea></div>
      <p class="m-0 text-xs text-ink-muted">Dự án khác đã đặt cùng máy trùng ngày: vẫn đặt được, nhưng sẽ hiện là xung đột ở trang Khối lượng công việc.</p>
    </form>
    <template #footer>
      <button class="btn" type="button" @click="booking.open = false">Hủy</button>
      <button class="btn btn-primary" type="submit" form="booking-form" :disabled="busy">Đặt máy</button>
    </template>
  </Drawer>
</template>
