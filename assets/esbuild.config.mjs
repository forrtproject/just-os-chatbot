import * as esbuild from "esbuild";
import copyStaticFiles from "esbuild-copy-static-files";

let minify = false;
let sourcemap = true;
let watch = true;

if (process.env.NODE_ENV === "production") {
  minify = true;
  sourcemap = false;
  watch = false;
}

// JS (with DOMPurify and marked) and the vendor CSS (icons, Roboto Mono) from node_modules:
// public/js/*.js, public/css/vendor.css and the font files in public/fonts/
const config = {
  entryPoints: {
    "js/app": "./js/app.js",
    "js/arena": "./js/arena.js",
    "css/vendor": "./css/vendor.css",
  },
  outdir: "../public",
  bundle: true,
  loader: { ".woff2": "file", ".woff": "file", ".ttf": "file" },
  assetNames: "fonts/[name]-[hash]",
  minify: minify,
  sourcemap: sourcemap,
  plugins: [copyStaticFiles()],
};

if (watch) {
  let context = await esbuild.context({ ...config, logLevel: "info" });
  await context.watch();
} else {
  await esbuild.build(config);
}
