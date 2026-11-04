<script setup>
import { computed, inject, onMounted, reactive, ref, watch } from "vue";
import Icon from "../../components/Icon.vue";
import { api } from "../../lib/api.js";
import { boot } from "../../lib/boot.js";
import { debounce } from "../../lib/format.js";
import { toast } from "../../lib/toast.js";
import { deadlineText, deadlineTone, groupCards } from "../../lib/work.js";

// Kanban: the leaf tasks in their status columns. A card moves by drag and drop (desktop) or by its menu (phone);
// finishing late work asks for the delay reason in the task panel, where the server's rule is explained.
const { name: project, openTask, version, reload } = inject("project");
const columns = ref([]);
const cards = ref([]);
const more = ref(false);
const canMove = ref(false);
const loading = ref(false);
const filters = reactive({ search: "", late: false, mine: false });
const dragging = ref("");
const over = ref("");
const grouped = computed(() => groupCards(columns.value, cards.value));

async function load() {
  loading.value = true;
  try {
    const result = await api.tasks.kanban(project.value, {
      search: filters.search, late: filters.late ? 1 : 0,
      accountable: filters.mine ? boot.user.name : null,
    });
    columns.value = result.columns;
    cards.value = result.cards;
    more.value = result.more;
    canMove.value = result.can_move;
  } catch (e) {
    toast(e.message, "error", 7000);
  } finally {
    loading.value = false;
  }
}

async function move(card, status) {
  if (!status || status === card.status) return;
  const before = card.status;
  card.status = status;  // optimistic: the board answers at once, the server has the last word
  try {
    await api.tasks.move(card.name, status);
    reload();
  } catch (e) {
    card.status = before;
    toast(e.message, "error", 8000);
    if (/quá hạn|lý do chậm|biểu mẫu/i.test(e.message)) openTask(card.name);
  }
  await load();
}

function drop(status) {
  const card = cards.value.find((c) => c.name === dragging.value);
  over.value = "";
  dragging.value = "";
  if (card) move(card, status);
}

const search = debounce(load, 300);
watch(() => filters.search, search);
watch(() => [filters.late, filters.mine], load);
watch(version, load);
onMounted(load);
</script>

<template>
  <div class="mb-3 flex flex-wrap items-center gap-2">
    <input v-model="filters.search" class="input max-w-xs" type="search" placeholder="Tìm công việc" aria-label="Tìm công việc" />
    <label class="flex items-center gap-1 text-sm"><input v-model="filters.late" type="checkbox" /> Chỉ việc quá hạn</label>
    <label class="flex items-center gap-1 text-sm"><input v-model="filters.mine" type="checkbox" /> Tôi chịu trách nhiệm</label>
    <Icon v-if="loading" name="loader" spin class="text-ink-muted" />
  </div>
  <p v-if="more" class="mb-2 text-sm text-warning">Chỉ hiện 500 việc đầu tiên: hãy lọc bớt.</p>

  <div class="flex snap-x gap-3 overflow-x-auto pb-3">
    <section v-for="column in columns" :key="column.status" class="flex w-72 shrink-0 snap-start flex-col rounded-xl bg-surface-muted p-2"
      :class="{ 'ring-2 ring-primary': over === column.status }" :aria-label="column.label"
      @dragover.prevent="over = column.status" @dragleave="over = ''" @drop.prevent="drop(column.status)">
      <h2 class="m-0 flex items-center justify-between px-1 py-1 text-sm font-semibold">
        {{ column.label }} <span class="badge badge-muted">{{ grouped[column.status]?.length || 0 }}</span>
      </h2>
      <ul class="m-0 mt-1 flex min-h-16 list-none flex-col gap-2 p-0">
        <li v-for="card in grouped[column.status]" :key="card.name" :draggable="canMove" class="card cursor-pointer p-3 text-sm"
          @dragstart="dragging = card.name" @dragend="dragging = ''" @click="openTask(card.name)">
          <p class="m-0 text-xs text-ink-muted">{{ card.pm_wbs_code }}</p>
          <p class="m-0 font-medium">{{ card.subject }}</p>
          <div class="mt-2 flex items-center gap-2 text-xs">
            <span class="truncate text-ink-muted">{{ card.accountable_name || "Chưa giao" }}</span>
            <span class="ml-auto shrink-0" :class="deadlineTone(deadlineText(card))">{{ deadlineText(card) }}</span>
          </div>
          <div class="mt-2 h-1 overflow-hidden rounded-full bg-surface-muted"><div class="h-full bg-primary" :style="{ width: `${Math.min(100, card.progress || 0)}%` }"></div></div>
          <select v-if="canMove" class="input mt-2 !min-h-0 !py-1 text-xs sm:hidden" :value="card.status" aria-label="Chuyển cột"
            @click.stop @change="move(card, $event.target.value)">
            <option v-for="c in columns" :key="c.status" :value="c.status">{{ c.label }}</option>
          </select>
        </li>
      </ul>
    </section>
  </div>
</template>
