import { existsSync } from "node:fs";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";
import { createApp } from "./web/app.mjs";

const root = join(dirname(fileURLToPath(import.meta.url)));
const snapshot = join(root, "public", "demo-snapshot.json");
if (!existsSync(snapshot)) {
  console.error(
    "Missing public/demo-snapshot.json — run: npm run build  (needs git pull on main)",
  );
  process.exit(1);
}

const app = createApp();
const port = Number(process.env.PORT) || 3000;
const host = process.env.HOST || "127.0.0.1";

const server = app.listen(port, host, () => {
  console.log(`winnow web listening on http://${host}:${port}/`);
  console.log("Leave this terminal open while you use the browser.");
});

server.on("error", (err) => {
  if (err.code === "EADDRINUSE") {
    console.error(`Port ${port} is already in use. Try: PORT=3001 npm run dev`);
    process.exit(1);
  }
  throw err;
});