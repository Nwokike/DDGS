## Fix Plan: Reader, BottomSheet Expand, SearchBar

### 1. Content Reader Fixes (`content_reader_screen.py`)

**Add exit button**: Add a prominent "X" (close) button in AppBar actions that always exits the reader, regardless of back stack state. The existing back arrow handles history navigation; the X always exits.

**Add all 5 format options**: Currently only shows Markdown/Plain/Rich. Add Raw HTML (`text`) and Raw Bytes (`content`) to match the full `EXTRACT_FORMATS` list from `core/constants.py`.

**Add save-to-file**: Import `_save_bytes_content` and `_save_text_content` from `components.results.downloader`. Add a save icon button in AppBar that saves the current content to file.

**Fix back button**: When `_url_stack` is empty, always call `_exit_reader()` instead of silently doing nothing.

### 2. BottomSheet Expand to Reader (`detail_sheet.py` + `content_fetcher.py`)

**detail_sheet.py**: Add an "Open in Full Reader" outlined button below the primary action for non-media results. This calls `page._ddgs_controller.open_content_reader(url, content)` to push the full reader.

**content_fetcher.py**: In the 75% preview BottomSheet header, add an "expand" icon button (fullscreen icon) that:
1. Closes the current BottomSheet
2. Pushes the content reader with the current URL and content
3. When the reader is closed, the user returns to the results screen

### 3. SearchBar Replacement (`home_screen.py`)

Replace the plain `ft.TextField` with `ft.SearchBar`:
- `bar_leading`: search icon
- `bar_trailing`: paste button
- `bar_hint_text`: dynamic per tab
- `on_submit`: trigger search
- `on_change`: update query state
- `full_screen=True` for modern mobile experience
- Style with Outfit font, primary focus color, proper padding

### Files to modify:
- `src/screens/content_reader_screen.py` — exit button, all formats, save
- `src/components/results/detail_sheet.py` — add "Open in Reader" button
- `src/components/results/content_fetcher.py` — add expand-to-reader in preview header
- `src/screens/home_screen.py` — replace TextField with SearchBar

### Verification:
- `ruff check src/`
- `flet run` — test extract flow, link navigation, reader exit, save, format switching, search bar