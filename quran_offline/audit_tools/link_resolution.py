"""Phase 5: browser-style link/asset/form resolution on served pages.

For a set of served pages, extract every href/src/action, then:
  * confirm no active http(s) ref points off-localhost
  * GET every localhost ref and record status (resolves / not-cached / broken)
  * confirm form actions stay local
  * confirm CSP header forbids outbound connections

Local-only; the only HTTP traffic is to 127.0.0.1.
"""
from __future__ import annotations

import collections
import urllib.parse
import urllib.request
from html.parser import HTMLParser

PAGES = [
    "/wordbyword.jsp?chapter=1&verse=1",
    "/translation.jsp?chapter=1&verse=1",
    "/treebank.jsp?chapter=1&verse=1",
    "/qurandictionary.jsp?q=rHm",
    "/concept.jsp?id=adam",
]


class P(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.links, self.srcs, self.actions = [], [], []

    def handle_starttag(self, tag, attrs):
        d = dict(attrs)
        if "href" in d and d["href"]:
            self.links.append(d["href"])
        if "src" in d and d["src"]:
            self.srcs.append(d["src"])
        if tag == "form" and d.get("action"):
            self.actions.append(d["action"])


def get(base, path):
    try:
        with urllib.request.urlopen(base + path, timeout=20) as r:
            return r.status, r.headers.get("Content-Type", ""), r.headers.get("Content-Security-Policy", ""), r.read()
    except urllib.error.HTTPError as e:
        return e.code, "", "", b""
    except Exception as e:
        return 0, str(e), "", b""


def is_offlocal(ref):
    pu = urllib.parse.urlparse(ref)
    return pu.scheme in ("http", "https") and pu.hostname not in ("127.0.0.1", "localhost", None)


def ignored(ref):
    r = ref.strip().lower()
    return not r or r.startswith(("#", "mailto:", "javascript:", "data:", "about:", "tel:"))


def main():
    import sys
    base = f"http://127.0.0.1:{sys.argv[1] if len(sys.argv) > 1 else '8799'}"
    grand = collections.Counter()
    off_local_refs = []
    for path in PAGES:
        status, ctype, csp, body = get(base, path)
        html = body.decode("utf-8", "replace")
        p = P()
        p.feed(html)
        all_refs = p.links + p.srcs
        local_refs = set()
        for ref in all_refs:
            if ignored(ref):
                continue
            if is_offlocal(ref):
                off_local_refs.append((path, ref))
                continue
            pu = urllib.parse.urlparse(ref)
            local_refs.add(urllib.parse.urlunparse(("", "", pu.path or "/", "", pu.query, "")))
        # check form actions
        bad_actions = [a for a in p.actions if is_offlocal(a)]
        # resolve local refs
        res = collections.Counter()
        broken = []
        for ref in sorted(local_refs):
            s, ct, _, b = get(base, ref)
            if s == 200:
                # distinguish "Not cached" body
                if b"<h1>Not cached</h1>" in b:
                    res["not-cached(200)"] += 1
                else:
                    res["ok(200)"] += 1
            else:
                res[f"http{s}"] += 1
                broken.append((ref, s))
        grand.update(res)
        connect_none = "connect-src 'none'" in csp
        form_self = "form-action 'self'" in csp
        print(f"\n{path}")
        print(f"  CSP present: {bool(csp)} | connect-src none: {connect_none} | form-action self: {form_self}")
        print(f"  refs total={len(all_refs)} local-unique={len(local_refs)} off-local={sum(1 for pp,_ in off_local_refs if pp==path)}")
        print(f"  form actions={p.actions} off-local-actions={bad_actions}")
        print(f"  local resolution: {dict(res)}")
        if broken:
            print(f"  BROKEN: {broken[:5]}")
    print("\n=== TOTALS ===")
    print(f"  off-localhost active refs across all pages: {len(off_local_refs)}")
    if off_local_refs:
        for pp, r in off_local_refs[:10]:
            print(f"    {pp}  ->  {r}")
    print(f"  aggregate local ref resolution: {dict(grand)}")


if __name__ == "__main__":
    import urllib.error
    main()
