<script setup>
import { api } from "../../lib/api.js";

// Thumbnails of a comment's photos (or of a gallery); a click opens the large view.
defineProps({
  photos: { type: Array, default: () => [] },
  size: { type: String, default: "md" },
});
const emit = defineEmits(["open"]);
</script>

<template>
  <ul v-if="photos.length" class="m-0 mt-2 grid list-none gap-1.5 p-0" :class="size === 'lg' ? 'grid-cols-3 sm:grid-cols-5' : 'grid-cols-3 sm:grid-cols-4'">
    <li v-for="(photo, index) in photos" :key="photo.name || photo.uuid" class="relative aspect-square overflow-hidden rounded-md bg-surface-muted">
      <button type="button" class="block h-full w-full p-0" :aria-label="`Xem ảnh ${index + 1}`" @click="emit('open', index)">
        <img :src="photo.preview || api.media.url(photo.name, 'thumb')" alt="" loading="lazy" class="h-full w-full object-cover" />
      </button>
      <slot name="badge" :photo="photo" />
    </li>
  </ul>
</template>
