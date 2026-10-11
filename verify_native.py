"""Run from buildscripts AFTER bundle_default.sh. No Android execution here."""
import hashlib
import json
import re
import subprocess
import zipfile
from pathlib import Path

root = Path.cwd()
abis = ['arm64-v8a', 'armeabi-v7a', 'x86', 'x86_64']
arches = dict(zip(abis, ['aarch64', 'armv7a', 'i686', 'x86_64']))
nm = root / 'sdk/android-sdk-linux/ndk/25.2.9519653/toolchains/llvm/prebuilt/linux-x86_64/bin/llvm-nm'
report = {'candidate_source': 'uploaded libmpv-android-video-build-1.1.11',
          'scope': 'compiled writers and packaging only; device recording NOT verified',
          'flavor_sha256': hashlib.sha256((root/'flavors/default.sh').read_bytes()).hexdigest(),
          'dependencies': {}, 'abis': {}}
for folder in sorted((root/'deps').iterdir()):
    if (folder/'.git').exists():
        report['dependencies'][folder.name] = subprocess.check_output(
            ['git', '-C', str(folder), 'rev-parse', 'HEAD'], text=True, timeout=10).strip()
for abi in abis:
    # The actual suffixes are supplied by build.sh's loadarch; search configs
    # rather than assume the upstream naming scheme.
    candidates = list((root/'deps/ffmpeg').glob('_build*/config.h'))
    matching = []
    for config in candidates:
        makefile = config.parent/'ffbuild/config.mak'
        text = makefile.read_text() if makefile.exists() else ''
        if str(root/'prefix'/abi) in text:
            matching.append(config)
    if len(matching) != 1:
        raise SystemExit(f'FAIL: cannot identify exactly one FFmpeg config for {abi}')
    config = matching[0]
    text = config.read_text()
    # FFmpeg versions may put component flags in config_components.h.
    components = config.parent/'config_components.h'
    if components.exists():
        text += '\n'+components.read_text()
    for flag in ['MPEGTS_MUXER', 'MATROSKA_MUXER']:
        if not re.search(r'^#define CONFIG_'+flag+r'\s+1\s*$', text, re.M):
            raise SystemExit(f'FAIL: {abi} missing CONFIG_{flag}')
    symbols = subprocess.check_output([str(nm), '--defined-only',
        str(root/'prefix'/abi/'lib/libavformat.a')], text=True, timeout=30)
    for symbol in ['ff_mpegts_muxer', 'ff_matroska_muxer']:
        if not re.search(r'\b'+symbol+r'\b', symbols):
            raise SystemExit(f'FAIL: {abi} missing compiled {symbol}')
    jar = root/'artifacts/default'/f'default-{abi}.jar'
    with zipfile.ZipFile(jar) as archive:
        assert archive.testzip() is None, f'Corrupt JAR: {abi}'
        packaged = archive.read(f'lib/{abi}/libmpv.so')
    binary = (root/'prefix'/abi/'lib/libmpv.so').read_bytes()
    if packaged != binary:
        raise SystemExit(f'FAIL: {abi} JAR does not contain the newly built libmpv')
    report['abis'][abi] = {'jar_sha256': hashlib.sha256(jar.read_bytes()).hexdigest(),
        'libmpv_sha256': hashlib.sha256(binary).hexdigest(),
        'compiled_writers': ['mpegts', 'matroska']}
(root/'artifacts/default/native-build-report.json').write_text(json.dumps(report, indent=2)+'\n')
print('PASS: all four ABI packages contain the candidate with compiled recording writers.')
print('Android recording and frame decoding remain unverified until the device check passes.')
