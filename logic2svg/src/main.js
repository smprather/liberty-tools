import { parse } from "./parse.js";
import { lower, demorgan } from "./lower.js";
import { layout } from "./layout.js";
import { render } from "./render.js";

const inp = document.getElementById("expr");
const out = document.getElementById("out");
const err = document.getElementById("err");

export function build(text) {
  return render(layout(demorgan(lower(parse(text))), { minWidthRatio: 0.5 }));
}

function update() {
  err.textContent = "";
  try {
    out.innerHTML = build(inp.value);
  } catch (e) {
    err.textContent = e.message;
  }
}

inp.addEventListener("input", update);
document.querySelectorAll(".ex").forEach((btn) => {
  btn.onclick = () => { inp.value = btn.textContent; update(); inp.focus(); };
});
document.getElementById("download").onclick = () => {
  const svg = out.querySelector("svg");
  if (!svg) return;
  const blob = new Blob([svg.outerHTML], { type: "image/svg+xml" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = "symbol.svg";
  a.click();
  URL.revokeObjectURL(a.href);
};

inp.value = "(!s & a & en) + s & b";
update();
