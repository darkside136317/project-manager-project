<script setup>
import { Gantt } from "@svar-ui/vue-gantt";
import "@svar-ui/vue-gantt/all.css";
import { toDate } from "./data.js";

const props = defineProps({ plan: { type: Object, required: true } });
const TYPES = { FS: "e2s", SS: "s2s", FF: "e2e", SF: "s2e" };
const tasks = props.plan.tasks.map((t) => ({
  id: t.id, parent: t.parent, text: `${t.wbs} ${t.text}`, start: toDate(t.start), end: toDate(t.end),
  progress: t.progress, type: t.group ? "summary" : "task", open: true,
}));
const links = props.plan.links.map((l) => ({ id: l.id, source: l.source, target: l.target, type: TYPES[l.type] }));
const scales = [
  { unit: "month", step: 1, format: "%F %Y" },
  { unit: "week", step: 1, format: "%W" },
];
</script>

<template>
  <div class="host"><Gantt :tasks="tasks" :links="links" :scales="scales" :cell-width="40" /></div>
</template>

<style scoped>
.host { height: 100%; }
</style>
