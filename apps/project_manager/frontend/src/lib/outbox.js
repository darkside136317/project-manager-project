// Outbox: what someone writes while the site has no signal (comments with photos, progress reports) waits in
// IndexedDB and is sent in order once the connection is back, also after the app was closed and opened again.
// Every item carries the ids the server deduplicates on (client_uuid), so an item resent after a lost answer is
// still recorded once. Only data that is added (never edited) goes through here (plan D12).

export const WAITING = "waiting";
export const SENDING = "sending";
export const FAILED = "failed";

export function newId() {
  if (globalThis.crypto?.randomUUID) return globalThis.crypto.randomUUID();
  return `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 12)}-${Math.random().toString(36).slice(2, 8)}`;
}

/** No answer at all (offline, server unreachable): try again later. */
export const isNetworkError = (error) => !error?.status;

/** Errors that may pass by themselves: no network, server overloaded or restarting, expired session or token. */
export function isRetryable(error) {
  const status = error?.status || 0;
  return !status || status >= 500 || status === 429 || status === 401 || error?.excType === "CSRFTokenError"
    || error?.excType === "AuthenticationError";
}

/** Kept in memory: tests, and browsers without IndexedDB (the queue then lives until the tab closes). */
export class MemoryStore {
  constructor() {
    this.rows = new Map();
  }

  async all() {
    return [...this.rows.values()];
  }

  async put(row) {
    this.rows.set(row.id, row);
  }

  async delete(id) {
    this.rows.delete(id);
  }
}

/** The browser's IndexedDB: survives reloads and closing the app. Photos are stored as ArrayBuffers (every browser,
 * Safari included, keeps those; some old ones lose Blobs). */
export class IdbStore {
  constructor(name = "pm-outbox") {
    this.name = name;
    this.ready = null;
  }

  open() {
    if (!this.ready) {
      this.ready = new Promise((resolve, reject) => {
        const request = indexedDB.open(this.name, 1);
        request.onupgradeneeded = () => request.result.createObjectStore("items", { keyPath: "id" });
        request.onsuccess = () => resolve(request.result);
        request.onerror = () => reject(request.error);
      });
    }
    return this.ready;
  }

  async run(mode, action) {
    const db = await this.open();
    return new Promise((resolve, reject) => {
      const transaction = db.transaction("items", mode);
      const request = action(transaction.objectStore("items"));
      transaction.oncomplete = () => resolve(request?.result);
      transaction.onerror = () => reject(transaction.error);
      transaction.onabort = () => reject(transaction.error);
    });
  }

  all() {
    return this.run("readonly", (store) => store.getAll());
  }

  put(row) {
    return this.run("readwrite", (store) => store.put(row));
  }

  delete(id) {
    return this.run("readwrite", (store) => store.delete(id));
  }
}

/**
 * The queue. `senders[kind](item, saveProgress)` sends one item and returns the server's answer; it may mark parts
 * done (an uploaded photo) and call saveProgress() so a reload does not send them again.
 * Items are sent oldest first; an error that may pass stops the round (order matters: a comment written after
 * another arrives after it), an error that will not pass (refused by the server) marks the item failed and the round
 * goes on. Items of another account stay in the queue untouched until that account signs in again.
 */
export function createOutbox({ store, senders, user = "", onChange = () => {}, onSent = () => {} }) {
  let items = [];
  let loading = null;
  let running = null;

  const changed = () => onChange([...items]);

  function load() {
    if (!loading) {
      loading = store.all().then((rows) => {
        items = rows.sort((a, b) => a.created - b.created);
        // a round cut short by closing the app leaves "sending": it is simply waiting again
        for (const item of items) if (item.state === SENDING) item.state = WAITING;
        changed();
        return items;
      });
    }
    return loading;
  }

  async function save(item) {
    await store.put(item);
    changed();
  }

  async function add(kind, payload, { id = newId(), reference = null, label = "", photos = [] } = {}) {
    await load();
    const item = {
      id, kind, user, reference, label, payload, state: WAITING, tries: 0, error: "", created: Date.now(),
      photos: photos.map((photo) => ({ ...photo, uuid: photo.uuid || newId(), done: false })),
    };
    items.push(item);
    await save(item);
    return item;
  }

  async function remove(id) {
    await load();
    items = items.filter((item) => item.id !== id);
    await store.delete(id);
    changed();
  }

  async function retry(id) {
    await load();
    const item = items.find((row) => row.id === id);
    if (item) {
      item.state = WAITING;
      item.error = "";
      await save(item);
    }
    return flush();
  }

  async function round() {
    await load();
    const result = { sent: 0, failed: 0, waiting: 0 };
    for (const item of [...items]) {
      if (item.user !== user || item.state === FAILED) continue;
      item.state = SENDING;
      item.tries += 1;
      changed();
      try {
        const answer = await senders[item.kind](item, () => save(item));
        items = items.filter((row) => row !== item);
        await store.delete(item.id);
        result.sent += 1;
        changed();
        onSent(item, answer);
      } catch (error) {
        item.error = error?.message || String(error);
        if (isRetryable(error)) {
          item.state = WAITING;
          await save(item);
          result.waiting += 1;
          break;
        }
        item.state = FAILED;
        await save(item);
        result.failed += 1;
      }
    }
    result.waiting = items.filter((item) => item.user === user && item.state === WAITING).length;
    return result;
  }

  /** Send what waits; a second call while a round runs joins it. */
  function flush() {
    if (!running) running = round().finally(() => { running = null; });
    return running;
  }

  return {
    load, add, remove, retry, flush,
    get items() { return items; },
    get busy() { return Boolean(running); },
  };
}

/** Readable size of a photo or a file. */
export function sizeText(bytes) {
  if (!bytes) return "0 KB";
  if (bytes < 1024 * 1024) return `${Math.max(1, Math.round(bytes / 1024))} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1).replace(".", ",")} MB`;
}
