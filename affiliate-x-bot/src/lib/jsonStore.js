import fs from 'node:fs';
import path from 'node:path';

export function loadJson(filePath, fallback = {}) {
  try {
    return JSON.parse(fs.readFileSync(path.resolve(filePath), 'utf-8'));
  } catch {
    return fallback;
  }
}

export function saveJson(filePath, data) {
  const resolved = path.resolve(filePath);
  fs.mkdirSync(path.dirname(resolved), { recursive: true });
  fs.writeFileSync(resolved, JSON.stringify(data, null, 2) + '\n');
}
