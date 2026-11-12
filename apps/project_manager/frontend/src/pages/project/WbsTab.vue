<script setup>
import { inject, onMounted, reactive, ref, watch } from "vue";
import ConfirmDialog from "../../components/ConfirmDialog.vue";
import EmptyState from "../../components/EmptyState.vue";
import Icon from "../../components/Icon.vue";
import ReasonDialog from "../../components/ReasonDialog.vue";
import { api } from "../../lib/api.js";
import { toast } from "../../lib/toast.js";
import ImportDialog from "./ImportDialog.vue";
import WbsRow from "./WbsRow.vue";

// Công việc: the WBS tree, one level at a time. Planners add, rename, reorder, indent / outdent, cancel and delete;
// everyone opens a task in the drawer. A person who only sees their own tasks gets them as a flat list.
const { name: project, openTask, version, reload } = inject("project");

const ROOT = "";
const tree = reactive({
  children: {}, expanded: {}, loading: {}, more: {}, flat: false, canPlan: false,
  async load(parent = ROOT, append = false) {
    tree.loading[parent] = true;
    try {
      const start = append ? (tree.children[parent] || []).length : 0;
      const result = await api.wbs.children(project.value, parent || null, start);
      tree.children[parent] = append ? [...(tree.children[parent] || []), ...result.rows] : result.rows;
      tree.more[parent] = result.more;
      if (parent === ROOT) {
        tree.flat = result.flat;
        tree.canPlan = result.can_plan;
      }
    } catch (e) {
      toast(e.message, "error", 7000);
    } finally {
      tree.loading[parent] = false;
    }
  },
  async toggle(node) {
    if (tree.expanded[node.name]) {
      delete tree.expanded[node.name];
      return;
    }
    tree.expanded[node.name] = true;
    if (!tree.children[node.name]) await tree.load(node.name);
  },
});
const adding = reactive({ open: false, parent: null, subject: "", is_group: false, start: "", end: "" });
const renaming = reactive({ node: null, subject: "" });
const reason = reactive({ open: false, node: null });
const removing = ref(null);
const importing = ref(false);
const busy = ref(false);

async function refresh(parents = null) {
  const keys = parents || [ROOT, ...Object.keys(tree.expanded)];
  await Promise.all([...new Set(keys)].map((key) => tree.load(key)));
}

function parentKey(node) {
  return node?.parent_task || ROOT;
}

async function act(fn, message, parents) {
  busy.value = true;
  try {
    await fn();
    if (message) toast(message);
    await refresh(parents);
    reload();
    return true;
  } catch (e) {
    toast(e.message, "error", 7000);
    return false;
  } finally {
    busy.value = false;
  }
}

function startAdd(parent = null) {
  Object.assign(adding, { open: true, parent, subject: "", is_group: false, start: "", end: "" });
}

async function add() {
  const parent = adding.parent;
  const ok = await act(() => api.wbs.add(project.value, {
    subject: adding.subject, parent: parent?.name || null, is_group: adding.is_group ? 1 : 0,
    start: adding.start || null, end: adding.end || null,
  }), "Đã thêm công việc", [parentKey(parent), parent?.name || ROOT]);
  if (ok) {
    if (parent) tree.expanded[parent.name] = true;
    adding.subject = "";
  }
}

async function onAction({ kind, node, index }) {
  const siblings = tree.children[parentKey(node)] || [];
  if (kind === "add") return startAdd(node);
  if (kind === "rename") return Object.assign(renaming, { node, subject: node.subject });
  if (kind === "cancel") return Object.assign(reason, { open: true, node });
  if (kind === "delete") return (removing.value = node);
  if (kind === "up" || kind === "down") {
    const to = kind === "up" ? index - 1 : index + 1;
    return act(() => api.wbs.move(node.name, node.parent_task || null, to), "", [parentKey(node)]);
  }
  if (kind === "indent") {
    const target = siblings[index - 1];
    tree.expanded[target.name] = true;
    return act(() => api.wbs.move(node.name, target.name), "Đã thụt vào", [parentKey(node), target.name]);
  }
  if (kind === "outdent") {
    const parentRow = Object.values(tree.children).flat().find((row) => row.name === node.parent_task);
    const grand = parentRow?.parent_task || null;
    const at = (tree.children[grand || ROOT] || []).findIndex((row) => row.name === node.parent_task);
    return act(() => api.wbs.move(node.name, grand, at >= 0 ? at + 1 : null), "Đã đưa ra ngoài", [grand || ROOT, node.parent_task]);
  }
  return null;
}

async function rename() {
  const node = renaming.node;
  const ok = await act(() => api.wbs.update(node.name, { subject: renaming.subject }), "Đã đổi tên", [parentKey(node)]);
  if (ok) renaming.node = null;
}

async function cancelTask(text) {
  const node = reason.node;
  if (await act(() => api.wbs.cancel(node.name, text), "Đã hủy công việc", [parentKey(node)])) reason.open = false;
}

async function remove() {
  const node = removing.value;
  if (await act(() => api.wbs.remove(node.name), "Đã xóa công việc", [parentKey(node)])) removing.value = null;
}

watch(version, () => refresh());
onMounted(() => tree.load(ROOT));
</script>

<template>
  <div class="mb-3 flex flex-wrap items-center gap-2">
    <template v-if="tree.canPlan">
      <button class="btn btn-primary" type="button" @click="startAdd(null)"><Icon name="plus" :size="16" /> Thêm hạng mục</button>
      <button class="btn" type="button" @click="importing = 'excel'"><Icon name="file-spreadsheet" :size="16" /> Nhập từ Excel</button>
      <button class="btn" type="button" @click="importing = 'msproject'"><Icon name="file-up" :size="16" /> Nhập MS Project</button>
    </template>
    <a class="btn" :href="api.wbs.msprojectExportUrl(project)" data-msproject-export><Icon name="file-down" :size="16" /> Xuất MS Project</a>
    <button class="btn btn-ghost ml-auto" type="button" :disabled="busy" @click="refresh()"><Icon name="refresh-cw" :size="16" /> Tải lại</button>
  </div>

  <form v-if="adding.open" class="card mb-3 grid gap-3 p-3 sm:grid-cols-[1fr_140px_140px_auto]" @submit.prevent="add">
    <div class="sm:col-span-4 text-sm text-ink-muted">
      Thêm vào: <strong>{{ adding.parent ? `${adding.parent.pm_wbs_code} ${adding.parent.subject}` : "cấp cao nhất của dự án" }}</strong>
    </div>
    <input v-model="adding.subject" class="input" placeholder="Tên công việc" aria-label="Tên công việc" required />
    <input v-model="adding.start" class="input" type="date" aria-label="Ngày bắt đầu" />
    <input v-model="adding.end" class="input" type="date" aria-label="Ngày kết thúc" />
    <div class="flex items-center gap-2">
      <label class="flex items-center gap-1 text-sm"><input v-model="adding.is_group" type="checkbox" /> Nhóm</label>
      <button class="btn btn-primary" type="submit" :disabled="busy">Thêm</button>
      <button class="btn" type="button" @click="adding.open = false">Đóng</button>
    </div>
  </form>

  <form v-if="renaming.node" class="card mb-3 flex flex-wrap gap-2 p-3" @submit.prevent="rename">
    <input v-model="renaming.subject" class="input flex-1" aria-label="Tên mới" required />
    <button class="btn btn-primary" type="submit" :disabled="busy">Lưu</button>
    <button class="btn" type="button" @click="renaming.node = null">Hủy</button>
  </form>

  <p v-if="tree.flat" class="mb-2 text-sm text-ink-muted">Bạn chỉ thấy các việc được giao cho mình hoặc đội của mình.</p>
  <div class="card px-2 py-1">
    <div class="hidden grid-cols-[1fr_96px_110px_150px_auto] gap-2 border-b border-line px-1 py-2 text-xs font-semibold uppercase tracking-wide text-ink-muted sm:grid">
      <span>Công việc</span><span>Tiến độ</span><span>Trạng thái</span><span>Phụ trách · hạn</span><span class="w-14"></span>
    </div>
    <p v-if="tree.loading[ROOT] && !tree.children[ROOT]" class="flex items-center gap-2 p-3 text-sm text-ink-muted"><Icon name="loader" spin /> Đang tải...</p>
    <EmptyState v-else-if="!(tree.children[ROOT] || []).length" icon="list-tree" title="Chưa có công việc nào"
      :text="tree.canPlan ? 'Thêm hạng mục, nhập từ Excel, hoặc tạo dự án từ một dự án mẫu.' : ''" />
    <ul class="m-0 list-none p-0" role="tree" aria-label="Cây công việc">
      <WbsRow v-for="(node, i) in tree.children[ROOT] || []" :key="node.name" :node="node" :tree="tree" :index="i"
        :siblings="(tree.children[ROOT] || []).length" :can-plan="tree.canPlan && !tree.flat" @open="openTask" @action="onAction" />
    </ul>
    <div v-if="tree.more[ROOT]" class="p-2 text-center"><button class="btn" type="button" @click="tree.load(ROOT, true)">Xem thêm</button></div>
  </div>

  <ReasonDialog :open="reason.open" title="Hủy công việc" label="Lý do hủy" confirm-text="Hủy việc" danger :busy="busy"
    :message="reason.node ? `${reason.node.pm_wbs_code} ${reason.node.subject}: việc bị hủy không còn tính vào tiến độ, lịch sử được giữ lại.` : ''"
    @confirm="cancelTask" @cancel="reason.open = false" />
  <ConfirmDialog :open="Boolean(removing)" title="Xóa công việc" danger confirm-text="Xóa"
    :message="removing ? `Xóa ${removing.pm_wbs_code} ${removing.subject}? Việc đã giao hoặc đã có lịch sử thì chỉ hủy được, không xóa được.` : ''"
    @confirm="remove" @cancel="removing = null" />
  <ImportDialog :open="Boolean(importing)" :kind="importing || 'excel'" :project="project" @close="importing = false" @done="importing = false; refresh(); reload()" />
</template>
