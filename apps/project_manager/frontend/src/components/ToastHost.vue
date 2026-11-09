<script setup>
import { dismiss, toasts } from "../lib/toast.js";
import Icon from "./Icon.vue";

// success (default), warning (kept for later: no connection...), error
const LOOK = {
  success: { border: "border-success", icon: "circle-check", color: "text-success" },
  warning: { border: "border-warning", icon: "alert-triangle", color: "text-warning" },
  error: { border: "border-danger", icon: "alert-triangle", color: "text-danger" },
};
const look = (kind) => LOOK[kind] || LOOK.success;
</script>

<template>
  <div class="pointer-events-none fixed bottom-4 right-4 z-[80] flex w-[min(92vw,380px)] flex-col gap-2" aria-live="polite">
    <div
      v-for="item in toasts"
      :key="item.id"
      class="card pointer-events-auto flex items-start gap-3 px-4 py-3 shadow-pop"
      :class="look(item.kind).border"
      role="status"
    >
      <Icon :name="look(item.kind).icon" :class="look(item.kind).color" />
      <p class="m-0 flex-1 whitespace-pre-line text-sm">{{ item.message }}</p>
      <button class="btn btn-ghost btn-icon !min-h-0 !p-1" type="button" aria-label="Đóng thông báo" @click="dismiss(item.id)">
        <Icon name="x" :size="16" />
      </button>
    </div>
  </div>
</template>
