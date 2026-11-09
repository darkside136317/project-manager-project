<script setup>
import { computed } from "vue";
import { boot } from "../lib/boot.js";
import { network } from "../lib/sync.js";
import Icon from "./Icon.vue";

// In the header: no connection, and how much waits to be sent (a link to the queue screen).
const mine = computed(() => network.items.filter((item) => item.user === boot.user.name));
const failed = computed(() => mine.value.filter((item) => item.state === "failed").length);
</script>

<template>
  <span v-if="!network.online" class="badge badge-warning inline-flex items-center gap-1 whitespace-nowrap" role="status">
    <Icon name="wifi-off" :size="14" /> Mất mạng
  </span>
  <RouterLink v-if="mine.length" to="/hang-doi" class="badge inline-flex items-center gap-1 whitespace-nowrap no-underline" :class="failed ? 'badge-danger' : 'badge-info'"
    :aria-label="`${mine.length} mục đang chờ gửi${failed ? `, ${failed} không gửi được` : ''}`">
    <Icon :name="network.sending ? 'loader' : 'cloud-upload'" :size="14" :spin="network.sending" /> {{ mine.length }}
  </RouterLink>
</template>
