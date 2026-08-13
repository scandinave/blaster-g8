# Bootstrap Icons (bundled sources)

The application's icons come from [Bootstrap Icons](https://icons.getbootstrap.com)
**v1.13.1**, MIT licensed (see `LICENSE`). Only the icons actually used are
vendored here — the whole set is ~2000 files.

These `.svg` are *build* sources, not runtime assets: nothing loads them (or
anything else over the network) while the application runs. They are rasterized
into alpha masks by `tools/build_icons.py`, which writes the generated module
`soundblaster_g8/gui/icon_data.py`; that module is what ships and what the GUI
reads. Re-run the tool after adding or replacing an icon here.

To add one, download it from upstream and add the mapping in
`soundblaster_g8/gui/icons.py`:

```bash
curl -O https://raw.githubusercontent.com/twbs/icons/main/icons/<name>.svg
python tools/build_icons.py
```
