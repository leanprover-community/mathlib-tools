#!/bin/bash
# Install Homebrew
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/master/install.sh)"

# Install dependencies
brew install gmp coreutils python3 pipx

# Install Elan
# At startup, Bash sources .bash_profile, or if that doesn't exist, .profile.
# Elan adds itself to the PATH in .bash_profile, or if that doesn't exist, .profile.
# pipx only adds itself to the PATH in .bash_profile.
# So we will create .bash_profile if it doesn't exist yet, ensuring .profile still gets loaded after installing pipx.
if ! [ -r ~/.bash_profile ]; then
echo '[ -r ~/.profile ] && source ~/.profile' >> ~/.bash_profile
fi
curl https://raw.githubusercontent.com/Kha/elan/master/elan-init.sh -sSf | sh

# Install mathlib supporting tools
pipx ensurepath
source ~/.bash_profile
pipx install mathlibtools

# Install and configure VS Code
if ! which code; then
brew install --cask visual-studio-code
fi
code --install-extension jroesch.lean
