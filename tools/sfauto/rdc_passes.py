#!/usr/bin/env python
# Copyright (c) 2026 Saud Hamad Alsuwailih
# SPDX-License-Identifier: AGPL-3.0-or-later OR LicenseRef-Saud-Commercial
"""rdc_passes.py -- dump every render pass of a RenderDoc D3D12 capture (.rdc): draw counts, targets,
what is bound on texture slots 0-7, viewport/scissor, pipeline blend/depth state, and a freshness check
of the depth-as-colour copy.  READ ONLY: it converts the capture to XML with renderdoccmd (into
sfauto/tools/out/rdc_cache/) and never touches the game, the project sources or any process.

  python sfauto/tools/rdc_passes.py CAPTURE.rdc [CAPTURE2.rdc ...] [--out DIR] [--json] [--keep-xml]

A "pass" is a run of consecutive draws with the same (render target, depth target).  Pass names are
guessed from the targets (shadow = depth only, no colour target); the guess is printed as ASSUMED.
Everything else is read from the capture and is VERIFIED against the API stream.

Needs only the standard library (renderdoccmd.exe from the RenderDoc install).
"""
import argparse, collections, json, os, subprocess, sys
import xml.etree.ElementTree as ET

RDCMD = r"C:\Program Files\RenderDoc\renderdoccmd.exe"
HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_OUT = os.path.join(HERE, "out")


def child(el, name):
    if el is None:
        return None
    for c in el:
        if c.get("name") == name:
            return c
    return None


def txt(el, name):
    c = child(el, name)
    return None if c is None else (c.get("string") or c.text)


def num(el, name, default=None):
    c = child(el, name)
    if c is None or c.text is None:
        return default
    try:
        return float(c.text)
    except ValueError:
        return default


def to_xml(rdc, cache_dir, keep=True):
    os.makedirs(cache_dir, exist_ok=True)
    xml = os.path.join(cache_dir, os.path.splitext(os.path.basename(rdc))[0] + ".xml")
    if not (os.path.exists(xml) and os.path.getmtime(xml) >= os.path.getmtime(rdc)):
        r = subprocess.run([RDCMD, "convert", "-f", rdc, "-o", xml, "-c", "xml"], capture_output=True, text=True)
        if not os.path.exists(xml):
            raise SystemExit("renderdoccmd convert failed: %s %s" % (r.stdout, r.stderr))
    return xml


def analyse(xml_path):
    res = {}      # resource id -> description
    srv = {}      # (heap, index) -> dict
    pso = {}      # pso id -> blend/depth state
    st = dict(pso=None, rt=[], ds=None, tables={}, vp=None, sc=None)
    draws = []
    api_counts = collections.Counter()
    for _, el in ET.iterparse(xml_path, events=("end",)):
        if el.tag != "chunk":
            continue
        nm = el.get("name")
        api_counts[nm] += 1
        if nm == "ID3D12Device::CreateCommittedResource":
            d = child(el, "pDesc")
            ids = [c.text for c in el if c.tag == "ResourceId"]
            if d is not None and ids:
                res[ids[-1]] = dict(dim=txt(d, "Dimension"), w=int(num(d, "Width", 0)), h=int(num(d, "Height", 0)),
                                    arr=int(num(d, "DepthOrArraySize", 1)), mips=int(num(d, "MipLevels", 1)),
                                    fmt=(txt(d, "Format") or "").replace("DXGI_FORMAT_", ""),
                                    flags=(txt(d, "Flags") or "").replace("D3D12_RESOURCE_FLAG_", ""))
        elif nm == "ID3D12Device::CreateShaderResourceView":
            d, dst = child(el, "desc"), child(el, "dst")
            if d is not None and dst is not None:
                dd = child(d, "Descriptor")
                srv[(txt(dst, "heap"), int(num(dst, "index", 0)))] = dict(
                    res=txt(d, "Resource"), fmt=(txt(dd, "Format") or "").replace("DXGI_FORMAT_", ""))
        elif nm == "ID3D12Device::CreateGraphicsPipeline":
            d = child(el, "pDesc")
            ids = [c.text for c in el if c.tag == "ResourceId" and c.get("name") in ("pPipelineState", "ppPipelineState")]
            if d is not None and ids:
                bs = child(d, "BlendState"); rta = child(bs, "RenderTarget"); rt0 = list(rta)[0] if rta is not None else None
                dss = child(d, "DepthStencilState")
                pso[ids[-1]] = dict(
                    blend=txt(rt0, "BlendEnable"), src=(txt(rt0, "SrcBlend") or "").replace("D3D12_BLEND_", ""),
                    dst=(txt(rt0, "DestBlend") or "").replace("D3D12_BLEND_", ""),
                    zen=txt(dss, "DepthEnable"), zw=(txt(dss, "DepthWriteMask") or "").replace("D3D12_DEPTH_WRITE_MASK_", ""),
                    zf=(txt(dss, "DepthFunc") or "").replace("D3D12_COMPARISON_FUNC_", ""))
        elif nm == "ID3D12GraphicsCommandList::SetPipelineState":
            st["pso"] = txt(el, "pPipelineState")
        elif nm == "ID3D12GraphicsCommandList::SetGraphicsRootSignature":
            st["tables"] = {}
        elif nm == "ID3D12GraphicsCommandList::SetGraphicsRootDescriptorTable":
            b = child(el, "BaseDescriptor")
            st["tables"][int(num(el, "RootParameterIndex", 0))] = (txt(b, "heap"), int(num(b, "index", 0)))
        elif nm == "ID3D12GraphicsCommandList::OMSetRenderTargets":
            rts = []
            arr = child(el, "pRenderTargetDescriptors")
            if arr is not None:
                for s in arr:
                    rts.append(txt(s, "Resource"))
            ds = child(el, "pDepthStencilDescriptor")
            st["rt"] = [r for r in rts if r]
            st["ds"] = txt(ds, "Resource") if (ds is not None and ds.tag == "struct") else None
        elif nm == "ID3D12GraphicsCommandList::RSSetViewports":
            arr = child(el, "pViewports")
            v = list(arr)[0] if arr is not None and len(arr) else None
            if v is not None:
                st["vp"] = (num(v, "Width"), num(v, "Height"))
        elif nm == "ID3D12GraphicsCommandList::RSSetScissorRects":
            arr = child(el, "pRects")
            r = list(arr)[0] if arr is not None and len(arr) else None
            if r is not None:
                st["sc"] = (int(num(r, "left")), int(num(r, "top")), int(num(r, "right")), int(num(r, "bottom")))
        elif nm == "ID3D12GraphicsCommandList::DrawInstanced":
            t1 = st["tables"].get(1)
            slots = [srv.get((t1[0], t1[1] + i)) if t1 else None for i in range(8)]
            draws.append(dict(chunk=int(el.get("chunkIndex", 0)), pso=st["pso"], rt=list(st["rt"]), ds=st["ds"],
                              verts=int(num(el, "VertexCountPerInstance", 0)), inst=int(num(el, "InstanceCount", 1)),
                              slots=slots, vp=st["vp"], sc=st["sc"]))
        if nm.startswith("ID3D12GraphicsCommandList::DrawIndexed"):
            api_counts["_indexed_draw_seen"] += 1
        el.clear()
    return dict(res=res, pso=pso, draws=draws, api=dict(api_counts))


def rdesc(res, rid):
    r = res.get(rid)
    if not r:
        return "res#%s" % rid
    return "res#%s %dx%d %s" % (rid, r["w"], r["h"], r["fmt"])


def is_depth(res, rid):
    r = res.get(rid)
    return bool(r and "DEPTH_STENCIL" in r["flags"])


def build_passes(a):
    res, draws = a["res"], a["draws"]
    passes = []
    for d in draws:
        key = (tuple(d["rt"]), d["ds"])
        if passes and passes[-1]["key"] == key:
            passes[-1]["draws"].append(d)
        else:
            passes.append(dict(key=key, draws=[d]))
    out = []
    for p in passes:
        rt, ds = p["key"]
        ds_r = res.get(ds) if ds else None
        if not rt and ds:
            guess = "shadow/depth-only"
        elif rt and ds and ds_r and (ds_r["w"], ds_r["h"]) == (res.get(rt[0], {}).get("w"), res.get(rt[0], {}).get("h")) and len(p["draws"]) > 100:
            guess = "main scene"
        elif rt and not ds:
            guess = "full-screen/copy/post"
        else:
            guess = "post/UI/other"
        slot_depth = collections.Counter()
        slot0 = collections.Counter()
        for d in p["draws"]:
            for i, s in enumerate(d["slots"]):
                if s and is_depth(res, s["res"]):
                    slot_depth[i] += 1
            s0 = d["slots"][0] if d["slots"] else None
            slot0[rdesc(res, s0["res"]) + " view=" + s0["fmt"] if s0 else "EMPTY"] += 1
        psos = collections.Counter(d["pso"] for d in p["draws"])
        vps = collections.Counter(d["vp"] for d in p["draws"]); scs = collections.Counter(d["sc"] for d in p["draws"])
        out.append(dict(
            guess=guess, rt=[rdesc(res, r) for r in rt], ds=rdesc(res, ds) if ds else None,
            draws=len(p["draws"]), verts=sum(d["verts"] for d in p["draws"]),
            first_chunk=p["draws"][0]["chunk"], last_chunk=p["draws"][-1]["chunk"],
            distinct_pso=len(psos), depth_on_slots=dict(slot_depth), slot0_top=dict(slot0.most_common(4)),
            viewport=vps.most_common(1)[0][0], scissor=scs.most_common(1)[0][0],
            pso_state=[dict(pso=k, n=n, **a["pso"].get(k, {})) for k, n in psos.most_common(4)]))
    return out


def freshness(a, passes):
    """For every draw that samples a depth-capable texture: was the colour copy refreshed after the last
    depth-only draw?  Returns (fresh, not_fresh) or None when the capture has no depth-only pass."""
    res, draws = a["res"], a["draws"]
    depth_ids = {rid for rid in res if is_depth(res, rid)}
    sm = {d["ds"] for d in draws if not d["rt"] and d["ds"]}
    if not sm:
        return None
    last_sh = last_cp = None; fresh = stale = 0
    for d in sorted(draws, key=lambda x: x["chunk"]):
        if not d["rt"] and d["ds"] in sm:
            last_sh = d["chunk"]
        elif d["rt"] and not d["ds"] and res.get(d["rt"][0], {}).get("fmt") == "R8G8B8A8_UNORM" and res[d["rt"][0]]["w"] == res[d["rt"][0]]["h"]:
            last_cp = d["chunk"]
        elif d["rt"] and d["ds"]:
            if any(s and s["res"] in sm for s in d["slots"]):
                if last_cp is not None and (last_sh is None or last_cp > last_sh):
                    fresh += 1
                else:
                    stale += 1
    return fresh, stale


def to_md(name, a, passes, fr):
    L = ["# %s" % name, "",
         "Resources: %d  | pipelines: %d  | draws: %d  | indexed-draw API calls seen: %d" % (
             len(a["res"]), len(a["pso"]), len(a["draws"]), a["api"].get("_indexed_draw_seen", 0)), "",
         "| # | pass (ASSUMED name) | render target | depth target | draws | vertices | pipelines | depth bound on slots | viewport | scissor |",
         "|---|---|---|---|---:|---:|---:|---|---|---|"]
    for i, p in enumerate(passes):
        L.append("| %d | %s | %s | %s | %d | %d | %d | %s | %sx%s | %s |" % (
            i, p["guess"], "; ".join(p["rt"]) or "none", p["ds"] or "none", p["draws"], p["verts"], p["distinct_pso"],
            p["depth_on_slots"] or "-", int(p["viewport"][0] or 0), int(p["viewport"][1] or 0), p["scissor"]))
    L += ["", "## Slot 0 (first texture) per pass", ""]
    for i, p in enumerate(passes):
        if p["draws"] >= 20:
            L.append("- pass %d (%s, %d draws): %s" % (i, p["guess"], p["draws"], p["slot0_top"]))
    if fr:
        L += ["", "## Depth-as-colour copy freshness", "",
              "Main-pass draws that sample the shadow map after the copy was refreshed: %d; not refreshed: %d" % fr]
    return "\n".join(L) + "\n"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("captures", nargs="+")
    ap.add_argument("--out", default=DEFAULT_OUT)
    ap.add_argument("--json", action="store_true", help="also write <capture>.passes.json")
    a = ap.parse_args()
    cache = os.path.join(a.out, "rdc_cache")
    os.makedirs(a.out, exist_ok=True)
    for cap in a.captures:
        xml = to_xml(cap, cache)
        an = analyse(xml)
        passes = build_passes(an)
        fr = freshness(an, passes)
        name = os.path.splitext(os.path.basename(cap))[0]
        md = to_md(name, an, passes, fr)
        open(os.path.join(a.out, name + ".passes.md"), "w", encoding="utf-8").write(md)
        if a.json:
            json.dump(dict(passes=passes, freshness=fr, api=an["api"]), open(os.path.join(a.out, name + ".passes.json"), "w"), indent=1)
        print(md)


if __name__ == "__main__":
    main()
