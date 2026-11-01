#!/usr/bin/env python3
# 원 저자 task 이미지 sequenceiq/hadoop-docker:2.4.0을 Docker Hub 레지스트리 API로 직접 받아
# Docker 1.12.1이 `docker load`로 읽는 legacy 형식 tar로 묶는다.
#   - Docker 1.12.1: 현재 Docker Hub pull 불가 / 최신 Docker(29): schema v1 manifest pull 불가
#   - schema v1의 v1Compatibility(id·parent·config)를 그대로 써서 레이어·ENV가 원본과 같음
# 맥·VM(python 3.5) 둘 다 실행 가능. 의존성 없음.
# usage: python3 fetch-sequenceiq-image.py <out_dir> [tag]   (기본 tag 2.4.0 — 원 README "tested 2.4.0")
#        → <out_dir>/sequenceiq-hadoop-docker-<tag>.tar, VM에서 `docker load -i`
import gzip, hashlib, json, os, shutil, sys, tarfile, urllib.request

REPO = "sequenceiq/hadoop-docker"
out_dir = sys.argv[1]
tag = sys.argv[2] if len(sys.argv) > 2 else "2.4.0"
blob_dir = os.path.join(out_dir, "blobs")
os.makedirs(blob_dir, exist_ok=True)


class DropAuthOnRedirect(urllib.request.HTTPRedirectHandler):
    # 블롭은 CDN으로 redirect됨 → 레지스트리 토큰을 CDN에 넘기지 않음
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        new = super().redirect_request(req, fp, code, msg, headers, newurl)
        if new is not None:
            new.remove_header("Authorization")
        return new


opener = urllib.request.build_opener(DropAuthOnRedirect)
tok_url = ("https://auth.docker.io/token?service=registry.docker.io&scope=repository:%s:pull" % REPO)
token = json.loads(opener.open(tok_url).read().decode())["token"]


def get(path, accept=None):
    req = urllib.request.Request("https://registry-1.docker.io/v2/%s/%s" % (REPO, path))
    req.add_header("Authorization", "Bearer " + token)
    if accept:
        req.add_header("Accept", accept)
    return opener.open(req)


manifest = json.loads(get("manifests/" + tag).read().decode())
assert manifest["schemaVersion"] == 1, "schema v1이 아님"
layers = list(zip(manifest["fsLayers"], manifest["history"]))   # 위(최신) → 아래(베이스) 순서
print("%s:%s  %s, 레이어 %d개" % (REPO, tag, manifest["architecture"], len(layers)))

# 1) 블롭 다운로드 (.part → sha256 검증 후 이름 변경, 이미 받은 것은 건너뜀)
for i, digest in enumerate(sorted(set(f["blobSum"] for f, _ in layers))):
    path = os.path.join(blob_dir, digest.replace(":", "_"))
    if os.path.exists(path):
        continue
    h = hashlib.sha256()
    with get("blobs/" + digest) as r, open(path + ".part", "wb") as w:
        while True:
            chunk = r.read(1 << 20)
            if not chunk:
                break
            h.update(chunk)
            w.write(chunk)
    assert "sha256:" + h.hexdigest() == digest, "digest 불일치: " + digest
    os.rename(path + ".part", path)
    print("  받음 %s (%.1f MB)" % (digest[:19], os.path.getsize(path) / 2 ** 20))

# 2) legacy load 형식: <id>/{VERSION,json,layer.tar} + repositories
stage = os.path.join(out_dir, "stage")
shutil.rmtree(stage, ignore_errors=True)
os.makedirs(stage)
for f, hist in layers:
    v1 = json.loads(hist["v1Compatibility"])
    d = os.path.join(stage, v1["id"])
    if os.path.isdir(d):   # 2.4.0 매니페스트는 최상위 레이어가 같은 id로 두 번 들어 있음
        continue
    os.makedirs(d)
    with open(os.path.join(d, "VERSION"), "w") as w:
        w.write("1.0")
    with open(os.path.join(d, "json"), "w") as w:
        w.write(hist["v1Compatibility"])
    src = os.path.join(blob_dir, f["blobSum"].replace(":", "_"))
    with gzip.open(src, "rb") as r, open(os.path.join(d, "layer.tar"), "wb") as w:
        shutil.copyfileobj(r, w, 1 << 20)
top_id = json.loads(layers[0][1]["v1Compatibility"])["id"]
with open(os.path.join(stage, "repositories"), "w") as w:
    json.dump({REPO: {tag: top_id}}, w)

out = os.path.join(out_dir, "sequenceiq-hadoop-docker-%s.tar" % tag)
with tarfile.open(out, "w") as t:
    for name in sorted(os.listdir(stage)):
        t.add(os.path.join(stage, name), arcname=name)
shutil.rmtree(stage)
print("완료: %s (%.0f MB) → VM에서 docker load -i" % (out, os.path.getsize(out) / 2 ** 20))
