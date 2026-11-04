<script setup>
import { computed } from "vue";
import { useRoute } from "vue-router";
import TaskDetail from "../components/TaskDetail.vue";

// /pm/cong-viec/:id — where notifications point.
const route = useRoute();
const name = computed(() => String(route.params.id || ""));
</script>

<template>
  <div class="card mx-auto max-w-3xl p-5">
    <TaskDetail :name="name" />
  </div>
</template>
