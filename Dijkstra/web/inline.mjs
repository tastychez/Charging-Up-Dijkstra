// Fold the Vite build (dist/) into one HTML file that opens with a double-click,
// no server needed: ../dijkstra-demo.html
import { readFileSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const dist = join(here, "dist");
const out = join(here, "..", "dijkstra-demo.html");

let html = readFileSync(join(dist, "index.html"), "utf8");

html = html.replace(/<link rel="stylesheet"[^>]*href="\.\/([^"]+)"[^>]*>/g, (_, file) =>
  `<style>\n${readFileSync(join(dist, file), "utf8")}\n</style>`);

html = html.replace(/<script type="module"[^>]*src="\.\/([^"]+)"[^>]*><\/script>/g, (_, file) => {
  const js = readFileSync(join(dist, file), "utf8").replace(/<\/script/gi, "<\\/script");
  return `<script type="module">\n${js}\n</script>`;
});

if (/src="\.\/assets|href="\.\/assets/.test(html)) throw new Error("an asset was not inlined");
writeFileSync(out, html);
console.log(`wrote ${out} (${(html.length / 1024).toFixed(0)} kB)`);
