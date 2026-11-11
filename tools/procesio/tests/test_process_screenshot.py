"""Area geometry in DESIGNER coordinates, and process-screenshot (designer view of a process).

The geometry facts are pinned from screenshots of the Process Designer: a square/circle/
diamond action's stored position is the TOP-LEFT of its 48 px icon with the name centred
under it, a For Each's position is its frame top-left with the name under the frame, and
canvas shapes are top-left too. Before this was measured the areas were fitted as if the
action position were the icon's centre, and every area sat 24 px up and left of its actions
with their labels on the bottom border.
"""
from __future__ import annotations

import argparse
import json
from types import SimpleNamespace

import pytest

from tools.procesio.errors import UsageError
from tools.procesio.handlers import process_screenshot as ps
from tools.procesio.layout import areas


def _sq(aid, x, y, parent=None, kind="square"):
    return {"id": aid, "parentId": parent,
            "customData": {"type": kind, "position": {"x": x, "y": y}}}


def _fe(aid, x, y, w, h):
    return {"id": aid, "parentId": None,
            "customData": {"type": "area", "position": {"x": x, "y": y},
                           "areaSize": {"width": w, "height": h}}}


# --- geometry -------------------------------------------------------------------------

def test_a_square_action_is_drawn_from_its_top_left_with_the_label_centred_under_it():
    box = areas.node_boxes([_sq("a", 100, 200)])["a"]
    icon_centre = 100 + areas.NODE / 2
    assert box[0] == icon_centre - areas.HALF_W and box[2] == icon_centre + areas.HALF_W
    assert box[1] < 200                                   # room for the incoming arrow
    assert box[3] >= 200 + areas.NODE + areas.LABEL_H     # the name under the icon


def test_the_area_around_one_action_is_centred_on_it_and_holds_its_label():
    acts = [_sq("a", 100, 200)]
    rect = areas.fit(areas.node_boxes(acts), [("g", ["a"])], {"g": ("T", "one line")})["g"][0]
    cx = 100 + areas.NODE / 2
    assert abs((cx - rect[0]) - (rect[2] - cx)) < 1e-6    # same margin left and right
    assert rect[3] - (200 + areas.NODE) >= areas.LABEL_H  # the label is inside the border


def test_a_for_each_area_holds_the_loop_name_under_its_frame():
    rect = areas.fit(areas.node_boxes([_fe("L", 0, 0, 300, 200)]), [("g", ["L"])],
                     {"g": ("Loop", "")})["g"][0]
    assert rect[3] >= 200 + areas.LABEL_H


def test_the_centre_of_an_action_is_the_middle_of_its_icon():
    by = {"a": _sq("a", 100, 200), "L": _fe("L", 1000, 50, 300, 200),
          "c": _sq("c", 40, 70, parent="L")}
    assert areas.centre(by["a"], by) == (124.0, 224.0)
    assert areas.centre(by["c"], by) == (1064.0, 144.0)   # frame + relative + half an icon


def test_an_area_fitted_before_the_fix_still_claims_its_actions():
    # an old rectangle (fitted as if the position were the centre) must still read back
    # the same members, so areas saved earlier keep their meaning until the next re-fit
    x, y = 100, 200
    old = {"id": "s", "kind": 0, "position": {"x": x - 72, "y": y - 80},
           "dimension": {"width": 144, "height": 140}, "title": "T", "text": ""}
    assert areas.membership([_sq("a", x, y)], [old]) == {0: ["a"]}


# --- fitting the designer view ----------------------------------------------------------

def _flow(shapes=None, viewport=(0, 0, 1)):
    canvas = {"x": viewport[0], "y": viewport[1], "zoom": viewport[2], "shapes": shapes or []}
    return {"title": "t", "actions": [_sq("a", 100, 100), _sq("b", 700, 400)],
            "canvasData": json.dumps(canvas)}


def test_content_bbox_covers_actions_labels_and_shapes():
    shape = {"id": "s", "kind": 0, "position": {"x": -50, "y": -40},
             "dimension": {"width": 60, "height": 30}}
    bb = ps.content_bbox(_flow([shape]))
    assert bb[0] == -50 and bb[1] == -40
    assert bb[3] >= 400 + areas.NODE + areas.LABEL_H


@pytest.mark.parametrize("vp", [(0, 0, 1.0), (-300, 250, 0.7), (500, -900, 1.5), (40, 40, 0.5)])
def test_the_pan_puts_the_content_under_the_toolbars_and_the_drag_stays_on_the_canvas(vp):
    flow = _flow(viewport=vp)
    bb, view = ps.content_bbox(flow), ps.viewport_of(flow)
    fit = ps.plan_fit(bb, view)
    z = view["zoom"]
    # after the pan the content's top-left is just inside the chrome
    assert bb[0] * z + view["x"] + fit["pan"][0] == pytest.approx(ps.LEFT_BAR + ps.MARGIN, abs=0.2)
    assert bb[1] * z + view["y"] + fit["pan"][1] == pytest.approx(ps.TOP_BAR + ps.MARGIN, abs=0.2)
    # the whole content fits the window once panned
    assert (bb[2] - bb[0]) * z + ps.LEFT_BAR + ps.MARGIN <= fit["width"] - ps.RIGHT_BAR
    assert (bb[3] - bb[1]) * z + ps.TOP_BAR + ps.MARGIN <= fit["height"]
    # both drag ends are over the canvas (a pointer that leaves it stops the pan)
    for x, y in (fit["drag_from"], fit["drag_to"]):
        assert ps.LEFT_BAR < x < fit["width"] - ps.RIGHT_BAR
        assert ps.TOP_BAR < y < fit["height"]
    # and the drag starts on empty canvas: right of or below the content as it opens
    fx, fy = fit["drag_from"]
    assert fx > bb[2] * z + view["x"] or fy > bb[3] * z + view["y"]


# --- the action -----------------------------------------------------------------------

class FakeDriver:
    def __init__(self):
        self.calls = []
        self.page = SimpleNamespace(mouse=SimpleNamespace(
            move=lambda x, y, steps=1: self.calls.append(("move", x, y)),
            down=lambda: self.calls.append(("down",)),
            up=lambda: self.calls.append(("up",))))

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def set_viewport(self, w, h):
        self.calls.append(("viewport", w, h))

    def add_cookies(self, cookies):
        self.calls.append(("cookies", [c["name"] for c in cookies], cookies[0]["url"]))

    def goto(self, url):
        self.calls.append(("goto", url))

    def eval_js(self, _script):
        return 1

    def wait(self, _ms):
        pass

    def screenshot(self, path, full_page=True):
        self.calls.append(("shot", path, full_page))

    def diagnostics(self):
        return {"page_errors": [], "bad_responses": [{"url": "https://x.google.com/a", "status": 400}]}

    def current_url(self):
        return self._url

    _url = "https://procesio.app/admin/process/designer/P1#W1"


class FakeClient:
    def __init__(self, kind="userpass"):
        self.name, self.workspace_id = "acct", "W1"
        self.profile = {"type": kind, "web_base": "https://webapi.example",
                        "app_base": "https://app.example"}
        self._session = None

    def get(self, path):
        assert path == "/api/Projects/P1"
        return {"flow": _flow()}


def _ns(tmp_path, **over):
    base = dict(id="P1", out=str(tmp_path / "p.png"), no_fit=False, settle_ms=0, headed=False)
    base.update(over)
    return argparse.Namespace(**base)


def test_screenshot_signs_in_with_the_profile_cookies_before_opening_the_designer(tmp_path, monkeypatch):
    drv = FakeDriver()
    monkeypatch.setattr(ps, "_open_driver", lambda headless: drv)
    monkeypatch.setattr(ps.auth, "get_valid_cookies", lambda *a: {"__Host-procesio.access": "v"})
    out = ps.process_screenshot(FakeClient(), _ns(tmp_path))["result"]
    kinds = [c[0] for c in drv.calls]
    assert kinds.index("cookies") < kinds.index("goto")
    assert ("cookies", ["__Host-procesio.access"], "https://webapi.example") in drv.calls
    assert ("goto", "https://app.example/admin/process/designer/P1#W1") in drv.calls
    assert kinds.index("down") < kinds.index("up") < kinds.index("shot")
    assert out["signed_in"] and out["fit"]["pan"]
    assert out["bad_responses"] == []          # third-party noise is not reported


def test_no_fit_keeps_the_stored_view(tmp_path, monkeypatch):
    drv = FakeDriver()
    monkeypatch.setattr(ps, "_open_driver", lambda headless: drv)
    monkeypatch.setattr(ps.auth, "get_valid_cookies", lambda *a: {"c": "v"})
    out = ps.process_screenshot(FakeClient(), _ns(tmp_path, no_fit=True))["result"]
    assert out["fit"] is None and "down" not in [c[0] for c in drv.calls]


def test_an_api_key_profile_is_refused_with_the_way_out(tmp_path, monkeypatch):
    monkeypatch.setattr(ps, "_open_driver", lambda headless: pytest.fail("must not open a browser"))
    with pytest.raises(UsageError, match="username/password profile"):
        ps.process_screenshot(FakeClient("apikey"), _ns(tmp_path))
