<script setup>
import { computed, nextTick, ref, watch } from "vue";
import { useRouter } from "vue-router";
import { boot } from "../lib/boot.js";
import Icon from "./Icon.vue";

// Ctrl/Cmd+K: jump to any screen of the sidebar from anywhere (finding projects and tasks comes with search, M5).
const props = defineProps({ open: { type: Boolean, default: false } });
const emit = defineEmits(["close"]);
const router = useRouter();

const query = ref("");
const input = ref(null);
const active = ref(0);

const toPath = (route) => route.replace(/^\/pm/, "") || "/";
const screens = computed(() => [
  ...boot.nav.flatMap((g) => g.items.map((i) => ({ label: i.label, icon: i.icon, to: toPath(i.route) }))),
]);
const matchingScreens = computed(() => {
  const needle = query.value.trim().toLowerCase();
  return screens.value.filter((s) => !needle || s.label.toLowerCase().includes(needle)).slice(0, 8);
});

const entries = computed(() => matchingScreens.value.map((s) => ({ ...s, group: "Đi tới" })));

watch(query, () => { active.value = 0; });
watch(() => props.open, async (open) => {
  if (!open) return;
  query.value = "";
  active.value = 0;
  await nextTick();
  input.value?.focus();
});

function go(entry) {
  emit("close");
  router.push(entry.to);
}
function onKey(event) {
  if (event.key === "Escape") emit("close");
  else if (event.key === "ArrowDown") { event.preventDefault(); active.value = Math.min(entries.value.length - 1, active.value + 1); }
  else if (event.key === "ArrowUp") { event.preventDefault(); active.value = Math.max(0, active.value - 1); }
  else if (event.key === "Enter" && entries.value[active.value]) { event.preventDefault(); go(entries.value[active.value]); }
}
</script>

<template>
  <Teleport to="body">
    <div v-if="open" class="fixed inset-0 z-[70] grid place-items-start justify-items-center px-4 pt-[12vh]" role="dialog" aria-modal="true" aria-label="Tìm nhanh">
      <div class="absolute inset-0 bg-black/50" @click="emit('close')"></div>
      <div class="card relative w-full max-w-xl overflow-hidden shadow-pop" @keydown="onKey">
        <div class="flex items-center gap-3 border-b border-line px-4">
          <Icon name="search" class="text-ink-muted" />
          <input ref="input" v-model="query" class="h-12 flex-1 border-0 bg-transparent text-base outline-none" type="text" placeholder="Đi tới màn hình..." aria-label="Tìm nhanh" role="combobox" aria-expanded="true" autocomplete="off" />
          <kbd class="rounded border border-line px-1.5 py-0.5 text-xs text-ink-muted">Esc</kbd>
        </div>
        <ul class="m-0 max-h-[52vh] list-none overflow-y-auto p-2" role="listbox">
          <template v-for="(entry, index) in entries" :key="entry.group + entry.label + index">
            <li v-if="index === 0 || entries[index - 1].group !== entry.group" class="px-3 pb-1 pt-2 text-[11px] font-semibold uppercase tracking-wider text-ink-muted" role="presentation">{{ entry.group }}</li>
            <li
              role="option"
              :aria-selected="index === active"
              class="flex cursor-pointer items-center gap-3 rounded-md px-3 py-2 text-sm"
              :class="index === active ? 'bg-primary-soft' : ''"
              @mouseenter="active = index"
              @click="go(entry)"
            >
              <Icon :name="entry.icon" :size="17" class="shrink-0 text-ink-muted" />
              <span class="min-w-0 flex-1"><span class="block truncate font-medium">{{ entry.label }}</span><span v-if="entry.hint" class="block truncate text-xs text-ink-muted">{{ entry.hint }}</span></span>
              <Icon v-if="index === active" name="corner-down-left" :size="14" class="text-ink-muted" />
            </li>
          </template>
          <li v-if="!entries.length" class="px-3 py-6 text-center text-sm text-ink-muted">Không có kết quả</li>
        </ul>
      </div>
    </div>
  </Teleport>
</template>
