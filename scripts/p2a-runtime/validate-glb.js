"use strict";

const fs = require("node:fs");
const validator = require("gltf-validator");

function fail(message) {
  process.stderr.write(`${message}\n`);
  process.exit(2);
}

async function main() {
  if (process.argv.length !== 2) {
    fail("GLB bytes must be provided only on standard input");
  }
  const payload = fs.readFileSync(0);
  let report;
  try {
    report = await validator.validateBytes(new Uint8Array(payload), {
      externalResourceFunction: async () => Buffer.alloc(0),
      maxIssues: 10000,
    });
  } catch (error) {
    if (typeof error !== "string") throw error;
    report = {
      issues: {
        numErrors: 1,
        numWarnings: 0,
        numInfos: 0,
        numHints: 0,
        messages: [{ severity: 0, code: "INVALID_CONTAINER" }],
        truncated: false,
      },
    };
  }
  const messages = Array.isArray(report.issues && report.issues.messages)
    ? report.issues.messages
    : [];
  const severityCounts = { errors: 0, warnings: 0, infos: 0, hints: 0 };
  const codeCounts = {};
  const errorCodeCounts = {};
  for (const message of messages) {
    const severity = Number(message.severity);
    if (severity === 0) severityCounts.errors += 1;
    else if (severity === 1) severityCounts.warnings += 1;
    else if (severity === 2) severityCounts.infos += 1;
    else if (severity === 3) severityCounts.hints += 1;
    const code = typeof message.code === "string" ? message.code : "UNKNOWN";
    codeCounts[code] = (codeCounts[code] || 0) + 1;
    if (severity === 0) {
      errorCodeCounts[code] = (errorCodeCounts[code] || 0) + 1;
    }
  }
  const result = {
    validator: "KhronosGroup/glTF-Validator",
    version:
      typeof validator.version === "function"
        ? String(validator.version())
        : String(validator.version || "unknown"),
    validatedAt: null,
    numErrors: Number(report.issues && report.issues.numErrors) || 0,
    numWarnings: Number(report.issues && report.issues.numWarnings) || 0,
    numInfos: Number(report.issues && report.issues.numInfos) || 0,
    numHints: Number(report.issues && report.issues.numHints) || 0,
    severityCounts,
    codeCounts: Object.fromEntries(Object.entries(codeCounts).sort()),
    errorCodeCounts: Object.fromEntries(Object.entries(errorCodeCounts).sort()),
    truncated: Boolean(report.issues && report.issues.truncated),
  };
  process.stdout.write(`${JSON.stringify(result)}\n`);
}

main().catch((error) => fail(`validator failed: ${error && error.name ? error.name : "Error"}`));
