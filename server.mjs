import { createApp } from "./web/app.mjs";

const app = createApp();
const port = Number(process.env.PORT) || 3000;

app.listen(port, () => {
  console.log(`winnow web listening on http://127.0.0.1:${port}`);
});