# Smart Document Finder 3.1 — Search-first UI

## Start

Run:

```powershell
python app.py
```

The terminal prompts for the document folder. You can also pass it directly:

```powershell
python app.py "C:\Users\YourName\Documents"
```

Use `--reindex` when you want a full rebuild.

## UI

- The user primarily sees the search box and language selector.
- Voice search is available from the microphone icon inside the search box.
- `Recent` is a toggle for the results drawer.
- Search results are hidden on startup and shown after a search.
- Clicking `Recent` again hides the drawer.
- Folder selection is not exposed inside the UI.
- There is no text-to-speech result control.
