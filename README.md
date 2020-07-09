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

Those tools use python3, at least python 3.5, which is the oldest
version of python supported by the python foundation. They can be
installed using [pip](https://pypi.org/project/mathlibtools/). The basic
install command is thus:
```
pip install mathlibtools
```

Depending on your setup `pip` may be called `pip3` to distinguish it from its
deprecated python2 version. The above command may complain about
permissions. This can be solved by running it as root, but this is not
recommended in general. You can run `pip install --user mathlibtools`
to install it in your home directory, and then make sure that
`$HOME/.local/bin/` is in your shell path. 

Alternatively, a convenient way to hide those issues is to use
[pipx](https://pipxproject.github.io/pipx/) (this requires python 3.6 or
newer). On Linux, you can do:
```bash
python3 -m pip install --user pipx
python3 -m pipx ensurepath
source ~/.profile
pipx install mathlibtools
```
and on MacOS
```bash
brew install gmp coreutils python3 pipx
pipx ensurepath
source ~/.bash_profile
pipx install mathlibtools
```

If you are using NixOS, you can also install mathlib tools using the bundled `default.nix` file:
```
nix-env -if https://github.com/leanprover-community/mathlib-tools/archive/master.tar.gz
```

If you want to use the latest development version, you can clone this
repository, go to the repository folder, and run `pip install .`.

## Usage

See the [dedicated page](https://leanprover-community.github.io/leanproject.html) on the community website.
