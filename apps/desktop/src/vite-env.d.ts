/// <reference types="vite/client" />

// 3Dmol ships types for its main entry but not the ESM build path we lazy-import.
declare module "3dmol/build/3Dmol.es6.js";
