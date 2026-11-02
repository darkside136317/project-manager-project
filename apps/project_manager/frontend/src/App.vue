<script setup>
import { boot } from "./lib/boot.js";
</script>

<template>
  <div class="shell">
    <header class="bar">
      <strong>Quản lý dự án</strong>
      <span class="who">{{ boot.full_name || boot.user }}</span>
    </header>
    <main class="body">
      <h1>{{ boot.company || "Quản lý dự án" }}</h1>
      <p>Hệ thống đã cài đặt xong. Các chức năng quản lý dự án sẽ xuất hiện ở đây.</p>
      <p><a href="/desk">Mở giao diện quản trị ERPNext</a></p>
      <p class="muted">Phiên bản {{ boot.version }}</p>
    </main>
  </div>
</template>

<style>
:root {
  --pm-bg: #f7f8fa;
  --pm-fg: #1d2330;
  --pm-muted: #667085;
  --pm-bar: #12345a;
  --pm-bar-fg: #ffffff;
  --pm-link: #1a5fb4;
}
@media (prefers-color-scheme: dark) {
  :root {
    --pm-bg: #14171d;
    --pm-fg: #e6e8ec;
    --pm-muted: #98a2b3;
    --pm-bar: #0b2440;
    --pm-link: #78aeff;
  }
}
body {
  margin: 0;
  background: var(--pm-bg);
  color: var(--pm-fg);
  font-family: system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;
}
a { color: var(--pm-link); }
.bar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  padding: 12px 16px;
  background: var(--pm-bar);
  color: var(--pm-bar-fg);
}
.who { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.body { max-width: 720px; margin: 0 auto; padding: 24px 16px; line-height: 1.5; }
.body h1 { font-size: 1.5rem; margin: 0 0 12px; }
.muted { color: var(--pm-muted); font-size: 0.875rem; }
</style>
