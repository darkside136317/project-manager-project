// Live updates through Frappe's own Socket.IO server (the `websocket` service, behind nginx at /socket.io).
// A screen watches a document room (a task, a project): the server checks the user may read that document before it
// lets them in, and services/timeline.py publishes to the room after each commit. Without a connection nothing
// breaks: screens still reload when they come back to the foreground.
import { io } from "socket.io-client";
import { boot } from "./boot.js";

let socket = null;
const rooms = new Map();  // "doctype\u0000name" -> number of screens watching it

function roomKey(doctype, name) {
  return `${doctype}\u0000${name}`;
}

function connect() {
  if (socket || !boot.site || typeof window === "undefined") return socket;
  socket = io(`${window.location.origin}/${boot.site}`, {
    // WebSocket only: long-polling needs sticky sessions and answers 400 to a session lost while offline
    path: "/socket.io", transports: ["websocket"], withCredentials: true, reconnectionDelayMax: 15000, timeout: 8000,
  });
  socket.on("connect", () => {
    for (const key of rooms.keys()) socket.emit("doc_subscribe", ...key.split("\u0000"));
  });
  return socket;
}

/**
 * Call `handler(message)` when `event` arrives for this document. Returns a function that stops watching.
 * `accept(message)` filters messages of other rooms the same page watches.
 */
export function watchDocument(doctype, name, event, handler, accept = () => true) {
  const live = connect();
  if (!live) return () => {};
  const key = roomKey(doctype, name);
  rooms.set(key, (rooms.get(key) || 0) + 1);
  if (live.connected) live.emit("doc_subscribe", doctype, name);
  const listener = (message) => {
    if (accept(message || {})) handler(message || {});
  };
  live.on(event, listener);
  return () => {
    live.off(event, listener);
    const left = (rooms.get(key) || 1) - 1;
    if (left > 0) {
      rooms.set(key, left);
    } else {
      rooms.delete(key);
      if (live.connected) live.emit("doc_unsubscribe", doctype, name);
    }
  };
}
