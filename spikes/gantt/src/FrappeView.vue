<script setup>
import Gantt from "frappe-gantt";
import "frappe-gantt-css";
import { onMounted, ref } from "vue";
import { isoDay } from "./data.js";

// frappe-gantt has no tree and only finish-to-start arrows: every task is one flat row.
const props = defineProps({ plan: { type: Object, required: true } });
const el = ref(null);
onMounted(() => {
  const incoming = {};
  for (const l of props.plan.links) (incoming[l.target] ||= []).push(String(l.source));
  const tasks = props.plan.tasks.map((t) => ({
    id: String(t.id), name: `${t.wbs} ${t.text}`, start: isoDay(t.start), end: isoDay(Math.max(t.end, t.start + 86400000)),
    progress: t.progress, dependencies: (incoming[t.id] || []).join(", "),
  }));
  new Gantt(el.value, tasks, { view_mode: "Week", readonly: true });
});
</script>

<template>
  <div class="host"><div ref="el"></div></div>
</template>

<style scoped>
.host { height: 100%; overflow: auto; }
</style>
