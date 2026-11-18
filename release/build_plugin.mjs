/**
 * 构建 DSH 插件发行包（开发工具，不随插件发布）。
 *
 * 用法：node release/build_plugin.mjs
 * 产物：vocab-app-releases/learning-patch-20261117/dsh/dsh-vocab-app-<version>.tgz
 *
 * 只把白名单文件放进 `package/`，词库从 ../data 按需复制，避免在仓库里再存一份
 * 20MB 的数据；个人记录、恢复文件、测试、审计/开发文档不进包，仅随包提供用户 readme.md。
 * 使用版本化 staging；任何 staging/发行目标已存在都失败，不覆盖或删除历史。
 */
import { createHash } from 'node:crypto';
import { execFileSync } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.dirname(HERE);
const PLUGIN = path.join(ROOT, 'dsh-plugin');
const RELEASE = path.join(ROOT, 'vocab-app-releases', 'learning-patch-20261117', 'dsh');
const STAGE = path.join(ROOT, '.build', 'plugin-package-learning-patch-20261117');
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

function rejectLinkTree(root) {
  const info = fs.lstatSync(root);
  if (info.isSymbolicLink() || (!info.isDirectory() && !info.isFile())) fail('拒绝链接或特殊文件：' + root);
  if (!info.isDirectory()) return;
  for (const name of fs.readdirSync(root)) rejectLinkTree(path.join(root, name));
}

function copyTree(from, to, filter) {
  fs.mkdirSync(to, { recursive: true });
  for (const entry of fs.readdirSync(from, { withFileTypes: true })) {
    const source = path.join(from, entry.name);
    const target = path.join(to, entry.name);
    const info = fs.lstatSync(source);
    if (info.isSymbolicLink() || (!info.isDirectory() && !info.isFile())) fail('拒绝链接或特殊文件：' + source);
    if (entry.isDirectory()) {
      if (entry.name === '__pycache__' || entry.name === 'node_modules') continue;
      fs.mkdirSync(target, { recursive: true });
      copyTree(source, target, filter);
    } else if (!filter || filter(source)) {
      fs.copyFileSync(source, target, fs.constants.COPYFILE_EXCL);
    }
  }
}

const manifest = JSON.parse(fs.readFileSync(path.join(PLUGIN, 'package.json'), 'utf8'));
const version = manifest.version;
if (version !== '0.1.11') fail('package.json version 必须为 0.1.11：' + version);

for (const name of REQUIRED) {
  if (!fs.existsSync(path.join(PLUGIN, name))) fail('缺少插件文件：' + name);
}
for (const name of DATA_FILES) {
  if (!fs.existsSync(path.join(ROOT, 'data', name))) fail('缺少词库文件：data/' + name);
}
for (const source of [PLUGIN, path.join(PLUGIN, 'lib'), path.join(PLUGIN, 'locale'), path.join(ROOT, 'data')]) {
  rejectLinkTree(source);
}
const archive = path.join(RELEASE, `dsh-vocab-app-${version}.tgz`);
const archiveTemp = path.join(RELEASE, `dsh-vocab-app-${version}.tgz.tmp`);
const sums = path.join(RELEASE, `SHA256SUMS-v${version}.txt`);
for (const target of [STAGE, archive, archiveTemp, sums]) {
  try {
    fs.lstatSync(target);
    fail('目标已存在，拒绝覆盖：' + target);
  } catch (error) {
    if (error.code !== 'ENOENT') throw error;
  }
}
try {
  const info = fs.lstatSync(RELEASE);
  if (info.isSymbolicLink() || !info.isDirectory()) fail('发行目录不是普通目录：' + RELEASE);
  const entries = fs.readdirSync(RELEASE);
  if (entries.some((name) => name !== '安装说明.txt')) fail('发行目录含已有制品，拒绝写入：' + RELEASE);
  const note = path.join(RELEASE, '安装说明.txt');
  try {
    const noteInfo = fs.lstatSync(note);
    if (noteInfo.isSymbolicLink() || !noteInfo.isFile()) fail('准备说明不是普通文件：' + note);
  } catch (error) {
    if (error.code !== 'ENOENT') throw error;
  }
} catch (error) {
  if (error.code !== 'ENOENT') throw error;
}
for (const directory of [path.dirname(STAGE), path.dirname(RELEASE)]) {
  if (fs.existsSync(directory)) {
    const info = fs.lstatSync(directory);
    if (info.isSymbolicLink() || (!info.isDirectory() && !info.isFile())) fail('目录为链接或特殊文件，拒绝写入：' + directory);
  }
}

fs.mkdirSync(STAGE);
const pkg = path.join(STAGE, 'package');
fs.mkdirSync(pkg);

for (const name of REQUIRED) copyFile(path.join(PLUGIN, name), path.join(pkg, name));
copyTree(path.join(PLUGIN, 'lib'), path.join(pkg, 'lib'), (file) => file.endsWith('.js'));
copyTree(path.join(PLUGIN, 'locale'), path.join(pkg, 'locale'), (file) => file.endsWith('.json'));
for (const name of DATA_FILES) copyFile(path.join(ROOT, 'data', name), path.join(pkg, 'data', name));

// 词库是运行必需资产：只读源字节复制，绝不重新生成或改写顺序。
const dataAfter = DATA_FILES.map((name) => sha256(path.join(pkg, 'data', name)));
const dataBefore = DATA_FILES.map((name) => sha256(path.join(ROOT, 'data', name)));
if (JSON.stringify(dataAfter) !== JSON.stringify(dataBefore)) fail('词库复制后哈希不一致');

// Pin the platform tar path; never resolve an executable from PATH.
const tar = process.platform === 'win32'
  ? path.join(process.env.SystemRoot || 'C:\\Windows', 'System32', 'tar.exe')
  : '/usr/bin/tar';
if (!fs.existsSync(tar)) fail('缺少固定 tar：' + tar);
const tarVersion = execFileSync(tar, ['--version'], { encoding: 'utf8' }).split(/\r?\n/, 1)[0];
if (!/^(bsdtar|tar \(GNU tar\)) /.test(tarVersion)) fail('无法识别系统 tar：' + tarVersion);
console.log('系统归档工具：' + tarVersion);
fs.mkdirSync(path.dirname(RELEASE), { recursive: true });
fs.mkdirSync(RELEASE);
execFileSync(tar, ['-czf', archiveTemp, '-C', STAGE, 'package'], { stdio: 'inherit' });

const digest = sha256(archiveTemp);
const line = `${digest}  ${path.basename(archive)}\n`;
fs.linkSync(archiveTemp, archive);
fs.unlinkSync(archiveTemp);
fs.writeFileSync(sums, line, { flag: 'wx' });

const size = (fs.statSync(archive).size / (1024 * 1024)).toFixed(1);
console.log(`完成：${archive}（${size} MiB）`);
console.log(`SHA-256：${digest}`);
