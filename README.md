# mathlib-tools

![Test on Linux](https://github.com/leanprover-community/mathlib-tools/workflows/Test%20on%20Linux/badge.svg)
![Test on MacOS](https://github.com/leanprover-community/mathlib-tools/workflows/Test%20on%20MacOS/badge.svg)
![Test on Windows](https://github.com/leanprover-community/mathlib-tools/workflows/Test%20on%20Windows/badge.svg)

This package contains `leanproject`, a supporting tool for [Lean mathlib](https://leanprover-community.github.io/).

## Installation

In principle, you should install those tools as part of the 
[global Lean installation procedure](https://leanprover-community.github.io/get_started.html#regular-install) recommended by the Lean community. 
Read what what remains of this section only if you want more details
about this specific part of the procedure (the tools described here won't give
you anything if Lean itself is not available).

### Released version

#### `pipx`

The tools in this repository use python3, at least python
3.6, which is the oldest version of python supported
by the python foundation. They can be installed using
[pip](https://pypi.org/project/mathlibtools/). The basic install command
for the latest released version is thus:
```bash
python3 -m pip install mathlibtools
```

The above command may complain about permissions. This can be solved
by running it as root, but this is not recommended in general. You can
run `python3 -m pip install --user mathlibtools` to install it in your
home directory (make sure that `$HOME/.local/bin/` is on your shell path
afterwards), but an even better way is to use
[pipx](https://pipxproject.github.io/pipx/):

```bash
python3 -m pip install --user pipx
python3 -m pipx ensurepath
source ~/.profile
pipx install mathlibtools
```

#### `macOS`

If you are on macOS, the recommended way to install is via homebrew,
which will handle the above Python installation for you:

```bash
brew install mathlibtools
```

#### `NixOS`

If you are using NixOS, you can also install mathlib tools using the
bundled `default.nix` file:

```
nix-env -if https://github.com/leanprover-community/mathlib-tools/archive/master.tar.gz
```

### Development version

If you want to use the latest development version, you can clone this
repository, go to the repository folder, and run `pip install .`.

## Usage

See the [dedicated page](https://leanprover-community.github.io/leanproject.html) on the community website.
