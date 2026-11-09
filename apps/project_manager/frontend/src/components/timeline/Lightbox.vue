<script setup>
import { computed, onBeforeUnmount, ref, watch } from "vue";
import { api } from "../../lib/api.js";
import { formatDateTime } from "../../lib/format.js";
import { mapLink } from "../../lib/timeline.js";
import Icon from "../Icon.vue";

// One photo at full size, with the previous and next ones of the same set; when and where it was taken.
const props = defineProps({
  photos: { type: Array, default: () => [] },
  index: { type: Number, default: -1 },
});
const emit = defineEmits(["close"]);
const current = ref(props.index);
watch(() => props.index, (value) => { current.value = value; });
const photo = computed(() => props.photos[current.value] || null);
const open = computed(() => current.value >= 0 && Boolean(photo.value));

function go(step) {
  const count = props.photos.length;
  if (count) current.value = (current.value + step + count) % count;
}

function onKey(event) {
  if (!open.value) return;
  if (event.key === "Escape") emit("close");
  if (event.key === "ArrowRight") go(1);
  if (event.key === "ArrowLeft") go(-1);
}
watch(open, (value) => {
  if (value) document.addEventListener("keydown", onKey);
  else document.removeEventListener("keydown", onKey);
}, { immediate: true });
onBeforeUnmount(() => document.removeEventListener("keydown", onKey));
</script>

<template>
  <div v-if="open" class="fixed inset-0 z-50 flex flex-col bg-black/90" role="dialog" aria-modal="true" aria-label="Xem ảnh">
    <div class="flex items-center gap-2 px-3 py-2 text-sm text-white">
      <span>{{ current + 1 }}/{{ photos.length }}</span>
      <span v-if="photo.taken_at" class="opacity-80">· Chụp {{ formatDateTime(photo.taken_at) }}</span>
      <a v-if="mapLink(photo.lat, photo.lng)" :href="mapLink(photo.lat, photo.lng)" target="_blank" rel="noopener" class="inline-flex items-center gap-1 text-white underline">
        <Icon name="map-pin" :size="14" /> Vị trí
      </a>
      <a v-if="photo.name" :href="api.media.url(photo.name, 'full')" target="_blank" rel="noopener" class="ml-auto inline-flex items-center gap-1 text-white underline">
        <Icon name="external-link" :size="14" /> Mở ảnh gốc
      </a>
      <button type="button" class="ml-2 rounded p-1.5 text-white hover:bg-white/10" :class="{ 'ml-auto': !photo.name }" aria-label="Đóng" @click="emit('close')">
        <Icon name="x" :size="20" />
      </button>
    </div>
    <div class="relative flex min-h-0 flex-1 items-center justify-center px-2 pb-4" @click.self="emit('close')">
      <img :src="photo.preview || api.media.url(photo.name, 'full')" alt="" class="max-h-full max-w-full object-contain" />
      <button v-if="photos.length > 1" type="button" class="absolute left-2 rounded-full bg-black/50 p-2 text-white" aria-label="Ảnh trước" @click="go(-1)"><Icon name="chevron-left" :size="22" /></button>
      <button v-if="photos.length > 1" type="button" class="absolute right-2 rounded-full bg-black/50 p-2 text-white" aria-label="Ảnh sau" @click="go(1)"><Icon name="chevron-right" :size="22" /></button>
    </div>
  </div>
</template>
