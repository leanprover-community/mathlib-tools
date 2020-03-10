import setuptools

with open("README.md", "r") as fh:
    long_description = fh.read()

setuptools.setup(
    name="mathlibtools",
    version="0.0.3",
    author="The mathlib community",
    description="Lean prover mathlib supporting tools.",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/leanprover-community/mathlib-tools",
    packages=setuptools.find_packages(),
    entry_points={
        "console_scripts": [
            "leanproject = mathlibtools.leanproject:cli",
        ]},
    package_data = { 'mathlibtools': ['post-commit', 'post-checkout'] },
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: Apache Software License",
        "Operating System :: OS Independent" ],
    python_requires='>=3.5',
    install_requires=['toml', 'PyGithub', 'certifi', 'gitpython', 'requests',
                      'Click', 'tqdm', 'paramiko']
)
