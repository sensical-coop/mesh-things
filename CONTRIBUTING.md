# Contributing

Thank you for helping with Mesh Things. This guide covers how changes reach `main`: branches, commits, pull requests, and the deploy notes every pull request carries. Code style, comments and docstrings follow [AGENTS.md](AGENTS.md).

## Branches

Each pull request has its own branch, created from `main`. Name it after the kind of change, with a short slug:

| Prefix | Use |
|---|---|
| `feat/` | New behaviour |
| `fix/` | Bug fixes |
| `security/` | Dependency bumps for advisories |
| `build/` | Images, locks and CI |
| `docs/` | Documentation only |
| `chore/` | Anything else |

When a change builds on another pull request that is still open, base the new branch on that one and open the pull request against it. Merge stacked pull requests in order, with merge commits rather than squash, so the next one in the stack does not conflict with `main`. Before opening a stacked pull request, check that its base has not been merged already. If it has, target `main` instead.

## Commits

Write each commit message as one line in the imperative, saying what the change does, for example `Leave the writer's bookkeeping fields out of readings`. Commits carry no `Co-Authored-By` trailers or links to tools that helped write them.

## Before opening a pull request

The PR checks workflow runs the API tests, the root tests, every image build, the compose files, the production settings, the client schema and the dependency locks. You can save a round trip by keeping these in step yourself:

- **API schema.** Any change to an endpoint, a parameter, a serializer field or a view docstring raises `__version__` in `server/mesh_things/src/mesh_things/__init__.py`. Then run `scripts/regen-client-schema.sh` and commit the snapshot and type stub it writes. When two branches raise the version at once, keep the higher one and regenerate.
- **Endpoints.** New or changed endpoints get an example in `server/mesh_things/examples/`, which a test runs through the mesh-things client. Update the documentation as well, which lives in the docs app of [mesh-things-apps](https://github.com/sensical-coop/mesh-things-apps).
- **Migrations.** Model changes come with their migration. CI fails if the models and migrations disagree.
- **Python dependencies.** Edit the relevant `requirements.txt`, then run `scripts/lock-deps.sh` and commit the lock files. Every image installs from its lock, with hashes.
- **Images.** Keep the compose profiles able to rebuild every service that a change touches, so no image is left stale.

## Pull requests

Keep the description short. Say what changes and why, as a few bullet points if there are several parts, and link the issue it closes. If the pull request depends on another one, say so on the last line, for example `Depends on #75.` Descriptions carry no attribution footers.

Request a CodeRabbit review by commenting `@coderabbitai review`. Address its notes, or reply on the thread when a note does not apply.

### Deploy comment

Production `.env` is not in the repository, and deploys are run by hand, so every pull request gets a comment with what the operator needs. Post it when you open the pull request, and update it if the pull request changes. Use the production invocation, `docker compose --profile full`, never the dev overlay.

````markdown
### .env

Variables to add, change or remove, or "Nothing to add, change or remove."

### Commands

One sentence on which images change and why, then the exact commands. When the Flink image changes, keep the redeploy line, and leave the Flink services out of the `up -d` line:

```
git pull
docker compose --profile full build <services>
./scripts/redeploy-flink.sh   # only when the Flink image changes
docker compose --profile full up -d --no-deps <services>
```

Check:

```
<commands that show the change works, with the expected output as a comment>
```

### Rollback

Only when rolling back needs more than checking out the previous commit.

### PyPI

Only when the mesh-things version changes: tag `mesh-things-v<version>` once this is deployed.
````

For stacked pull requests, open the comment by naming the pull request it builds on, and list only what this one adds. The last pull request in a stack can add a combined section for deploying the whole stack at once.

## Deploying

Run the commands from the deploy comment on the server, in the repository checkout.

- **API.** `registry_api` applies migrations and seeds the catalog when it starts, so there are no separate `manage.py` steps unless the deploy comment lists one.
- **Flink.** Always redeploy the Flink services with `./scripts/redeploy-flink.sh`, and run it before any `up -d`. It stops each job with a savepoint and resumes it on the new image. A plain `up -d` recreates the cluster without savepoints.
- **Monitor.** The monitor runs on its own machine. There, run `git pull`, then `docker compose -f compose/monitor.yml -f compose/monitor.caddy.yml --env-file monitor.env --profile monitor up -d --build`.

## Releasing mesh-things

The mesh-things package is published to PyPI from this repository. Once a deploy that changes the schema is live, tag the commit the server runs, not the newest commit on `main`. Something merged after the deploy would otherwise be published without having been deployed. On the server, `git rev-parse HEAD` prints that commit. Tag it and push the tag:

```sh
git fetch origin
git tag mesh-things-v<version> <deployed-sha>
git push origin mesh-things-v<version>
```

The release workflow checks that the tag matches `__version__`, builds the package, tests the wheel outside the checkout and publishes it through PyPI Trusted Publishing. The newest release always matches the production API, and [mesh-things-apps](https://github.com/sensical-coop/mesh-things-apps) syncs its contract from that tag.
