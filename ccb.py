import re
import sys

from github import Github


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
    content = [c for c in repo.get_contents(path)]
    for c in content:
        if c.type == "dir":
            rm_recursive(repo, c.path, message)
        else:
            repo.delete_file(c.path, message, c.sha)


if __name__ == "__main__":
    g = Github(login_or_token="XXXX")

    org = g.get_organization("clld")

    # all_repos = org.get_repos(type="public", sort="full_name", direction="asc")
    # print("total: {}".format(all_repos.totalCount))
    # all_repos = [g.get_repo("clld/tsammalex")]
    all_repos = [g.get_repo("clld/afbo"), g.get_repo("clld/tsammalex")]

    for repo in all_repos:
        if repo.archived:
            continue
        content = get_content(repo)
        versions = [match.group(0)
                    for match in map(re.compile(r"migrations/versions/.*").match, content)
                    if match]

        if "alembic.ini" in content and "migrations" not in content:
            print_repo_info(repo)
            print("\t- contains 'alembic.ini' without 'migrations/'\n")

        elif "migrations" in content and \
             ("migrations/versions" not in content or not versions):
            print_repo_info(repo)
            print("\t- 'migrations/versions' does not exist or is empty\n")
            fork = repo.create_fork()
            rm_recursive(fork, "migrations", "delete 'migrations/'")
            rm(fork, "alembic.ini", "delete 'alembic.ini'")

        elif versions:
            del_versions = [match.group(0)
                            for match in
                            map(re.compile(r".*fix_polymorphic_type.py$|.*update_unique_null.py$").match, versions)
                            if match]
            if del_versions:
                fork = repo.create_fork()
                print_repo_info(repo)
                print("\t- delete {}".format(", ".join(del_versions)))
                for v in del_versions:
                    rm(fork, v, "delete {}".format(v))
                if len(del_versions) == len(versions):
                    print("\t- 'migrations/versions' is now empty")
                    rm_recursive(fork, "migrations", "delete 'migrations/'")
                    rm(fork, "alembic.ini", "delete 'alembic.ini'")
                print("")
