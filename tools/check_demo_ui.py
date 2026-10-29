"""Optional browser acceptance for the loopback synthetic demo (Playwright + Chrome)."""

import argparse
import json
from pathlib import Path
from urllib.parse import urlsplit

from playwright.sync_api import sync_playwright


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("url")
    parser.add_argument("--chrome", default=r"C:\Program Files\Google\Chrome\Application\chrome.exe")
    parser.add_argument("--output", type=Path, default=Path("evidence/local/demo-ui"))
    args = parser.parse_args()
    assert urlsplit(args.url).hostname == "127.0.0.1", "Only the local demo is tested"
    args.output.mkdir(parents=True, exist_ok=True)
    reports, errors = [], []
    with sync_playwright() as pw:
        browser = pw.chromium.launch(executable_path=args.chrome, headless=True)
        for width, scheme in ((1280, "light"), (1280, "dark"), (360, "light"), (320, "dark")):
            context = browser.new_context(viewport={"width": width, "height": 1100},
                                          color_scheme=scheme, reduced_motion="reduce")
            page = context.new_page()
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.goto(args.url)
            page.wait_for_function("() => document.getElementById('app').dataset.ready === 'true'")
            assert page.locator('#model').get_attribute('data-renderer') == 'webgl-depth'
            assert page.locator('#model').get_attribute('data-cradle-opacity') == '0.18'
            # Crossing geometry: the near part of a long tilted shaft must
            # cover a block, its far part must be hidden, in either draw order.
            depth_check = page.evaluate("""() => {
              const layer=createDepthLayer(), flat=(z,color)=>({points:[[10,20,z],[190,20,z],[190,180,z],[10,180,z]],color});
              const shaft={points:[[0,80,1],[200,80,4],[200,120,4],[0,120,1]],color:[0,1,0,1]};
              const block=flat(2,[1,0,0,1]), sample=(polys,x)=>{
                const out=document.createElement('canvas');out.width=200;out.height=200;
                const c=out.getContext('2d');c.drawImage(layer.render(polys,200,200,1),0,0);
                return Array.from(c.getImageData(x,100,1,1).data);
              };
              const orders=[[shaft,block],[block,shaft]];
              const near=orders.map(p=>sample(p,40)),far=orders.map(p=>sample(p,180));
              const hidden=sample([shaft,block,flat(5,[0,0,1,.18])],180);
              const visible=sample([shaft,block,flat(.8,[0,0,1,.18])],180);
              return {near,far,hidden,visible};
            }""")
            assert all(v[1] > 250 and v[0] < 3 for v in depth_check['near']), depth_check
            assert all(v[0] > 250 and v[1] < 3 for v in depth_check['far']), depth_check
            assert depth_check['hidden'][:3] == [255, 0, 0], depth_check
            assert 195 < depth_check['visible'][0] < 220 and 35 < depth_check['visible'][2] < 60, depth_check
            expected = page.request.get(args.url + "api/demo").json()
            assert not expected["hardware_connected"] and expected["data_kind"] == "synthetic"
            for case in expected["scenarios"]:
                page.select_option("#scenario", case["id"])
                for stage in ("before", "after"):
                    page.click("#" + stage)
                    assert page.locator("#app").get_attribute("data-stage") == stage
                    for i, key in enumerate(("a", "b")):
                        shown = float(page.locator("#mass-" + key).inner_text().split()[0].replace(",", "."))
                        assert abs(shown - case[stage]["planes"][i]["equivalent_mass_g"]) <= .00051
                    plan = case[stage]["removal_plan"]
                    assert page.locator("#app").get_attribute("data-removal") == plan["status"]
                    rows = page.locator("#removal-actions tr")
                    assert rows.count() == len(plan["actions"])
                    for i, action in enumerate(plan["actions"]):
                        assert rows.nth(i).locator("td").nth(0).inner_text() == action["counterweight"]
                        shown = float(rows.nth(i).locator("td").nth(1).inner_text().replace(",", "."))
                        assert abs(shown - action["mass_g"]) <= .00051
            page.select_option("#scenario", "asymmetric")
            page.click("#before")
            assert page.locator("button[data-cw]").count() == 8
            for i in range(1, 9):
                page.click(f"button[data-cw='CW{i}']")
                assert page.locator("#app").get_attribute("data-selected-cw") == f"CW{i}"
                assert f"CW{i}:" in page.locator("#counterweight-info").inner_text()
            page.click("button[data-cw='CW3']")
            page.click("#zero")
            assert page.locator("#app").get_attribute("data-phase") == "zero"
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 1")
            page.click("#view")
            assert page.locator("#view").inner_text() == "Общий вид"
            page.click("#view")
            page.click("#play")
            assert page.locator("#play").inner_text() == "Следующая фаза"
            # Both strings must retain length even in the magnified drawing.
            error = page.evaluate("""async () => {
              const data=await (await fetch('/api/demo')).json();
              const canvas=document.createElement('canvas');
              const model=createCradle(canvas);let error=0;
              for(const s of data.scenarios)for(const stage of ['before','after']){
                model.set(s[stage],data.rpm,10,data.geometry);
                for(let j=0;j<40;j++)for(const x of [-.34,.34]){
                  const q=model.transform(j*Math.PI/20)([x,0,0]);
                  error=Math.max(error,Math.abs(Math.hypot(q[0]-x,q[1],q[2]-.8)-.8));
                }
              }
              return error;
            }""")
            assert error < 1e-8, error
            page.screenshot(path=str(args.output / f"demo-{width}-{scheme}.png"), full_page=True)
            reports.append(dict(width=width, scheme=scheme, fixed_string_length_error_m=error,
                                scenarios=3, stages=2, values_match_python=True, overflow=False,
                                counterweights=8, removal_plan_matches_python=True, zero_mark=True,
                                depth_occlusion=depth_check, renderer='webgl-depth', translucent_cradle=True))
            if width == 1280:
                page.click('#zero')
                page.locator('#model').screenshot(path=str(args.output / f'model-zero-{scheme}.png'))
                page.click('#play')
                page.locator('#model').screenshot(path=str(args.output / f'model-phase-{scheme}.png'))
                bounds = page.locator('#model').bounding_box()
                page.mouse.move(bounds['x'] + bounds['width'] / 2, bounds['y'] + 220)
                page.mouse.down()
                page.mouse.move(bounds['x'] + bounds['width'] / 2 + 170, bounds['y'] + 240, steps=8)
                page.mouse.up()
                page.locator('#model').screenshot(path=str(args.output / f'model-rotated-{scheme}.png'))
            context.close()
        # Real-time playback stops by itself and supports a manual pause.
        context = browser.new_context(viewport={"width": 1280, "height": 1100})
        page = context.new_page()
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(args.url)
        page.wait_for_function("() => document.getElementById('app').dataset.ready === 'true'")
        page.click("#play")
        page.wait_for_function("() => document.getElementById('play').textContent === 'Показать движение'", timeout=12000)
        page.click("#play")
        assert page.locator("#play").inner_text() == "Пауза"
        page.click("#play")
        assert page.locator("#play").inner_text() == "Показать движение"
        context.close()
        context = browser.new_context(viewport={"width": 1280, "height": 1100})
        context.add_init_script("""const original=HTMLCanvasElement.prototype.getContext;
          HTMLCanvasElement.prototype.getContext=function(type,...args){
            return type==='webgl'?null:original.call(this,type,...args);
          };""")
        page = context.new_page()
        page.on('pageerror', lambda error: errors.append(str(error)))
        page.goto(args.url)
        page.wait_for_function("() => document.getElementById('app').dataset.ready === 'true'")
        assert page.locator('#model').get_attribute('data-renderer') == 'unavailable'
        assert 'г' in page.locator('#mass-a').inner_text()
        page.click('#after')
        assert page.locator('#app').get_attribute('data-stage') == 'after'
        context.close()
        browser.close()
    assert not errors, errors
    result = dict(ok=True, browser_errors=errors, layouts=reports, finite_playback=True,
                  numerical_results_without_webgl=True)
    (args.output / "checks.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
