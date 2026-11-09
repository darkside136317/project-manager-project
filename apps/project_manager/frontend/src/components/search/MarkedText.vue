<script setup>
import { computed } from "vue";
import { marked } from "../../lib/timeline.js";
import { plainText } from "../../lib/timeline.js";

// A search result's text with the found words highlighted (the server marks them; no HTML is involved).
const props = defineProps({ text: { type: String, default: "" } });
const parts = computed(() => marked(plainText(props.text)));
</script>

<template>
  <span><template v-for="(part, index) in parts" :key="index"><mark v-if="part.marked" class="rounded bg-warning-soft px-0.5 text-ink">{{ part.text }}</mark><template v-else>{{ part.text }}</template></template></span>
</template>
