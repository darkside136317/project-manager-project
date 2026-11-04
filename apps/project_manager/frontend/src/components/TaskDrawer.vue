<script setup>
import Drawer from "./Drawer.vue";
import TaskDetail from "./TaskDetail.vue";

// The task panel over any list (my tasks, the board, the tree): closing it keeps the user where they were.
defineProps({ name: { type: String, default: "" } });
const emit = defineEmits(["close", "changed"]);
</script>

<template>
  <Drawer :open="Boolean(name)" title="Chi tiết công việc" width="640px" @close="emit('close')">
    <TaskDetail v-if="name" :name="name" @changed="emit('changed', $event)" />
  </Drawer>
</template>
