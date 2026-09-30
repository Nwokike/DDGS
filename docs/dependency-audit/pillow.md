# Pillow (PIL 12.3.0) — Dependency Audit for DDGS

- Installed version: **12.3.0** (`PIL/_version.py`), 97 `.py` files in
  `.venv/Lib/site-packages/PIL/` (115 entries incl. 7 `*.pyd` C extensions,
  `*.pyi` stubs, `__pycache__`).
- Why it is installed: **transitive dev-only dependency, zero direct imports in
  DDGS code** (`grep -rn "from PIL|import PIL" src/ tests/` → no hits). Chain:
  `dev` group `flet[cli,desktop]` → `flet-cli 1.0.1` → `flet-platform-assets`
  → `pillow` (uv.lock). `flet-cli` also pulls `qrcode 8.2`, whose optional
  `qrcode.image.pil.PilImage` backend (`new_image/drawrect/save`) is the only
  other PIL consumer in the venv. Pillow is **not** in `[project].dependencies`,
  so production/`flet build` (Android) does not get it unless the build host
  resolves dev tooling.
- How DDGS handles images today (no PIL): `src/components/results/cards_media.py`
  `_image_card` renders `ft.Image(src=r.thumbnail or r.image_url)` at 165×120
  tiles; `detail_sheet.py` shows full image from remote URL; `downloader.py`
  saves bytes via `services/media_downloader.py` with no re-encode/resize;
  `SearchResult.width/height` (shown as "WxH") comes from ddgs metadata, not
  local probing.

## 1. API INVENTORY (capability-level, concrete names)

- Open/identify: `Image.open(fp)` lazy-load + `im.load()`/`verify()`, `Image.init/preinit`,
  `registered_extensions()`, `UnidentifiedImageError`; `ImageFile.Parser` incremental feed.
- Create/generate: `Image.new(mode,size,color)`, `frombytes/frombuffer/fromarray/fromarrow`,
  `effect_mandelbrot/effect_noise/linear_gradient/radial_gradient`.
- Save/encode: `im.save(fp,format,**params)` (`quality/optimize/progressive` JPEG,
  `compress_level` PNG, `save_all/append_images/duration/loop` multi-frame),
  `Image.register_save/register_save_all`.
- Formats in `PIL/__init__._plugins` (~47): JPEG, PNG, GIF, BMP, TIFF, WebP, AVIF,
  JPEG2000, ICO, ICNS, PSD, PDF (read), EPS, TGA, PCX, PPM, SGI, DDS, BLP, FLI,
  QOI, MPO, DCX/XVThumb, plus stub plugins (BUFR/GRIB/HDF5 = metadata-only).
- Resize/resample: `im.resize(size,resample,box,reducing_gap)` with
  `Resampling.{NEAREST,BOX,BILINEAR,HAMMING,BICUBIC,LANCZOS}`; `im.reduce(factor)`;
  `im.thumbnail(size)` in-place aspect-preserving downscale (default BICUBIC);
  `im.draft(mode,size)` reader-side fast JPEG downscale.
- Crop/compose/geometry: `im.crop(box)`, `im.paste(im2,box,mask)`,
  `Image.alpha_composite/blend/composite/merge`, `im.split/getchannel/putalpha`,
  `im.rotate(angle,resample,expand,center,translate)`,
  `im.transpose(Transpose.{FLIP_LEFT_RIGHT,FLIP_TOP_BOTTOM,ROTATE_90/180/270,TRANSPOSE,TRANSVERSE})`,
  `im.transform(size,Transform.{AFFINE,PERSPECTIVE,QUAD,MESH},data)` + `ImageTransform` classes,
  `im.effect_spread`, `ImageOps.{contain,cover,pad,fit,scale,crop,expand,deform}`.
- EXIF/metadata: `im.getexif()` (mutable `Exif`: `tobytes/load/hide_offsets`),
  `ExifTags.TAGS/GPSTAGS/IFD`, `ImageOps.exif_transpose(in_place=)`,
  `im.getxmp()`, `im.info/tag/tag_v2` (PNG/TIFF), `im.get_child_images()` (MPO).
- Draw shapes: `ImageDraw.Draw(im)` → `arc/bitmap/chord/ellipse/circle/line/shape/
  pieslice/point/polygon/regular_polygon/rectangle/rounded_rectangle`, plus
  `floodfill(xy,value,border,thresh)`, `ImageDraw2.Draw` Pen/Brush/Font vector API,
  `PSDraw.PSDraw` PostScript output.
- Draw text: `ImageDraw.text/multiline_text` (`anchor/align/stroke_width/
  stroke_fill/features/direction/language`), `textlength/textbbox/multiline_textbbox`,
  `ImageText.Text` wrapping engine.
- Fonts: `ImageFont.truetype(file,size,index,encoding,layout_engine)`,
  `FreeTypeFont.{getname,getmetrics,getbbox,getmask/getmask2,font_variant,
  get/set_variation_by_*}` (variable fonts), `load/load_path/load_default`
  (bundles Aileron via base64 — no system font needed), `TransposedFont`.
- Filters: `im.filter(ImageFilter.{BLUR,CONTOUR,DETAIL,EDGE_ENHANCE(_MORE),EMBOSS,
  FIND_EDGES,SHARPEN,SMOOTH(_MORE},GaussianBlur,BoxBlur,UnsharpMask,
  Kernel(size,kernel,scale,offset),RankFilter,MedianFilter,MinFilter,MaxFilter,
  ModeFilter,Color3DLUT.generate/transform})` (convolution rejects mode `P`).
- Ops/enhance/color: `ImageOps.{autocontrast,colorize,equalize,flip,grayscale,
  invert,mirror,posterize,solarize}`, `ImageEnhance.{Color,Contrast,Brightness,
  Sharpness}(im).enhance(factor)` (factor 1.0 = identity, blend-based),
  `ImageColor.{getrgb,getcolor}` (CSS names/#rgb/rgb()/hsl()/hsv()/rgba()),
  `ImageChops.{lighter,darker,difference,multiply,screen,invert,constant,duplicate}`,
  `ImageMath` lambda engine, `ImageMorph.{LutBuilder,MorphOp}`,
  `ImageCms.profileToProfile` ICC color management (`littlecms2` module),
  `ImagePalette.{raw,make_linear_lut,make_gamma_lut,negative,random,sepia,wedge}`,
  `im.convert/quantize/remap_palette/putpalette/getpalette/point/getcolors/
  getbbox/histogram/entropy/getextrema/getprojection/getpixel/putpixel/putdata`.
- Animation/sequences: `im.seek/tell`, `ImageSequence.Iterator/all_frames`,
  GIF `n_frames/is_animated/disposal_method/duration/loop`, WebP animated
  (`duration/loop/lossless/quality/alpha_quality/method`), `im.show()` +
  `ImageShow.{register,show}` viewer chain (Windows/Mac/XDG/EOG/IPython).
- Capture/clipboard: `ImageGrab.grab(bbox,include_layered_windows,all_screens,window)`
  (win32/macOS/X11+fallbacks to gnome-screenshot/grim/spectacle),
  `ImageGrab.grabclipboard()` (win32/macOS/wl-paste|xclip).
- Capability probing: `features.{check,version,get_supported}` over modules
  (pil/tkinter/freetype2/littlecms2/webp/avif), codecs (jpg/jpg_2000/zlib/libtiff),
  features (raqm/fribidi/harfbuzz/libjpeg_turbo/mozjpeg/zlib_ng/libimagequant/xcb);
  `python -m PIL` (`report.py`) prints full install/format matrix.
- Qt/Tk/Win bridges (unused by Flet): `im.toqimage/toqpixmap`, `fromqimage/fromqpixmap`,
  `ImageTk.PhotoImage`, `ImageQt`, `ImageWin.HWND/Dib`.

## 2. LATENT CAPABILITIES FOR DDGS (ranked, all currently unused)

1. Image-result thumbnails — `Image.open(BytesIO).thumbnail((320,240))` (+`draft`
   for JPEG) before caching to disk: `_image_card` grid currently hot-loads full
   remote files at 165×120 tiles; local downscaled cache = faster grids, less RAM.
2. WebP conversion on download — `im.save(...,format="WEBP",quality=80,method=6)` in
   `media_downloader.py`: smaller files for metered/Android users vs raw JPEG/PNG.
3. EXIF strip on save (privacy) — re-save downloads without `exif` (`save()` drops
   EXIF unless re-attached; `getexif()` to audit first): DDGS is privacy-branded,
   downloaded photos currently keep GPS/camera tags.
4. GIF/animated preview — `ImageSequence.Iterator` + `n_frames/is_animated/duration`:
   show animated badge / first-frame still in `cards_media.py` instead of a static fetch.
5. On-the-fly crop for grid tiles — `ImageOps.fit(im,(165,120),centering=)` server-side
   equivalent: uniform tiles with no CSS-stretch, replaces `BoxFit.COVER` guesswork.
6. Progress/placeholder overlays — `ImageDraw.rounded_rectangle/text` + `ImageFont.
   load_default()`: branded skeleton/placeholder tiles and download-progress badges
   drawn locally (Aileron bundled → safe on Android, no system font needed).
7. Share cards / OG images — `Image.new + ImageDraw.text/multiline_text + paste(logo)`:
   generate shareable PNGs for saved pages (title + thumbnail + branding).
8. QR raster output — `qrcode.make(url,image_factory=PilImage).save()` for a
   "share result as QR" action; `qrcode` is already in the venv via flet-cli, PIL is
   its only raster backend.
9. Local image metadata in details — `Image.open` header probe (`im.size/mode/format`,
   `getexif()` dimensions): show real dimensions/format in `detail_sheet.py` instead of
   trusting ddgs metadata (`r.width` may be empty).
10. Lightbox preprocessing — `ImageOps.{exif_transpose,contain}` + `ImageEnhance.
    Sharpness/Contrast`: auto-orient phone photos (EXIF orientation 6/8 is currently
    ignored) and fit-to-screen before display.

## 3. GOTCHAS

- Mode conversions: filters/ops reject palette mode (`P`) — call `im.convert("RGB"/"RGBA")`
  first; alpha work needs `RGBA` + `putalpha`/`alpha_composite` (JPEG has no alpha —
  convert drops it silently); `ImageOps._lut` only supports `L/RGB/1`.
- Decompression-bomb guard: `Image.MAX_IMAGE_PIXELS` ≈ 89.5 MP
  (`1024**3//4//3`); over-limit `open/load` raises `DecompressionBombError`
  (warning first) — hostile image-search results can trip this; catch it or set
  `Image.MAX_IMAGE_PIXELS = None` only with explicit trust.
- Fonts on Android: `truetype()` needs a real TTF path (no guaranteed system fonts
  in the APK) — bundle a font asset or use `ImageFont.load_default()` (embedded
  Aileron); FreeType keeps files open on Windows (512-handle limit — prefer BytesIO).
- Memory on big images: `open()` is lazy but `load/resize/filter` decodes fully;
  use `draft()` (JPEG) / `reduce()` / `thumbnail(reducing_gap=)` and `getbbox` early-outs;
  `ImageFile.LOAD_TRUNCATED_IMAGES=True` rescues broken hosts but hides corruption.
- Save pitfalls: default JPEG `quality=75`; PNG needs `optimize=True` to slim;
  multi-frame needs `save_all=True, append_images=[...]`; TIFF `compression=` must be
  explicit (default raw); WebP/AVIF need `features.check("webp"/"avif")` at runtime.
- Production-packaging note: Pillow rides the **dev** group (`flet-cli`); importing
  PIL in `src/` without adding `pillow` to `[project].dependencies` breaks
  `flet build apk` — any latent capability above must add the floor pin first.

## 4. COVERAGE

- Read completely (16): `__init__.py`, `ImageFilter.py`, `ImageColor.py`,
  `ImageOps.py`, `ImageEnhance.py`, `ImageGrab.py`, `features.py`, `_util.py`,
  `ImageShow.py` (API/register/show + viewer classes), `ImageDraw.py` + `ImageDraw2.py`
  + `ImageFont.py` (all method signatures + `truetype`/`load_default` bodies),
  `Image.py` (all ~140 def/class signatures + `thumbnail`/`open`/`MAX_IMAGE_PIXELS`
  regions), `ExifTags.py` (Base/GPS/IFD enums + TAGS/GPSTAGS maps), `TiffImagePlugin.py`
  (compression/save-all paths), `WebPImagePlugin.py` + `GifImagePlugin.py`
  (animation/save params).
- Skimmed one-line-each via def/class grep (~81 remaining `.py`): all other format
  plugins, `ImageSequence/Stat/Chops/Math/Morph/Transform/Palette/Cms/Path/Mode/Text/
  File`, `JpegPresets`, `ContainerIO/TarIO`, `ImageQt/Tk/Win`, `FontFile/GdImageFile`,
  `PSDraw`, `report.py`, `qrcode/image/pil.py` handoff; DDGS side: `pyproject.toml`,
  `uv.lock` (pillow/qrcode/flet chains), `cards_media.py`, `detail_sheet.py`,
  `downloader.py`, `media_downloader.py` (no PIL refs), full `src/` PIL grep (zero hits).
- Total: **97 `.py` files** — 16 fully read, ~81 skimmed.
