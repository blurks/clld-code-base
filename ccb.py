import os
import re
import sys

from time import sleep
from github import Github, GithubException, GithubObject


VERS_REGEX = re.compile(r"migrations/versions/(.*fix_polymorphic_type.py$|.*update_unique_null.py$)")
LOG = True
BRANCH = "cleanup"


def print_log(msg):
    if LOG:
        print(msg)


def get_content(repo, ref=GithubObject.NotSet):
    """get the content of the repo as list of paths."""
    content = [c.path
               for c in repo.get_contents("", ref=ref)
               if c.path in ["alembic.ini", "migrations"]]
    if "migrations" in content:
        content.extend([c.path
                        for c in repo.get_contents("migrations", ref=ref)
                        if c.path == "migrations/versions"])
    if "migrations/versions" in content:
        content.extend([c.path
                        for c in repo.get_contents("migrations/versions", ref=ref)])
    return content


def is_relevant(repo):
    """return True if repo needs cleanup"""
    if repo.archived:
        return False

    c = get_content(repo)

    if (("migrations" in c or "alembic.ini" in c) and
        ("migrations/versions" not in c or
         [m for m in map(VERS_REGEX.match, c) if m] or
         not repo.get_contents("migrations/versions"))):
        return True
    return False


def rm_recursive(repo, branch, path, message):
    """delete the given directory."""
    try:
        content = [c for c in repo.get_contents(path, ref=branch)]
    except GithubException as e:
        print("Error: {}: {}".format(e.data["message"], path))
        return
    except TypeError as e:  # if repo.get_contents returns a singleton instead of a list
        print("Error: {} is apparently not a directory ({})".format(path, e))
        return
    for c in content:
        if c.type == "dir":
            rm_recursive(repo, branch, c.path, message)
        else:
            repo.delete_file(c.path, message + " ({})".format(c.path), c.sha,
                             branch=branch)


def process_versions(repo, branch):
    """delete 'migrations/versions/.*(fix_polymorphic_type.py|update_unique_null.py)'.
    If these files don't exist, return false. If they exist and were
    successfully deleted, return True.
    """
    try:
        versions = repo.get_contents("migrations/versions", ref=branch)
    except GithubException:  # if there is no 'migrations/versions/' directory
        return False

    del_versions = [v for v in versions if VERS_REGEX.match(v.path)]
    if del_versions:
        for v in del_versions:
            print_log("{r}: deleting {f}".format(r=repo.name, f=v.path))
            try:
                repo.delete_file(v.path, "delete {}".format(v.path), v.sha, branch=branch)
            except GithubException as e:
                print("Error: {}: {}".format(e.data["message"], v.path))

        return True
    else:
        return False


def process_migrations(repo, branch):
    """if 'migrations/versions' doesn't exist or is empty, delete 'alembic.ini'
    and 'migrations/'.  Return True if something was deleted.
    """
    content = get_content(repo, ref=branch)
    if "alembic.ini" in content and "migrations" not in content:
        print(("Error: {r} contains 'alembic.ini' without 'migrations/'. " +
               "Don't know what to do\n").format(r=repo.name))
        return False
    elif "migrations" in content and \
         ("migrations/versions" not in content or
          not repo.get_contents("migrations/versions", ref=branch)):

        print_log("{r}: deleting 'migrations/'".format(r=repo.name))
        rm_recursive(repo, branch, "migrations", "delete 'migrations/'")
        print_log("{r}: deleting 'alembic.ini'".format(r=repo.name))
        repo.delete_file("alembic.ini", "delete 'alembic.ini'",
                         repo.get_contents("alembic.ini").sha, branch=branch)
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

    all_repos = org.get_repos(type="all", sort="full_name", direction="asc")
    # all_repos = [g.get_repo("clld/afbo"), g.get_repo("clld/tsammalex")]

    forks = []
    for repo in all_repos:
        if is_relevant(repo):
            myfork = repo.create_fork()
            sleep(1)
            forks.append(myfork)

            try:
                # branch from the latest upstream comit. this might fail is
                # upstream is ahead of our fork
                myfork.create_git_ref(ref="refs/heads/" + BRANCH,
                                      sha=repo.get_branch("master").commit.sha)
            except GithubException as e:
                if e.status == 422:
                    pass  # branch already exists, so we need not create it
                else:
                    raise e

            process_versions(myfork, BRANCH)
            process_migrations(myfork, BRANCH)

    print("cleaned up {} repos:".format(len(forks)))
    for f in forks:
        pr = f.parent.create_pull(title="Cleanup migrations/",
                                  body="this pr was automatically generated by " +
                                  "https://github.com/blurks/clld-code-base/blob/master/ccb.py",
                                  head="blurks:cleanup",
                                  base="master")
        print("{name:<16}: {url} {ar} (#{pr})".format(name=f.name, url=f.html_url,
                                                      ar="(ARCHIVED)" if f.archived else "",
                                                      pr=pr.number))
        # f.get_git_ref("heads/" + BRANCH).delete()


if __name__ == "__main__":
    main()
