# mathlib-tools

[![Build Status](https://travis-ci.org/leanprover-community/mathlib-tools.svg?branch=master)](https://travis-ci.org/leanprover-community/mathlib-tools)
[![Build status](https://ci.appveyor.com/api/projects/status/t353pkb62tep1rth?svg=true)](https://ci.appveyor.com/project/cipher1024/mathlib-tools)

This package contains several supporting tools for [Lean mathlib](https://leanprover-community.github.io/).

  - `update-mathlib` fetches precompiled olean files if you use mathlib as a dependency
  - `cache-olean` fetches precompiled olean files if you're working on mathlib
  - `setup-lean-git-hooks` automates the usage of `cache-olean` using git hooks

See also [the documentation in the mathlib repository](https://github.com/leanprover-community/mathlib/blob/8700aa7d78b10b65cf8db1d9e320872ae313517a/docs/contribute/index.md).

You can install `mathlib-tools` using [pip](https://pypi.org/project/mathlibtools/):
```
sudo pip3 install mathlibtools
```

If you are using NixOS, you can also install it using the bundled `default.nix` file:
```
nix-env -if https://github.com/leanprover-community/mathlib-tools/archive/master.tar.gz
```
