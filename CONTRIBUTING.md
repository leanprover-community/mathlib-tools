# Contributing to mathlib-tools

Pull requests are welcome. The heaving lifting is done in
`mathlibtools/lib.py` (which you can also use as a library for other
python programs that want to manipulate Lean projects). Command line
parsing is done in `mathlibtools/leanproject.py`, using the 
[click library](https://click.palletsprojects.com/en/7.x/).

Please do not add code without type annotations. And of course you need
to be able to run `mypy mathlibtools` without any error.

##  Testing

We run our tests using [pytest](https://docs.pytest.org/en/latest/).
As usual with pytest, no much will work as expected if you don't install
the package you want to test. So the first step is to run 
`pip install .` in the toplevel folder of this repository, the one
containing `setup.py` (as usual, depending on your python setup, `pip`
could be called `pip3`, and you may need administration permissions if
you want to make a system-wide install). 
If you want to quickly modify code and retest, it is more convenient to
use "editable install", by running `pip install -e .` which creates a
link to your working copy instead of copying it (see 
[pip's documentation](https://pip.pypa.io/en/stable/reference/pip_install/#editable-installs)
if needed).
Once the package is installed, you can run `pytest` from the toplevel
folder.

Our continuous integration tests use python 3.5 to 3.8. 
This can be done locally using
[tox](https://tox.readthedocs.io/en/latest/). For this you need `tox`
of course, but also various versions of python. One convenient way
to ensure that is to use [pyenv](https://github.com/pyenv/pyenv).
After setting up `pyenv` and installing, say python 3.5.6, 3.6.8,
3.7.2 and 3.8.0 (using `pyenv install 3.5.6` etc.), you can create,
inside the toplevel folder of your working copy, a
file `.python-version` containing
```
3.8.0
3.7.2
3.6.8
3.5.6
```
Then you can run `tox` to run our test suite against all those versions
of python.

Tests in `tests/test_functional.py` are end-to-end tests that actually
download things from the internet and write on disk (in temporary
folders). They are pretty slow. Other test files are meant for unit tests.
Don't hesitate to add tests!

