// Shared page chrome and helpers for the Charter site.
import { openDataset } from "../lib/charter-data.js";

export const GITHUB = "https://github.com/zachmacsmith/charter";
export const DATASET_REPO = "zachmacsmith/charter-runs";
export const DATASET_URL = `https://huggingface.co/datasets/${DATASET_REPO}`;
const THEMES = [["swiss", "Swiss"], ["broadsheet", "Broadsheet"], ["night", "Night"]];

// ------------------------------------------------------------------ theme (set before paint by the inline snippet in each page)
export function currentTheme() {
  const q = new URLSearchParams(location.search).get("theme");
  if (q) { try { localStorage.setItem("charter-theme", q); } catch (e) {} return q; }
  try { return localStorage.getItem("charter-theme") || "broadsheet"; } catch (e) { return "broadsheet"; }
}
function setTheme(t) {
  document.documentElement.dataset.theme = t;
  try { localStorage.setItem("charter-theme", t); } catch (e) {}
  document.querySelectorAll(".themes button").forEach((b) => b.classList.toggle("on", b.dataset.t === t));
  document.dispatchEvent(new CustomEvent("themechange", { detail: t }));
}

// ------------------------------------------------------------------ data source: a local copy while developing, else the Hub
export function dataSource() {
  const q = new URLSearchParams(location.search);
  if (q.get("data") === "hf") return { repo: DATASET_REPO };
  if (q.get("data")) return { base: q.get("data") };
  const local = ["localhost", "127.0.0.1", ""].includes(location.hostname);
  return local ? { base: new URL("_data", siteRoot()).href.replace(/\/$/, "") } : { repo: DATASET_REPO };
}
let _ds;
export function dataset() { return (_ds ||= openDataset(dataSource())); }
export function siteRoot() { return new URL("../", import.meta.url).href; }

// ------------------------------------------------------------------ chrome
export function chrome(active) {
  document.documentElement.dataset.theme = currentTheme();
  const nav = [["index.html", "The experiment", "home"], ["runs.html", "Runs", "runs"], ["notes.html", "Notes", "notes"]];
  const head = document.createElement("header");
  head.className = "site-head";
  head.innerHTML = `<div class="wrap">
    <a class="brand" href="index.html">Charter</a>
    <nav class="nav">${nav.map(([h, t, k]) => `<a href="${h}" class="${k === active ? "on" : ""}">${t}</a>`).join("")}
      <a href="${GITHUB}">GitHub</a><a href="${DATASET_URL}">Dataset</a></nav>
    ${new URLSearchParams(location.search).has("themes") ? `<div class="themes" title="Design">${THEMES.map(([k, t]) => `<button data-t="${k}">${t}</button>`).join("")}</div>` : ""}</div>`;
  document.body.prepend(head);
  head.querySelectorAll(".themes button").forEach((b) => (b.onclick = () => setTheme(b.dataset.t)));
  setTheme(currentTheme());
  const foot = document.createElement("footer");
  foot.className = "site-foot";
  foot.innerHTML = `<div class="wrap"><span>Charter: societies of LLM agents</span>
    <a href="${GITHUB}">Code (MIT)</a><a href="${DATASET_URL}">Data (CC BY 4.0)</a>
    <a href="https://zachmacsmith.com">Zach Macsmith</a></div>`;
  document.body.append(foot);
}

// ------------------------------------------------------------------ helpers
export const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
export const $ = (sel, root = document) => root.querySelector(sel);
export function mascot(name, mood = "ok", size = 52) {
  return `<svg class="m" width="${size}" height="${size}" viewBox="-2 -2 44 44" aria-hidden="true"><use href="assets/mascots.svg#${esc(name)}-${mood}"/></svg>`;
}
export const modelShort = (m) => String(m || "").replace(/^claude-/, "").replace(/-(\d+)-(\d+)$/, " $1.$2").replace(/^\w/, (c) => c.toUpperCase());
export const parse = (v) => { if (v == null || typeof v !== "string") return v ?? null; try { return JSON.parse(v); } catch (e) { return null; } };
export function runFacts(r) {
  const models = (parse(r.models_list_json) || []).map(modelShort);
  return { models, rounds: r.rounds_played ?? r.rounds, tags: parse(r.tags_json) || [] };
}
