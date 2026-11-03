<script setup>
import { gantt } from "dhtmlx-gantt";
import "dhtmlx-gantt/codebase/dhtmlxgantt.css";
import { onBeforeUnmount, onMounted, ref } from "vue";

// DHTMLX Gantt, Standard edition (MIT since v9). Smart rendering draws only the visible rows.
const props = defineProps({ plan: { type: Object, required: true } });
const TYPES = { FS: "0", SS: "1", FF: "2", SF: "3" };
const el = ref(null);
onMounted(() => {
  gantt.config.date_format = "%Y-%m-%d %H:%i";
  gantt.config.smart_rendering = true;
  gantt.config.readonly = false;
  gantt.config.scales = [{ unit: "month", step: 1, format: "%F %Y" }, { unit: "week", step: 1, format: "W%W" }];
  gantt.config.columns = [{ name: "text", label: "Công việc", tree: true, width: 260 }];
  gantt.init(el.value);
  gantt.parse({
    data: props.plan.tasks.map((t) => ({
      id: t.id, parent: t.parent, text: `${t.wbs} ${t.text}`, start_date: new Date(t.start), end_date: new Date(Math.max(t.end, t.start + 86400000)),
      progress: t.progress / 100, type: t.group ? "project" : "task", open: true,
    })),
    links: props.plan.links.map((l) => ({ id: l.id, source: l.source, target: l.target, type: TYPES[l.type] })),
  });
});
onBeforeUnmount(() => gantt.clearAll());
</script>

<template>
  <div ref="el" class="host"></div>
</template>

<style scoped>
.host { height: 100%; width: 100%; }
</style>
