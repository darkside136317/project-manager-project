<script setup>
import { inject, onMounted, reactive, ref } from "vue";
import EmptyState from "../../components/EmptyState.vue";
import Icon from "../../components/Icon.vue";
import LinkSelect from "../../components/LinkSelect.vue";
import { api } from "../../lib/api.js";
import { formatDate } from "../../lib/format.js";
import { toast } from "../../lib/toast.js";

// Thành viên: who is in the project, in which role, for which period. Work can only be given to members.
const { name: project, reload } = inject("project");
const data = ref(null);
const busy = ref(false);
const form = reactive({ open: false, user: "", project_role: "", valid_from: "", valid_to: "" });

async function load() {
  try {
    data.value = await api.projects.members(project.value);
  } catch (e) {
    toast(e.message, "error", 7000);
  }
}

const searchPeople = async (txt) => (await api.projects.candidates(project.value, txt))
  .map((row) => ({ value: row.name, label: row.full_name || row.name, description: row.name }));

async function add() {
  busy.value = true;
  try {
    await api.projects.addMember(project.value, { user: form.user, project_role: form.project_role,
      valid_from: form.valid_from || null, valid_to: form.valid_to || null });
    toast("Đã thêm thành viên");
    Object.assign(form, { open: false, user: "", project_role: "", valid_from: "", valid_to: "" });
    await load();
    reload();
  } catch (e) {
    toast(e.message, "error", 7000);
  } finally {
    busy.value = false;
  }
}

async function setActive(row, active) {
  busy.value = true;
  try {
    await api.projects.setMember(row.name, { is_active: active ? 1 : 0 });
    await load();
  } catch (e) {
    toast(e.message, "error", 7000);
  } finally {
    busy.value = false;
  }
}

onMounted(load);
</script>

<template>
  <template v-if="data">
    <div class="mb-3 flex items-center gap-2">
      <button v-if="data.can_manage && !form.open" class="btn btn-primary" type="button" @click="form.open = true"><Icon name="user-plus" :size="16" /> Thêm thành viên</button>
    </div>
    <form v-if="form.open" class="card mb-3 grid gap-3 p-3 sm:grid-cols-2" @submit.prevent="add">
      <div class="sm:col-span-2">
        <label class="label" for="m-user">Người</label>
        <LinkSelect v-model="form.user" input-id="m-user" doctype="User" :searcher="searchPeople" />
      </div>
      <div>
        <label class="label" for="m-role">Vai trò trong dự án</label>
        <select id="m-role" v-model="form.project_role" class="input" required>
          <option value="" disabled>Chọn...</option>
          <option v-for="role in data.roles" :key="role" :value="role">{{ role }}</option>
        </select>
      </div>
      <div class="grid grid-cols-2 gap-2">
        <div><label class="label" for="m-from">Từ ngày</label><input id="m-from" v-model="form.valid_from" class="input" type="date" /></div>
        <div><label class="label" for="m-to">Đến ngày</label><input id="m-to" v-model="form.valid_to" class="input" type="date" /></div>
      </div>
      <div class="flex justify-end gap-2 sm:col-span-2">
        <button class="btn" type="button" @click="form.open = false">Hủy</button>
        <button class="btn btn-primary" type="submit" :disabled="busy || !form.user">Thêm</button>
      </div>
    </form>

    <EmptyState v-if="!data.rows.length" icon="users" title="Dự án chưa có thành viên" />
    <ul v-else class="card m-0 list-none divide-y divide-line p-0">
      <li v-for="row in data.rows" :key="row.name" class="flex flex-wrap items-center gap-2 px-4 py-3 text-sm" :class="{ 'opacity-60': !row.current }">
        <span class="font-medium">{{ row.full_name || row.user }}</span>
        <span class="text-ink-muted">{{ row.user }}</span>
        <span class="badge badge-info">{{ row.project_role }}</span>
        <span v-if="row.valid_from || row.valid_to" class="text-xs text-ink-muted">{{ formatDate(row.valid_from) || "…" }} → {{ formatDate(row.valid_to) || "…" }}</span>
        <span v-if="!row.is_active" class="badge badge-muted">Ngừng</span>
        <button v-if="data.can_manage" class="btn btn-ghost ml-auto !min-h-0 !py-1 text-xs" type="button" :disabled="busy" @click="setActive(row, !row.is_active)">
          {{ row.is_active ? "Ngừng tham gia" : "Cho tham gia lại" }}
        </button>
      </li>
    </ul>
  </template>
</template>
