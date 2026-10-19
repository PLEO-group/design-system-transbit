#!/usr/bin/env node

import fs from "node:fs";
import path from "node:path";
import process from "node:process";
import { fileURLToPath } from "node:url";

const scriptDir = path.dirname(fileURLToPath(import.meta.url));
const skillDir = path.resolve(scriptDir, "..");
const agentsDir = path.join(skillDir, "agents");
const fullModePath = path.join(skillDir, "extended", "full-mode.md");
const snippetsPath = path.join(skillDir, "references", "instruction-snippets.md");
const skillPath = path.join(skillDir, "SKILL.md");
const allowedStatuses = new Set(["ga", "preview", "restricted", "deprecated"]);
const staleAfterDays = 14;
const officialDomains = {
  claude: ["anthropic.com", "claude.com"],
  gemini: ["google.com", "google.dev"],
  openai: ["openai.com"],
};
const errors = [];

function read(filePath) {
  return fs.readFileSync(filePath, "utf8");
}

function fail(filePath, message) {
  errors.push(`${path.relative(skillDir, filePath)}: ${message}`);
}

function scalar(text, key) {
  const match = text.match(new RegExp(`^\\s{2}${key}:\\s*["']?([^"'\\n]+)["']?\\s*$`, "m"));
  return match?.[1]?.trim();
}

function section(text, key) {
  const lines = text.split(/\r?\n/);
  const start = lines.findIndex((line) => line === `  ${key}:`);
  if (start < 0) return [];

  const result = [];
  for (let index = start + 1; index < lines.length; index += 1) {
    const line = lines[index];
    if (/^  \S/.test(line)) break;
    if (line.trim()) result.push(line);
  }
  return result;
}

function mapping(text, key) {
  const result = new Map();
  for (const line of section(text, key)) {
    const match = line.match(/^    ([^:]+):\s*["']?([^"'\n]+)["']?\s*$/);
    if (match) result.set(match[1].trim(), match[2].trim());
  }
  return result;
}

function tierModels(text) {
  const models = new Set();
  for (const line of section(text, "tier_map")) {
    const match = line.match(/^    (cheap|balanced|deep|max):\s*\[(.*)]\s*$/);
    if (!match) continue;
    for (const value of match[2].split(",")) {
      const model = value.trim().replace(/^['"]|['"]$/g, "");
      if (model) models.add(model);
    }
  }
  return models;
}

function pricing(text) {
  const result = new Map();
  let currentModel;
  for (const line of section(text, "pricing_estimates")) {
    const model = line.match(/^    ([^:]+):\s*$/);
    if (model) {
      currentModel = model[1].trim();
      result.set(currentModel, new Map());
      continue;
    }

    const field = line.match(/^      ([^:]+):\s*["']?([^"'\n]+)["']?\s*$/);
    if (field && currentModel) result.get(currentModel).set(field[1].trim(), field[2].trim());
  }
  return result;
}

function reasoningModels(text) {
  return new Set(
    section(text, "reasoning_levels")
      .map((line) => line.match(/^    ([^:]+):/u)?.[1]?.trim())
      .filter(Boolean),
  );
}

function inlineList(text, key) {
  const match = text.match(new RegExp(`^\\s{2}${key}:\\s*\\[(.*)]\\s*$`, "m"));
  if (!match) return [];
  return match[1]
    .split(",")
    .map((value) => value.trim().replace(/^['"]|['"]$/g, ""))
    .filter(Boolean);
}

function markdownRows(text, model) {
  return text
    .split(/\r?\n/)
    .filter((line) => line.startsWith("|") && line.includes(model))
    .join("\n");
}

function normalizedPrice(value) {
  const number = Number(value);
  return Number.isFinite(number) ? `$${number.toFixed(2)}` : undefined;
}

function frontmatterVersion(text) {
  return text.match(/^version:\s*([^\s]+)\s*$/m)?.[1];
}

const skillText = read(skillPath);
const fullModeText = read(fullModePath);
const snippetsText = read(snippetsPath);
const version = frontmatterVersion(skillText);

if (!version) fail(skillPath, "brak version w frontmatter");
if (!fullModeText.includes(`WERSJA ${version}`) || !fullModeText.includes(`SKILL.md ${version}`))
  fail(fullModePath, `wersja nie jest zsynchronizowana z SKILL.md ${version}`);
if (!snippetsText.includes(`WERSJA ${version}`) || !snippetsText.includes(`SKILL.md ${version}`))
  fail(snippetsPath, `wersja nie jest zsynchronizowana z SKILL.md ${version}`);

for (const fileName of fs.readdirSync(agentsDir).filter((name) => name.endsWith(".yaml")).sort()) {
  const agentPath = path.join(agentsDir, fileName);
  const agentText = read(agentPath);
  const provider = scalar(agentText, "name");
  const verifiedOn = scalar(agentText, "catalog_verified_on");
  const reference = scalar(agentText, "reference");
  const defaultModel = scalar(agentText, "default_model");
  const models = tierModels(agentText);
  const prices = pricing(agentText);
  const statuses = mapping(agentText, "model_status");
  const perModelReasoning = reasoningModels(agentText);
  const globalReasoning = inlineList(agentText, "reasoning_levels");
  const aliases = mapping(agentText, "aliases");

  if (!provider || !officialDomains[provider]) {
    fail(agentPath, `nieobsługiwany provider: ${provider ?? "brak"}`);
    continue;
  }
  if (!verifiedOn || !/^\d{4}-\d{2}-\d{2}$/.test(verifiedOn))
    fail(agentPath, "catalog_verified_on musi mieć format YYYY-MM-DD");
  if (!reference) {
    fail(agentPath, "brak reference");
    continue;
  }

  const referencePath = path.join(skillDir, reference);
  if (!fs.existsSync(referencePath)) {
    fail(agentPath, `reference nie istnieje: ${reference}`);
    continue;
  }

  const referenceText = read(referencePath);
  const docDate = referenceText.match(/`doc_date`:\s*`?(\d{4}-\d{2}-\d{2})`?/)?.[1];
  if (docDate !== verifiedOn)
    fail(referencePath, `doc_date ${docDate ?? "brak"} != catalog_verified_on ${verifiedOn ?? "brak"}`);
  if (docDate) {
    const ageInDays = Math.floor((Date.now() - Date.parse(`${docDate}T00:00:00Z`)) / 86_400_000);
    if (ageInDays < 0) fail(referencePath, `doc_date ${docDate} jest w przyszłości`);
    if (ageInDays > staleAfterDays)
      fail(referencePath, `katalog ma ${ageInDays} dni i przekracza stale_after_days=${staleAfterDays}`);
  }

  const sourceUrls = referenceText
    .split("## Źródła")[1]
    ?.match(/https:\/\/[^\s)]+/g) ?? [];
  if (sourceUrls.length === 0) fail(referencePath, "brak oficjalnych URL-i w sekcji Źródła");
  for (const sourceUrl of sourceUrls) {
    const hostname = new URL(sourceUrl).hostname;
    if (!officialDomains[provider].some((domain) => hostname === domain || hostname.endsWith(`.${domain}`)))
      fail(referencePath, `źródło spoza oficjalnej domeny providera: ${sourceUrl}`);
  }

  if (models.size === 0) fail(agentPath, "tier_map nie zawiera modeli");
  if (!models.has(defaultModel)) fail(agentPath, `default_model ${defaultModel ?? "brak"} nie występuje w tier_map`);
  if (perModelReasoning.size === 0 && globalReasoning.length === 0)
    fail(agentPath, "reasoning_levels nie zawiera poziomów");
  if (!/^  aliases:/m.test(agentText)) fail(agentPath, "brak jawnego pola aliases");

  for (const [alias, target] of aliases) {
    if (!models.has(target)) fail(agentPath, `alias ${alias} wskazuje model spoza tier_map: ${target}`);
    if (!referenceText.includes(`\`${alias}\``) || !referenceText.includes(`\`${target}\``))
      fail(referencePath, `alias ${alias} -> ${target} nie jest udokumentowany`);
  }

  for (const model of models) {
    if (!referenceText.includes(`\`${model}\``)) fail(referencePath, `brak modelu ${model}`);
    if (!fullModeText.includes(model)) fail(fullModePath, `brak modelu ${model}`);
    if (!prices.has(model)) fail(agentPath, `brak pricing_estimates dla ${model}`);
    if (!statuses.has(model) || !allowedStatuses.has(statuses.get(model)?.toLowerCase()))
      fail(agentPath, `brak poprawnego model_status dla ${model}`);
    const catalogLine = referenceText.split(/\r?\n/).find((line) => line.includes(`\`${model}\``));
    if (catalogLine && !catalogLine.toLowerCase().includes(`status \`${statuses.get(model)?.toLowerCase()}\``))
      fail(referencePath, `${model}: status ${statuses.get(model)} nie jest jawnie zsynchronizowany`);

    if (perModelReasoning.size > 0 && !perModelReasoning.has(model))
      fail(agentPath, `brak reasoning_levels dla ${model}`);
    const reasoningLevels = perModelReasoning.has(model)
      ? section(agentText, "reasoning_levels")
          .find((line) => line.startsWith(`    ${model}:`))
          ?.match(/\[(.*)]/)?.[1]
          ?.split(",")
          ?.map((value) => value.trim().replace(/^['"]|['"]$/g, "")) ?? []
      : globalReasoning;
    for (const level of reasoningLevels) {
      if (!referenceText.includes(`\`${level}\``))
        fail(referencePath, `${model}: reasoning level ${level} z YAML nie występuje w reference`);
    }

    const referenceRows = markdownRows(referenceText, model);
    const fullModeRows = markdownRows(fullModeText, model);
    for (const [field, value] of prices.get(model) ?? []) {
      if (!field.includes("input_per_1m") && !field.includes("output_per_1m")) continue;
      const formatted = normalizedPrice(value);
      if (formatted && !referenceRows.includes(formatted))
        fail(referencePath, `${model}: cena ${field}=${formatted} nie występuje w tabeli`);
      if (formatted && !fullModeRows.includes(formatted))
        fail(fullModePath, `${model}: cena ${field}=${formatted} nie występuje w tabeli`);
    }

    for (const [field, value] of prices.get(model) ?? []) {
      if (!field.includes("through")) continue;
      if (!referenceText.includes(value) || !fullModeText.includes(value))
        fail(agentPath, `${model}: data ${field}=${value} nie jest zsynchronizowana w reference i Full Mode`);
    }
  }
}

if (errors.length > 0) {
  console.error(`Model catalog validation failed (${errors.length}):`);
  for (const error of errors) console.error(`- ${error}`);
  process.exit(1);
}

console.log(`Model catalog validation passed for version ${version}.`);
