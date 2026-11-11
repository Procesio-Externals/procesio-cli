"""process-screenshot: look at a process the way a person sees it in the Process Designer.

The API returns what a process STORES; only the designer shows how that reads on the canvas
(areas around their actions, labels clear of the borders, connectors without jogs). This
opens the designer in a headless browser with the profile's own sign-in, pans the canvas so
every action and area is in view, and saves a PNG. Nothing is clicked and nothing is saved.

Sign-in: a username/password profile's Web-API session cookies (`auth.get_valid_cookies`)
are put into the browser before it opens the designer, so no saved browser login is needed
and none can go stale. An API-key profile has no browser session: use a userpass profile.

Fitting: designer coordinates map to the screen as `canvas * zoom + viewport`, with the stored
viewport `canvasData {x, y, zoom}` (a process the tool saved opens at 0, 0, 1). The bounding
box of the actions and shapes is computed from the flow, the browser window is sized to hold
it, and one drag on empty canvas (which pans the designer) moves it under the top-left
toolbars. The canvas is never zoomed, so the picture is at the designer's real scale.
"""
from __future__ import annotations

import argparse
import json
import os
import time

from tools.procesio import auth, config
from tools.procesio.actiondef import ActionDef
from tools.procesio.errors import ProcesioAPIError, UsageError
from tools.procesio.handlers.common import add_profile_arg
from tools.procesio.layout import areas

LEFT_BAR, TOP_BAR, RIGHT_BAR = 80, 64, 56     # designer chrome over the canvas, in screen px
MARGIN = 40                                   # empty canvas kept around the content
MIN_W, MIN_H = 1280, 800


def _args(p: argparse.ArgumentParser) -> None:
    add_profile_arg(p)
    p.add_argument("--id", required=True, help="process (project) id")
    p.add_argument("--out", required=True, help="PNG file to write")
    p.add_argument("--no-fit", dest="no_fit", action="store_true",
                   help="keep the stored viewport instead of panning the content into view")
    p.add_argument("--settle-ms", dest="settle_ms", type=int, default=2500,
                   help="wait after the canvas appears, for the designer to draw (default 2500)")
    p.add_argument("--headed", action="store_true", help="show the browser window")


def _parse(v):
    if isinstance(v, str):
        try:
            return json.loads(v)
        except ValueError:
            return {}
    return v or {}


def content_bbox(flow: dict) -> tuple[float, float, float, float] | None:
    """Designer-coordinate bounding box of every top-level action (label included) and shape."""
    actions = areas._g(flow, "actions", "Actions", default=[]) or []
    norm = []
    for a in actions:
        cd = _parse(areas._g(a, "customData", "CustomData"))
        norm.append({"id": areas._g(a, "id", "Id"), "parentId": areas._g(a, "parentId", "ParentId"),
                     "customData": cd})
    rects = list(areas.node_boxes(norm).values())
    canvas = _parse(areas._g(flow, "canvasData", "CanvasData"))
    rects += [areas.shape_rect(s) for s in (canvas.get("shapes") or [])]
    if not rects:
        return None
    return (min(r[0] for r in rects), min(r[1] for r in rects),
            max(r[2] for r in rects), max(r[3] for r in rects))


def viewport_of(flow: dict) -> dict:
    canvas = _parse(areas._g(flow, "canvasData", "CanvasData"))
    try:
        return {"x": float(canvas.get("x") or 0), "y": float(canvas.get("y") or 0),
                "zoom": float(canvas.get("zoom") or 1) or 1.0}
    except (TypeError, ValueError):
        return {"x": 0.0, "y": 0.0, "zoom": 1.0}


def plan_fit(bbox, vp: dict) -> dict:
    """Window size and the pan (drag) that put `bbox` just inside the designer's chrome."""
    z = vp["zoom"]
    cur = (bbox[0] * z + vp["x"], bbox[1] * z + vp["y"],
           bbox[2] * z + vp["x"], bbox[3] * z + vp["y"])
    dx = (LEFT_BAR + MARGIN) - cur[0]
    dy = (TOP_BAR + MARGIN) - cur[1]
    w = (cur[2] - cur[0]) + LEFT_BAR + RIGHT_BAR + 2 * MARGIN
    h = (cur[3] - cur[1]) + TOP_BAR + 2 * MARGIN
    # The drag starts on empty canvas (right of and below the content as it opens) and both
    # of its ends must stay over the canvas, inside the window: a pointer that leaves the
    # canvas stops the pan.
    sx = max(cur[2] + 30, LEFT_BAR + 20, LEFT_BAR + 20 - dx)
    sy = max(cur[3] + 30, TOP_BAR + 20, TOP_BAR + 20 - dy)
    width = int(max(MIN_W, w, sx + max(dx, 0) + RIGHT_BAR + 40))
    height = int(max(MIN_H, h, sy + max(dy, 0) + 40))
    start = (sx, sy)
    return {"width": width, "height": height, "drag_from": start,
            "drag_to": (start[0] + dx, start[1] + dy), "pan": (round(dx, 1), round(dy, 1))}


def _browser_cookies(client) -> list[dict]:
    if client.profile.get("type") != "userpass":
        raise UsageError("process-screenshot needs a username/password profile: the designer "
                         "signs in with the Web-API session cookies, which an API key does not "
                         "have. Pass --profile <a userpass profile>.")
    cookies = auth.get_valid_cookies(client.name, client.profile, client._session)
    web = config.web_base(client.profile)
    return [{"name": k, "value": v, "url": web, "secure": True, "httpOnly": True,
             "sameSite": "None"} for k, v in cookies.items()]


def _open_driver(headless: bool):
    from tools.web.driver import PlaywrightDriver   # lazy: playwright is only needed here
    return PlaywrightDriver(headless=headless)


def process_screenshot(client, args) -> dict:
    try:
        resp = client.get(f"/api/Projects/{args.id}")
    except ProcesioAPIError as e:
        raise UsageError(f"could not read process {args.id}: {e}") from e
    flow = resp.get("flow", resp) if isinstance(resp, dict) else resp
    if not isinstance(flow, dict):
        raise UsageError(f"process {args.id}: unexpected read shape")
    ws = client.workspace_id or client.profile.get("workspace_id") or ""
    url = f"{config.app_base(client.profile)}/admin/process/designer/{args.id}"
    if ws:
        url += f"#{ws}"
    bbox = content_bbox(flow)
    vp = viewport_of(flow)
    fit = plan_fit(bbox, vp) if (bbox and not args.no_fit) else None
    cookies = _browser_cookies(client)
    out = os.path.abspath(args.out)
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)

    with _open_driver(headless=not args.headed) as d:
        d.set_viewport(fit["width"] if fit else MIN_W + 320, fit["height"] if fit else MIN_H + 200)
        d.add_cookies(cookies)
        d.goto(url)
        deadline = time.time() + 45
        while time.time() < deadline:
            if d.eval_js("document.querySelectorAll('canvas').length"):
                break
            d.wait(500)
        else:
            raise UsageError(f"the designer did not draw a canvas within 45 s (landed on "
                             f"{d.current_url()}); diagnostics: "
                             f"{json.dumps(d.diagnostics().get('bad_responses'))[:300]}")
        d.wait(max(0, args.settle_ms))
        if fit:
            page = d.page
            (fx, fy), (tx, ty) = fit["drag_from"], fit["drag_to"]
            # a press, a short nudge, then the move: the canvas starts panning only once the
            # pointer has moved a few pixels with the button down
            page.mouse.move(fx, fy)
            d.wait(150)
            page.mouse.down()
            d.wait(150)
            page.mouse.move(fx + 5, fy + 5, steps=3)
            page.mouse.move(tx, ty, steps=25)
            d.wait(150)
            page.mouse.up()
            d.wait(600)
        d.screenshot(out, full_page=False)
        diag = d.diagnostics()
        final_url = d.current_url()

    bad = [r for r in diag.get("bad_responses", []) if "procesio" in str(r.get("url", ""))]
    return {"result": {
        "id": args.id, "path": out, "url": url, "final_url": final_url,
        "signed_in": "/designer/" in final_url,
        "viewport": vp, "content_bbox": [round(v, 1) for v in bbox] if bbox else None,
        "fit": ({k: fit[k] for k in ("width", "height", "pan")} if fit else None),
        "page_errors": diag.get("page_errors", []), "bad_responses": bad,
    }}


ACTIONS = {
    "process-screenshot": ActionDef(
        func=process_screenshot, add_args=_args, needs_client=True,
        description=("Screenshot a live process in the Process Designer, as a person sees it: "
                     "opens the designer headless with the profile's own sign-in (a userpass "
                     "profile; no saved browser login), pans every action and canvas area into "
                     "view at real scale and writes a PNG. Read-only: nothing is clicked or "
                     "saved. Use it to check what the API cannot show - areas around their "
                     "actions, labels clear of borders, connector routing. Needs the Playwright "
                     "Chromium browser. Workspace-scoped: pass --workspace-id."),
    ),
}
