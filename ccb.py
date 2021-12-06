import os
import re
import sys

from time import sleep

from github import Github, GithubException


def print_repo_info(repo):
    print("{name}: {url} {ar}".format(name=repo.name, url=repo.html_url,
                                      ar="(ARCHIVED)" if repo.archived else ""))


def get_content(repo):
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


def rm(repo, path, message):
    f = repo.get_contents(path)
    repo.delete_file(f.path, message, f.sha)


def rm_recursive(repo, path, message):
    try:
        content = [c for c in repo.get_contents(path)]
    except GithubException as e:
        print("Error: {}: {}".format(e.data["message"], path))
        return
    for c in content:
        if c.type == "dir":
            rm_recursive(repo, c.path, message)
        else:
            repo.delete_file(c.path, message, c.sha)


def process_versions(repo):
    """delete 'migrations/versions/.*(fix_polymorphic_type.py|update_unique_null.py)'.
    If these files don't exist, return false. If they exist and were successfully
    deleted, return True.
    """
    try:
        versions = repo.get_contents("migrations/versions")
    except GithubException:
        return None

    regex = re.compile(r".*fix_polymorphic_type.py$|.*update_unique_null.py$")

    del_versions = [v for v in versions if regex.match(v.path)]
    if del_versions:
        fork = repo.create_fork()
        sleep(1)  # wait for github to complete forking

        print_repo_info(repo)
        print("\t- delete files:\n\t\t{}".format("\n\t\t".join([v.path for v in del_versions])))

        for v in del_versions:
            try:
                fork.delete_file(v.path, "delete {}".format(v.path), v.sha)
                sleep(1)  # wait for changes to take effect
            except GithubException as e:
                print("Error: {}: {}".format(e.data["message"], v.path))

        return fork
    else:
        return None


def process_migrations(repo):
    """if 'migrations/versions' doesn't exist or is empty, delete 'alembic.ini'
    and 'migrations/'.  Return True if something was deleted
    """
    content = get_content(repo)
    if "alembic.ini" in content and "migrations" not in content:
        print_repo_info(repo)
        print("\t- contains 'alembic.ini' without 'migrations/'. Don't know what to do\n")
        return False
    elif "migrations" in content and \
         ("migrations/versions" not in content or not repo.get_contents("migrations/versions")):
        print_repo_info(repo)
        print("\t- 'migrations/versions' does not exist or is empty\n")
        fork = repo.create_fork()
        sleep(1)  # wait for github to complete forking
        rm_recursive(fork, "migrations", "delete 'migrations/'")
        try:
            rm(fork, "alembic.ini", "delete 'alembic.ini'")
        except GithubException as e:
            print("Error: couldn't delete 'alembic.ini': {}".format(e.data["message"]))
        return fork
    else:
        return None


def main():
    if sys.argv[1:]:
        access_token = sys.argv[1]
    elif "GH_TOKEN" in os.environ.keys():
        access_token = os.environ["GH_TOKEN"]
    else:
        print("please set the GH_TOKEN env variable or provide a github access" +
              "token as commandline parameter\n" +
              "Usage: {} [access_token]".format(sys.argv[0]))
        exit(1)

    g = Github(login_or_token=access_token)

    try:
        org = g.get_organization("clld")
    except GithubException as e:
        print("Error: {}".format(e.data["message"]))
        exit(1)

    # all_repos = org.get_repos(type="public", sort="full_name", direction="asc")
    # print("total: {}".format(all_repos.totalCount))
    # all_repos = [g.get_repo("clld/tsammalex")]
    all_repos = [g.get_repo("clld/afbo"), g.get_repo("clld/tsammalex")]
    forks = []
    for repo in all_repos:
        if repo.archived:
            continue
        try:
            f = process_versions(repo) or process_migrations(repo)
            if f:
                forks.append(f)
        except GithubException as e:
            print("Main Error: " + e.data["message"])

    print("cleaned up {} repos:".format(len(forks)))
    for f in forks:
        print_repo_info(f)
        f.delete()


if __name__ == "__main__":
    main()
