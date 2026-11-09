<script setup>
import { computed, inject, onBeforeUnmount, onMounted, reactive, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import Icon from "@pm/components/Icon.vue";
import ReasonDialog from "@pm/components/ReasonDialog.vue";
import Lightbox from "@pm/components/timeline/Lightbox.vue";
import PhotoGrid from "@pm/components/timeline/PhotoGrid.vue";
import { formatDate, formatDateTime } from "@pm/lib/format.js";
import { network, onSent, preparePhotos, queueItem } from "@pm/lib/sync.js";
import { toast } from "@pm/lib/toast.js";
import { DIARY_TONE, construction, diaryRows, qtyText, today } from "./construction.js";

// Nhật ký thi công: one diary per day. On site: weather, people, what was done, the quantity of each work item, photos;
// submitted through the outbox, so it also works without a connection. The commander confirms it or sends it back.
const { name: project, openTask, reload } = inject("project");
const route = useRoute();
const router = useRouter();
const list = ref(null);
const day = ref(String(route.query.ngay || today()));
const current = ref(null);
const works = ref([]);
const lines = ref([]);
const photos = ref([]);
const form = reactive({ weather: "", temperature: "", workers: "", work_summary: "", issues: "", safety: "" });
const busy = ref(false);
const preparing = ref(false);
const sendingBack = ref(false);
const lightbox = ref({ photos: [], index: -1 });
const camera = ref(null);
const gallery = ref(null);

const editable = computed(() => Boolean(current.value?.can?.edit));
const queued = computed(() => network.items.find((item) => item.kind === "diary" && item.payload.project === project.value && item.payload.day === day.value));
const workOptions = computed(() => works.value.map((w) => ({ ...w, label: `${w.pm_wbs_code || ""} ${w.subject}`.trim() })));

async function loadList() {
  try {
    list.value = await construction.diaries(project.value);
  } catch (e) {
    toast(e.message, "error");
  }
}

async function loadDay() {
  try {
    current.value = await construction.diaryDay(project.value, day.value);
  } catch (e) {
    current.value = null;
    toast(e.message, "error");
    return;
  }
  for (const key of Object.keys(form)) form[key] = current.value[key] ?? "";
  lines.value = (current.value.rows || []).map((row) => ({ task: row.task, label: row.label, qty: row.qty, note: row.note || "", uom: row.uom }));
  if (editable.value && !lines.value.length) lines.value.push(blank());
  photos.value = [];
  if (editable.value && !works.value.length) works.value = await construction.diaryWorks(project.value).catch(() => []);
}

function blank() {
  return { task: "", label: "", qty: "", note: "", uom: "", query: "" };
}

function pick(line, work) {
  Object.assign(line, { task: work.name, label: work.label, uom: work.pmc_uom, query: "", remaining: work.remaining });
}

function matches(line) {
  const text = (line.query || "").toLowerCase();
  return workOptions.value.filter((w) => !text || w.label.toLowerCase().includes(text) || (w.pmc_norm_code || "").toLowerCase().includes(text)).slice(0, 8);
}

async function onFiles(event) {
  const files = [...(event.target.files || [])];
  event.target.value = "";
  if (!files.length) return;
  preparing.value = true;
  try {
    const ready = await preparePhotos(files.slice(0, 12 - photos.value.length));
    for (const photo of ready) photo.preview = URL.createObjectURL(new Blob([photo.data], { type: photo.type }));
    photos.value = [...photos.value, ...ready];
  } finally {
    preparing.value = false;
  }
}

function values() {
  return { ...form, workers: Number(form.workers) || 0 };
}

async function saveDraft() {
  const { rows, errors } = diaryRows(lines.value);
  if (errors.length) return toast(errors.join("\n"), "error", 7000);
  busy.value = true;
  try {
    current.value = await construction.diarySave(project.value, day.value, values(), rows);
    toast("Đã lưu nháp");
    loadList();
  } catch (e) {
    toast(e.message, "error", 8000);
  } finally {
    busy.value = false;
  }
}

async function submit() {
  const { rows, errors } = diaryRows(lines.value);
  if (errors.length) return toast(errors.join("\n"), "error", 7000);
  if (!rows.length && !form.work_summary.trim()) return toast("Ghi công việc đã làm hoặc khối lượng", "error");
  busy.value = true;
  try {
    const ready = photos.value.map(({ preview, ...photo }) => photo);
    const [y, m, d] = day.value.split("-");
    await queueItem("diary", { project: project.value, day: day.value, values: values(), rows }, {
      reference: { doctype: "PMC Site Diary", name: current.value.name, link: `/du-an/${project.value}/nhat-ky?ngay=${day.value}` },
      photos: ready, label: `Nhật ký ngày ${d}/${m}/${y}`,
    });
    photos.value.forEach((photo) => photo.preview && URL.revokeObjectURL(photo.preview));
    photos.value = [];
    if (!network.online) toast("Chưa có mạng: nhật ký được giữ lại, sẽ tự gửi khi có mạng", "warning", 7000);
  } finally {
    busy.value = false;
  }
}

async function confirmDiary() {
  busy.value = true;
  try {
    current.value = await construction.diaryConfirm(current.value.name);
    toast("Đã xác nhận nhật ký");
    loadList();
  } catch (e) {
    toast(e.message, "error");
  } finally {
    busy.value = false;
  }
}

async function sendBack(reason) {
  busy.value = true;
  try {
    current.value = await construction.diarySendBack(current.value.name, reason);
    sendingBack.value = false;
    toast("Đã trả lại nhật ký");
    await loadDay();
    loadList();
    reload();
  } catch (e) {
    toast(e.message, "error");
  } finally {
    busy.value = false;
  }
}

const stopSent = onSent((item, answer) => {
  if (item.kind !== "diary" || item.payload.project !== project.value) return;
  toast(`Đã nộp ${item.label.toLowerCase()}`);
  if (item.payload.day === day.value) current.value = answer;
  loadList();
  reload();
});
onBeforeUnmount(stopSent);

watch(day, (value) => {
  router.replace({ query: { ...route.query, ngay: value } });
  loadDay();
});
onMounted(() => {
  loadList();
  loadDay();
});
</script>

<template>
  <div class="grid gap-4 lg:grid-cols-[1fr_300px]">
    <section class="min-w-0 space-y-3" aria-label="Nhật ký trong ngày">
      <div class="flex flex-wrap items-center gap-2">
        <label class="sr-only" for="diary-day">Ngày</label>
        <input id="diary-day" v-model="day" class="input w-auto" type="date" :max="today()" />
        <span v-if="current?.status" class="badge" :class="DIARY_TONE[current.status]">{{ current.status }}</span>
        <span v-else-if="current" class="text-sm text-ink-muted">Chưa có nhật ký ngày này</span>
      </div>

      <p v-if="queued" class="m-0 flex items-center gap-2 rounded-md border border-dashed border-warning bg-warning-soft p-2 text-sm">
        <Icon :name="queued.state === 'sending' ? 'loader' : 'cloud-upload'" :size="16" :spin="queued.state === 'sending'" />
        {{ queued.state === "failed" ? `Không gửi được: ${queued.error}` : network.online ? "Đang gửi nhật ký…" : "Nhật ký đang chờ có mạng để gửi" }}
      </p>
      <p v-if="current?.return_note" class="m-0 rounded-md bg-danger-soft p-2 text-sm text-danger">Bị trả lại: {{ current.return_note }}</p>

      <!-- writing -->
      <form v-if="current && editable" class="space-y-3" @submit.prevent="submit">
        <fieldset class="m-0 border-0 p-0">
          <legend class="label">Thời tiết</legend>
          <div class="flex flex-wrap gap-1.5">
            <button v-for="item in list?.weather || []" :key="item" type="button" class="rounded-full border px-3 py-1 text-sm"
              :class="form.weather === item ? 'border-primary bg-primary text-white' : 'border-line'" :aria-pressed="form.weather === item"
              @click="form.weather = form.weather === item ? '' : item">{{ item }}</button>
          </div>
        </fieldset>
        <div class="grid grid-cols-2 gap-3">
          <div><label class="label" for="diary-workers">Nhân công trên công trường</label><input id="diary-workers" v-model="form.workers" class="input" type="number" min="0" /></div>
          <div><label class="label" for="diary-temperature">Nhiệt độ</label><input id="diary-temperature" v-model="form.temperature" class="input" maxlength="40" placeholder="Ví dụ: 28–33 °C" /></div>
        </div>

        <section aria-labelledby="diary-qty">
          <h3 id="diary-qty" class="m-0 mb-1.5 text-sm font-semibold">Khối lượng đã làm</h3>
          <ul class="m-0 list-none space-y-2 p-0">
            <li v-for="(line, index) in lines" :key="index" class="rounded-lg border border-line p-2">
              <div class="relative">
                <p v-if="line.task" class="m-0 flex items-start gap-2 text-sm">
                  <span class="min-w-0 flex-1">{{ line.label }}<span v-if="line.remaining !== undefined" class="block text-xs text-ink-muted">Còn lại {{ qtyText(line.remaining, line.uom) }}</span></span>
                  <button type="button" class="text-xs underline" @click="Object.assign(line, blank())">Đổi</button>
                </p>
                <template v-else>
                  <label class="sr-only" :for="`diary-work-${index}`">Công tác</label>
                  <input :id="`diary-work-${index}`" v-model="line.query" class="input" placeholder="Gõ tên hoặc mã công tác" autocomplete="off" />
                  <ul v-if="line.query" class="absolute left-0 right-0 z-30 m-0 mt-1 max-h-60 list-none overflow-y-auto rounded-md border border-line bg-surface p-1 shadow-pop">
                    <li v-for="work in matches(line)" :key="work.name">
                      <button type="button" class="block w-full rounded px-2 py-1.5 text-left text-sm hover:bg-surface-muted" @click="pick(line, work)">
                        {{ work.label }} <span class="text-xs text-ink-muted">· còn {{ qtyText(work.remaining, work.pmc_uom) }}</span>
                      </button>
                    </li>
                    <li v-if="!matches(line).length" class="px-2 py-1.5 text-sm text-ink-muted">Không có công tác khớp</li>
                  </ul>
                </template>
              </div>
              <div class="mt-2 flex gap-2">
                <label class="sr-only" :for="`diary-q-${index}`">Khối lượng</label>
                <input :id="`diary-q-${index}`" v-model="line.qty" class="input w-32" inputmode="decimal" placeholder="Khối lượng" />
                <span class="self-center text-sm text-ink-muted">{{ line.uom }}</span>
                <input v-model="line.note" class="input min-w-0 flex-1" maxlength="500" placeholder="Ghi chú (vị trí, trục...)" aria-label="Ghi chú khối lượng" />
                <button type="button" class="btn btn-ghost px-2" aria-label="Bỏ dòng" @click="lines.splice(index, 1)"><Icon name="x" :size="16" /></button>
              </div>
            </li>
          </ul>
          <button type="button" class="btn btn-ghost mt-2 px-2 text-sm" @click="lines.push(blank())"><Icon name="plus" :size="16" /> Thêm công tác</button>
        </section>

        <div><label class="label" for="diary-summary">Công việc đã làm</label><textarea id="diary-summary" v-model="form.work_summary" class="input" rows="3" maxlength="5000"></textarea></div>
        <div><label class="label" for="diary-issues">Vướng mắc, sự cố</label><textarea id="diary-issues" v-model="form.issues" class="input" rows="2" maxlength="5000"></textarea></div>
        <div><label class="label" for="diary-safety">An toàn lao động, vệ sinh môi trường</label><input id="diary-safety" v-model="form.safety" class="input" maxlength="2000" /></div>

        <div>
          <p class="label">Ảnh</p>
          <ul v-if="photos.length" class="m-0 mb-2 flex list-none flex-wrap gap-2 p-0" aria-label="Ảnh sẽ gửi">
            <li v-for="(photo, index) in photos" :key="photo.uuid" class="relative h-16 w-16 overflow-hidden rounded-md">
              <img :src="photo.preview" alt="" class="h-full w-full object-cover" />
              <button type="button" class="absolute right-0.5 top-0.5 rounded-full bg-black/60 p-0.5 text-white" :aria-label="`Bỏ ảnh ${index + 1}`" @click="photos.splice(index, 1)"><Icon name="x" :size="12" /></button>
            </li>
          </ul>
          <input ref="camera" class="hidden" type="file" accept="image/*" capture="environment" @change="onFiles" />
          <input ref="gallery" class="hidden" type="file" accept="image/*" multiple @change="onFiles" />
          <div class="flex gap-2">
            <button type="button" class="btn btn-ghost px-2" :disabled="preparing" @click="camera.click()"><Icon name="camera" :size="16" /> Chụp ảnh</button>
            <button type="button" class="btn btn-ghost px-2" :disabled="preparing" @click="gallery.click()"><Icon name="image" :size="16" /> Chọn ảnh</button>
          </div>
        </div>

        <div class="flex flex-wrap justify-end gap-2">
          <button type="button" class="btn" :disabled="busy || !network.online" @click="saveDraft">Lưu nháp</button>
          <button type="submit" class="btn btn-primary" :disabled="busy || preparing || Boolean(queued)"><Icon name="send" :size="16" /> Nộp nhật ký</button>
        </div>
      </form>

      <!-- reading -->
      <article v-else-if="current?.status" class="space-y-3 text-sm">
        <p class="m-0 text-ink-muted">{{ current.weather || "—" }}<span v-if="current.temperature"> · {{ current.temperature }}</span> · {{ current.workers || 0 }} nhân công · lập bởi {{ current.author_name }}<span v-if="current.submitted_on">, nộp {{ formatDateTime(current.submitted_on) }}</span>
          <span v-if="current.confirmed_by"> · xác nhận: {{ current.confirmed_by_name }}</span></p>
        <table v-if="current.rows.length" class="w-full text-sm">
          <thead class="text-left text-xs text-ink-muted"><tr><th class="py-1">Công tác</th><th class="text-right">Khối lượng</th><th class="text-right">Đã làm / thiết kế</th></tr></thead>
          <tbody>
            <tr v-for="row in current.rows" :key="row.name" class="border-t border-line">
              <td class="py-1.5"><button type="button" class="text-left hover:underline" @click="openTask(row.task)">{{ row.label }}</button><span v-if="row.note" class="block text-xs text-ink-muted">{{ row.note }}</span></td>
              <td class="text-right">{{ qtyText(row.qty, row.uom) }}</td>
              <td class="text-right text-ink-muted">{{ qtyText(row.done_qty) }} / {{ qtyText(row.planned_qty) }}</td>
            </tr>
          </tbody>
        </table>
        <p v-if="current.work_summary" class="m-0 whitespace-pre-line"><strong>Công việc:</strong> {{ current.work_summary }}</p>
        <p v-if="current.issues" class="m-0 whitespace-pre-line"><strong>Vướng mắc:</strong> {{ current.issues }}</p>
        <p v-if="current.safety" class="m-0"><strong>An toàn:</strong> {{ current.safety }}</p>
        <PhotoGrid :photos="current.photos" @open="(index) => (lightbox = { photos: current.photos, index })" />
        <div v-if="current.can.confirm" class="flex flex-wrap gap-2">
          <button type="button" class="btn btn-primary" :disabled="busy" @click="confirmDiary"><Icon name="badge-check" :size="16" /> Xác nhận</button>
          <button type="button" class="btn" :disabled="busy" @click="sendingBack = true"><Icon name="undo" :size="16" /> Trả lại</button>
        </div>
      </article>
    </section>

    <aside aria-label="Các ngày đã ghi">
      <h3 class="m-0 mb-2 text-sm font-semibold">Các ngày đã ghi</h3>
      <p v-if="list && !list.diaries.length" class="m-0 text-sm text-ink-muted">Chưa có nhật ký nào.</p>
      <ul class="m-0 list-none space-y-1 p-0">
        <li v-for="item in list?.diaries || []" :key="item.name">
          <button type="button" class="flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left text-sm hover:bg-surface-muted"
            :class="String(item.diary_date) === day ? 'bg-surface-muted font-semibold' : ''" @click="day = String(item.diary_date)">
            <span class="w-20 shrink-0">{{ formatDate(item.diary_date) }}</span>
            <span class="badge" :class="DIARY_TONE[item.status]">{{ item.status }}</span>
            <span class="ml-auto text-xs text-ink-muted">{{ item.quantities }} CT<span v-if="item.photos"> · {{ item.photos }} ảnh</span></span>
          </button>
        </li>
      </ul>
    </aside>

    <Lightbox :photos="lightbox.photos" :index="lightbox.index" @close="lightbox = { photos: [], index: -1 }" />
    <ReasonDialog :open="sendingBack" title="Trả lại nhật ký" label="Cần sửa gì" :busy="busy" @confirm="sendBack" @cancel="sendingBack = false" />
  </div>
</template>
