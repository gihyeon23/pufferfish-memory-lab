#!/usr/bin/env python3
# 공식 dist jar vs 소스 빌드 jar를 javap -p -s(클래스·필드·메서드 시그니처)로 비교
# JDK가 달라 바이트는 달라도 구조가 같으면 같은 소스로 판단
# usage: cmpsig.py <official hadoop dir> <source tree>
import glob, os, subprocess, sys, zipfile

off, src = sys.argv[1], sys.argv[2]

def classes(jar):
    with zipfile.ZipFile(jar) as z:
        return sorted(n[:-6].replace('/', '.') for n in z.namelist() if n.endswith('.class'))

def sigs(jar, names):
    out = {}
    for i in range(0, len(names), 300):
        chunk = names[i:i + 300]
        txt = subprocess.run(['javap', '-p', '-s', '-cp', jar] + chunk,
                             stdout=subprocess.PIPE, universal_newlines=True).stdout
        cur, buf = None, []
        for line in txt.splitlines():
            if line.startswith('Compiled from'):
                continue
            if not line.startswith(' ') and line.rstrip().endswith('{'):
                cur, buf = line, []
            elif line == '}' and cur is not None:
                # 멤버 순서는 컴파일러마다 다를 수 있어 정렬
                out[cur] = sorted(buf)
                cur = None
            elif cur is not None and line.strip():
                buf.append(line.strip())
    return out

print('%-58s %6s %6s %6s %6s' % ('JAR', 'class', 'same', 'diff', 'only'))
jars = []
for d in ('common', 'hdfs', 'mapreduce', 'yarn'):
    jars += sorted(glob.glob('%s/share/hadoop/%s/hadoop-*2.7.3.jar' % (off, d)))
for j in jars:
    n = os.path.basename(j)
    cands = [p for p in glob.glob('%s/**/target/%s' % (src, n), recursive=True) if '/lib/' not in p]
    if not cands:
        print('%-58s (no source build)' % n)
        continue
    s = cands[0]
    ca, cb = classes(j), classes(s)
    common = sorted(set(ca) & set(cb))
    only = sorted(set(ca) ^ set(cb))
    sa, sb = sigs(j, common), sigs(s, common)
    diff = [k for k in sa if sa[k] != sb.get(k)]
    print('%-58s %6d %6d %6d %6d' % (n, len(set(ca) | set(cb)), len(common) - len(diff), len(diff), len(only)))
    for k in diff[:8]:
        print('    diff: ' + k[:110])
    for k in only[:8]:
        print('    only-%s: %s' % ('official' if k in ca else 'source', k))
