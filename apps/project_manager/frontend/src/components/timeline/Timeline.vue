<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { api } from "../../lib/api.js";
import { initials } from "../../lib/boot.js";
import { formatDateTime } from "../../lib/format.js";
import { watchDocument } from "../../lib/realtime.js";
import { network, onSent, queuedFor, removeQueued, retryQueued } from "../../lib/sync.js";
import { KINDS, byDay, entryIcon, queuedState } from "../../lib/timeline.js";
import { toast } from "../../lib/toast.js";
import ConfirmDialog from "../ConfirmDialog.vue";
import Icon from "../Icon.vue";
import Composer from "./Composer.vue";
import Lightbox from "./Lightbox.vue";
import MessageText from "./MessageText.vue";
import PhotoGrid from "./PhotoGrid.vue";

// The discussion of a task or a project, newest first: comments with photos and the history of changes, what this
// person has queued but not yet sent (with its state), new entries arriving live, and the composer.
const props = defineProps({
  doctype: { type: String, required: true },
  name: { type: String, required: true },
  label: { type: String, default: "" },
  showTask: { type: Boolean, default: false },
  filters: { type: Boolean, default: false },
  composer: { type: Boolean, default: true },
});
const emit = defineEmits(["open-task"]);

const entries = ref([]);
const more = ref(false);
const next = ref(null);
const following = ref(false);
const unread = ref(0);
const lastRead = ref(0);
const loading = ref(false);
const error = ref("");
const kind = ref("");
const lightbox = ref({ photos: [], index: -1 });
const hiding = ref(null);
const previews = new Map();

const queued = computed(() => queuedFor(props.doctype, props.name));
const groups = computed(() => byDay(entries.value));

function previewOf(item, photo) {
  if (photo.done || !photo.data) return null;
  const key = `${item.id}:${photo.uuid}`;
  if (!previews.has(key)) previews.set(key, URL.createObjectURL(new Blob([photo.data], { type: photo.type })));
  return previews.get(key);
}
const queuedPhotos = (item) => item.photos.map((photo) => ({ uuid: photo.uuid, preview: previewOf(item, photo) }))
  .filter((photo) => photo.preview);

async function load(reset = true) {
  loading.value = true;
  error.value = "";
  try {
    const page = await api.activity.feed(props.doctype, props.name, { kind: kind.value, before: reset ? null : next.value });
    entries.value = reset ? page.entries : [...entries.value, ...page.entries];
    more.value = page.more;
    next.value = page.next;
    following.value = page.following;
    unread.value = page.unread;
    lastRead.value = page.last_read;
    if (reset) markRead();
  } catch (e) {
    error.value = e.message;
  } finally {
    loading.value = false;
  }
}

function markRead() {
  const newest = entries.value[0]?.name || 0;
  if (newest > lastRead.value && document.visibilityState !== "hidden") {
    lastRead.value = newest;
    unread.value = 0;
    api.activity.markRead(props.doctype, props.name, newest).catch(() => {});
  }
}

function add(entry) {
  if (!entry || entries.value.some((row) => row.name === entry.name)) return;
  if (!matchesKind(entry)) return;
  entries.value = [entry, ...entries.value].sort((a, b) => b.name - a.name);
  markRead();
}

function matchesKind(entry) {
  if (kind.value === "comment") return entry.type === "Bình luận";
  if (kind.value === "progress") return entry.type === "Tiến độ";
  if (kind.value === "change") return !["Bình luận", "Tiến độ"].includes(entry.type);
  return true;
}

async function refreshEntry(id) {
  try {
    const entry = await api.activity.entry(id);
    const index = entries.value.findIndex((row) => row.name === entry.name);
    if (index >= 0) entries.value.splice(index, 1, entry);
    else add(entry);
  } catch {
    // not visible to this user, or gone
  }
}

async function toggleFollow() {
  try {
    following.value = (await api.activity.follow(props.doctype, props.name, !following.value)).following;
    toast(following.value ? "Sẽ báo cho bạn khi có trao đổi mới" : "Đã thôi theo dõi");
  } catch (e) {
    toast(e.message, "error");
  }
}

async function hide() {
  const entry = hiding.value;
  hiding.value = null;
  try {
    await api.activity.hide(entry.name);
    entries.value = entries.value.filter((row) => row.name !== entry.name);
  } catch (e) {
    toast(e.message, "error");
  }
}

function openPhotos(photos, index) {
  lightbox.value = { photos, index };
}

const stopSent = onSent((item, answer) => {
  if (item.kind === "comment" && item.reference?.doctype === props.doctype && item.reference?.name === props.name) add(answer);
});
let stopLive = () => {};
let stopThumbs = () => {};
const sameRoom = (message) => (message.reference_doctype === props.doctype && message.reference_name === props.name)
  || (props.doctype === "Project" && message.project === props.name);

function onVisible() {
  if (document.visibilityState === "visible" && !loading.value) load();
}

onMounted(() => {
  load();
  stopLive = watchDocument(props.doctype, props.name, "pm_timeline", (message) => refreshEntry(message.id), sameRoom);
  stopThumbs = watchDocument(props.doctype, props.name, "pm_thumb", (message) => message.activity && refreshEntry(message.activity));
  document.addEventListener("visibilitychange", onVisible);
});
onBeforeUnmount(() => {
  stopSent();
  stopLive();
  stopThumbs();
  document.removeEventListener("visibilitychange", onVisible);
  previews.forEach((url) => URL.revokeObjectURL(url));
});
watch(kind, () => load());
watch(() => [props.doctype, props.name], () => load());
</script>

<template>
  <section class="space-y-3" :aria-label="doctype === 'Task' ? 'Trao đổi và lịch sử của công việc' : 'Trao đổi của dự án'">
    <div class="flex flex-wrap items-center gap-2">
      <slot name="title" />
      <span v-if="unread" class="badge badge-info">{{ unread }} mới</span>
      <div v-if="filters" class="flex flex-wrap gap-1" role="group" aria-label="Lọc theo loại">
        <button v-for="item in KINDS" :key="item.value" type="button" class="rounded-full border px-2.5 py-0.5 text-xs"
          :class="kind === item.value ? 'border-primary bg-primary text-white' : 'border-line text-ink-soft'" :aria-pressed="kind === item.value"
          @click="kind = item.value">{{ item.label }}</button>
      </div>
      <button type="button" class="btn btn-ghost ml-auto px-2 text-xs" :aria-pressed="following" @click="toggleFollow">
        <Icon :name="following ? 'bell' : 'bell-off'" :size="14" /> {{ following ? "Đang theo dõi" : "Theo dõi" }}
      </button>
    </div>

    <Composer v-if="composer" :doctype="doctype" :name="name" :label="label" />

    <!-- what this person queued: shown until the server has it -->
    <ol v-if="queued.length" class="m-0 list-none space-y-2 p-0" aria-label="Đang chờ gửi">
      <li v-for="item in queued" :key="item.id" class="rounded-lg border border-dashed border-warning bg-warning-soft p-2.5 text-sm">
        <p class="m-0 flex flex-wrap items-center gap-2 text-xs">
          <Icon :name="item.state === 'sending' ? 'loader' : item.state === 'failed' ? 'alert-triangle' : 'cloud-upload'" :size="14" :spin="item.state === 'sending'" />
          <span :class="`text-${queuedState(item, network.online).tone}`">{{ queuedState(item, network.online).text }}</span>
          <button v-if="item.state === 'failed'" type="button" class="underline" @click="retryQueued(item.id)">Thử lại</button>
          <button v-if="item.state !== 'sending'" type="button" class="underline" @click="removeQueued(item.id)">Bỏ</button>
        </p>
        <MessageText v-if="item.payload.content" class="mt-1" :content="item.payload.content" />
        <PhotoGrid :photos="queuedPhotos(item)" @open="(index) => openPhotos(queuedPhotos(item), index)" />
      </li>
    </ol>

    <p v-if="error" class="m-0 rounded-md bg-danger-soft p-2 text-sm text-danger">{{ error }}
      <button type="button" class="ml-2 underline" @click="load()">Tải lại</button></p>

    <div v-for="group in groups" :key="group.day">
      <h4 class="m-0 mb-1.5 text-xs font-semibold uppercase tracking-wide text-ink-muted">{{ group.label }}</h4>
      <ol class="m-0 list-none space-y-2.5 p-0">
        <li v-for="entry in group.entries" :key="entry.name" class="text-sm" :data-entry="entry.name">
          <div v-if="entry.type === 'Bình luận'" class="flex gap-2.5">
            <span class="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-primary-soft text-xs font-semibold text-primary" aria-hidden="true">{{ initials(entry.actor_name) }}</span>
            <div class="min-w-0 flex-1 rounded-lg bg-surface-muted px-3 py-2">
              <p class="m-0 flex flex-wrap items-baseline gap-x-2 text-xs">
                <strong class="text-sm text-ink">{{ entry.actor_name }}</strong>
                <span class="text-ink-muted">{{ formatDateTime(entry.creation).slice(-5) }}</span>
                <button v-if="showTask && entry.task_label" type="button" class="truncate text-primary underline" @click="emit('open-task', entry.task)">↳ {{ entry.task_label }}</button>
                <button v-if="entry.mine" type="button" class="ml-auto text-ink-muted hover:text-danger" :aria-label="'Ẩn bình luận'" @click="hiding = entry">
                  <Icon name="eye-off" :size="14" />
                </button>
              </p>
              <MessageText v-if="entry.content" class="mt-0.5 text-ink" :content="entry.content" />
              <PhotoGrid :photos="entry.photos" @open="(index) => openPhotos(entry.photos, index)" />
            </div>
          </div>
          <p v-else class="m-0 flex gap-2.5 text-ink-soft">
            <span class="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-full border border-line text-ink-muted" aria-hidden="true"><Icon :name="entryIcon(entry.type)" :size="14" /></span>
            <span class="min-w-0 flex-1 py-1">
              <strong class="font-medium text-ink">{{ entry.actor_name }}</strong>
              <span class="whitespace-pre-line"> · {{ entry.content || entry.type }}</span>
              <button v-if="showTask && entry.task_label" type="button" class="ml-1 text-primary underline" @click="emit('open-task', entry.task)">↳ {{ entry.task_label }}</button>
              <span class="ml-1 text-xs text-ink-muted">{{ formatDateTime(entry.creation).slice(-5) }}</span>
            </span>
          </p>
        </li>
      </ol>
    </div>

    <p v-if="!loading && !entries.length && !queued.length && !error" class="m-0 py-6 text-center text-sm text-ink-muted">Chưa có trao đổi nào.</p>
    <div v-if="more || loading" class="flex justify-center">
      <button type="button" class="btn" :disabled="loading" @click="load(false)">
        <Icon :name="loading ? 'loader' : 'chevron-down'" :size="16" :spin="loading" /> {{ loading ? "Đang tải…" : "Xem cũ hơn" }}
      </button>
    </div>

    <Lightbox :photos="lightbox.photos" :index="lightbox.index" @close="lightbox = { photos: [], index: -1 }" />
    <ConfirmDialog :open="Boolean(hiding)" title="Ẩn bình luận?" message="Bình luận sẽ không hiện với mọi người nữa (vẫn được lưu trong hệ thống)."
      confirm-text="Ẩn" danger @confirm="hide" @cancel="hiding = null" />
  </section>
</template>
