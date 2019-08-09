# Docs

Build the docs:

`make html`

This generates docs at docs/build/html that can be served.
During development, an easy way to preview is:

```commandline
cd build/html
python -m http.server
```

Afterward, you can remove the build:

`make clean`
