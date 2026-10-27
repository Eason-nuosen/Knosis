"""knowledge view: the agent writes a self-contained page; Knosis checks it is offline-only and the knowledge is unchanged."""

from knosis.knowledge import layout, load_units, view, write_units

from test_consolidate import base, unit  # noqa: F401


def fake_agent(monkeypatch, edit):
    calls = []

    def run(cmd, *args, **kw):
        calls.append(cmd)
        edit(len(calls))
        return type("R", (), {"returncode": 0})()

    monkeypatch.setattr(view.subprocess, "run", run)
    monkeypatch.setattr(view.webbrowser, "open", lambda url: calls.append(("open", url)))
    monkeypatch.setattr(view, "browser", lambda: None)  # the headless JavaScript check is covered separately
    return calls


def test_view_prompt_lists_forms(base):
    write_units(layout(base).units, [unit("a"), unit("b", status="merged", merged_into="a")])
    text = view.prompt(base, request="只看订单表")
    assert "1 条活跃、1 条已失效" in text and "知识图谱：还没有" in text and "只看订单表" in text


def test_view_checks_offline_and_unchanged_knowledge(base, monkeypatch):
    write_units(layout(base).units, [unit("a")])
    page = view.page(base)

    def remote_then_fixed(n):
        html = '<script src="https://cdn.example/d3.js"></script>' if n == 1 else '<a href="https://x.org">ok</a><svg></svg>'
        page.write_text(f"<html>{html}</html>")

    calls = fake_agent(monkeypatch, remote_then_fixed)
    result = view.run(base, agent="codex")
    assert result["issues"] == [] and result["generated"] and len([c for c in calls if c[0] != "open"]) == 2
    assert calls[-1] == ("open", page.as_uri())

    # existing page, no --refresh / --request: just open it
    calls = fake_agent(monkeypatch, lambda n: None)
    assert view.run(base)["generated"] is False and calls == [("open", page.as_uri())]

    def touch_knowledge(n):
        write_units(layout(base).units, load_units(layout(base).units) + [unit(f"x{n}")])

    calls = fake_agent(monkeypatch, touch_knowledge)
    result = view.run(base, refresh=True)
    assert any("knowledge layer" in i for i in result["issues"]) and not any(c[0] == "open" for c in calls)
    assert [u["id"] for u in load_units(layout(base).units)] == ["a"]  # restored


def test_view_reports_script_errors(base, monkeypatch):
    page = view.page(base)
    page.parent.mkdir(parents=True)
    page.write_text("<html></html>")
    monkeypatch.setattr(view, "browser", lambda: "/bin/chrome-headless-shell")
    stderr = '[1027/1:INFO:CONSOLE:101] "Uncaught TypeError: x is undefined", source: file:///p/index.html (101)\n'
    monkeypatch.setattr(view.subprocess, "run", lambda *a, **k: type("R", (), {"stderr": stderr, "returncode": 0})())
    assert any("Uncaught TypeError" in i for i in view.issues(base, None))
