"use strict";

const fs = require("fs");
const path = require("path");
const { spawnSync } = require("child_process");
const readline = require("readline");

const REPO = path.resolve(process.env.TRADYSQUID_REPO || "");
const CONTROL = path.resolve(process.env.TRADYSQUID_CONTROL || "");
const LEARNING = path.resolve(process.env.TRADYSQUID_LEARNING || "");
const BLOCKED_NAMES = new Set([".env", ".env.local", ".git"]);
const MAX_TEXT = 200000;

function text(value) {
  return { content: [{ type: "text", text: String(value) }] };
}

function fail(message) {
  return { isError: true, content: [{ type: "text", text: String(message) }] };
}

function run(command, args, options = {}) {
  const result = spawnSync(command, args, {
    cwd: options.cwd || REPO,
    encoding: "utf8",
    windowsHide: true,
    timeout: options.timeout || 120000,
    shell: false,
  });
  if (result.error) throw result.error;
  if (result.status !== 0 && !options.allowFailure) {
    throw new Error((result.stderr || result.stdout || `${command} failed`).trim());
  }
  return {
    status: result.status,
    stdout: (result.stdout || "").trimEnd(),
    stderr: (result.stderr || "").trimEnd(),
  };
}

function ensureConfigured() {
  for (const [label, target] of [["repository", REPO], ["control", CONTROL], ["learning", LEARNING]]) {
    if (!target || !fs.existsSync(target)) throw new Error(`${label} path is missing: ${target}`);
  }
}

function within(root, requested) {
  const resolved = path.resolve(root, requested || ".");
  const relative = path.relative(root, resolved);
  if (relative.startsWith("..") || path.isAbsolute(relative)) {
    throw new Error("Path is outside the approved folder.");
  }
  return resolved;
}

function safeRepoFile(requested, forWrite = false) {
  const target = within(REPO, requested);
  const relative = path.relative(REPO, target);
  const parts = relative.split(path.sep);
  if (parts.some((part) => BLOCKED_NAMES.has(part.toLowerCase()))) {
    throw new Error("Secrets and Git internals are not available to this extension.");
  }
  if (forWrite && relative.startsWith(`state${path.sep}`)) {
    throw new Error("Runtime state files cannot be edited through Claude.");
  }
  return target;
}

function requireClaudeLock() {
  const lockPath = path.join(CONTROL, "UPDATE_LOCK.json");
  if (!fs.existsSync(lockPath)) throw new Error("Acquire the shared update lock before modifying files.");
  const lock = JSON.parse(fs.readFileSync(lockPath, "utf8"));
  if (String(lock.actor || "").toLowerCase() !== "claude") {
    throw new Error(`The shared lock belongs to ${lock.actor || "another actor"}.`);
  }
  return lock;
}

function readLimited(target) {
  const stats = fs.statSync(target);
  if (!stats.isFile()) throw new Error("Requested path is not a file.");
  if (stats.size > MAX_TEXT) throw new Error("File is too large for safe text access.");
  if (target.match(/\.(png|jpg|jpeg|gif|sqlite|db|pyc|zip|mcpb)$/i)) {
    throw new Error("Binary files are not available through the text reader.");
  }
  return fs.readFileSync(target, "utf8");
}

const tools = [
  {
    name: "coordination_status",
    description: "Read shared current state, active lock, and Claude handoff before beginning work.",
    inputSchema: { type: "object", properties: {}, additionalProperties: false },
  },
  {
    name: "begin_update",
    description: "Acquire Claude's exclusive OneDrive update lock. Stop if another actor owns it.",
    inputSchema: {
      type: "object",
      properties: {
        task: { type: "string" },
        method: { type: "string" },
      },
      required: ["task", "method"],
      additionalProperties: false,
    },
  },
  {
    name: "finish_update",
    description: "Record summary, method, tests, files, and commit; then release Claude's lock.",
    inputSchema: {
      type: "object",
      properties: {
        summary: { type: "string" },
        method: { type: "string" },
        tests: { type: "string" },
        files: { type: "array", items: { type: "string" } },
        commit: { type: "string" },
      },
      required: ["summary", "method", "tests", "files"],
      additionalProperties: false,
    },
  },
  {
    name: "repo_status",
    description: "Inspect authoritative Git status, current commit, and recent commits.",
    inputSchema: { type: "object", properties: {}, additionalProperties: false },
  },
  {
    name: "read_file",
    description: "Read one safe repository text file. Secrets, Git internals, databases, and binaries are blocked.",
    inputSchema: {
      type: "object",
      properties: { file: { type: "string" } },
      required: ["file"],
      additionalProperties: false,
    },
  },
  {
    name: "search_repo",
    description: "Search safe repository text files for a literal or regular expression.",
    inputSchema: {
      type: "object",
      properties: {
        query: { type: "string" },
        regex: { type: "boolean", default: false },
      },
      required: ["query"],
      additionalProperties: false,
    },
  },
  {
    name: "replace_text",
    description: "Replace exactly one occurrence in a repository text file. Requires Claude's lock.",
    inputSchema: {
      type: "object",
      properties: {
        file: { type: "string" },
        old_text: { type: "string" },
        new_text: { type: "string" },
      },
      required: ["file", "old_text", "new_text"],
      additionalProperties: false,
    },
  },
  {
    name: "create_file",
    description: "Create a new repository text file. Refuses overwrite and requires Claude's lock.",
    inputSchema: {
      type: "object",
      properties: {
        file: { type: "string" },
        content: { type: "string" },
      },
      required: ["file", "content"],
      additionalProperties: false,
    },
  },
  {
    name: "run_tests",
    description: "Run Python syntax compilation and the full unit test suite without changing project files.",
    inputSchema: { type: "object", properties: {}, additionalProperties: false },
  },
  {
    name: "git_diff",
    description: "Show current status and diff for review before publication.",
    inputSchema: {
      type: "object",
      properties: {
        files: { type: "array", items: { type: "string" } },
      },
      additionalProperties: false,
    },
  },
  {
    name: "publish_update",
    description: "Stage only explicit files, commit with a Claude marker, and push normally to origin main. Requires Claude's lock.",
    inputSchema: {
      type: "object",
      properties: {
        files: { type: "array", items: { type: "string" } },
        message: { type: "string" },
      },
      required: ["files", "message"],
      additionalProperties: false,
    },
  },
  {
    name: "learning_report",
    description: "Read the sanitized OneDrive outcome-learning report and summary.",
    inputSchema: {
      type: "object",
      properties: {
        format: { type: "string", enum: ["report", "summary"], default: "report" },
      },
      additionalProperties: false,
    },
  },
];

function callTool(name, args) {
  ensureConfigured();
  if (name === "coordination_status") {
    const files = ["CURRENT_STATE.md", "HANDOFF_CLAUDE.md"];
    return text(files.map((file) => `## ${file}\n${readLimited(path.join(CONTROL, file))}`).join("\n"));
  }
  if (name === "begin_update") {
    const result = run("python", [
      "ai_coordination.py", "begin", "--actor", "Claude",
      "--task", args.task, "--method", args.method,
    ]);
    return text(result.stdout);
  }
  if (name === "finish_update") {
    requireClaudeLock();
    const command = [
      "ai_coordination.py", "finish", "--actor", "Claude",
      "--summary", args.summary, "--method", args.method,
      "--tests", args.tests, "--files", ...(args.files || []),
    ];
    if (args.commit) command.push("--commit", args.commit);
    return text(run("python", command).stdout);
  }
  if (name === "repo_status") {
    const output = [
      run("git", ["status", "-sb"]).stdout,
      run("git", ["log", "-8", "--oneline"]).stdout,
    ].join("\n\n");
    return text(output);
  }
  if (name === "read_file") return text(readLimited(safeRepoFile(args.file)));
  if (name === "search_repo") {
    const pattern = args.regex ? args.query : args.query.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
    const result = run("rg", [
      "-n", "--hidden", "--glob", "!.git/**", "--glob", "!.env",
      "--glob", "!state/**", pattern, ".",
    ], { allowFailure: true });
    if (result.status > 1) throw new Error(result.stderr || "Search failed.");
    return text(result.stdout || "No matches.");
  }
  if (name === "replace_text") {
    requireClaudeLock();
    const target = safeRepoFile(args.file, true);
    const original = readLimited(target);
    const first = original.indexOf(args.old_text);
    if (first < 0) throw new Error("Exact old_text was not found.");
    if (original.indexOf(args.old_text, first + args.old_text.length) >= 0) {
      throw new Error("old_text is not unique; provide more surrounding context.");
    }
    fs.writeFileSync(target, original.slice(0, first) + args.new_text + original.slice(first + args.old_text.length), "utf8");
    return text(`Updated ${args.file}.`);
  }
  if (name === "create_file") {
    requireClaudeLock();
    const target = safeRepoFile(args.file, true);
    if (fs.existsSync(target)) throw new Error("File already exists; use replace_text.");
    fs.mkdirSync(path.dirname(target), { recursive: true });
    fs.writeFileSync(target, args.content, "utf8");
    return text(`Created ${args.file}.`);
  }
  if (name === "run_tests") {
    const compile = run("python", ["-m", "compileall", "-q", "."], { timeout: 120000 });
    const tests = run("python", ["-m", "unittest", "discover", "-q"], { timeout: 120000 });
    return text(`Syntax: passed\nTests:\n${tests.stdout || tests.stderr || "passed"}`);
  }
  if (name === "git_diff") {
    const fileArgs = (args.files || []).map((file) => path.relative(REPO, safeRepoFile(file)));
    const status = run("git", ["status", "-sb"]).stdout;
    const diff = run("git", ["diff", "--", ...fileArgs]).stdout;
    return text(`${status}\n\n${diff || "No unstaged diff."}`);
  }
  if (name === "publish_update") {
    requireClaudeLock();
    if (!Array.isArray(args.files) || !args.files.length) throw new Error("Explicit files are required.");
    const files = args.files.map((file) => path.relative(REPO, safeRepoFile(file, true)));
    run("git", ["add", "--", ...files]);
    const staged = run("git", ["diff", "--cached", "--quiet", "--", ...files], { allowFailure: true });
    if (staged.status === 0) throw new Error("No staged changes to publish.");
    if (staged.status !== 1) throw new Error("Could not verify staged changes.");
    run("git", ["commit", "-m", `${args.message} [Claude]`]);
    run("git", ["push", "origin", "HEAD:main"], { timeout: 120000 });
    return text(run("git", ["rev-parse", "HEAD"]).stdout);
  }
  if (name === "learning_report") {
    const file = args.format === "summary" ? "learning_summary.json" : "learning_report.md";
    return text(readLimited(within(LEARNING, file)));
  }
  throw new Error(`Unknown tool: ${name}`);
}

function respond(id, result) {
  process.stdout.write(JSON.stringify({ jsonrpc: "2.0", id, result }) + "\n");
}

function handle(message) {
  if (!message || message.jsonrpc !== "2.0") return;
  if (message.method === "initialize") {
    respond(message.id, {
      protocolVersion: "2025-06-18",
      capabilities: { tools: { listChanged: false } },
      serverInfo: { name: "tradysquid-maintainer", version: "1.0.0" },
      instructions: "Read coordination_status before work. Acquire begin_update before every write. Preserve unrelated changes. Run tests, publish explicit files, then finish_update. Never expose secrets or execute brokerage trades.",
    });
    return;
  }
  if (message.method === "tools/list") {
    respond(message.id, { tools });
    return;
  }
  if (message.method === "tools/call") {
    try {
      respond(message.id, callTool(message.params.name, message.params.arguments || {}));
    } catch (error) {
      respond(message.id, fail(error && error.message ? error.message : error));
    }
    return;
  }
  if (message.id !== undefined && message.id !== null) respond(message.id, {});
}

ensureConfigured();
const input = readline.createInterface({ input: process.stdin, crlfDelay: Infinity });
input.on("line", (line) => {
  if (!line.trim()) return;
  try {
    handle(JSON.parse(line));
  } catch (error) {
    process.stderr.write(String(error && error.stack ? error.stack : error) + "\n");
  }
});
