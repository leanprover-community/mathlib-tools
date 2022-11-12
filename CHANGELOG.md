# Change log

## 1.3.0 (2022-11-13)

* Add `port-status` command

## 1.2.0 (2022-10-23)

* import-graph: allow to write raw dot file to ".rawdot" without layout
  info
* Add `--exclude-tactics` flag to exclude tactics in import-graph
* Add `--port-status` flag to the `import-graph` command to color node by
  porting status
* Add `--port-status-url` option to specify a url for the YaML file
  containing porting status information.

## 1.1.1 (2022-02-24)

* Fix mathlib update bug for project depending on mathlib

## 1.1.0 (2021-09-18)

* Add `reduce-imports` command
* Add `pull` command
* `get-mathlib-cache` no longer understands `--rev`; if you want to use a
  different mathlib version, edit your `leanproject.toml`. If you are trying to get
  the cache when working on mathlib itself, use `get-cache --rev`.
* Add `--fallback` to `get-cache` for traversing the git history to find an
  approximate cache.
* `get-cache` no longer modifies `.lean` files in the working directory.
* `mk-cache --force` no longer permits the working tree to be dirty.
* `mk-all` now correctly handles filenames with special characters.

## 1.0.0 (2020-11-10)

* Only look for .xz archives
* Increase tolerance to weird git setups
* Add pr command
* Add rebase command
* Add option --rev to get-cache and get-mathlib-cache
* Drop python 3.5 support

## 0.0.10 (2020-07-28)

* SSH handling tweaks

## 0.0.9 (2020-07-12)

* Add mk-all command
* Add decls command
* Many small fixes

## 0.0.8 (2020-05-25)

* Fix a bug and workaround some Windows bug

## 0.0.7 (2020-05-23)

* Try to download .xz-compressed olean archives

## 0.0.6 (2020-05-09)

* Add `leanproject get -b` to create a new branch

## 0.0.5 (2020-04-07)

* Add import-graph command
* Add delete-zombies command

## 0.0.4 (2020-03-24)

* Add get-mathlib-cache command
* Add --debug flag

## 0.0.3 (2020-03-11)

Switch from update-mathlib to leanproject

## 0.0.2 (2019-12-28)

Fix packaging issue

## 0.0.1 (2019-12-28)

Version PyPi release of old mathlib tools
