"use strict";

import crypto from "node:crypto";
import fs from "node:fs";
// Import the exact installed file. Package export maps are metadata controlled
// by package.json and must not be able to redirect the locked witness runtime.
import Module from "./node_modules/manifold-3d/manifold.js";

const MAX_TRIANGLES = 1_000_000;
const MAX_VERTICES = 3_000_000;
const EXPECTED_FIELDS = new Set([
  "canonical_mesh_sha256",
  "profile",
  "schema",
  "schema_version",
  "triangles",
  "vertices",
]);
const EXPECTED_PROFILE = {
  child_address_space_bytes: 12884901888,
  child_output_bytes: 1048576,
  child_timeout_seconds: 180,
  manifold_operations: ["CONSTRUCT", "STATUS", "GET_MESH"],
  max_triangles: MAX_TRIANGLES,
  max_vertices: MAX_VERTICES,
  merge_vectors: "FORBIDDEN",
  node_max_old_space_mib: 1024,
  repair: "FORBIDDEN",
  simplification: "FORBIDDEN",
  tolerance: 0,
};

function fail(message) {
  process.stderr.write(`${message}\n`);
  process.exit(2);
}

function sha256(payload) {
  return crypto.createHash("sha256").update(payload).digest("hex");
}

function equalObject(first, second) {
  return JSON.stringify(first) === JSON.stringify(second);
}

function float32Hex(value) {
  const bytes = Buffer.allocUnsafe(4);
  bytes.writeFloatLE(value, 0);
  return bytes.toString("hex");
}

function vertexKey(values, offset) {
  return [
    float32Hex(values[offset]),
    float32Hex(values[offset + 1]),
    float32Hex(values[offset + 2]),
  ].join("");
}

function rotateFace(keys) {
  const rotations = [
    [keys[0], keys[1], keys[2]],
    [keys[1], keys[2], keys[0]],
    [keys[2], keys[0], keys[1]],
  ];
  rotations.sort((a, b) => a.join(":").localeCompare(b.join(":")));
  return rotations[0];
}

function topologyDigest(properties, numProp, triangles) {
  const keys = [];
  for (let offset = 0; offset < properties.length; offset += numProp) {
    keys.push(vertexKey(properties, offset));
  }
  const unique = new Set(keys);
  const faces = [];
  for (let offset = 0; offset < triangles.length; offset += 3) {
    const face = rotateFace([
      keys[triangles[offset]],
      keys[triangles[offset + 1]],
      keys[triangles[offset + 2]],
    ]);
    faces.push(face.join(":"));
  }
  faces.sort();
  const vertices = Array.from(unique).sort();
  return {
    digest: sha256(JSON.stringify({ faces, vertices })),
    duplicate_vertex_count: keys.length - unique.size,
    face_count: faces.length,
    vertex_count: vertices.length,
  };
}

function validateInput(value) {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    fail("witness input must be an object");
  }
  const fields = Object.keys(value);
  if (fields.length !== EXPECTED_FIELDS.size || fields.some((field) => !EXPECTED_FIELDS.has(field))) {
    fail("witness input fields differ from the closed contract");
  }
  if (value.schema !== "MVX-P2B-MANIFOLD-WITNESS-INPUT" || value.schema_version !== "0.1.0") {
    fail("witness input schema is invalid");
  }
  if (typeof value.canonical_mesh_sha256 !== "string" || !/^[0-9a-f]{64}$/.test(value.canonical_mesh_sha256)) {
    fail("canonical mesh commitment is invalid");
  }
  if (!equalObject(value.profile, EXPECTED_PROFILE)) {
    fail("witness profile differs from the locked profile");
  }
  if (!Array.isArray(value.vertices) || !Array.isArray(value.triangles)) {
    fail("vertices and triangles must be arrays");
  }
  if (value.vertices.length > MAX_VERTICES || value.triangles.length > MAX_TRIANGLES) {
    return "RESOURCE_LIMIT";
  }
  if (value.vertices.length === 0 || value.triangles.length === 0) {
    return "EMPTY";
  }
  for (const vertex of value.vertices) {
    if (!Array.isArray(vertex) || vertex.length !== 3 || vertex.some((item) => typeof item !== "number" || !Number.isFinite(item))) {
      fail("vertex coordinates must be finite triples");
    }
  }
  for (const triangle of value.triangles) {
    if (!Array.isArray(triangle) || triangle.length !== 3) {
      fail("triangles must contain index triples");
    }
    for (const index of triangle) {
      if (!Number.isSafeInteger(index) || index < 0 || index >= value.vertices.length) {
        fail("triangle index is out of bounds");
      }
    }
  }
  return "READY";
}

async function main() {
  if (process.argv.length !== 2) {
    fail("witness input must be provided only on standard input");
  }
  let value;
  try {
    value = JSON.parse(fs.readFileSync(0, "utf8"));
  } catch {
    fail("witness input is not valid UTF-8 JSON");
  }
  const validation = validateInput(value);
  if (validation === "RESOURCE_LIMIT") {
    process.stdout.write(`${JSON.stringify({
      canonical_mesh_sha256: value.canonical_mesh_sha256,
      diagnostic: "DECLARED_TRIANGLE_OR_VERTEX_BOUND_REACHED",
      manifold_status: null,
      output_mesh: null,
      schema: "MVX-P2B-MANIFOLD-WITNESS-RESULT",
      schema_version: "0.1.0",
      status: "RESOURCE_LIMIT",
    })}\n`);
    return;
  }
  if (validation === "EMPTY") {
    process.stdout.write(`${JSON.stringify({
      canonical_mesh_sha256: value.canonical_mesh_sha256,
      diagnostic: "EMPTY_CANONICAL_SURFACE_FORBIDDEN",
      manifold_status: null,
      output_mesh: null,
      schema: "MVX-P2B-MANIFOLD-WITNESS-RESULT",
      schema_version: "0.1.0",
      status: "ERROR",
    })}\n`);
    return;
  }

  const flatVertices = new Float32Array(value.vertices.length * 3);
  for (let index = 0; index < value.vertices.length; index += 1) {
    flatVertices.set(value.vertices[index], index * 3);
  }
  const flatTriangles = new Uint32Array(value.triangles.length * 3);
  for (let index = 0; index < value.triangles.length; index += 1) {
    flatTriangles.set(value.triangles[index], index * 3);
  }
  const inputTopology = topologyDigest(flatVertices, 3, flatTriangles);
  if (inputTopology.duplicate_vertex_count !== 0) {
    process.stdout.write(`${JSON.stringify({
      canonical_mesh_sha256: value.canonical_mesh_sha256,
      diagnostic: "BINARY64_VERTICES_COLLIDE_AFTER_REQUIRED_FLOAT32_CONVERSION",
      manifold_status: null,
      output_mesh: {
        input_topology_sha256: inputTopology.digest,
        input_triangle_count: value.triangles.length,
        input_vertex_count: value.vertices.length,
        output_topology_sha256: null,
        output_triangle_count: null,
        output_vertex_count: null,
      },
      schema: "MVX-P2B-MANIFOLD-WITNESS-RESULT",
      schema_version: "0.1.0",
      status: "MANIFOLD_DISCREPANCY",
    })}\n`);
    return;
  }

  const module = await Module();
  module.setup();
  const mesh = new module.Mesh({
    numProp: 3,
    tolerance: 0,
    triVerts: flatTriangles,
    vertProperties: flatVertices,
  });
  let manifold;
  let output;
  try {
    manifold = new module.Manifold(mesh);
    const manifoldStatus = String(manifold.status());
    const outputMesh = manifold.getMesh();
    const outputTopology = topologyDigest(
      outputMesh.vertProperties,
      outputMesh.numProp,
      outputMesh.triVerts,
    );
    const unchanged =
      manifoldStatus === "NoError" &&
      manifold.numTri() === value.triangles.length &&
      manifold.numVert() === value.vertices.length &&
      outputTopology.face_count === value.triangles.length &&
      outputTopology.vertex_count === value.vertices.length &&
      outputTopology.duplicate_vertex_count === 0 &&
      outputTopology.digest === inputTopology.digest &&
      outputMesh.mergeFromVert.length === 0 &&
      outputMesh.mergeToVert.length === 0;
    output = {
      canonical_mesh_sha256: value.canonical_mesh_sha256,
      diagnostic: unchanged
        ? "MANIFOLD_ACCEPTED_WITHOUT_OBSERVABLE_TOPOLOGY_CHANGE"
        : "MANIFOLD_REJECTED_OR_CHANGED_CANONICAL_TOPOLOGY",
      manifold_status: manifoldStatus,
      output_mesh: {
        input_topology_sha256: inputTopology.digest,
        input_triangle_count: value.triangles.length,
        input_vertex_count: value.vertices.length,
        output_topology_sha256: outputTopology.digest,
        output_triangle_count: manifold.numTri(),
        output_vertex_count: manifold.numVert(),
      },
      schema: "MVX-P2B-MANIFOLD-WITNESS-RESULT",
      schema_version: "0.1.0",
      status: unchanged ? "MANIFOLD_CORROBORATED" : "MANIFOLD_DISCREPANCY",
    };
  } catch (error) {
    if (!error || typeof error.code !== "string") throw error;
    output = {
      canonical_mesh_sha256: value.canonical_mesh_sha256,
      diagnostic: "MANIFOLD_CONSTRUCTOR_REJECTED_CANONICAL_TOPOLOGY",
      manifold_status: error.code,
      output_mesh: {
        input_topology_sha256: inputTopology.digest,
        input_triangle_count: value.triangles.length,
        input_vertex_count: value.vertices.length,
        output_topology_sha256: null,
        output_triangle_count: null,
        output_vertex_count: null,
      },
      schema: "MVX-P2B-MANIFOLD-WITNESS-RESULT",
      schema_version: "0.1.0",
      status: "MANIFOLD_DISCREPANCY",
    };
  } finally {
    if (manifold) manifold.delete();
  }
  process.stdout.write(`${JSON.stringify(output)}\n`);
}

main().catch((error) => fail(`manifold witness failed: ${error && error.name ? error.name : "Error"}`));
