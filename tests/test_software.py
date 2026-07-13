import json

from verdict import repro


def _fake_urlopen(payload=None, raise_exc=None):
    """Return a urlopen stand-in: a context manager whose .read() yields json.dumps(payload),
    or one that raises `raise_exc` (to simulate an unreachable resolver)."""
    class _Resp:
        def __init__(self, data):
            self._data = data
        def read(self):
            return self._data
        def __enter__(self):
            return self
        def __exit__(self, *a):
            return False

    def _open(url, timeout=10):
        if raise_exc is not None:
            raise raise_exc
        return _Resp(json.dumps(payload).encode())
    return _open


_HIT = {"hits": {"hits": [{"_source": {"item": {"name": "ImageJ"}}}]}}


def test_software_no_rrid_abstains():
    # A named tool with no RRID can't be resolved — abstain (rule), never a guessed PASS, no citation.
    f = repro.check_software("ImageJ", "", "images were analyzed in ImageJ")
    assert f.result == "INSUFFICIENT" and f.kind == "software" and f.method == "rule", (f.result, f.method)
    assert not f.citation


def test_software_resolves_to_pass(monkeypatch):
    monkeypatch.setattr(repro.urllib.request, "urlopen", _fake_urlopen(_HIT))
    f = repro.check_software("ImageJ", "RRID:SCR_003070", "ImageJ (RRID:SCR_003070)")
    assert f.result == "PASS" and f.method == "rule"
    assert f.citation == "RRID:SCR_003070", f.citation
    assert "ImageJ" in f.detail


def test_software_finds_rrid_in_evidence_not_just_the_field(monkeypatch):
    # The SCR id may only appear in the verbatim evidence phrase, not the extracted rrid field.
    monkeypatch.setattr(repro.urllib.request, "urlopen", _fake_urlopen(_HIT))
    f = repro.check_software("ImageJ", "", "analyzed in ImageJ (RRID:SCR_003070)")
    assert f.result == "PASS" and f.citation == "RRID:SCR_003070"


def test_software_unresolvable_rrid_abstains(monkeypatch):
    # An RRID that resolves to no registered tool must abstain, never PASS.
    monkeypatch.setattr(repro.urllib.request, "urlopen", _fake_urlopen({"hits": {"hits": []}}))
    f = repro.check_software("MadeUpTool", "RRID:SCR_999999", "MadeUpTool (RRID:SCR_999999)")
    assert f.result == "INSUFFICIENT" and not f.citation


def test_software_unreachable_resolver_abstains(monkeypatch):
    # A network failure degrades to abstain — never crashes a review, never guesses a PASS.
    monkeypatch.setattr(repro.urllib.request, "urlopen", _fake_urlopen(raise_exc=OSError("no network")))
    f = repro.check_software("ImageJ", "RRID:SCR_003070", "")
    assert f.result == "INSUFFICIENT" and not f.citation


def test_software_gate_never_fails(monkeypatch):
    # Software identity is a citation-completeness check, not a misidentification risk: it is only ever
    # PASS or INSUFFICIENT — a software finding must never fabricate a deterministic FAIL / "Needs fixes".
    monkeypatch.setattr(repro.urllib.request, "urlopen", _fake_urlopen({"hits": {"hits": []}}))
    for args in [("ImageJ", "", ""), ("ImageJ", "RRID:SCR_999999", ""), ("", "", "")]:
        assert repro.check_software(*args).result != "FAIL", args


def test_run_gates_includes_software(monkeypatch):
    # run_gates over an already-extracted resource dict emits a software finding for each tool.
    monkeypatch.setattr(repro.urllib.request, "urlopen", _fake_urlopen(_HIT))
    res = {"cell_lines": [], "antibodies": [], "rigor": {},
           "software": [{"name": "ImageJ", "rrid": "RRID:SCR_003070", "evidence": "ImageJ (RRID:SCR_003070)"}]}
    rep = repro.run_gates(res, "Images were analyzed in ImageJ (RRID:SCR_003070).")
    sw = [f for f in rep.findings if f.kind == "software"]
    assert len(sw) == 1 and sw[0].result == "PASS" and sw[0].citation == "RRID:SCR_003070", rep.findings
