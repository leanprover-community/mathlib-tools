# mathlib-tools

![Test on Linux](https://github.com/leanprover-community/mathlib-tools/workflows/Test%20on%20Linux/badge.svg)
![Test on MacOS](https://github.com/leanprover-community/mathlib-tools/workflows/Test%20on%20MacOS/badge.svg)
![Test on Windows](https://github.com/leanprover-community/mathlib-tools/workflows/Test%20on%20Windows/badge.svg)

This package contains `leanproject`, a supporting tool for [Lean mathlib](https://leanprover-community.github.io/).

See also [the documentation in the mathlib repository](https://github.com/leanprover-community/mathlib/blob/8700aa7d78b10b65cf8db1d9e320872ae313517a/docs/contribute/index.md).

You can install `mathlib-tools` using [pip](https://pypi.org/project/mathlibtools/):
```
sudo pip3 install mathlibtools
```

If you are using NixOS, you can also install it using the bundled `default.nix` file:
```
nix-env -if https://github.com/leanprover-community/mathlib-tools/archive/master.tar.gz
```
