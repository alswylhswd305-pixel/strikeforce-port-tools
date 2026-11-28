#!/usr/bin/env python
# Copyright (c) 2026 Saud Hamad Alsuwailih
# SPDX-License-Identifier: AGPL-3.0-or-later OR LicenseRef-Saud-Commercial
"""rdc_export.py -- replay a RenderDoc capture inside qrenderdoc (headless script mode) and export
  * every depth-only pass target, as a PNG after the last draw that wrote it (e.g. the shadow map),
  * the colour target(s) with the most draws (the main scene) at the end of the frame,
  * optional pixel history for pixels you name: which draws wrote each pixel, with depth values.

  python sfauto/tools/rdc_export.py CAPTURE.rdc [--pixel 1000,470 --pixel 900,470] [--out DIR] [--timeout 420]

Process rules: it starts ONE qrenderdoc.exe, waits for it to finish by itself, and only if the timeout
expires it stops that same PID.  It never touches any other process, the game, or project sources.
Output: DIR/<capture>_export/{depth_<id>.png, color_<id>.png, pixhist.txt, export_log.txt}
Depth PNGs are normalised to the min/max actually present (the log prints both).
"""
import argparse, os, subprocess, sys, time

QRD = r"C:\Program Files\RenderDoc\qrenderdoc.exe"
HERE = os.path.dirname(os.path.abspath(__file__))

TEMPLATE = r'''
import os, traceback
import renderdoc as rd
CAP = %(cap)r
OUT = %(out)r
PIXELS = %(pixels)r
os.makedirs(OUT, exist_ok=True)
LOG = open(os.path.join(OUT, "export_log.txt"), "w")
def log(*a):
    LOG.write(" ".join(str(x) for x in a) + "\n"); LOG.flush()

def flatten(actions, acc):
    for a in actions:
        if a.flags & rd.ActionFlags.Drawcall:
            acc.append(a)
        flatten(a.children, acc)

def col(mv):
    try:
        c = mv.col.floatValue
        return "(%%.3f,%%.3f,%%.3f,%%.3f)" %% (c[0], c[1], c[2], c[3])
    except Exception:
        return "?"

def save(controller, tex, path, lo=None, hi=None):
    ts = rd.TextureSave()
    ts.resourceId = tex.resourceId
    ts.destType = rd.FileType.PNG
    ts.mip = 0
    ts.slice.sliceIndex = 0
    ts.alpha = rd.AlphaMapping.Discard
    if lo is not None:
        ts.comp.blackPoint = lo
        ts.comp.whitePoint = hi if hi > lo else lo + 1.0
    controller.SaveTexture(ts, path)

def work(controller):
    try:
        textures = {t.resourceId: t for t in controller.GetTextures()}
        draws = []
        flatten(controller.GetRootActions(), draws)
        log("draws:", len(draws))
        last_depth_only = {}   # depth tex id -> last eid of a draw with no colour target
        colour_draws = {}      # colour tex id -> draws
        for a in draws:
            controller.SetFrameEvent(a.eventId, False)
            ps = controller.GetPipelineState()
            dt = ps.GetDepthTarget().resource
            outs = [o.resource for o in ps.GetOutputTargets() if o.resource != rd.ResourceId.Null()]
            if not outs and dt != rd.ResourceId.Null():
                last_depth_only[dt] = a.eventId
            for o in outs:
                colour_draws[o] = colour_draws.get(o, 0) + 1
        for dt, eid in last_depth_only.items():
            t = textures[dt]
            controller.SetFrameEvent(eid, True)
            mm = controller.GetMinMax(dt, rd.Subresource(0, 0, 0), rd.CompType.Typeless)
            lo, hi = mm[0].floatValue[0], mm[1].floatValue[0]
            p = os.path.join(OUT, "depth_%%s.png" %% str(dt).replace("ResourceId::", ""))
            save(controller, t, p, lo, hi)
            log("depth-only target", str(dt), "%%dx%%d" %% (t.width, t.height), "last eid", eid, "min/max", lo, hi, "->", p)
        controller.SetFrameEvent(draws[-1].eventId, True)
        top = sorted(colour_draws.items(), key=lambda kv: -kv[1])[:2]
        for cid, n in top:
            t = textures[cid]
            p = os.path.join(OUT, "color_%%s.png" %% str(cid).replace("ResourceId::", ""))
            save(controller, t, p)
            log("colour target", str(cid), "%%dx%%d" %% (t.width, t.height), "draws", n, "->", p)
        if PIXELS and top:
            tgt = textures[top[0][0]]
            actions = {}
            def walk(acts):
                for a in acts:
                    actions[a.eventId] = a
                    walk(a.children)
            walk(controller.GetRootActions())
            sf = controller.GetStructuredFile()
            with open(os.path.join(OUT, "pixhist.txt"), "w") as f:
                for (x, y) in PIXELS:
                    hist = controller.PixelHistory(tgt.resourceId, x, y, rd.Subresource(0, 0, 0), rd.CompType.Typeless)
                    f.write("=== pixel (%%d,%%d) on %%s: %%d modifications\n" %% (x, y, str(tgt.resourceId), len(hist)))
                    for m in hist:
                        a = actions.get(m.eventId)
                        nm = a.GetName(sf)[:42] if a is not None else "?"
                        flags = [k for k in ("backfaceCulled", "depthClipped", "viewClipped", "scissorClipped", "shaderDiscarded", "depthTestFailed", "stencilTestFailed") if getattr(m, k, False)]
                        try:
                            dep = " depth pre=%%.5f shaderOut=%%.5f post=%%.5f" %% (m.preMod.depth, m.shaderOut.depth, m.postMod.depth)
                        except Exception:
                            dep = ""
                        f.write("  eid %%d %%s verts=%%s pre=%%s shaderOut=%%s post=%%s%%s %%s\n" %% (
                            m.eventId, nm, a.numIndices if a is not None else "?", col(m.preMod), col(m.shaderOut), col(m.postMod), dep, ",".join(flags) or "passed"))
        log("DONE")
    except Exception:
        log("EXCEPTION", traceback.format_exc())

try:
    pyrenderdoc.LoadCapture(CAP, rd.ReplayOptions(), CAP, False, False)
    pyrenderdoc.Replay().BlockInvoke(lambda c: None)
    pyrenderdoc.Replay().BlockInvoke(work)
except Exception:
    log("EXCEPTION top", traceback.format_exc())
LOG.close()
os._exit(0)
'''


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("capture")
    ap.add_argument("--pixel", action="append", default=[], help="x,y on the main colour target (repeatable)")
    ap.add_argument("--out", default=os.path.join(HERE, "out"))
    ap.add_argument("--timeout", type=int, default=420)
    a = ap.parse_args()
    cap = os.path.abspath(a.capture)
    name = os.path.splitext(os.path.basename(cap))[0]
    out = os.path.join(os.path.abspath(a.out), name + "_export")
    os.makedirs(out, exist_ok=True)
    pixels = [tuple(int(v) for v in p.split(",")) for p in a.pixel]
    script = os.path.join(out, "_qrd_script.py")
    open(script, "w", encoding="utf-8").write(TEMPLATE % dict(cap=cap, out=out, pixels=pixels))
    if not os.path.isfile(QRD):
        sys.exit("qrenderdoc.exe not found at %s" % QRD)
    p = subprocess.Popen([QRD, "--python", script])
    t0 = time.time()
    while p.poll() is None and time.time() - t0 < a.timeout:
        time.sleep(2)
    if p.poll() is None:
        print("timeout: stopping my own qrenderdoc pid %d" % p.pid)
        p.kill()
    log = os.path.join(out, "export_log.txt")
    print(open(log, encoding="utf-8").read() if os.path.exists(log) else "no log written")
    print("output folder:", out)


if __name__ == "__main__":
    main()
