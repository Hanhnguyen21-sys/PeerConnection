// Single shared demo data store, persisted in localStorage so changes survive a
// refresh. Holds demo records only: never passwords, tokens, or real user data
// beyond the signed-in user's name and email (so supervisors can see who registered).
import { campusToday } from "../../lib/campusTime";
import { createSeedData } from "./fixtures";

const STORAGE_KEY = "peer-connections.demo-data.v1";
// Bump when the demo data shape or fixtures change; older saved data is replaced.
const VERSION = 2;

let cache = null;

function persist() {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify({ version: VERSION, data: cache }));
  } catch {
    // Storage can be unavailable (private mode, quota); keep working in memory.
  }
}

function loadSaved() {
  try {
    const saved = JSON.parse(localStorage.getItem(STORAGE_KEY));
    return saved?.version === VERSION ? saved.data : null;
  } catch {
    return null;
  }
}

export function readStore() {
  if (!cache) {
    cache = loadSaved();
    if (!cache) {
      cache = createSeedData(campusToday());
      persist();
    }
  }
  return cache;
}

// Applies a change to a copy of the store and saves it, so a failed update never
// leaves half-written data behind.
export function updateStore(mutate) {
  const draft = structuredClone(readStore());
  const result = mutate(draft);
  cache = draft;
  persist();
  return result;
}

export function resetStore() {
  cache = createSeedData(campusToday());
  persist();
}

export function nextId(records, key) {
  return records.reduce((max, record) => Math.max(max, record[key]), 0) + 1;
}
