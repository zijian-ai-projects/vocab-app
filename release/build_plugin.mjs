/**
 * 构建 DSH 插件发行包（开发工具，不随插件发布）。
 *
 * 用法：node release/build_plugin.mjs
 * 产物：vocab-app-releases/v1.4.3/dsh-vocab-app-<version>.tgz
 *
 * 只把白名单文件放进 `package/`，词库从 ../data 按需复制，避免在仓库里再存一份
 * 20MB 的数据；个人记录、恢复文件、测试、审计/开发文档不进包，仅随包提供用户 readme.md。
 */
import { createHash } from 'node:crypto';
import { execFileSync } from 'node:child_process';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.dirname(HERE);
const PLUGIN = path.join(ROOT, 'dsh-plugin');
const RELEASE = path.join(ROOT, 'vocab-app-releases', 'v1.4.3');
const STAGE = path.join(ROOT, '.build', 'plugin-package');
const DATA_FILES = ['bank.json', 'books.json', 'phrases.json', 'phrase_books.json', 'level_meanings.json'];
const REQUIRED = ['package.json', 'index.js', 'client.js', 'cordis.patch.yml', 'icon.svg', 'readme.md'];

function fail(message) {
  console.error('构建失败：' + message);
  process.exit(1);
}

function sha256(file) {
  return createHash('sha256').update(fs.readFileSync(file)).digest('hex');
}

function copyFile(from, to) {
  fs.mkdirSync(path.dirname(to), { recursive: true });
  fs.copyFileSync(from, to);
}

function copyTree(from, to, filter) {
  for (const entry of fs.readdirSync(from, { withFileTypes: true })) {
    const source = path.join(from, entry.name);
    const target = path.join(to, entry.name);
    if (entry.isDirectory()) {
      if (entry.name === '__pycache__' || entry.name === 'node_modules') continue;
      copyTree(source, target, filter);
    } else if (!filter || filter(source)) {
      copyFile(source, target);
    }
  }
}

const manifest = JSON.parse(fs.readFileSync(path.join(PLUGIN, 'package.json'), 'utf8'));
const version = manifest.version;
if (!/^\d+\.\d+\.\d+$/.test(version)) fail('package.json version 非法：' + version);

for (const name of REQUIRED) {
  if (!fs.existsSync(path.join(PLUGIN, name))) fail('缺少插件文件：' + name);
}
for (const name of DATA_FILES) {
  if (!fs.existsSync(path.join(ROOT, 'data', name))) fail('缺少词库文件：data/' + name);
}

fs.rmSync(STAGE, { recursive: true, force: true });
const pkg = path.join(STAGE, 'package');
fs.mkdirSync(pkg, { recursive: true });

for (const name of REQUIRED) copyFile(path.join(PLUGIN, name), path.join(pkg, name));
copyTree(path.join(PLUGIN, 'lib'), path.join(pkg, 'lib'), (file) => file.endsWith('.js'));
copyTree(path.join(PLUGIN, 'locale'), path.join(pkg, 'locale'), (file) => file.endsWith('.json'));
for (const name of DATA_FILES) copyFile(path.join(ROOT, 'data', name), path.join(pkg, 'data', name));

// 词库是运行必需资产：只读源字节复制，绝不重新生成或改写顺序。
const dataAfter = DATA_FILES.map((name) => sha256(path.join(pkg, 'data', name)));
const dataBefore = DATA_FILES.map((name) => sha256(path.join(ROOT, 'data', name)));
if (JSON.stringify(dataAfter) !== JSON.stringify(dataBefore)) fail('词库复制后哈希不一致');

fs.mkdirSync(RELEASE, { recursive: true });
const archive = path.join(RELEASE, `dsh-vocab-app-${version}.tgz`);
fs.rmSync(archive, { force: true });

// npm 兼容的 .tgz：gzip + 顶层 `package/` 前缀。Windows 自带 bsdtar 即可。
const tar = 'tar';
execFileSync(tar, ['-czf', archive, '-C', STAGE, 'package'], { stdio: 'inherit' });

const digest = sha256(archive);
const sums = path.join(RELEASE, 'SHA256SUMS.txt');
const line = `${digest}  ${path.basename(archive)}\n`;
const existing = fs.existsSync(sums) ? fs.readFileSync(sums, 'utf8') : '';
const retained = existing.split(/\r?\n/).filter((item) => {
  const fields = item.trim().split(/\s+/);
  return fields.length === 2 && fields[1] !== path.basename(archive);
});
fs.writeFileSync(sums, retained.map((item) => item + '\n').join('') + line);

const size = (fs.statSync(archive).size / (1024 * 1024)).toFixed(1);
console.log(`完成：${archive}（${size} MiB）`);
console.log(`SHA-256：${digest}`);
