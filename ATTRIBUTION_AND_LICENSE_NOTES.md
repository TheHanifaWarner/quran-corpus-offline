# Attribution & License Notes

This document records what is known about the provenance and licensing of the
materials this tool depends on, and gives a conservative recommendation about what
is safe to publish. **This is not legal advice.** When in doubt, defer to the
original rights holders and obtain explicit permission.

---

## 1. The original project

| Field | Value |
| --- | --- |
| Project name | **Quranic Arabic Corpus** (Quranic Arabic Corpus / "quranic-corpus") |
| Original site | <https://corpus.quran.com> |
| Original author / lead | **Kais Dukes** |
| Created at | **Language Research Group, University of Leeds** |
| Current hosting/maintenance | associated with the **quran.com** community/maintainers (verify current status on the site) |
| Academic references | Dukes, K. & Habash, N. (2010), *Morphological Annotation of Quranic Arabic*, LREC 2010; Dukes, K., Atwell, E. & Habash, N. (2013), *Supervised Collaboration for Syntactic Annotation of Quranic Arabic*, Language Resources & Evaluation. |

**This repository is unofficial** and is not endorsed by, affiliated with, or
approved by any of the above unless they explicitly state so.

---

## 2. The morphology data file

- File: `quranic-corpus-morphology-0.4.txt` (Quranic Arabic Corpus, version 0.4).
- Source / official download: **<https://corpus.quran.com/download/>**.
- Licensing as published by the project: the Quranic Arabic Corpus annotation data
  is distributed by the project under the **GNU General Public License (GPL)**.
  - Practical implication: the *data* may generally be redistributed **with
    attribution and under the same GPL terms**, but the cleanest and most
    respectful path is for each user to download it themselves from the official
    page so they accept the official terms directly.
- **Action taken in this repo:** the full file is **not** shipped. Only a tiny
  attributed 7-line sample (`data/sample-morphology.txt`) is included for testing.
- **Verify before relying on this:** licensing statements can change between
  versions. Re-read the official download page for the exact current terms.

---

## 3. The Quranic Arabic text

- The Arabic Quranic text used by the Corpus is sourced from the **Tanzil Project**
  (<https://tanzil.net>).
- Tanzil text is provided under the **Tanzil terms of use / Creative Commons
  Attribution-NoDerivs**, which require attribution and forbid modification of the
  text, and restrict certain redistributions.
- **Action taken in this repo:** the Quranic text is not shipped; it is present
  only inside data the user downloads/caches themselves.

---

## 4. English translations shown on the Corpus site

- Translations such as **Sahih International, Pickthall, Yusuf Ali**, and others
  appear on `translation.jsp` and word-by-word pages.
- These are **third-party copyrighted works** owned by their respective
  translators/publishers. They are generally **not freely redistributable**.
- **This is the single biggest licensing risk** for redistributing any cached HTML.
- **Action taken in this repo:** no translations are included or redistributed.

---

## 5. Corpus page HTML / CSS / JS / images / treebank / ontology

- The page markup, styling, scripts, dependency-graph/treebank graphics, and
  ontology content on corpus.quran.com are the **copyrighted work of the Quranic
  Arabic Corpus project**.
- Caching them locally for personal study is one thing; **re-publishing** them is a
  separate act that needs permission.
- **Action taken in this repo:** none of these are included.

---

## 6. This repository's own code

- The Python application, launchers, and audit tooling are **original work** and
  are licensed under the **MIT License** (see `LICENSE`).
- MIT applies to the code only and grants **no rights** over any Corpus data, text,
  translation, or page content.

---

## 7. Uncertainty about redistributing the cached archive

Open questions that should be resolved **before** any cache is published:

1. **Translations** — redistributing cached `translation.jsp` / word-by-word pages
   would redistribute third-party translations. ❗ High risk without permission.
2. **GPL + non-GPL mix** — the cache mixes GPL morphology annotations, CC-ND Tanzil
   text, third-party translations, and the site's own copyrighted markup. These
   licenses are **not all mutually compatible for redistribution**.
3. **Site terms of service** — bulk copying/redistribution may be restricted by the
   site's terms even where individual licenses differ.
4. **Attribution chain** — a redistributed cache must carry correct, per-source
   attribution, which is hard to guarantee mechanically.

Because of (1)–(4), the safe default is: **do not redistribute the cache; ship code
that lets each user build their own cache locally.**

---

## 8. Recommendation: is the full cache ZIP safe to release now?

**No — do not release the full cache ZIP now.** Recommendation:

- ✅ **Publish the code-only repository now** (MIT code + docs + attribution). It
  contains no third-party content and is low-risk.
- ⛔ **Hold the full-cache ZIP** pending explicit permission. The cache bundles
  third-party translations and the Corpus project's own copyrighted pages/assets,
  whose licenses do not clearly permit redistribution.
- ✅ **Preferred alternative to a cache ZIP:** the included builder
  (`cache_corpus_pages.py`) lets each user create their own personal cache from the
  official source — no redistribution of third-party content by this project.
- If a cache archive is ever desired publicly, first obtain **written permission**
  from: the Quranic Arabic Corpus maintainers (site content + annotations), and the
  relevant **translation** rights holders; and confirm **Tanzil** redistribution
  terms for the text.

---

## 9. Takedown / transfer notice

This project intends to defer entirely to the original Quranic Arabic Corpus
project and the rights holders of any referenced content.

> If you are a rights holder (Quranic Arabic Corpus maintainers, a translation
> publisher, Tanzil, or the University of Leeds) and you object to any part of this
> project, please open an issue or contact the repository owner. Upon a reasonable
> request we will promptly **remove** the relevant material, **transfer** stewardship,
> or **take the repository down**. No claim of ownership, authority, or endorsement
> over the Corpus or its content is made or intended.
