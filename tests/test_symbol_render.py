import json
from pathlib import Path
import shutil
import subprocess
import textwrap

import pytest


def test_logic_symbol_bubbles_stay_small():
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is required for symbol renderer smoke test")

    script = textwrap.dedent(
        r"""
        const fs = require("fs");
        const vm = require("vm");
        const { pathToFileURL } = require("url");

        function bubbleRadii(svg) {
          return [...svg.matchAll(/<circle class="bub"[^>]* r="([^"]+)"/g)]
            .map((m) => Number(m[1]));
        }

        function outputBubbleCount(svg) {
          const bubbles = [...svg.matchAll(/<circle class="bub"[^>]* cx="([^"]+)" cy="([^"]+)" r="([^"]+)"/g)]
            .map((m) => ({ cx: Number(m[1]), cy: Number(m[2]), r: Number(m[3]) }));
          const wires = [...svg.matchAll(/<path class="wire" d="M([^,]+),([^ ]+) L([^,]+),([^"]+)"/g)]
            .map((m) => ({ x1: Number(m[1]), y1: Number(m[2]), x2: Number(m[3]), y2: Number(m[4]) }));
          const same = (a, b) => Math.abs(a - b) < 1e-6;
          return bubbles.filter((bubble) =>
            wires.some((wire) =>
              same(wire.y1, bubble.cy) &&
              same(wire.x1, bubble.cx + bubble.r) &&
              wire.x2 > wire.x1
            )
          ).length;
        }

        const cases = ["!(A&B)", "!(A+B)", "!A + !B", "!(A&B&C)"];
        const outputPreferred = "!(A&B) + C";
        const source = fs.readFileSync("viewer/static/symbol.js", "utf8");
        const context = { window: {} };
        vm.runInNewContext(source, context);
        const viewer = cases.map((expr) => ({
          expr,
          radii: bubbleRadii(context.window.functionToSvg(
            expr,
            "Y",
            { minWidthRatio: 0.5, dots: false, demorgan: true, fitHeight: [90, 280] }
          )),
        }));
        const viewerOutputPreferred = outputBubbleCount(context.window.functionToSvg(
          outputPreferred,
          "Y",
          { minWidthRatio: 0.5, dots: false, demorgan: true, fitHeight: [90, 280] }
        ));

        (async () => {
          const root = process.cwd();
          const [{ parse }, { lower, demorgan }, { layout }, { render }] = await Promise.all([
            import(pathToFileURL(root + "/logic2svg/src/parse.js")),
            import(pathToFileURL(root + "/logic2svg/src/lower.js")),
            import(pathToFileURL(root + "/logic2svg/src/layout.js")),
            import(pathToFileURL(root + "/logic2svg/src/render.js")),
          ]);
          const logic2svg = cases.map((expr) => ({
            expr,
            radii: bubbleRadii(render(layout(demorgan(lower(parse(expr))), { minWidthRatio: 0.5 }))),
          }));
          const logic2svgOutputPreferred = outputBubbleCount(render(layout(
            demorgan(lower(parse(outputPreferred))),
            { minWidthRatio: 0.5 }
          )));
          console.log(JSON.stringify({
            viewer,
            logic2svg,
            outputPreferred: {
              viewer: viewerOutputPreferred,
              logic2svg: logic2svgOutputPreferred,
            },
          }));
        })().catch((err) => {
          console.error(err && err.stack ? err.stack : err);
          process.exit(1);
        });
        """
    )
    result = subprocess.run(
        [node, "-e", script],
        cwd=Path(__file__).resolve().parents[1],
        check=True,
        text=True,
        capture_output=True,
    )
    rendered = json.loads(result.stdout)

    for renderer_cases in (rendered["viewer"], rendered["logic2svg"]):
        for case in renderer_cases:
            assert case["radii"], case["expr"]
            assert max(case["radii"]) <= 4, case

    assert rendered["outputPreferred"] == {"viewer": 1, "logic2svg": 1}
