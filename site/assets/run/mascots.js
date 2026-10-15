// Mascots: one creature per agent, dressed for its class, in its own colour, with four moods (ok, happy, sad, gone).
// Drawing code from charter/viewer/template.html (accessory, mascotSymbol).
const hash = (s) => { let h = 2166136261; for (const c of String(s)) { h ^= c.charCodeAt(0); h = Math.imul(h, 16777619); } return h >>> 0; };
export const MOODS = ["ok", "happy", "sad", "gone"];

function accessory(cls, deep, body, eyeKind) {
  const ink = "#2b2a28";
  switch (cls) {
    case "legislator": return `<rect x="13" y="0.5" width="14" height="9.5" rx="1.6" fill="${ink}"/><rect x="13" y="6.8" width="14" height="1.8" fill="#C96442"/><rect x="9.5" y="9.2" width="21" height="2.6" rx="1.3" fill="${ink}"/>`;
    case "worker": return `<path d="M10.5 12.2a9.5 8.6 0 0 1 19 0z" fill="#F2B632"/><rect x="19" y="3.8" width="2" height="8" rx="1" fill="#D99A1E"/><rect x="7.5" y="11.2" width="25" height="2.6" rx="1.3" fill="#D99A1E"/>`;
    case "scientist": return eyeKind === 2
      ? `<circle cx="20" cy="21.5" r="6.6" fill="none" stroke="${ink}" stroke-width="1.5"/><path d="M13.4 21H7.5M26.6 21h5.9" stroke="${ink}" stroke-width="1.3"/>`
      : `<circle cx="15" cy="22" r="5.2" fill="none" stroke="${ink}" stroke-width="1.4"/><circle cx="25" cy="22" r="5.2" fill="none" stroke="${ink}" stroke-width="1.4"/><path d="M19.6 21.5h.8M9.8 21.5H7.2M30.2 21.5h2.6" stroke="${ink}" stroke-width="1.3"/><path d="M15 4q2 3 0 6M20 3q2 3 0 6" fill="none" stroke="#7FA7D9" stroke-width="1.2" stroke-linecap="round"/>`;
    case "media": return `<path d="M10 13.5Q11 4 20 4.5Q29 4 30 13.5z" fill="#6b6f78"/><circle cx="20" cy="4.8" r="1.6" fill="#4b4e55"/><path d="M24 13Q32 12 34 15L24 15z" fill="#4b4e55"/><rect x="25" y="7" width="6" height="4" rx=".6" fill="#fff" stroke="#4b4e55" stroke-width=".6" transform="rotate(14 28 9)"/>`;
    case "board": return `<path d="M15.5 34l4.5 2.2-4.5 2.2zM24.5 34L20 36.2l4.5 2.2z" fill="${ink}"/><circle cx="20" cy="36.2" r="1.2" fill="${ink}"/><circle cx="25" cy="22" r="5" fill="none" stroke="#D9A93A" stroke-width="1.3"/><path d="M29.5 24.5q2 5 0 10" fill="none" stroke="#D9A93A" stroke-width=".8"/>`;
    case "fixer": return `<path d="M9 13q11-6 22 0l-1.2 2.4q-9.8-4.6-19.6 0z" fill="#C44B3D"/><path d="M30 14l4 2-3.5 1z" fill="#C44B3D"/><g transform="rotate(30 34 26)"><rect x="32.6" y="20" width="2.8" height="13" rx="1.4" fill="#8a8d93"/><circle cx="34" cy="19" r="3.6" fill="#8a8d93"/><rect x="33" y="14.8" width="2" height="4.4" fill="${body}"/></g>`;
    case "observer": return `<path d="M4.5 33C3.5 12 36.5 12 35.5 33C33.5 22 28.5 16.5 20 16.5S6.5 22 4.5 33z" fill="#3d3c47"/><path d="M20 4L13.5 15.5Q20 12.5 26.5 15.5z" fill="#3d3c47"/>`;
    default: return `<line x1="20" y1="11" x2="20" y2="4.5" stroke="${deep}" stroke-width="1.6" stroke-linecap="round"/><circle cx="20" cy="4" r="2.4" fill="#F2B632" stroke="${deep}" stroke-width=".8"/>`;
  }
}
function mascotSymbol(a, mood, dk) {
  const k = hash(a.id), h = a.hue, gone = mood === "gone";
  const sat = gone ? 6 : 62;
  const body = `hsl(${h} ${sat}% ${dk ? 58 : 64}%)`, deep = `hsl(${h} ${gone ? 6 : 50}% ${dk ? 30 : 34}%)`, belly = `hsl(${h} ${gone ? 6 : 75}% ${dk ? 74 : 85}%)`;
  const shape = k % 4, eyeKind = (k >>> 4) % 3, top = [11, 10, 12, 10][shape];
  const bodies = [`<circle cx="20" cy="24" r="13"/>`, `<ellipse cx="20" cy="24" rx="12.4" ry="14"/>`, `<rect x="7" y="12" width="26" height="25" rx="10"/>`,
    `<path d="M20 10C30 10 33 20 33 28C33 34 28 37 20 37C12 37 7 34 7 28C7 20 10 10 20 10Z"/>`];
  const b = bodies[shape].replace("/>", ` fill="${body}" stroke="${deep}" stroke-width="1.3"/>`);
  const px = ((k >>> 8) % 3 - 1) * 0.8;
  const pupil = "#1d1c1b";
  let eyes;
  if (gone) eyes = `<path d="M12.5 22.5h5M22.5 22.5h5" stroke="${deep}" stroke-width="1.6" stroke-linecap="round"/>`;
  else if (eyeKind === 2) eyes = `<circle cx="20" cy="21.5" r="5.2" fill="#fff" stroke="${deep}" stroke-width=".8"/><circle cx="${20 + px}" cy="22" r="2.5" fill="${pupil}"/><circle cx="${21 + px}" cy="21" r=".85" fill="#fff"/>`;
  else { const r = eyeKind ? 4.1 : 3.5;
    eyes = [15, 25].map(x => `<circle cx="${x}" cy="22" r="${r}" fill="#fff" stroke="${deep}" stroke-width=".7"/><circle cx="${x + px}" cy="22.6" r="${(r * .5).toFixed(2)}" fill="${pupil}"/><circle cx="${x + px + .7}" cy="21.7" r=".6" fill="#fff"/>`).join(""); }
  if (mood === "sad" && !gone) eyes += `<path d="M11.5 16.5l5 1.6M28.5 16.5l-5 1.6" stroke="${deep}" stroke-width="1.2" stroke-linecap="round"/>`;
  const ms = `fill="none" stroke="${deep}" stroke-width="1.5" stroke-linecap="round"`;
  const mouth = { happy: `<path d="M15.5 28.2Q20 33.5 24.5 28.2" ${ms}/><path d="M16.8 29.3Q20 32 23.2 29.3z" fill="#E86A6A" opacity=".55"/>`,
    sad: `<path d="M16.5 31.2Q20 27.6 23.5 31.2" ${ms}/>`, ok: `<path d="M17.2 29.4Q20 31.2 22.8 29.4" ${ms}/>`, gone: `<path d="M18 30.2h4" ${ms}/>` }[mood];
  const cheeks = gone ? "" : `<ellipse cx="11.3" cy="27.3" rx="2.3" ry="1.4" fill="#ff7a8a" opacity="${mood === "happy" ? .6 : .35}"/><ellipse cx="28.7" cy="27.3" rx="2.3" ry="1.4" fill="#ff7a8a" opacity="${mood === "happy" ? .6 : .35}"/>`;
  const sweat = mood === "sad" ? `<path d="M31.5 15.5q1.8 3 0 4.2q-1.8-1.2 0-4.2z" fill="#7FC4FF"/>` : "";
  const zz = gone ? `<text x="29" y="9" font-size="7" font-family="sans-serif" fill="${deep}">z</text><text x="33" y="5" font-size="5" font-family="sans-serif" fill="${deep}">z</text>` : "";
  const feet = `<ellipse cx="14.2" cy="37.3" rx="3.8" ry="2" fill="${deep}"/><ellipse cx="25.8" cy="37.3" rx="3.8" ry="2" fill="${deep}"/>`;
  const belly2 = `<ellipse cx="20" cy="31.5" rx="7" ry="4.6" fill="${belly}"/>`;
  const acc = `<g transform="translate(0 ${top - 10})">${accessory(a.cls, deep, body, eyeKind)}</g>`;
  return `<symbol id="m${a.n}-${mood}" viewBox="-2 -2 44 44">${feet}${b}${belly2}${eyes}${cheeks}${mouth}${sweat}${zz}${acc}</symbol>`;
}

// one hidden <svg> holding every agent's symbols; mascot() references them
export { mascotSymbol };
export function buildSprite(S, dark = false) {
  let el = document.getElementById("run-sprite");
  if (!el) { el = document.createElementNS("http://www.w3.org/2000/svg", "svg"); el.id = "run-sprite";
    el.setAttribute("width", "0"); el.setAttribute("height", "0"); el.style.position = "absolute"; document.body.prepend(el); }
  el.innerHTML = "<defs>" + S.agents.map((a) => MOODS.map((m) => mascotSymbol(a, m, dark)).join("")).join("") +
    `<symbol id="m-anon" viewBox="-2 -2 44 44"><path d="M20 10C30 10 33 20 33 28C33 34 28 37 20 37C12 37 7 34 7 28C7 20 10 10 20 10Z" fill="#8a8890" stroke="#55545b" stroke-width="1.3"/><path d="M10 20q10-6 20 0v4q-10-4-20 0z" fill="#2b2a28"/><circle cx="15" cy="22" r="1.5" fill="#fff"/><circle cx="25" cy="22" r="1.5" fill="#fff"/><text x="20" y="34" text-anchor="middle" font-size="9" font-family="sans-serif" fill="#fff">?</text></symbol></defs>`;
}
export function agentColor(a, kind = "ink", dark = false) {
  if (!a) return kind === "ink" ? "var(--muted)" : "var(--surface-2)";
  const h = a.hue;
  return { ink: dark ? `hsl(${h} 70% 72%)` : `hsl(${h} 58% 34%)`, solid: `hsl(${h} 55% ${dark ? 52 : 46}%)`,
    tint: dark ? `hsl(${h} 30% 20%)` : `hsl(${h} 45% 93%)` }[kind];
}
