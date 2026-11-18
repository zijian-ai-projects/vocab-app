"""Static validation only: never import or execute packaged application code."""
import ast
import hashlib
import io
import json
import marshal
from pathlib import Path
import struct
import tarfile
import types
import zipfile
import zlib

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'vocab-app-releases' / 'learning-patch-20261117'
DATA = ('bank.json', 'books.json', 'phrases.json', 'phrase_books.json', 'level_meanings.json')


def digest(data):
    return hashlib.sha256(data).hexdigest()


def signature(code):
    if isinstance(code, types.CodeType):
        return (code.co_code, code.co_names, code.co_varnames, code.co_argcount,
                code.co_kwonlyargcount, code.co_flags,
                tuple(signature(c) for c in code.co_consts))
    return code


def pyz_modules(executable):
    magic = b'MEI\014\013\012\013\016'
    cookie = executable.rfind(magic)
    _, length, offset, size, version, _ = struct.unpack('!8sIIII64s', executable[cookie:cookie + 88])
    assert version == 308
    start = cookie + 88 - length
    toc = executable[start + offset:start + offset + size]
    pos = 0
    while pos < len(toc):
        entry_size, entry_offset, packed, unpacked, compressed, kind = struct.unpack('!IIIIBc', toc[pos:pos + 18])
        if kind == b'z':
            blob = executable[start + entry_offset:start + entry_offset + packed]
            if compressed:
                blob = zlib.decompress(blob)
            assert blob[:4] == b'PYZ\0'
            entries = dict(marshal.loads(blob[struct.unpack('!i', blob[8:12])[0]:]))
            return {name: marshal.loads(zlib.decompress(blob[off:off + count]))
                    for name, (_, off, count) in entries.items() if name in ('main', 'study_queue', 'scheduler')}
        pos += entry_size
    raise AssertionError('No embedded PYZ')


def main():
    windows = OUT / 'windows' / 'VocabApp-1.4.3-windows-x64.zip'
    plugin = OUT / 'dsh' / 'dsh-vocab-app-0.1.11.tgz'
    with zipfile.ZipFile(windows) as archive:
        assert archive.testzip() is None
        names = archive.namelist()
        prefix = 'VocabApp-1.4.3-windows-x64/'
        assert all(n.startswith(prefix) and '..' not in n.split('/') for n in names)
        assert not any(any(x.lower() in ('userdata', 'progress.json', '_win.json', 'node_modules', 'tests', '__pycache__') for x in n.split('/')) for n in names)
        for name in DATA:
            assert archive.read(prefix + '_internal/data/' + name) == (ROOT / 'data' / name).read_bytes()
        assert set(n[len(prefix + '_internal/data/'):] for n in names if n.startswith(prefix + '_internal/data/')) == set(DATA)
        for executable in ('VocabApp.exe', 'ResetRecords.exe'):
            blob = archive.read(prefix + executable)
            pe = struct.unpack('<I', blob[60:64])[0]
            assert blob[pe:pe+4] == b'PE\0\0' and struct.unpack('<H', blob[pe+4:pe+6])[0] == 0x8664
        modules = pyz_modules(archive.read(prefix + 'VocabApp.exe'))
        assert set(modules) == {'main', 'study_queue', 'scheduler'}
        for name, code in modules.items():
            source = ROOT / 'app' / (name + '.py')
            assert signature(code) == signature(compile(source.read_bytes(), str(source), 'exec')), name
        tree = ast.parse((ROOT / 'app/main.py').read_text(encoding='utf-8'))
        assert any(isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == 'VERSION' for t in n.targets) and n.value.s == '1.4.3' for n in tree.body)
    with tarfile.open(plugin, 'r:gz') as archive:
        members = archive.getmembers()
        assert all(m.isdir() or m.isfile() for m in members)
        actual = {m.name: archive.extractfile(m).read() for m in members if m.isfile()}
        expected = {}
        base = ROOT / 'dsh-plugin'
        for name in ('package.json', 'index.js', 'client.js', 'cordis.patch.yml', 'icon.svg', 'readme.md'):
            expected['package/' + name] = (base / name).read_bytes()
        for folder, suffix in (('lib', '.js'), ('locale', '.json')):
            for path in (base / folder).rglob('*' + suffix):
                expected['package/' + path.relative_to(base).as_posix()] = path.read_bytes()
        for name in DATA:
            expected['package/data/' + name] = (ROOT / 'data' / name).read_bytes()
        assert actual == expected, 'Plugin package must exactly match runtime whitelist and current source'
        assert json.loads(actual['package/package.json'])['version'] == '0.1.11'
    old = {'VocabApp-1.4.3-windows-x64.zip': '4e0baba44ce53a40bf6798f50bdc4f40b1228fe3eeff24bbbe043ab6aa76566c',
           'dsh-vocab-app-0.1.10.tgz': '1b1446c54718eb0114a3fab69c794e5e41a94639db8163016f0d131893dd8d93'}
    for name, value in old.items():
        assert digest((ROOT / 'vocab-app-releases/v1.4.3' / name).read_bytes()) == value
    lines = []
    for path in (windows, plugin):
        value = digest(path.read_bytes())
        sidecar = next(path.parent.glob('SHA256SUMS-*.txt')).read_text(encoding='utf-8').split()[0]
        assert value == sidecar
        print('%s: %d bytes; SHA256 %s' % (path.name, path.stat().st_size, value))
        lines.append('%s  %s' % (value, path.relative_to(OUT).as_posix()))
    with (OUT / 'SHA256SUMS.txt').open('x', encoding='utf-8') as stream:
        stream.write('\n'.join(lines) + '\n')
    print('PASS: archive integrity, x64 PE headers, Windows embedded code matches current source, versions, plugin exact whitelist, unchanged data, hashes and preserved old archives. No application executed.')


if __name__ == '__main__':
    main()
