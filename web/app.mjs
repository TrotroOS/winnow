import express from "express";
import { loadSnapshot } from "./load-snapshot.mjs";
import { renderPage } from "./render.mjs";

/** @returns {import("express").Express} */
export function createApp() {
  const app = express();

  app.get("/health", (_req, res) => {
    res.type("text/plain").send("ok");
  });

  app.get("/demo-snapshot.json", (_req, res) => {
    res.json(loadSnapshot());
  });

  app.get("/", (_req, res) => {
    const html = renderPage(loadSnapshot());
    res.type("html").send(html);
  });

  app.get("*", (_req, res) => {
    res.status(404).type("text/plain").send("not found");
  });

  return app;
}