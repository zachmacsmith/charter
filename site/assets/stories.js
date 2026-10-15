// The home page's stories: a carousel over the dataset's stories registry (stories.json), in a fresh random order on every
// visit. Shows up to three at a time and slides on by itself; pauses on hover, on focus, when the tab is hidden and for
// reduced motion.
import { esc } from "./site.js";
import { mascotSymbol } from "./run/mascots.js";

const hash = (s) => { let h = 2166136261; for (const c of String(s)) { h ^= c.charCodeAt(0); h = Math.imul(h, 16777619); } return h >>> 0; };
const MOODS = ["ok", "happy", "sad"];
const EVERY = 7000;

function shuffle(xs) {
  const a = xs.slice();
  for (let i = a.length - 1; i > 0; i--) { const j = Math.floor(Math.random() * (i + 1)); [a[i], a[j]] = [a[j], a[i]]; }
  return a;
}

function sprite(stories) {
  const dark = document.documentElement.dataset.theme === "night";
  let el = document.getElementById("story-sprite");
  if (!el) { el = document.createElementNS("http://www.w3.org/2000/svg", "svg"); el.id = "story-sprite";
    el.setAttribute("width", "0"); el.setAttribute("height", "0"); el.style.position = "absolute"; document.body.prepend(el); }
  el.innerHTML = "<defs>" + stories.map((st, i) => mascotSymbol({ id: st.agent, n: `s${i}`, cls: st.class,
    hue: (hash(st.agent) % 360 + 18) % 360 }, MOODS.includes(st.mood) ? st.mood : "ok", dark)).join("") + "</defs>";
}

function card(st, i, run) {
  const who = [st.agent, [st.model, st.class].filter(Boolean).join(" ")].filter(Boolean).join(", ");
  const href = `run.html?id=${encodeURIComponent(st.run_id)}#people/${encodeURIComponent(st.agent)}${st.round ? `@${st.round}` : ""}`;
  return `<article class="story" aria-roledescription="slide">
    <div class="story-top"><svg class="m" viewBox="-2 -2 44 44" aria-hidden="true"><use href="#ms${i}-${MOODS.includes(st.mood) ? st.mood : "ok"}"/></svg>
      <div><h3>${esc(st.title)}</h3><p class="sub">${esc(st.subtitle)}</p></div></div>
    <blockquote>“${esc(st.quote)}”</blockquote>
    <div class="story-foot"><cite>${esc(who)}</cite>
      <a href="${href}">${esc(run ? run.title : st.run_id)} →</a></div></article>`;
}

export function storyCarousel(root, stories, runs = []) {
  const byId = Object.fromEntries(runs.map((r) => [r.run_id, r]));
  stories = shuffle(stories.filter((st) => st.title && st.quote && st.agent && st.run_id));
  if (!stories.length) { root.innerHTML = '<p class="meta">No stories yet.</p>'; return; }
  sprite(stories);
  document.addEventListener("themechange", () => sprite(stories));
  root.innerHTML = `<div class="carousel-view"><div class="carousel-track"></div></div>
    <div class="carousel-ctl"><button class="prev" aria-label="Previous stories">‹</button>
      <div class="carousel-bar"><span></span></div><button class="next" aria-label="Next stories">›</button></div>`;
  const track = root.querySelector(".carousel-track"), bar = root.querySelector(".carousel-bar span");
  const n = stories.length;
  const one = matchMedia("(max-width: 720px)"), two = matchMedia("(max-width: 1040px)");
  const perView = () => Math.min(n, one.matches ? 1 : two.matches ? 2 : 3);
  let per = 0, at = 0, timer = null, paused = false;

  function build() {                                    // the stories, then the first `per` again so the loop wraps seamlessly
    per = perView();
    root.style.setProperty("--per", per);
    const looped = n > per ? stories.concat(stories.slice(0, per)) : stories;
    track.innerHTML = looped.map((st, i) => card(st, i % n, byId[st.run_id])).join("");
    root.querySelector(".carousel-ctl").hidden = n <= per;
    at = 0; place(false);
  }
  function place(animate = true) {
    track.style.transition = animate ? "" : "none";
    const first = track.children[0], gap = parseFloat(getComputedStyle(track).columnGap) || 0;
    track.style.transform = `translateX(${-at * ((first ? first.getBoundingClientRect().width : 0) + gap)}px)`;
    bar.style.width = `${(((at % n) + per) / n) * 100}%`;
    track.querySelectorAll(".story").forEach((el, i) => el.toggleAttribute("inert", i < at || i >= at + per));
  }
  function go(step) {
    if (n <= per) return;
    if (at >= n) { at -= n; place(false); track.getBoundingClientRect(); }      // a wrap still waiting to snap back
    if (at + step < 0) { at += n; place(false); track.getBoundingClientRect(); }  // jump to the clones, then slide back
    at = Math.min(at + step, n);                       // never past the clones; at n they look exactly like the start
    place();
    if (at >= n) setTimeout(() => { if (at >= n) { at -= n; place(false); } }, 650);
    restart();
  }
  const reduced = matchMedia("(prefers-reduced-motion: reduce)").matches;
  function restart() {
    clearTimeout(timer);
    if (!reduced && !paused && !document.hidden && n > per) timer = setTimeout(() => go(per), EVERY);
  }
  root.querySelector(".prev").onclick = () => go(-per);
  root.querySelector(".next").onclick = () => go(per);
  root.addEventListener("mouseenter", () => { paused = true; restart(); });
  root.addEventListener("mouseleave", () => { paused = false; restart(); });
  root.addEventListener("focusin", () => { paused = true; restart(); });
  root.addEventListener("focusout", () => { paused = false; restart(); });
  document.addEventListener("visibilitychange", restart);
  const refit = () => { if (perView() !== per) build(); else place(false); restart(); };
  [one, two].forEach((mq) => mq.addEventListener("change", refit));
  let resizeT;
  addEventListener("resize", () => { clearTimeout(resizeT); resizeT = setTimeout(refit, 150); });
  build(); restart();
}
