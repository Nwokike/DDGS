# lxml — Dependency Audit (DDGS)

- Installed: **6.1.3** (`LXML_VERSION (6, 1, 3, 0)`), `lxml.__version__ == "6.1.3"`, libxml2/libxslt statically linked in wheel.
- Declared floor: `lxml>=6.1.1` in `pyproject.toml` (see §3 ceiling rule).
- DDGS usage today: **exactly one call site** — `src/services/agent_files.py:88-98` `extract_links()` does `from lxml import html as lxml_html; tree = lxml_html.fromstring(html)` + `tree.xpath("//a/@href")` with manual `urljoin(base, href)` + scheme/host dedupe. `src/services/search_service.py:436` `extract_url()` delegates extraction to `ddgs.extract(url, fmt=...)` (ddgs' own lxml path), not to lxml directly. No other `lxml` import in `src/`.

## 1. COMPLETE API INVENTORY

### etree — parsing entry points
- `etree.parse(source, parser=None, base_url=None)` — file path / file object / URL; returns `ElementTree`.
- `etree.fromstring(text, parser=None, base_url=None)` — bytes/str → single `Element`; workhorse.
- `etree.fromstringlist(strings, parser=None)` — parse from sequence of chunks.
- `etree.XML(text, parser=None, base_url=None)` / `etree.HTML(text, parser=None, base_url=None)` — strict-XML vs lenient-HTML convenience wrappers around `fromstring`.
- `etree.tostring(el_or_tree, encoding=None, method="xml", xml_declaration=None, pretty_print=False, with_tail=True, standalone=None, doctype=None, exclusive=False, inclusive_ns_prefixes=None, with_comments=True, strip_text=False)` — `method ∈ {xml, html, text, c14n, c14n2}`; `encoding="unicode"` → str.
- `etree.tostringlist(...)` / `etree.tounicode(..., method, pretty_print)` / `etree.dump(elem, pretty_print=True, with_tail=True)` / `etree.indent(tree, space="  ", level=0)` — chunked/str/debug/pretty-print variants.
- `etree.Element(tag, attrib, nsmap, **extra)` / `etree.SubElement(parent, tag, ...)` / `etree.Comment(text)` / `etree.ProcessingInstruction(target, text)` / `etree.Entity(name)` / `etree.CDATA(data)` / `etree.QName(ns_or_el, tag)` / `etree.iselement(x)` / `etree.register_namespace(prefix, uri)` — node constructors + tests.
- `etree.adopt_external_document(capsule, parser=None)` — adopt libxml2 doc capsule from another binding.

### etree — `_Element` API (works on `lxml.html.HtmlElement` too)
- Data: `.tag/.text/.tail/.attrib/.nsmap/.prefix/.sourceline/.base` (+ `getroottree().docinfo.URL/encoding/doctype/root_name/xml_version`).
- Attrs: `.get(k, default)/.set(k, v)/.keys()/.values()/.items()/.attrib` mapping.
- Mutation: `.append(el)/.extend(seq)/.insert(i, el)/.remove(el)/.clear(keep_tail)/.replace(old, new)/.addnext(el)/.addprevious(el)`.
- Navigation: `.getparent()/.getchildren()/.getnext()/.getprevious()/.getroottree()/.getpath()` + `.index(child, start, stop)`.
- Iteration: `.iter(tag)/.getiterator(tag)/.iterchildren(tag, reversed)/.iterdescendants(tag)/.iterancestors(tag)/.itersiblings(tag, preceding)/.itertext(tag, with_tail=True)/.iterfind/.getiterator()` (+ `ElementChildIterator/SiblingsIterator/AncestorsIterator/ElementDepthFirstIterator/ElementTextIterator` classes).
- Search: `.find(path, namespaces)/.findtext(path, default, namespaces)/.findall(path, namespaces)/.iterfind(path, namespaces)` (ElementPath subset) vs `.xpath(path, namespaces, extensions, regexp=True, smart_strings=True)` (full XPath 1.0 + EXSLT) vs `.cssselect(expr, translator='xml')` (needs `cssselect` package — NOT installed here).
- `.makeelement(tag, attrib, nsmap, **extra)` — same-class factory for custom lookup builds.
- `_ElementTree`: `.getroot()/.getpath(el)/.write(f, encoding, method, pretty_print, with_tail)/.xslt()/parseid()/docinfo` + `.write_c14n()`; `ElementTreeContentHandler/ElementTreeProducer/saxify(tree, handler)` in `sax.py` bridge to SAX.

### etree — XPath / XSLT / validation
- `etree.XPath(path, namespaces, extensions, regexp=True, smart_strings=True)` — precompiled expression, callable on tree/el.
- `etree.XPathElementEvaluator(el, ...)` / `etree.XPathDocumentEvaluator(tree, ...)` — bind once, evaluate many (`evaluator("a/b")`).
- `etree.FunctionNamespace(uri)` + `etree.Extension(module, ...)` — register Python XPath/XSLT extension functions (`ns['name'] = fn`).
- `etree.XSLT(xslt_input, extensions, regexp=True, access_control)` — compile stylesheet; call `transform(tree, profile_run=False, **strparams)` → `_XSLTResultTree` (has `.xslt_profile`, str() serializes); `etree.XSLTAccessControl(deny_network/read_file/write_file/read_network/write_network)` + `etree.XSLTError/XSLTParseError/XSLTApplyError`.
- Validators: `etree.DTD / RelaxNG / XMLSchema / Schematron / ISO Schematron (lxml.isoschematron)` (`assertValid(tree)` / `validate(tree)` + `.error_log`), `etree.DocumentInvalid`; canonicalize via `tostring(method="c14n"/"c14n2")`; XInclude via `tree.xinclude()`; `ElementInclude.include(elem, loader, base_url)` (XInclude `xi:include` with `default_loader/_lxml_default_loader`, `FatalIncludeError`).

### etree — parser configuration (the knobs that matter)
- `etree.XMLParser(encoding, attribute_defaults=False, dtd_validation=False, load_dtd=False, no_network=True, recover=False, huge_tree=False, resolve_entities='internal', remove_blank_text=False, remove_comments=False, remove_pis=False, strip_cdata=True, collect_ids=True, ns_clean=False, compact=True, schema=None, target=None)` — strict default; `recover=False` means broken input raises.
- `etree.HTMLParser(encoding, remove_blank_text=False, remove_comments=False, remove_pis=False, no_network=True, target=None, schema=None, recover=True, compact=True, collect_ids=True, huge_tree=False)` — lenient default (`recover=True`); same `no_network=True` default.
- `etree.XMLPullParser / HTMLPullParser(events, ...)` + `etree.iterparse(source, events, tag, ...)` / `etree.iterwalk` — incremental parsing for giant feeds; `etree._FeedParser.feed(data)/close()`; custom `target` parser interface (`start/end/comment/pi/data`).
- Key flags: `recover` (tolerate broken markup), `huge_tree` (lift libxml2 10M-node / entity-amplification limits), `no_network` (block external DTD/schema fetches — security default True), `resolve_entities` (`'internal'` safe vs `True` expands + fetches), `remove_blank_text/remove_comments/remove_pis/strip_cdata/compact/collect_ids` (memory/speed trims), `encoding` override, `schema` inline validation.

### lxml.html — the scrape layer DDGS actually wants
- `html.fromstring(html, base_url=None, parser=None, **kw)` — Lenient fragment-or-doc parse; sets `.base_url` when given (DDGS currently omits this — bug-adjacent, see §2.1).
- `html.document_fromstring(html, parser=None, ensure_head_body=False)` — always full `<html><head><body>` doc.
- `html.fragments_fromstring(html, no_leading_text=False, base_url=None, parser=None)` — list of els + strings.
- `html.fragment_fromstring(html, create_parent=False, base_url=None, parser=None)` — exactly-one-element or `ParserError`; `create_parent='div'` wraps multi-root/text.
- `html.parse(filename_or_url, parser=None, base_url=None)` — file/URL direct parse.
- `html.tostring(el, encoding, method="html", with_tail=True, doctype=None)` — `method="text"` gives de-tagged text; `html.html_to_xhtml(xhtml_parser)` / `html.xhtml_to_html` converters; `html.open_in_browser(doc)` debug; `html.submit_form(form, extra_values, open_http)` / `html.open_http_urllib(method, url, values)`.
- `HtmlElement.text_content()` — concatenated text of subtree (no tags); tail handling is the Markdown-cleanliness knob.
- `HtmlElement.cssselect(expr, translator='html')` — same `cssselect` extra requirement as etree.
- `HtmlElement.make_links_absolute(base_url=None, resolve_base_href=True, handle_failures=None)` — `handle_failures ∈ {None(raise), 'ignore', 'discard'}`; rewrites in place incl. `<base href>` consumption.
- `HtmlElement.resolve_base_href(handle_failures)` / `.rewrite_links(link_repl_func, resolve_base_href=True)` — general link-rewriting primitive behind `make_links_absolute`.
- `HtmlElement.iterlinks()` — yields `(element, attribute, link, pos)` across `a/img/link/script/form/object/embed/video/audio/source/blockquote` etc. per `html.defs.link_attrs` (covers far more than `//a/@href`); text-position `pos` ordering is reversed-in-string to allow in-place replacement; `<base href>` NOT applied.
- `HtmlElement.find_rel_links(rel)` / `.find_class(name)` / `.get_element_by_id(id)` / `.drop_tree()` (drop el + text) vs `.drop_tag()` (drop tag, keep children) / `.forms/.body/.head/.label/.base_url/.classes` (mutable `Classes` set with `add/discard/toggle/update`).
- Forms: `FormElement.action/method/inputs/fields/form_values` + `FieldsDict/InputGetter/InputMixin/TextareaElement/SelectElement/InputElement/CheckboxGroup/RadioGroup/CheckboxValues/MultipleSelectOptions/LabelElement` + `formfill.fill_form/fill_form_html/insert_errors/insert_errors_html` (prefill + validation-error injection).
- `html.builder` (`E` ElementMaker for html, `CLASS(v)`/`FOR(v)` reserved-word helpers) + top-level `lxml.builder.ElementMaker(namespace, nsmap, makeelement)` / `E` factory — programmatic HTML/XML construction.
- `html.html5parser.document_fromstring/fragments_fromstring/fragment_fromstring/fromstring/parse(guess_charset, parser)` (html5lib-compatible tree, `HTMLParser` subclass) + `html.soupparser.fromstring/parse/convert_tree(beautifulsoup, makeelement, **bsargs)` (BeautifulSoup fallback — BS4 NOT installed) + `html.ElementSoup` (legacy `BeautifulSoup` glue) + `html.diff.htmldiff/parse_html/cleanup_html/tokenize` (page-change diffing) + `html.defs` (tag/attr allow-lists).

### objectify / cssselect / clean / misc
- `lxml.objectify`: `fromstring/XML/parse(Element, DataElement, attrib, nsmap, _pytype, _xsi)` + typed els (`IntElement/FloatElement/StringElement/BoolElement/NoneElement/NumberElement/ObjectifiedDataElement/ObjectifiedElement`) + `ElementMaker` + `pyannotate/xsiannotate/annotate/deannotate(pytype, xsi)` + `set_default_parser/makeparser(**kw)` + `enable_recursive_str/dump` — attribute-heavy XML as Python objects (RSS/OPML/sitemap-shaped data).
- `lxml.cssselect.CSSSelector(css, namespaces, translator='xml'|'html'|'xhtml')` (subclass of `etree.XPath`; `LxmlTranslator/LxmlHTMLTranslator` + `:contains()` extension) — thin wrapper, **requires `cssselect` package; NOT installed in this venv** (import raises with install hint).
- Sanitizer: `lxml.html.clean` is a **shim only** — raises `ImportError` directing to `lxml_html_clean` (`clean_html/clean/Cleaner/autolink/autolink_html/word_break/word_break_html`); **`lxml_html_clean` NOT installed** so no sanitizer is available today.
- `lxml.sax` (SAX bridge), `lxml.ElementInclude` (XInclude), `lxml.pyclasslookup` (custom Python element classes), `lxml._elementpath` (`find/findall/iterfind/findtext/xpath_tokenizer`), `lxml.doctestcompare` (`LXMLOutputChecker/LHTMLOutputChecker/install`), `lxml.usedoctest`, `lxml.get_include()` (C headers for compiled extensions).

## 2. LATENT CAPABILITIES FOR DDGS (ranked by UX impact)

1. **`HtmlElement.make_links_absolute(base_url, handle_failures='ignore')` + pass `base_url` to `fromstring`** — TODAY `extract_links()` calls `fromstring(html)` with no `base_url` then hand-rolls `urljoin(base, href)` over `//a/@href` only; misses `img/src`, `srcset`, `link/href`, `form/action`, `video/source`, honors no `<base href>`. One call (`tree.make_links_absolute(base)` after parsing with `base_url=base`) fixes relative links/images in every saved/crawled page and kills a whole class of broken-link complaints. Cheapest, highest-visible win.
2. **`HtmlElement.iterlinks()` instead of `tree.xpath("//a/@href")`** — yields every link-bearing `(el, attr, link, pos)` per `defs.link_attrs` (images, stylesheets, feeds, media). Swap the single XPath for `iterlinks()` + scheme filter and the crawler (`scrape_site`, `MAX_CRAWL_PAGES=8`) discovers media/feed pages it currently never sees; also enables save-time asset inventory (what to download alongside the page).
3. **Sanitization before AI + save (`lxml_html_clean.Cleaner`, NOT installed)** — strip `script/style/nav/footer/form` + event attrs before `save_page`/chat context: fewer tokens per page (direct cost saving), no script noise in Markdown, XSS-safe rendered HTML. Requires adding `lxml_html_clean` (mind §3 ceiling — resolve from same index as lxml). Until then, poor-man's version: `tree.xpath('//script|//style|//noscript')` + `drop_tree()`.
4. **`recover=True` HTMLParser + explicit `no_network=True` for untrusted pages** — `lxml.html` already recovers, but the code never configures the parser; constructing `etree.HTMLParser(recover=True, no_network=True, huge_tree=False, remove_comments=True)` and passing it to `fromstring(html, parser=...)` makes broken-page tolerance + no-SSRF-by-parser explicit instead of accidental. Same pattern gives `remove_blank_text/remove_pis/strip_cdata` trims for the Markdown pipeline.
5. **`text_content()` + `tostring(method="text")` + `drop_tree/drop_tag` for the Markdown path** — `save_page(fmt="text_markdown")` currently trusts `ddgs.extract`; a local `text_content()` fallback (with `with_tail` control via `method="text"` serialization) produces cleaner offline/saved text than raw HTML dumps, and `drop_tree()` on boilerplate before extraction is a 5-line readability boost.
6. **Targeted XPath for structured extraction (titles/prices/tables/meta)** — `//meta[@property='og:*']/@content`, `//table//tr`, `//*[contains(@class,'price')]` — enables result-card enrichment (price, rating, og:image) and table-to-markdown without a new dependency. `XPathDocumentEvaluator` reuse for repeated queries on one crawl.
7. **`document_fromstring(ensure_head_body=True)` for saved HTML fidelity** — saved `.html` files from fragments render inconsistently; parsing via `document_fromstring` guarantees a complete doc before `_write_text`.
8. **`objectify` for sitemap/RSS/OPML crawls** — `objectify.fromstring` turns sitemap XML / RSS feeds into attribute-access Python (`feed.channel.item[*].link`), far less code than manual XPath when expanding `scrape_site` to feed-following.
9. **`rewrite_links()` for offline bundles** — rewrite every link to local file names when saving a crawled site so the Downloads/DDGS folder browses offline; generalizes #1.
10. **`huge_tree=True` + `iterparse` for giant pages/feeds** — opt-in guard for pathological pages (huge tables, giant sitemaps) instead of current all-or-nothing parse; `HTMLPullParser` streams multi-MB crawl targets without spiking mobile RAM.
11. **Encoding/charset handling (`HTMLParser(encoding=...)`, `docinfo.encoding`, `html5parser(guess_charset=...)`)** — non-UTF8 pages currently depend on ddgs guessing; explicit encoding fallback chain kills mojibake in saved files.
12. **XSLT + `formfill` + `diff.htmldiff`** — niche: XSLT for XML search sources, `formfill` for prefilling scraped forms, `htmldiff` for "page changed since last scrape" in the 24h cache layer.

## 3. GOTCHAS

- **VERSION CEILING — DO NOT RAISE THE FLOOR.** Owner rule, also pinned in `pyproject.toml` comments: `pypi.flet.dev` (the Android-build index) tops out at **lxml 6.1.1** while PyPI has 6.1.3 (this venv). Floor is `lxml>=6.1.1` deliberately. Raising it (even to the installed 6.1.3) breaks only the APK job with `No matching distribution found`. Keep `>=6.1.1`, never `==6.1.3`.
- **Compiled wheel per ABI.** lxml ships `etree/objectify/builder/sax/_elementpath/_difflib/diff` as `cp312-win_amd64.pyd` here; Android needs its own ABI wheel from the flet index — pure-Python shims (`cssselect.py`, `sax.py`, `builder.py`) travel, compiled parts do not. Test crawl paths on-device after any parser-flag change.
- **Parser network defaults are safe but must stay explicit.** Both `XMLParser` and `HTMLParser` default `no_network=True`; flipping `resolve_entities=True`, `load_dtd=True`, or `no_network=False` on untrusted scrape input re-opens SSRF/entity-expansion. Never accept parser kwargs from page content.
- **`recover` differs by parser.** `HTMLParser(recover=True)` default tolerates tag soup; `XMLParser(recover=False)` default raises on the same input (sitemap/RSS path must catch `etree.ParserError`/`LxmlSyntaxError` or opt into `recover=True` + `huge_tree` for hostile feeds).
- **`fragment_fromstring` is strict-single-element.** Multiple roots or leading/trailing non-whitespace text raises `ParserError`; use `fragments_fromstring` (plural) or `fragment_fromstring(..., create_parent='div')` for arbitrary page snippets — the crawler's per-card HTML hits this constantly.
- **`iterlinks` ignores `<base href>`; `make_links_absolute` consumes it.** Call `make_links_absolute` (or `resolve_base_href`) before reading `.base_url`-relative links, and note it mutates in place / strips the `<base>` tag.
- **lxml.html ≠ BeautifulSoup.** `soupparser`/`ElementSoup` need BS4 (not installed); `text_content()` concatenates without whitespace normalization; `.text` vs `.tail` split surprises Markdown converters (use `method="text"` serialization or explicit tail joins); `cssselect()` needs the missing `cssselect` package; `clean` needs the missing `lxml_html_clean` package — both raise `ImportError`, they do not degrade gracefully.
- **`//a/@href` misses most links and `urljoin` needs a valid base.** Current `extract_links` skips `javascript:`/`mailto:` correctly but also drops protocol-relative edge cases when `base` is malformed; `make_links_absolute(handle_failures='ignore'|'discard')` handles this centrally.

## 4. COVERAGE

- **29/29 `.py` files** under `site-packages/lxml/` (incl. `lxml/html/`) enumerated via `find` and inspected: every module-level `def/class` signature + docstring sampled (`__init__`, `cssselect`, `builder`, `sax`, `ElementInclude`, `pyclasslookup`, `_elementpath`, `doctestcompare`, `html/__init__` 1927 lines, `html/clean` shim, `html/defs`, `html/builder`, `html/formfill`, `html/html5parser`, `html/soupparser`, `html/diff`, `html/ElementSoup`, `isoschematron/__init__`, `includes/__init__`).
- **6/28 `.pyx/.pxi` API surfaces** read for exact constructor params (`etree.pyx` 3859 lines: element/tree/XPath entry points; `objectify.pyx` 2148 lines; `parser.pxi` XML/HTMLParser kwargs; `xpath.pxi` evaluator/XPath; `xslt.pxi` XSLT + access control; `serializer.pxi` method/encoding flags); 7 compiled `.pyd` verified present (`etree/objectify/builder/sax/_elementpath/html/_difflib/html/diff`).
- **Live verification** in project venv (`lxml 6.1.3`, `LXML_VERSION (6,1,3,0)`): `dir(lxml.html)` export list, `cssselect` import → absent, `lxml_html_clean` import → absent (confirms shim-only status).
- **Consumer grep**: `src/services/agent_files.py` (sole direct importer, `extract_links` + `scrape_site`/`save_page`), `src/services/search_service.py:436` (`extract_url` → `ddgs.extract`), `pyproject.toml` floor + ceiling comment; no `iterlinks/make_links_absolute/text_content/Cleaner/cssselect/objectify/XSLT` usage anywhere in `src/`.
