#!/bin/bash
# Install Homebrew if it's not yet installed
if ! which brew; then
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/master/install.sh)"
fi

# Install elan and mathlibtools
brew install elan mathlibtools

# Install and configure VS Code
if ! which code; then
brew install --cask visual-studio-code
fi
code --install-extension jroesch.lean
