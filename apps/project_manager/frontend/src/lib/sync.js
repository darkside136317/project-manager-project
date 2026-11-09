// The app's side of the outbox (lib/outbox.js): what a comment or a progress report becomes when it is queued,
// how it is sent, and when the queue is tried again — when the network comes back, when the app returns to the
// foreground, every 30 s while something waits, and at start-up (iPhones never send in the background: they send
// when the app is opened again).
import { reactive } from "vue";
import { api } from "./api.js";
import { boot } from "./boot.js";
import { currentPosition, describePhoto, shrink } from "./images.js";
import { FAILED, IdbStore, MemoryStore, WAITING, createOutbox, isNetworkError, newId } from "./outbox.js";

export const network = reactive({
  online: typeof navigator === "undefined" ? true : navigator.onLine !== false,
  items: [],
  sending: false,
});

const sentListeners = new Set();
let outbox = null;
let timer = null;

/** Called with (item, answer) after each queued item reaches the server. Returns a function that stops listening. */
export function onSent(listener) {
  sentListeners.add(listener);
  return () => sentListeners.delete(listener);
}

async function sendComment(item, saveProgress) {
  const { doctype, name } = item.reference;
  for (const photo of item.photos) {
    if (photo.done) continue;
    const form = new FormData();
    form.append("reference_doctype", doctype);
    form.append("reference_name", name);
    form.append("client_uuid", photo.uuid);
    if (photo.takenAt) form.append("taken_at", photo.takenAt);
    if (photo.lat !== null && photo.lat !== undefined) form.append("lat", String(photo.lat));
    if (photo.lng !== null && photo.lng !== undefined) form.append("lng", String(photo.lng));
    form.append("file", new Blob([photo.data], { type: photo.type || "image/jpeg" }), photo.name || "anh.jpg");
    await api.media.upload(form);
    photo.done = true;
    photo.data = null;  // uploaded: no need to keep the bytes on the phone
    await saveProgress();
  }
  return api.activity.post(doctype, name, {
    content: item.payload.content || "",
    media: item.photos.map((photo) => photo.uuid),
    client_uuid: item.id,
  });
}

function sendProgress(item) {
  return api.tasks.report(item.payload.task, { ...item.payload.values, client_uuid: item.id });
}

export const SENDERS = { comment: sendComment, progress: sendProgress };

function ensure() {
  if (!outbox) {
    const store = typeof indexedDB === "undefined" ? new MemoryStore() : new IdbStore();
    outbox = createOutbox({
      store, senders: SENDERS, user: boot.user.name,
      onChange: (items) => { network.items = items; },
      onSent: (item, answer) => sentListeners.forEach((listener) => listener(item, answer)),
    });
  }
  return outbox;
}

/** Try to send what waits (nothing happens while offline). */
export async function sendNow() {
  const queue = ensure();
  if (!network.online) return { sent: 0, failed: 0, waiting: queue.items.length };
  network.sending = true;
  try {
    return await queue.flush();
  } finally {
    network.sending = queue.busy;
  }
}

function schedule() {
  clearInterval(timer);
  timer = setInterval(() => {
    if (network.online && network.items.some((item) => item.state === WAITING && item.user === boot.user.name)) sendNow();
  }, 30000);
}

/** Start once, from main.js. */
export function startSync() {
  if (typeof window === "undefined") return;
  ensure().load().then(() => sendNow());
  window.addEventListener("online", () => { network.online = true; sendNow(); });
  window.addEventListener("offline", () => { network.online = false; });
  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState === "visible") sendNow();
  });
  schedule();
}

/** Prepare picked photos: when and where they were taken (before shrinking drops EXIF), then a small JPEG. */
export async function preparePhotos(files, { withPlace = false } = {}) {
  const place = withPlace ? await currentPosition() : null;
  const out = [];
  for (const file of files) {
    const facts = await describePhoto(file);
    const small = await shrink(file);
    out.push({
      uuid: newId(), name: (file.name || "anh.jpg").replace(/\.[^.]+$/, "") + ".jpg", type: small.type || "image/jpeg",
      size: small.size, data: await small.arrayBuffer(), takenAt: facts.takenAt,
      lat: facts.lat ?? place?.lat ?? null, lng: facts.lng ?? place?.lng ?? null,
    });
  }
  return out;
}

/** Queue a comment (with its prepared photos) and send it right away when there is a connection. */
export async function queueComment(reference, content, photos = [], label = "") {
  const item = await ensure().add("comment", { content }, { reference, photos, label });
  sendNow();
  return item;
}

/**
 * A progress report: sent directly when online (so the server's checks answer at once); kept in the queue only
 * when there is no answer, with the same id, so a report that did arrive is not recorded twice.
 * Returns { queued: false, result } or { queued: true }.
 */
export async function reportProgress(task, values, label = "") {
  const id = newId();
  if (network.online) {
    try {
      return { queued: false, result: await api.tasks.report(task, { ...values, client_uuid: id }) };
    } catch (error) {
      if (!isNetworkError(error)) throw error;
    }
  }
  await ensure().add("progress", { task, values }, { id, reference: { doctype: "Task", name: task }, label });
  return { queued: true };
}

export const removeQueued = (id) => ensure().remove(id);
export const retryQueued = (id) => ensure().retry(id);

/** Queued items of one discussion (shown above its entries with their state). */
export function queuedFor(doctype, name) {
  return network.items.filter((item) => item.kind === "comment" && item.user === boot.user.name
    && item.reference?.doctype === doctype && item.reference?.name === name);
}

export const pendingCount = () => network.items.filter((item) => item.user === boot.user.name).length;
export const failedCount = () => network.items.filter((item) => item.user === boot.user.name && item.state === FAILED).length;
