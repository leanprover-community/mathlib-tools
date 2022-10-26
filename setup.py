import setuptools
from os import path

this_directory = path.abspath(path.dirname(__file__))

with open(path.join(this_directory, "README.md"), encoding='utf-8') as fh:
    long_description = fh.read()

with open(path.join(this_directory, 'mathlibtools', '_version.py'), encoding='utf-8') as f:
    exec(f.read())

setuptools.setup(
    name="mathlibtools",
    version=__version__,  # from _version.py
    author="The mathlib community",
    description="Lean prover mathlib supporting tools.",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/leanprover-community/mathlib-tools",
    packages=setuptools.find_packages(),
    entry_points={
        "console_scripts": [
            "leanproject = mathlibtools.leanproject:safe_cli",
        ]},
    package_data = { 'mathlibtools': ['post-commit', 'post-checkout', 'decls.lean'] },
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: Apache Software License",
        "Operating System :: OS Independent" ],
    python_requires='>=3.6',
    install_requires=['toml>=0.10.0', 'PyGithub', 'certifi', 'gitpython>=2.1.11', 'requests',
                      'Click', 'tqdm', 'networkx', 'pydot',
                      'PyYAML>=3.13', 'atomicwrites', "dataclasses; python_version=='3.6'"]
)
