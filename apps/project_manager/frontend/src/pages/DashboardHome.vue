<script setup>
import { computed } from "vue";
import Icon from "../components/Icon.vue";
import PageHeader from "../components/PageHeader.vue";
import { boot } from "../lib/boot.js";

// Home of the app: a greeting and shortcuts to every screen the user may open. Project figures (health, progress,
// alerts) arrive with the project screens.
const toPath = (route) => route.replace(/^\/pm/, "") || "/";
const shortcuts = computed(() => boot.nav
  .flatMap((group) => group.items.map((item) => ({ ...item, group: group.group, to: toPath(item.route) })))
  .filter((item) => item.to !== "/"));
const scopeText = computed(() => (boot.user.all_projects
  ? "Bạn được xem mọi dự án của công ty."
  : "Bạn xem các dự án mình tham gia và các dự án được cấp thêm."));
</script>

<template>
  <PageHeader title="Tổng quan" :subtitle="`Xin chào ${boot.user.full_name || boot.user.name}. ${scopeText}`" />

  <section v-if="shortcuts.length" aria-label="Lối tắt">
    <ul class="m-0 grid list-none grid-cols-1 gap-3 p-0 sm:grid-cols-2 xl:grid-cols-3">
      <li v-for="item in shortcuts" :key="item.route">
        <RouterLink :to="item.to" class="card flex items-center gap-3 px-4 py-3 text-ink no-underline hover:shadow-pop">
          <span class="grid h-10 w-10 shrink-0 place-items-center rounded-lg bg-primary-soft text-primary"><Icon :name="item.icon" :size="20" /></span>
          <span class="min-w-0">
            <span class="block truncate font-medium">{{ item.label }}</span>
            <span class="block truncate text-xs text-ink-muted">{{ item.group }}</span>
          </span>
        </RouterLink>
      </li>
    </ul>
  </section>
  <p v-else class="text-sm text-ink-muted">Chưa có màn hình nào dành cho tài khoản này.</p>
</template>
