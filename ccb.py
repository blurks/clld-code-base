import os
import re
import sys

from time import sleep

from github import Github, GithubException


VERS_REGEX = re.compile(r"migrations/versions/(.*fix_polymorphic_type.py$|.*update_unique_null.py$)")


def print_repo_info(repo):
    print("{name}: {url} {ar}".format(name=repo.name, url=repo.html_url,
                                      ar="(ARCHIVED)" if repo.archived else ""))


def get_content(repo):
    """get the content of the repo as list of paths."""
    content = [c.path
               for c in repo.get_contents("")
               if c.path in ["alembic.ini", "migrations"]]
    if "migrations" in content:
        content.extend([c.path
                        for c in repo.get_contents("migrations")
                        if c.path == "migrations/versions"])
    if "migrations/versions" in content:
        content.extend([c.path
                        for c in repo.get_contents("migrations/versions")])
    return content


def is_relevant(repo):
    if repo.archived:
        return False

    c = get_content(repo)

    if (("migrations" in c or "alembic.ini" in c) and
        ("migrations/versions" not in c or
         [m for m in map(VERS_REGEX.match, c) if m] or
         not repo.get_contents("migrations/versions"))):
        return True
    return False


def rm(repo, path, message):
    """delete a file identified by a path from the repo."""
    f = repo.get_contents(path)
    repo.delete_file(f.path, message, f.sha)


def rm_recursive(repo, path, message):
    """delete the given directory."""
    try:
        content = [c for c in repo.get_contents(path)]
    except GithubException as e:
        print("Error: {}: {}".format(e.data["message"], path))
        return
    except TypeError as e:  # if repo.get_contents returns a singleton instead of a list
        print("Error: {} is apparently not a directory ({})".format(path, e))
        return
    for c in content:
        if c.type == "dir":
            rm_recursive(repo, c.path, message)
        else:
            repo.delete_file(c.path, message, c.sha)


def process_versions(repo):
    """delete 'migrations/versions/.*(fix_polymorphic_type.py|update_unique_null.py)'.
    If these files don't exist, return false. If they exist and were
    successfully deleted, return True.
    """
    try:
        versions = repo.get_contents("migrations/versions")
    except GithubException:  # if there is no 'migrations/versions/' directory
        return False

    del_versions = [v for v in versions if VERS_REGEX.match(v.path)]
    if del_versions:
        print_repo_info(repo)
        print("\t- delete files:\n\t\t{}".format("\n\t\t".join([v.path for v in del_versions])))

        for v in del_versions:
            try:
                repo.delete_file(v.path, "delete {}".format(v.path), v.sha)
            except GithubException as e:
                print("Error: {}: {}".format(e.data["message"], v.path))

        return True
    else:
        return False


def process_migrations(repo):
    """if 'migrations/versions' doesn't exist or is empty, delete 'alembic.ini'
    and 'migrations/'.  Return True if something was deleted.
    """
    content = get_content(repo)
    if "alembic.ini" in content and "migrations" not in content:
        print_repo_info(repo)
        print("\t- contains 'alembic.ini' without 'migrations/'. " +
              "Don't know what to do\n")
        return False
    elif "migrations" in content and \
         ("migrations/versions" not in content or not repo.get_contents("migrations/versions")):
        print_repo_info(repo)
        print("\t- 'migrations/versions' does not exist or is empty\n")

        rm_recursive(repo, "migrations", "delete 'migrations/'")
        rm(repo, "alembic.ini", "delete 'alembic.ini'")

        return True
    else:
        return False


def main():
    if sys.argv[1:]:
        access_token = sys.argv[1]
    elif "GH_TOKEN" in os.environ.keys():
        access_token = os.environ["GH_TOKEN"]
    else:
        print("please set the GH_TOKEN env variable or provide a github " +
              "access token as commandline parameter\n" +
              "Usage: {} [access_token]".format(sys.argv[0]))
        exit(1)

    g = Github(login_or_token=access_token)

    try:
        org = g.get_organization("clld")
    except GithubException as e:  # probably authentication failure
        print("Error: {}".format(e.data["message"]))
        exit(1)

    # all_repos = org.get_repos(type="public", sort="full_name", direction="asc")
    # print("total: {}".format(all_repos.totalCount))
    # all_repos = [g.get_repo("clld/tsammalex")]
    all_repos = [g.get_repo("clld/afbo"), g.get_repo("clld/tsammalex")]
    forks = []
    for repo in all_repos:
        print(repo.name)
        if is_relevant(repo):
            print("relevant")
            myfork = repo.create_fork()
            sleep(1)
            forks.append(myfork)

            process_versions(myfork)
            process_migrations(myfork)

    print("cleaned up {} repos:".format(len(forks)))
    for f in forks:
        print_repo_info(f)
        f.delete()


if __name__ == "__main__":
    main()
