<script setup>
import { computed } from "vue";
import EmptyState from "../components/EmptyState.vue";
import Icon from "../components/Icon.vue";
import { boot } from "../lib/boot.js";
import { formatDateTime } from "../lib/format.js";
import { sizeText } from "../lib/outbox.js";
import { network, removeQueued, retryQueued, sendNow } from "../lib/sync.js";
import { plainText, queuedState } from "../lib/timeline.js";

// Hàng đợi: what was written without a connection and has not reached the server yet, oldest first (the order it
// will be sent in). Items of another account that used this phone stay here until that account signs in again.
const mine = computed(() => network.items.filter((item) => item.user === boot.user.name));
const others = computed(() => network.items.filter((item) => item.user !== boot.user.name));
const KIND = { comment: "Trao đổi", progress: "Báo cáo tiến độ" };

function summary(item) {
  if (item.kind === "progress") {
    const values = item.payload.values || {};
    return `${values.progress_value}%${values.note ? ` · ${values.note}` : ""}`;
  }
  const photos = item.photos.length ? ` · ${item.photos.length} ảnh (${sizeText(item.photos.reduce((sum, p) => sum + (p.size || 0), 0))})` : "";
  return `${plainText(item.payload.content) || "(chỉ có ảnh)"}${photos}`;
}

function linkOf(item) {
  if (item.reference?.doctype === "Task") return `/cong-viec/${item.reference.name}`;
  if (item.reference?.doctype === "Project") return `/du-an/${item.reference.name}/trao-doi`;
  return null;
}
</script>

<template>
  <div class="mx-auto max-w-3xl space-y-4">
    <div class="flex flex-wrap items-center gap-2">
      <h1 class="m-0 text-xl font-semibold">Hàng đợi gửi</h1>
      <span v-if="!network.online" class="badge badge-warning"><Icon name="wifi-off" :size="14" /> Mất mạng</span>
      <button type="button" class="btn ml-auto" :disabled="!network.online || network.sending || !mine.length" @click="sendNow">
        <Icon :name="network.sending ? 'loader' : 'refresh-cw'" :size="16" :spin="network.sending" /> Gửi ngay
      </button>
    </div>
    <p class="m-0 text-sm text-ink-muted">Trao đổi, ảnh và báo cáo tiến độ viết khi không có mạng nằm ở đây, rồi tự gửi theo thứ tự khi có mạng lại. Trên iPhone, hãy mở lại ứng dụng để gửi.</p>

    <EmptyState v-if="!mine.length && !others.length" icon="circle-check" title="Không có gì đang chờ" text="Mọi thứ đã được gửi lên máy chủ." />

    <ol v-if="mine.length" class="m-0 list-none space-y-2 p-0">
      <li v-for="item in mine" :key="item.id" class="card p-3 text-sm">
        <div class="flex flex-wrap items-center gap-2">
          <strong>{{ KIND[item.kind] || item.kind }}</strong>
          <RouterLink v-if="linkOf(item)" :to="linkOf(item)" class="truncate text-primary">{{ item.label || item.reference?.name }}</RouterLink>
          <span class="ml-auto text-xs text-ink-muted">{{ formatDateTime(new Date(item.created).toISOString()) }}</span>
        </div>
        <p class="m-0 mt-1 line-clamp-2 text-ink-soft">{{ summary(item) }}</p>
        <p class="m-0 mt-1 text-xs" :class="`text-${queuedState(item, network.online).tone}`">{{ queuedState(item, network.online).text }}
          <span v-if="item.tries > 1" class="text-ink-muted"> · đã thử {{ item.tries }} lần</span></p>
        <div v-if="item.state !== 'sending'" class="mt-2 flex gap-2">
          <button v-if="item.state === 'failed'" type="button" class="btn px-2 text-xs" @click="retryQueued(item.id)"><Icon name="refresh-cw" :size="14" /> Thử lại</button>
          <button type="button" class="btn btn-ghost px-2 text-xs text-danger" @click="removeQueued(item.id)"><Icon name="trash-2" :size="14" /> Bỏ mục này</button>
        </div>
      </li>
    </ol>

    <section v-if="others.length" class="card p-3 text-sm">
      <h2 class="m-0 text-sm font-semibold">Của tài khoản khác trên máy này ({{ others.length }})</h2>
      <p class="m-0 mt-1 text-ink-muted">Sẽ được gửi khi tài khoản đó đăng nhập lại.</p>
    </section>
  </div>
</template>
