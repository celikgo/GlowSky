/// <reference types="vitest/globals" />
// Merges @testing-library/jest-dom's matchers (toBeInTheDocument, …) into vitest's `expect`
// types across the project, so test files type-check under the build's `tsc --noEmit`.
import "@testing-library/jest-dom/vitest";
