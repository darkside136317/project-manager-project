<script setup>
import { computed } from "vue";

// Actual progress as a bar, with the planned progress as a tick when given.
const props = defineProps({
  value: { type: Number, default: 0 },
  planned: { type: Number, default: null },
  label: { type: String, default: "Tiến độ" },
});
const width = computed(() => `${Math.min(100, Math.max(0, props.value || 0))}%`);
const behind = computed(() => props.planned !== null && (props.value || 0) + 5 < props.planned);
</script>

<template>
  <div class="relative h-2 w-full overflow-hidden rounded-full bg-surface-muted" role="progressbar" :aria-label="label"
    :aria-valuenow="Math.round(value || 0)" aria-valuemin="0" aria-valuemax="100">
    <div class="h-full rounded-full" :class="behind ? 'bg-danger' : 'bg-primary'" :style="{ width }"></div>
    <div v-if="planned !== null" class="absolute top-0 h-full w-0.5 bg-ink" :style="{ left: `${Math.min(100, planned)}%` }"
      :title="`Kế hoạch ${Math.round(planned)}%`"></div>
  </div>
</template>
