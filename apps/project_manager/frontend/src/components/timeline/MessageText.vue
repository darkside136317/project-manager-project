<script setup>
import { computed } from "vue";
import { segments } from "../../lib/timeline.js";

// A comment's text: mentions shown as names (never as HTML), line breaks kept.
const props = defineProps({ content: { type: String, default: "" } });
const parts = computed(() => segments(props.content));
</script>

<template>
  <p class="m-0 whitespace-pre-line break-words"><template v-for="(part, index) in parts" :key="index"><span v-if="part.type === 'mention'" class="rounded bg-info-soft px-1 font-medium text-info" :title="part.user">@{{ part.name }}</span><template v-else>{{ part.text }}</template></template></p>
</template>
