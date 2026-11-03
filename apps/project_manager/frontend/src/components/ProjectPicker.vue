<script setup>
import { ref, watch } from "vue";
import { api } from "../lib/api.js";
import Icon from "./Icon.vue";
import LinkSelect from "./LinkSelect.vue";

// A list of projects: chips to remove, a search box to add. Value: [{project, project_name}].
const props = defineProps({
  modelValue: { type: Array, default: () => [] },
  disabled: { type: Boolean, default: false },
  label: { type: String, default: "Dự án" },
});
const emit = defineEmits(["update:modelValue"]);
const adding = ref("");

watch(adding, async (value) => {
  if (!value) return;
  if (!props.modelValue.some((row) => row.project === value)) {
    let name = value;
    try {
      const hit = (await api.linkSearch("Project", value)).find((row) => row.value === value);
      if (hit) name = hit.label;
    } catch {
      /* the code is a usable label */
    }
    emit("update:modelValue", [...props.modelValue, { project: value, project_name: name }]);
  }
  adding.value = "";
});

const remove = (project) => emit("update:modelValue", props.modelValue.filter((row) => row.project !== project));
</script>

<template>
  <div class="space-y-2">
    <ul v-if="modelValue.length" class="m-0 flex list-none flex-wrap gap-1.5 p-0" :aria-label="label">
      <li v-for="row in modelValue" :key="row.project" class="badge badge-info inline-flex items-center gap-1">
        {{ row.project_name || row.project }}
        <button v-if="!disabled" type="button" class="leading-none" :aria-label="`Bỏ ${row.project_name || row.project}`" @click="remove(row.project)">
          <Icon name="x" :size="12" />
        </button>
      </li>
    </ul>
    <p v-else class="m-0 text-xs text-ink-muted">Chưa chọn dự án nào.</p>
    <LinkSelect v-if="!disabled" v-model="adding" doctype="Project" :clearable="false" placeholder="Thêm dự án…" />
  </div>
</template>
