import { createApp } from "./App.js";

const root = document.querySelector("#app");

if (!root) {
  throw new Error("Missing #app root element");
}

createApp(root);

