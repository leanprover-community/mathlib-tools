from git import Repo, InvalidGitRepositoryError # type: ignore
from github import Github # type: ignore
import configparser

def auth_github(repo: Repo) -> Github:
    config = repo.config_reader()
    try:
        return Github(config.get('github', 'user'), config.get('github', 'password'))
    except configparser.NoSectionError:
        print('Info: No github section found in \'git config\', we will use GitHub with no authentication')
        return Github()
    except configparser.NoOptionError:
        try:
            return Github(config.get('github', 'oauthtoken'))
        except configparser.NoOptionError:
            print("Info: No github 'user'/'password' or 'oauthtoken' keys found in git config, "
                  "we will use GitHub with no authentication.")
            print('You can create an OAuth token at https://github.com/settings/tokens/new (no scopes are required).')
            return Github()
