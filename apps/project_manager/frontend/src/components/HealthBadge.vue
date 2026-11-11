<script setup>
import { computed } from "vue";
import { healthBadge, healthText } from "../lib/health.js";

// Sức khỏe of a project or a task: a coloured badge, the reason on hover (and below it when `detailed`).
const props = defineProps({
  level: { type: String, default: "" },
  reason: { type: String, default: "" },
  detailed: { type: Boolean, default: false },
  short: { type: Boolean, default: false },
});
const text = computed(() => (props.short ? props.level || "—" : healthText(props.level)));
</script>

<template>
  <span class="inline-flex flex-col items-start gap-0.5">
    <span :class="healthBadge(level)" :title="reason || undefined" data-health>
      <span class="mr-1 inline-block h-2 w-2 rounded-full bg-current align-middle" aria-hidden="true"></span>{{ text }}
    </span>
    <span v-if="detailed && reason" class="text-xs text-ink-muted">{{ reason }}</span>
  </span>
</template>
