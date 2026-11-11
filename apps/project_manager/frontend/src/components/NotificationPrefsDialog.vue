<script setup>
import { reactive, ref, watch } from "vue";
import { api } from "../lib/api.js";
import { toast } from "../lib/toast.js";
import Drawer from "./Drawer.vue";
import Icon from "./Icon.vue";

// Tùy chọn thông báo: email or not, quiet hours (email waits until they end; in-app notices always arrive), the daily
// and weekly digests, alert types one does not want.
const props = defineProps({ open: { type: Boolean, default: false } });
const emit = defineEmits(["close"]);

const form = reactive({ email: 1, quiet_start: "", quiet_end: "", digest_daily: 1, digest_weekly: 1, muted: [] });
const types = ref([]);
const emailReady = ref(false);
const error = ref("");
const busy = ref(false);
const loading = ref(false);

watch(() => props.open, async (open) => {
  if (!open) return;
  error.value = "";
  loading.value = true;
  try {
    const pref = await api.alerts.preference();
    Object.assign(form, { email: pref.email, quiet_start: pref.quiet_start, quiet_end: pref.quiet_end,
      digest_daily: pref.digest_daily, digest_weekly: pref.digest_weekly, muted: [...pref.muted_types] });
    types.value = pref.types;
    emailReady.value = pref.email_ready;
  } catch (e) {
    error.value = e.message;
  } finally {
    loading.value = false;
  }
});

async function save() {
  busy.value = true;
  error.value = "";
  try {
    await api.alerts.savePreference({ email: form.email ? 1 : 0, quiet_start: form.quiet_start || "", quiet_end: form.quiet_end || "",
      digest_daily: form.digest_daily ? 1 : 0, digest_weekly: form.digest_weekly ? 1 : 0, muted_types: form.muted.join("\n") });
    toast("Đã lưu tùy chọn thông báo");
    emit("close");
  } catch (e) {
    error.value = e.message;
  } finally {
    busy.value = false;
  }
}
</script>

<template>
  <Drawer :open="open" title="Tùy chọn thông báo" width="460px" @close="emit('close')">
    <form id="notification-prefs" class="space-y-5" @submit.prevent="save">
      <p v-if="error" class="rounded-md bg-danger-soft px-3 py-2 text-sm text-danger" role="alert">{{ error }}</p>
      <fieldset class="space-y-2" :disabled="loading">
        <legend class="label">Email</legend>
        <label class="flex items-center gap-2 text-sm"><input v-model="form.email" type="checkbox" :true-value="1" :false-value="0" /> Nhận cảnh báo và tóm tắt qua email</label>
        <p v-if="!emailReady" class="m-0 text-xs text-ink-muted">Hệ thống chưa có tài khoản email gửi đi: hiện chỉ có thông báo trong ứng dụng.</p>
      </fieldset>
      <fieldset class="space-y-2" :disabled="loading">
        <legend class="label">Giờ yên lặng</legend>
        <div class="grid grid-cols-2 gap-3">
          <div><label class="label" for="quiet-start">Từ</label><input id="quiet-start" v-model="form.quiet_start" class="input" type="time" /></div>
          <div><label class="label" for="quiet-end">Đến</label><input id="quiet-end" v-model="form.quiet_end" class="input" type="time" /></div>
        </div>
        <p class="m-0 text-xs text-ink-muted">Trong giờ yên lặng email chờ đến hết giờ mới gửi; thông báo trong ứng dụng vẫn đến.</p>
      </fieldset>
      <fieldset class="space-y-2" :disabled="loading">
        <legend class="label">Tóm tắt</legend>
        <label class="flex items-center gap-2 text-sm"><input v-model="form.digest_daily" type="checkbox" :true-value="1" :false-value="0" /> Tóm tắt hằng ngày (7 giờ sáng)</label>
        <label class="flex items-center gap-2 text-sm"><input v-model="form.digest_weekly" type="checkbox" :true-value="1" :false-value="0" /> Tóm tắt tuần cho dự án tôi quản lý (sáng thứ Hai)</label>
      </fieldset>
      <fieldset class="space-y-1" :disabled="loading">
        <legend class="label">Không nhận các loại cảnh báo</legend>
        <label v-for="type in types" :key="type" class="flex items-center gap-2 text-sm"><input v-model="form.muted" type="checkbox" :value="type" /> {{ type }}</label>
      </fieldset>
    </form>
    <template #footer>
      <button class="btn" type="button" @click="emit('close')">Hủy</button>
      <button class="btn btn-primary" type="submit" form="notification-prefs" :disabled="busy || loading"><Icon v-if="busy" name="loader" :size="16" spin /> Lưu</button>
    </template>
  </Drawer>
</template>
