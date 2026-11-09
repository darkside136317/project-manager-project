<script setup>
import { computed, nextTick, onBeforeUnmount, ref } from "vue";
import { api } from "../../lib/api.js";
import { sizeText } from "../../lib/outbox.js";
import { preparePhotos, queueComment } from "../../lib/sync.js";
import { insertMention, mentionAt } from "../../lib/timeline.js";
import { toast } from "../../lib/toast.js";
import Icon from "../Icon.vue";

// Writing in a discussion: text with @mentions, photos taken on the spot or picked from the phone, optionally the
// phone's position. Everything goes through the outbox (lib/sync.js): it shows at once and is sent when possible.
const props = defineProps({
  doctype: { type: String, required: true },
  name: { type: String, required: true },
  label: { type: String, default: "" },
  placeholder: { type: String, default: "Viết trao đổi, gõ @ để nhắc tên…" },
});
const emit = defineEmits(["queued"]);

const MAX_TEXT = 5000;
const MAX_PHOTOS = 12;
const PLACE_KEY = "pm.composer.place";
const text = ref("");
const photos = ref([]);
const preparing = ref(false);
const box = ref(null);
const camera = ref(null);
const gallery = ref(null);
const withPlace = ref(readPlace());
const people = ref(null);
const mention = ref(null);
const choices = ref([]);
const active = ref(0);
const tooLong = computed(() => text.value.length > MAX_TEXT);
const canSend = computed(() => !preparing.value && !tooLong.value && (text.value.trim() || photos.value.length));

function readPlace() {
  try {
    return localStorage.getItem(PLACE_KEY) === "1";
  } catch {
    return false;
  }
}

function togglePlace() {
  withPlace.value = !withPlace.value;
  try {
    localStorage.setItem(PLACE_KEY, withPlace.value ? "1" : "0");
  } catch {
    // private window: remembered for this page only
  }
}

async function loadPeople() {
  if (people.value) return people.value;
  try {
    people.value = await api.activity.people(props.doctype, props.name);
  } catch {
    people.value = [];  // offline: no suggestions, the text is still sent
  }
  return people.value;
}

async function onType() {
  const caret = box.value?.selectionStart ?? text.value.length;
  const found = mentionAt(text.value, caret);
  mention.value = found;
  if (!found) {
    choices.value = [];
    return;
  }
  const query = found.query.toLowerCase();
  const all = await loadPeople();
  choices.value = all.filter((p) => !query || p.full_name.toLowerCase().includes(query) || p.user.toLowerCase().includes(query)).slice(0, 6);
  active.value = 0;
}

async function choose(person) {
  const caret = box.value?.selectionStart ?? text.value.length;
  const result = insertMention(text.value, mention.value.start, caret, person);
  text.value = result.text;
  mention.value = null;
  choices.value = [];
  await nextTick();
  box.value?.focus();
  box.value?.setSelectionRange(result.caret, result.caret);
}

function closeSoon() {
  setTimeout(() => { choices.value = []; }, 150);  // after a click on a suggestion
}

function onKey(event) {
  if (choices.value.length) {
    if (event.key === "ArrowDown") { active.value = (active.value + 1) % choices.value.length; event.preventDefault(); }
    else if (event.key === "ArrowUp") { active.value = (active.value - 1 + choices.value.length) % choices.value.length; event.preventDefault(); }
    else if (event.key === "Enter" || event.key === "Tab") { choose(choices.value[active.value]); event.preventDefault(); }
    else if (event.key === "Escape") { choices.value = []; event.preventDefault(); }
    return;
  }
  if (event.key === "Enter" && (event.ctrlKey || event.metaKey)) {
    event.preventDefault();
    send();
  }
}

async function onFiles(event) {
  const files = [...(event.target.files || [])].filter((file) => /^image\//.test(file.type) || /\.(jpe?g|png|webp|heic)$/i.test(file.name));
  event.target.value = "";
  if (!files.length) return;
  const room = MAX_PHOTOS - photos.value.length;
  if (files.length > room) toast(`Mỗi lần gửi tối đa ${MAX_PHOTOS} ảnh`, "warning");
  preparing.value = true;
  try {
    const ready = await preparePhotos(files.slice(0, Math.max(0, room)), { withPlace: withPlace.value });
    for (const photo of ready) photo.preview = URL.createObjectURL(new Blob([photo.data], { type: photo.type }));
    photos.value = [...photos.value, ...ready];
  } catch (e) {
    toast(`Không đọc được ảnh: ${e.message}`, "error");
  } finally {
    preparing.value = false;
  }
}

function dropPhoto(index) {
  const [removed] = photos.value.splice(index, 1);
  if (removed?.preview) URL.revokeObjectURL(removed.preview);
}

async function send() {
  if (!canSend.value) return;
  const ready = photos.value.map(({ preview, ...photo }) => photo);
  try {
    const item = await queueComment({ doctype: props.doctype, name: props.name }, text.value.trim(), ready, props.label);
    photos.value.forEach((photo) => photo.preview && URL.revokeObjectURL(photo.preview));
    text.value = "";
    photos.value = [];
    emit("queued", item);
  } catch (e) {
    toast(`Không lưu được trao đổi: ${e.message}`, "error", 7000);
  }
}

onBeforeUnmount(() => photos.value.forEach((photo) => photo.preview && URL.revokeObjectURL(photo.preview)));
</script>

<template>
  <form class="rounded-lg border border-line bg-surface p-2.5" @submit.prevent="send">
    <div class="relative">
      <label class="sr-only" :for="`composer-${name}`">Nội dung trao đổi</label>
      <textarea :id="`composer-${name}`" ref="box" v-model="text" class="input min-h-[72px] resize-y" rows="3" :placeholder="placeholder"
        @input="onType" @click="onType" @keydown="onKey" @blur="closeSoon"></textarea>
      <ul v-if="choices.length" class="absolute left-0 right-0 top-full z-30 m-0 mt-1 list-none rounded-md border border-line bg-surface p-1 shadow-pop" role="listbox" aria-label="Nhắc tên">
        <li v-for="(person, index) in choices" :key="person.user" role="option" :aria-selected="index === active">
          <button type="button" class="block w-full rounded px-2 py-1.5 text-left text-sm" :class="index === active ? 'bg-surface-muted' : ''" @mousedown.prevent="choose(person)">
            {{ person.full_name }} <span class="text-xs text-ink-muted">{{ person.user }}</span>
          </button>
        </li>
      </ul>
    </div>
    <p v-if="tooLong" class="m-0 mt-1 text-xs text-danger">Dài quá {{ MAX_TEXT }} ký tự ({{ text.length }}).</p>

    <ul v-if="photos.length" class="m-0 mt-2 flex list-none flex-wrap gap-2 p-0" aria-label="Ảnh sẽ gửi">
      <li v-for="(photo, index) in photos" :key="photo.uuid" class="relative h-16 w-16 overflow-hidden rounded-md bg-surface-muted">
        <img :src="photo.preview" alt="" class="h-full w-full object-cover" />
        <span class="absolute bottom-0 left-0 right-0 bg-black/50 px-1 text-[10px] text-white">{{ sizeText(photo.size) }}</span>
        <button type="button" class="absolute right-0.5 top-0.5 rounded-full bg-black/60 p-0.5 text-white" :aria-label="`Bỏ ảnh ${index + 1}`" @click="dropPhoto(index)">
          <Icon name="x" :size="12" />
        </button>
      </li>
    </ul>

    <div class="mt-2 flex flex-wrap items-center gap-1.5">
      <input ref="camera" class="hidden" type="file" accept="image/*" capture="environment" @change="onFiles" />
      <input ref="gallery" class="hidden" type="file" accept="image/*" multiple @change="onFiles" />
      <button type="button" class="btn btn-ghost px-2" :disabled="preparing || photos.length >= MAX_PHOTOS" @click="camera.click()">
        <Icon name="camera" :size="16" /> <span class="hidden sm:inline">Chụp ảnh</span>
      </button>
      <button type="button" class="btn btn-ghost px-2" :disabled="preparing || photos.length >= MAX_PHOTOS" @click="gallery.click()">
        <Icon name="image" :size="16" /> <span class="hidden sm:inline">Chọn ảnh</span>
      </button>
      <button type="button" class="btn btn-ghost px-2" :aria-pressed="withPlace" :class="withPlace ? 'text-primary' : ''" title="Gắn vị trí của điện thoại vào ảnh không có sẵn vị trí" @click="togglePlace">
        <Icon name="map-pin" :size="16" /> <span class="hidden sm:inline">{{ withPlace ? "Có vị trí" : "Vị trí" }}</span>
      </button>
      <span v-if="preparing" class="text-xs text-ink-muted"><Icon name="loader" :size="14" spin /> Đang thu nhỏ ảnh…</span>
      <button type="submit" class="btn btn-primary ml-auto" :disabled="!canSend"><Icon name="send" :size="16" /> Gửi</button>
    </div>
  </form>
</template>
