<script setup>
import { computed } from "vue";
import Icon from "../../components/Icon.vue";
import { formatDate } from "../../lib/format.js";
import { deadlineText, deadlineTone, statusBadge, statusLabel } from "../../lib/work.js";

// One row of the WBS and, when opened, its children (recursive). Actions are emitted; WbsTab calls the server.
const props = defineProps({
  node: { type: Object, required: true },
  tree: { type: Object, required: true },
  depth: { type: Number, default: 0 },
  index: { type: Number, default: 0 },
  siblings: { type: Number, default: 1 },
  canPlan: { type: Boolean, default: false },
});
const emit = defineEmits(["open", "action"]);

const open = computed(() => Boolean(props.tree.expanded[props.node.name]));
const kids = computed(() => props.tree.children[props.node.name] || []);
const deadline = computed(() => deadlineText(props.node));
const relay = (event) => emit("action", event);
// A menu action closes its menu (otherwise it stays open, and follows the row when the row moves).
function act(event, dom) {
  dom?.currentTarget?.closest("details")?.removeAttribute("open");
  relay(event);
}
</script>

<template>
  <li role="treeitem" :aria-expanded="node.children ? open : undefined">
    <div class="group grid grid-cols-[1fr_auto] items-center gap-2 border-b border-line py-1.5 pr-1 hover:bg-surface-muted sm:grid-cols-[1fr_96px_110px_150px_auto]"
      :style="{ paddingLeft: `${depth * 20 + 4}px` }">
      <div class="flex min-w-0 items-center gap-1">
        <button v-if="node.children" class="grid h-6 w-6 shrink-0 place-items-center rounded text-ink-muted hover:bg-surface" type="button"
          :aria-label="open ? 'Thu gọn' : 'Mở rộng'" @click="tree.toggle(node)">
          <Icon :name="tree.loading[node.name] ? 'loader' : open ? 'chevron-down' : 'chevron-right'" :size="15" :spin="Boolean(tree.loading[node.name])" />
        </button>
        <span v-else class="inline-block h-6 w-6 shrink-0"></span>
        <span class="shrink-0 text-xs text-ink-muted">{{ node.pm_wbs_code }}</span>
        <button class="min-w-0 truncate rounded px-1 text-left text-sm hover:underline" :class="{ 'font-semibold': node.is_group, 'text-ink-subtle line-through': node.status === 'Cancelled' }"
          type="button" @click="emit('open', node.name)">{{ node.subject }}</button>
        <span v-if="node.pm_is_overdue" class="badge badge-danger shrink-0">Trễ {{ node.pm_delay_days }}n</span>
        <span class="ml-auto shrink-0 pl-1 text-xs text-ink-muted sm:hidden">{{ Math.round(node.progress || 0) }}%</span>
      </div>
      <div class="hidden items-center gap-2 sm:flex">
        <div class="h-1.5 flex-1 overflow-hidden rounded-full bg-surface-muted"><div class="h-full bg-primary" :style="{ width: `${Math.min(100, node.progress || 0)}%` }"></div></div>
        <span class="w-9 text-right text-xs">{{ Math.round(node.progress || 0) }}%</span>
      </div>
      <span class="hidden sm:block"><span :class="statusBadge(node.status)">{{ statusLabel(node.status) }}</span></span>
      <span class="hidden truncate text-xs sm:block" :class="deadlineTone(deadline)" :title="`${formatDate(node.exp_start_date)} → ${formatDate(node.exp_end_date)}`">
        {{ node.accountable_name || "—" }} · {{ formatDate(node.exp_end_date) || "chưa có hạn" }}
      </span>
      <div v-if="canPlan" class="flex items-center opacity-100 sm:opacity-0 sm:group-focus-within:opacity-100 sm:group-hover:opacity-100">
        <button class="btn btn-ghost btn-icon !min-h-0 !p-1" type="button" title="Thêm việc con" aria-label="Thêm việc con" @click="relay({ kind: 'add', node })"><Icon name="plus" :size="15" /></button>
        <details class="relative">
          <summary class="btn btn-ghost btn-icon !min-h-0 list-none !p-1" aria-label="Thao tác khác"><Icon name="ellipsis" :size="15" /></summary>
          <div class="absolute right-0 z-20 mt-1 w-48 rounded-lg border border-line bg-surface py-1 text-sm shadow-pop">
            <button class="block w-full px-3 py-1.5 text-left hover:bg-surface-muted" type="button" @click="act({ kind: 'rename', node }, $event)">Đổi tên</button>
            <button class="block w-full px-3 py-1.5 text-left hover:bg-surface-muted disabled:opacity-50" type="button" :disabled="index === 0" @click="act({ kind: 'up', node, index }, $event)">Lên trên</button>
            <button class="block w-full px-3 py-1.5 text-left hover:bg-surface-muted disabled:opacity-50" type="button" :disabled="index >= siblings - 1" @click="act({ kind: 'down', node, index }, $event)">Xuống dưới</button>
            <button class="block w-full px-3 py-1.5 text-left hover:bg-surface-muted disabled:opacity-50" type="button" :disabled="index === 0" @click="act({ kind: 'indent', node, index }, $event)">Thụt vào (thành việc con của mục trên)</button>
            <button class="block w-full px-3 py-1.5 text-left hover:bg-surface-muted disabled:opacity-50" type="button" :disabled="!node.parent_task" @click="act({ kind: 'outdent', node }, $event)">Đưa ra ngoài một cấp</button>
            <button v-if="!node.is_group && node.status !== 'Cancelled'" class="block w-full px-3 py-1.5 text-left hover:bg-surface-muted" type="button" @click="act({ kind: 'cancel', node }, $event)">Hủy việc</button>
            <button class="block w-full px-3 py-1.5 text-left text-danger hover:bg-surface-muted" type="button" @click="act({ kind: 'delete', node }, $event)">Xóa</button>
          </div>
        </details>
      </div>
    </div>
    <ul v-if="open" role="group" class="m-0 list-none p-0">
      <WbsRow v-for="(child, i) in kids" :key="child.name" :node="child" :tree="tree" :depth="depth + 1" :index="i" :siblings="kids.length"
        :can-plan="canPlan" @open="emit('open', $event)" @action="relay" />
      <li v-if="open && tree.more[node.name]" :style="{ paddingLeft: `${(depth + 1) * 20 + 34}px` }" class="py-1">
        <button class="text-xs underline" type="button" @click="tree.load(node.name, true)">Xem thêm</button>
      </li>
    </ul>
  </li>
</template>
