#!/bin/bash
# Install Homebrew
set -e

if ! which brew > /dev/null; then
    # Install Homebrew
    /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/master/install.sh)"
else
    # Update it, in case it has been ages since it's been updated
    brew update
fi

# workaround to fix broke MacOS testing
# hack for underlying  actions/runner-images issue #6459
brew install --overwrite python@3.10 python@3.11

brew install elan mathlibtools
elan toolchain install stable
elan default stable

# Install and configure VS Code
if ! which code > /dev/null; then
    brew install --cask visual-studio-code
fi
code --install-extension jroesch.lean
